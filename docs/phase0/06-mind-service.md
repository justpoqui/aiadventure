# Step 06 — Mind service and stand-in mind

**Goal:** a running WebSocket server that accepts Godot, completes the
handshake, opens the slot's `mind.sqlite`, drives a **stand-in mind** that walks
the body around, and answers save requests.

## 6.1 Stand-in mind (scaffolding, deleted in Phase 1)

`mind_service/src/mind/runtime/scripted_mind.py`
```python
"""STAND-IN MIND — Phase 0 scaffolding only. Deleted in Phase 1.

It walks the body around fixed waypoints so the action loop can be tested.
It is allowed to use coordinates because it is not a real mind.
"""
from ulid import ULID

from mind.transport.protocol import ActionCommand, ActionUpdate

DEFAULT_WAYPOINTS = [{"x": 20.0, "z": 0.0}, {"x": 20.0, "z": 15.0}, {"x": 0.0, "z": 15.0}, {"x": 0.0, "z": 0.0}]


class ScriptedMind:
    def __init__(self, agent_id: str, waypoints: list[dict] | None = None):
        self.agent_id = agent_id
        self.waypoints = waypoints or DEFAULT_WAYPOINTS
        self._i = 0

    def on_spawn(self) -> list[ActionCommand]:
        return [self._next()]

    def on_action_update(self, upd: ActionUpdate) -> list[ActionCommand]:
        if upd.status in ("completed", "failed"):
            return [self._next()]
        return []

    def _next(self) -> ActionCommand:
        wp = self.waypoints[self._i % len(self.waypoints)]
        self._i += 1
        return ActionCommand(action_id=str(ULID()), action_type="move_to", params={"target": wp})
```

## 6.2 Session: one per Godot connection

`mind_service/src/mind/runtime/session.py`
```python
"""One Session per Godot connection. Routes messages to handlers."""
import hashlib
import logging
import sqlite3
from pathlib import Path

from websockets.asyncio.server import ServerConnection

from mind.runtime.scripted_mind import ScriptedMind
from mind.storage.db import connect, migrate
from mind.transport.protocol import (ErrorMsg, HelloAck, Payload, Pong, ProtocolError,
                                     SaveReady, make, parse)

log = logging.getLogger("mind.session")
SERVICE_VERSION = "0.0.1"


class Session:
    def __init__(self, ws: ServerConnection):
        self.ws = ws
        self.tick = 0
        self.world_seed = 0
        self.db: sqlite3.Connection | None = None
        self.minds: dict[str, ScriptedMind] = {}

    async def send(self, type_: str, payload: Payload, agent_id: str | None = None) -> None:
        await self.ws.send(make(type_, payload, self.tick, agent_id))

    async def handle(self, raw: str) -> None:
        try:
            env, msg = parse(raw)
        except ProtocolError as e:
            log.warning("rejected message: %s %s", e.code, e)
            await self.send("error", ErrorMsg(code=e.code, message=str(e)))
            if e.code == "protocol_mismatch":
                # The close reason is what Godot reliably sees (see step 09).
                await self.ws.close(code=1002, reason=str(e)[:120])
            return
        self.tick = max(self.tick, env.tick)
        handler = getattr(self, f"on_{env.type}", None)
        if handler is None:
            log.warning("no handler for %s", env.type)
            return
        await handler(env, msg)

    # ---- handlers --------------------------------------------------------
    async def on_hello(self, env, msg):
        self.world_seed = msg.world_seed
        slot = Path(msg.slot_dir)
        slot.mkdir(parents=True, exist_ok=True)
        self.db = connect(slot / "mind.sqlite")
        version = migrate(self.db)
        agents = [r[0] for r in self.db.execute("SELECT agent_id FROM agents")]
        log.info("hello from godot: slot=%s schema=%s agents=%s", slot, version, agents)
        await self.send("hello_ack", HelloAck(service_version=SERVICE_VERSION,
                                              mind_schema=version, agents_known=agents))

    async def on_agent_spawned(self, env, msg):
        self._require_db()
        self.db.execute("INSERT OR IGNORE INTO agents (agent_id, created_tick, seed) VALUES (?, ?, ?)",
                        (msg.agent_id, env.tick, self.world_seed))
        mind = self.minds.setdefault(msg.agent_id, ScriptedMind(msg.agent_id))
        for cmd in mind.on_spawn():
            await self.send("action_command", cmd, msg.agent_id)

    async def on_action_update(self, env, msg):
        mind = self.minds.get(env.agent_id)
        if mind is None:
            log.warning("action_update for unknown agent %s", env.agent_id)
            return
        for cmd in mind.on_action_update(msg):
            await self.send("action_command", cmd, env.agent_id)

    async def on_tick(self, env, msg):
        pass

    async def on_ping(self, env, msg):
        await self.send("pong", Pong())

    async def on_save_request(self, env, msg):
        self._require_db()
        target = Path(msg.snapshot_dir) / "mind.sqlite"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        self.db.execute("VACUUM INTO ?", (str(target),))
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        await self.send("save_ready", SaveReady(snapshot_dir=msg.snapshot_dir,
                                                files={"mind.sqlite": digest}))

    async def on_shutdown(self, env, msg):
        await self.close()

    async def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def _require_db(self):
        if self.db is None:
            raise RuntimeError("hello must be the first message")
```

What each handler does:

| Message | Handler behaviour |
|---------|-------------------|
| `hello` | Opens `<slot>/mind.sqlite`, runs migrations, replies `hello_ack` with the schema version |
| `agent_spawned` | Registers the agent (once) and starts its stand-in mind |
| `action_update` | Passes the result to that agent's mind, which may send the next command |
| `save_request` | `VACUUM INTO` the snapshot folder, replies with the file's sha256 |
| `shutdown` | Closes the database cleanly |
| a bad version | Sends an `error`, then **closes with code 1002** and the explanation as the close reason. Godot relies on the close reason (step 09). |

## 6.3 Server and entry point

`mind_service/src/mind/transport/server.py`
```python
import logging

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from mind.runtime.session import Session

log = logging.getLogger("mind.server")


async def handler(ws: ServerConnection) -> None:
    session = Session(ws)
    log.info("godot connected")
    try:
        async for raw in ws:
            await session.handle(raw)
    except ConnectionClosed:
        pass  # Godot vanished without a close handshake (crash or kill): not an error here
    finally:
        await session.close()
        log.info("godot disconnected")


async def run(host: str, port: int) -> None:
    async with serve(handler, host, port) as server:
        log.info("mind service listening on ws://%s:%s", host, port)
        await server.serve_forever()
```

`mind_service/src/mind/__main__.py`
```python
import argparse
import asyncio
import logging

from mind.transport.server import run


def main() -> None:
    ap = argparse.ArgumentParser(prog="mind")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--log", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
```

## 6.4 Tests: unit tests plus a full conversation with a fake Godot

`mind_service/tests/test_scripted_mind.py`
```python
from mind.runtime.scripted_mind import ScriptedMind
from mind.transport.protocol import ActionUpdate


def test_walks_waypoints_in_order():
    m = ScriptedMind("a", [{"x": 1, "z": 0}, {"x": 2, "z": 0}])
    first = m.on_spawn()[0]
    assert first.params["target"] == {"x": 1, "z": 0}
    assert m.on_action_update(ActionUpdate(action_id=first.action_id, status="started")) == []
    nxt = m.on_action_update(ActionUpdate(action_id=first.action_id, status="completed"))[0]
    assert nxt.params["target"] == {"x": 2, "z": 0}
```

`mind_service/tests/test_server.py`
```python
"""End-to-end: a fake Godot client talks to the real server."""
import asyncio
import hashlib
import json

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from mind.transport.server import handler


@pytest.fixture
async def url():
    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"


def env(type_, payload, tick=0, agent_id=None, v=1):
    return json.dumps({"v": v, "type": type_, "msg_id": "m", "agent_id": agent_id,
                       "tick": tick, "payload": payload})


async def recv(ws):
    return json.loads(await asyncio.wait_for(ws.recv(), 5))


async def test_handshake_walk_and_save(url, tmp_path):
    async with connect(url) as ws:
        await ws.send(env("hello", {"client": "godot", "slot_dir": str(tmp_path), "world_seed": 42}))
        ack = await recv(ws)
        assert ack["type"] == "hello_ack" and ack["payload"]["mind_schema"] == 1

        await ws.send(env("agent_spawned", {"agent_id": "a_0001", "position": {"x": 0, "z": 0}},
                          tick=1, agent_id="a_0001"))
        cmd = await recv(ws)
        assert cmd["type"] == "action_command" and cmd["payload"]["action_type"] == "move_to"

        await ws.send(env("action_update", {"action_id": cmd["payload"]["action_id"], "status": "completed"},
                          tick=30, agent_id="a_0001"))
        cmd2 = await recv(ws)
        assert cmd2["payload"]["params"]["target"] != cmd["payload"]["params"]["target"]

        snap = tmp_path / "snapshots" / "test"
        await ws.send(env("save_request", {"snapshot_dir": str(snap)}, tick=31))
        ready = await recv(ws)
        assert ready["type"] == "save_ready"
        saved = (snap / "mind.sqlite").read_bytes()
        assert ready["payload"]["files"]["mind.sqlite"] == hashlib.sha256(saved).hexdigest()


async def test_protocol_mismatch_closes_cleanly(url):
    async with connect(url) as ws:
        await ws.send(env("hello", {}, v=99))
        err = await recv(ws)
        assert err["type"] == "error" and err["payload"]["code"] == "protocol_mismatch"
        with pytest.raises(ConnectionClosed) as closed:
            await asyncio.wait_for(ws.recv(), 5)
        # Godot relies on the close code + reason, not the error message (see step 09).
        assert closed.value.rcvd.code == 1002
        assert "v1" in closed.value.rcvd.reason
```

## Check it works

```bash
pytest -q                  # → 11 passed at this point
python -m mind             # → "mind service listening on ws://127.0.0.1:8765"
```

Leave it running and press Ctrl+C to stop. It must exit without a traceback.

## Common mistakes

- **Using the old websockets API** (`websockets.serve` with a
  `handler(ws, path)` signature). This guide uses the `websockets.asyncio`
  API, whose handlers take one argument.
- **Listening on `0.0.0.0`.** Keep it on `127.0.0.1` so the mind service is
  never reachable from your network.
- **Blocking the event loop.** Nothing in a handler may sleep or wait on the LLM
  synchronously. LLM calls become background tasks in Phase 1.
