# Step 04 — Protocol v1

**Goal:** define, in one place, every message allowed to cross the Godot ↔ mind
boundary, and make anything else get rejected.

**Why this matters:** the protocol *is* the perception boundary. If a message
type can't carry world truth, the mind can't cheat. In later phases, adding a
message type should be a deliberate act.

## 4.1 How it is organised

- The **Python pydantic models are the source of truth.** JSON Schema files in
  `shared/protocol/v1/` are generated from them. Never edit those files by hand.
- Every message is an **envelope** (`v`, `type`, `msg_id`, `agent_id`, `tick`)
  plus a **payload** whose shape depends on `type`.
- `extra="forbid"` means an unknown field is an error, not something silently
  ignored. Typos then fail loudly.

## 4.2 Create the protocol module

`mind_service/src/mind/transport/protocol.py`
```python
"""Protocol v1: the ONLY shapes allowed to cross the Godot <-> Mind boundary."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from ulid import ULID

PROTOCOL_VERSION = 1


class ProtocolError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    v: int
    type: str
    msg_id: str
    agent_id: str | None = None
    tick: int
    payload: dict[str, Any] = Field(default_factory=dict)


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Vec3(Payload):
    x: float
    y: float = 0.0  # elevation; always 0 in 2D
    z: float


# ---- Godot -> Mind -------------------------------------------------------
class Hello(Payload):
    client: Literal["godot"]
    slot_dir: str          # absolute path of the save slot folder
    world_seed: int


class AgentSpawned(Payload):
    agent_id: str
    position: Vec3


class Tick(Payload):
    pass


class ActionUpdate(Payload):
    action_id: str
    status: Literal["started", "progress", "completed", "failed", "interrupted"]
    reason: str | None = None
    percepts: list[dict[str, Any]] = Field(default_factory=list)


class SaveRequest(Payload):
    snapshot_dir: str


class Shutdown(Payload):
    pass


class Ping(Payload):
    pass


# ---- Mind -> Godot -------------------------------------------------------
class HelloAck(Payload):
    service_version: str
    mind_schema: int
    agents_known: list[str]


class ActionCommand(Payload):
    action_id: str
    action_type: Literal["move_to", "wait"]
    params: dict[str, Any]
    plan_step_id: str | None = None


class SaveReady(Payload):
    snapshot_dir: str
    files: dict[str, str]   # file name -> sha256 hex


class Pong(Payload):
    pass


class BeliefBrief(Payload):
    text: str
    confidence: float = Field(ge=0, le=1)
    hypothesis: bool = False


class MindTelemetry(Payload):
    """What the mind reports about ITSELF, for the observer UI only (character panel).
    Godot must never feed this into world logic. Everything here is subjective:
    perceived needs, self-assessed skills, beliefs that may be wrong."""
    self_name: str | None = None              # None until the survivor learns or chooses one
    activity: str = ""                        # "walking toward the tall metal structure"
    thought: str | None = None
    goal: str | None = None
    mood: str = "calm"
    mood_valence: float = Field(default=0.0, ge=-1, le=1)
    believed_place: str | None = None
    needs: dict[str, float] = Field(default_factory=dict)     # perceived DEFICIT 0..1 (1 = desperate)
    traits: dict[str, float] = Field(default_factory=dict)    # 0..1
    skills: dict[str, float] = Field(default_factory=dict)    # self-assessed 0..1
    beliefs: list[BeliefBrief] = Field(default_factory=list)  # most salient first
    last_journal: str | None = None


class ErrorMsg(Payload):
    code: str
    message: str


PAYLOADS: dict[str, type[Payload]] = {
    "hello": Hello, "agent_spawned": AgentSpawned, "tick": Tick,
    "action_update": ActionUpdate, "save_request": SaveRequest,
    "shutdown": Shutdown, "ping": Ping,
    "hello_ack": HelloAck, "action_command": ActionCommand,
    "save_ready": SaveReady, "pong": Pong, "error": ErrorMsg,
    "mind_telemetry": MindTelemetry,
}


def parse(raw: str) -> tuple[Envelope, Payload]:
    try:
        env = Envelope.model_validate_json(raw)
    except ValidationError as e:
        raise ProtocolError("bad_envelope", str(e)) from e
    if env.v != PROTOCOL_VERSION:
        raise ProtocolError("protocol_mismatch",
                            f"mind speaks v{PROTOCOL_VERSION}, got v{env.v}")
    model = PAYLOADS.get(env.type)
    if model is None:
        raise ProtocolError("unknown_type", env.type)
    try:
        return env, model.model_validate(env.payload)
    except ValidationError as e:
        raise ProtocolError("bad_payload", str(e)) from e


def make(type_: str, payload: Payload, tick: int, agent_id: str | None = None) -> str:
    assert isinstance(payload, PAYLOADS[type_]), f"{type_} needs {PAYLOADS[type_].__name__}"
    return Envelope(v=PROTOCOL_VERSION, type=type_, msg_id=str(ULID()), agent_id=agent_id,
                    tick=tick, payload=payload.model_dump()).model_dump_json()
```

Notes on the details:
- `y` in `Vec3` is elevation and is always 0 in 2D. It exists now so 3D needs no
  protocol change.
- `ActionCommand.action_type` only allows `move_to` and `wait` in Phase 0. New
  actions are added here when they are built.
- `MindTelemetry` is the mind's **self-report for the observer UI** (step 14).
  It is subjective (perceived needs, self-judged skills, beliefs that may be
  wrong), and Godot must never use it in world logic.
- Godot's JSON parser turns every number into a float (`12` → `12.0`). Pydantic
  accepts `12.0` for an `int` field, and the tests prove it.

## 4.3 Schema export tool

`mind_service/src/mind/tools/export_schemas.py`
```python
"""Write protocol JSON Schemas to shared/protocol/v1. Use --check in CI."""
import argparse, json, sys
from pathlib import Path

from mind.transport.protocol import PAYLOADS, Envelope

OUT = Path(__file__).resolve().parents[4] / "shared" / "protocol" / "v1"


def render() -> dict[str, str]:
    files = {"envelope.schema.json": Envelope.model_json_schema()}
    for name, model in PAYLOADS.items():
        files[f"{name}.schema.json"] = model.model_json_schema()
    return {k: json.dumps(v, indent=2, sort_keys=True) + "\n" for k, v in files.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, text in render().items():
        path = OUT / name
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(name)
        else:
            path.write_text(text)
    if stale:
        print("Out of date (run export_schemas without --check):", *stale, sep="\n  ")
        return 1
    print("schemas up to date" if args.check else f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run it once:
```bash
cd mind_service
python -m mind.tools.export_schemas          # writes shared/protocol/v1/*.schema.json
python -m mind.tools.export_schemas --check  # → "schemas up to date"
```

## 4.4 Tests

`mind_service/tests/test_protocol.py`
```python
import json

import pytest

from mind.transport.protocol import (PROTOCOL_VERSION, ActionCommand, ProtocolError, make, parse)


def envelope(type_, payload, v=PROTOCOL_VERSION, tick=5):
    return json.dumps({"v": v, "type": type_, "msg_id": "x", "agent_id": None,
                       "tick": tick, "payload": payload})


def test_roundtrip():
    raw = make("action_command", ActionCommand(action_id="a1", action_type="move_to",
                                               params={"target": {"x": 1, "z": 2}}), tick=7, agent_id="a_0001")
    env, msg = parse(raw)
    assert env.tick == 7 and env.agent_id == "a_0001"
    assert msg.params["target"] == {"x": 1, "z": 2}


def test_godot_floats_accepted_for_ints():
    # Godot's JSON parser turns every number into a float.
    env, _ = parse(envelope("tick", {}, tick=12.0))
    assert env.tick == 12


def test_version_mismatch_rejected():
    with pytest.raises(ProtocolError) as e:
        parse(envelope("ping", {}, v=2))
    assert e.value.code == "protocol_mismatch"


def test_unknown_field_rejected():
    with pytest.raises(ProtocolError) as e:
        parse(envelope("ping", {"surprise": 1}))
    assert e.value.code == "bad_payload"


def test_unknown_type_rejected():
    with pytest.raises(ProtocolError) as e:
        parse(envelope("teleport", {}))
    assert e.value.code == "unknown_type"


def test_telemetry_rejects_out_of_range_confidence():
    import pydantic

    from mind.transport.protocol import MindTelemetry
    with pytest.raises(pydantic.ValidationError):
        MindTelemetry(beliefs=[{"text": "The tower has water", "confidence": 1.5}])
```

## Check it works

```bash
cd mind_service
pytest -q tests/test_protocol.py               # → 6 passed
python -m mind.tools.export_schemas --check    # → schemas up to date
```

Commit `shared/protocol/v1/` together with the code.

## Common mistakes

- **Editing the JSON schema files by hand.** They are overwritten on the next
  export, and CI fails (step 13).
- **Adding a field to a payload without exporting the schemas.** Run the export
  after every protocol change.
- **Putting world truth into a payload "just for now"** (e.g. `is_bridge_safe`).
  Never do this. Phase 1 percepts carry appearances, not facts.
