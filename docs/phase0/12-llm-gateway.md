# Step 12 — LLM gateway

**Goal:** a single, safe door to the language model. Every call is
schema-validated, checked by the reality guard, retried once, and recorded in
the `llm_calls` ledger. Nothing else in the project may talk to Ollama
directly.

Phase 0 doesn't use the LLM for behaviour yet. This step proves the pipeline
end to end with one tiny purpose, `smoke_thought`.

## 12.1 Types: requests, responses, purposes

`mind_service/src/mind/llm/types.py`
```python
from dataclasses import dataclass
from string import Template
from typing import Protocol

from pydantic import BaseModel


class LLMRequest(BaseModel):
    purpose: str
    model: str
    system: str
    user: str
    output_schema: dict
    think: bool = False
    seed: int | None = None
    temperature: float = 0.7
    num_ctx: int = 8192


class LLMResponse(BaseModel):
    content: str
    thinking: str | None = None
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


class LLMProvider(Protocol):
    async def complete(self, req: LLMRequest) -> LLMResponse: ...


@dataclass(frozen=True)
class Purpose:
    """One kind of LLM call: its prompt, output shape and model route."""
    name: str
    version: str
    model: str
    system: Template
    user: Template
    output_model: type[BaseModel]
    think: bool = False
    temperature: float = 0.7

    def render(self, **ctx) -> tuple[str, str]:
        # substitute() (not safe_substitute) so a missing context key is a loud error
        return self.system.substitute(**ctx), self.user.substitute(**ctx)
```

A **Purpose** bundles everything about one kind of call: prompt templates,
output schema, model, and whether thinking is on. In Phase 1 you add purposes
(`interpret_percepts`, `daily_reflection`, …). You never add ad-hoc calls.

## 12.2 Providers: real, fake, and replay

`mind_service/src/mind/llm/providers.py`
```python
import json
import time
from collections.abc import Callable

import httpx

from mind.llm.types import LLMRequest, LLMResponse


class OllamaProvider:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 180.0):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def complete(self, req: LLMRequest) -> LLMResponse:
        options = {"num_ctx": req.num_ctx, "temperature": req.temperature}
        if req.seed is not None:
            options["seed"] = req.seed
        t0 = time.perf_counter()
        r = await self._client.post("/api/chat", json={
            "model": req.model, "stream": False, "think": req.think,
            "format": req.output_schema, "keep_alive": "30m", "options": options,
            "messages": [{"role": "system", "content": req.system},
                         {"role": "user", "content": req.user}],
        })
        r.raise_for_status()
        d = r.json()
        return LLMResponse(content=d["message"]["content"], thinking=d["message"].get("thinking"),
                           model=d.get("model", req.model), tokens_in=d.get("prompt_eval_count", 0),
                           tokens_out=d.get("eval_count", 0),
                           latency_ms=int((time.perf_counter() - t0) * 1000))

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeProvider:
    """Deterministic provider for tests. Give it a list of replies (str or dict)
    or a function(request) -> reply. Every request is kept in .requests."""

    def __init__(self, replies: list | Callable[[LLMRequest], object]):
        self._replies = replies
        self.requests: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        reply = self._replies(req) if callable(self._replies) else self._replies.pop(0)
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMResponse(content=content, model="fake")


class ReplayProvider:
    """Serves recorded responses from the llm_calls ledger (for deterministic replays)."""

    def __init__(self, db, prompt_hash: Callable[[LLMRequest], str]):
        self._db = db
        self._hash = prompt_hash

    async def complete(self, req: LLMRequest) -> LLMResponse:
        row = self._db.execute(
            "SELECT response_json FROM llm_calls WHERE prompt_hash = ? AND valid = 1 "
            "ORDER BY tick LIMIT 1", (self._hash(req),)).fetchone()
        if row is None:
            raise LookupError(f"no recorded response for {req.purpose}")
        return LLMResponse.model_validate_json(row[0])
```

- `OllamaProvider` sends `format` (the JSON schema) so the model is
  constrained to valid output, and `think` to switch Qwen3's reasoning on or
  off per purpose.
- `FakeProvider` makes tests deterministic and free.
- `ReplayProvider` serves answers from the ledger, so a recorded run can be
  replayed exactly.

## 12.3 The reality guard (ADR-017)

`mind_service/src/mind/llm/reality_guard.py`
```python
"""Rejects any LLM output that shows awareness of being simulated (ADR-017).

The blocklist is deliberately strict; false positives just cause a retry and
are logged in llm_calls.error so they can be reviewed and the list tuned.
"""
import re
from typing import Any

from pydantic import BaseModel

BLOCKLIST = re.compile(
    r"\b(simulat\w*|video ?games?|in-game|this game|the game world|players?|npcs?|quests?|"
    r"programm\w*|language models?|llms?|artificial intelligence|a\.?i\.?|prompts?|"
    r"developers?|the user|fictional|virtual world|game engine|godot)\b",
    re.IGNORECASE,
)


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def check(output: BaseModel) -> str | None:
    """Returns the offending phrase, or None if the output is clean."""
    for text in _strings(output.model_dump()):
        m = BLOCKLIST.search(text)
        if m:
            return m.group(0)
    return None
```

It is deliberately strict. A false positive costs one retry and leaves a ledger
row you can review. Note that it allows "game trail" and "pray", and blocks
"simulation", "NPC", "player", and similar.

## 12.4 The gateway

`mind_service/src/mind/llm/gateway.py`
```python
"""Every LLM call in the project goes through here. Nothing else talks to a model."""
import hashlib
import json
import logging
import sqlite3

from pydantic import BaseModel, ValidationError
from ulid import ULID

from mind.llm import reality_guard
from mind.llm.types import LLMProvider, LLMRequest, LLMResponse, Purpose

log = logging.getLogger("mind.llm")


def prompt_hash(req: LLMRequest) -> str:
    key = json.dumps([req.model, req.system, req.user, req.output_schema, req.think, req.seed],
                     sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()


class LLMGateway:
    def __init__(self, provider: LLMProvider, db: sqlite3.Connection, max_attempts: int = 2):
        self.provider = provider
        self.db = db
        self.max_attempts = max_attempts

    async def run(self, purpose: Purpose, *, agent_id: str | None, tick: int,
                  seed: int | None = None, **context) -> BaseModel | None:
        system, user = purpose.render(**context)
        req = LLMRequest(purpose=purpose.name, model=purpose.model, system=system, user=user,
                         output_schema=purpose.output_model.model_json_schema(),
                         think=purpose.think, temperature=purpose.temperature, seed=seed)
        for attempt in range(1, self.max_attempts + 1):
            resp, parsed, error = None, None, None
            try:
                resp = await self.provider.complete(req)
                parsed = purpose.output_model.model_validate_json(resp.content)
                hit = reality_guard.check(parsed)
                if hit:
                    parsed, error = None, f"meta_awareness: {hit!r}"
            except ValidationError as e:
                error = f"schema: {e.errors()[:3]}"
            except Exception as e:                       # network, timeout, HTTP error
                error = f"provider: {type(e).__name__}: {e}"
            self._record(purpose, req, resp, agent_id, tick, parsed is not None, error)
            if parsed is not None:
                return parsed
            log.warning("%s attempt %d/%d failed: %s", purpose.name, attempt, self.max_attempts, error)
        return None

    def _record(self, purpose: Purpose, req: LLMRequest, resp: LLMResponse | None,
                agent_id, tick, valid: bool, error: str | None) -> None:
        self.db.execute(
            "INSERT INTO llm_calls (llm_call_id, agent_id, tick, purpose, model, prompt_version, "
            "prompt_hash, seed, request_json, response_json, valid, error, tokens_in, tokens_out, latency_ms) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(ULID()), agent_id, tick, purpose.name, resp.model if resp else req.model,
             f"{purpose.name}/{purpose.version}", prompt_hash(req), req.seed,
             req.model_dump_json(), resp.model_dump_json() if resp else None, int(valid), error,
             resp.tokens_in if resp else None, resp.tokens_out if resp else None,
             resp.latency_ms if resp else None))
```

## 12.5 The Phase 0 purpose and a manual smoke test

`mind_service/src/mind/llm/purposes.py`
```python
"""Phase 0 has a single purpose, used to prove the gateway end to end."""
from string import Template

from pydantic import BaseModel, Field

from mind.llm.types import Purpose

PRIMARY_MODEL = "qwen3:8b"


class SmokeThought(BaseModel):
    thought: str = Field(description="one or two sentences of inner monologue")
    mood: str = Field(description="a single word for how you feel")


SMOKE_THOUGHT = Purpose(
    name="smoke_thought",
    version="v1",
    model=PRIMARY_MODEL,
    system=Template(
        "You are the private inner voice of a person. You woke at a campsite in a forest. "
        "You remember only this: you survived the night, you do not remember who you are, "
        "and there is an abandoned town nearby. Think in the first person. "
        "Mention only things you can see, feel, or remember from what you are told."),
    user=Template("Right now: $situation\nWhat goes through your mind?"),
    output_model=SmokeThought,
)
```

`mind_service/src/mind/tools/smoke_llm.py`
```python
"""Manual check against a real Ollama:  python -m mind.tools.smoke_llm"""
import asyncio
import tempfile
from pathlib import Path

from mind.llm.gateway import LLMGateway
from mind.llm.providers import OllamaProvider
from mind.llm.purposes import SMOKE_THOUGHT
from mind.storage.db import connect, migrate


async def main() -> None:
    db = connect(Path(tempfile.mkdtemp()) / "mind.sqlite")
    migrate(db)
    provider = OllamaProvider()
    gw = LLMGateway(provider, db)
    out = await gw.run(SMOKE_THOUGHT, agent_id=None, tick=0, seed=7,
                       situation="Grey morning light. Cold ashes in a fire pit. Your head aches.")
    print("RESULT:", out)
    for row in db.execute("SELECT purpose, model, valid, error, tokens_out, latency_ms FROM llm_calls"):
        print("LEDGER:", row)
    await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
```

## 12.6 Tests

`mind_service/tests/test_gateway.py`
```python
import pytest

from mind.llm import reality_guard
from mind.llm.gateway import LLMGateway
from mind.llm.providers import FakeProvider
from mind.llm.purposes import SMOKE_THOUGHT, SmokeThought
from mind.storage.db import connect, migrate


@pytest.fixture
def db(tmp_path):
    con = connect(tmp_path / "mind.sqlite")
    migrate(con)
    return con


def ledger(db):
    return db.execute("SELECT valid, error FROM llm_calls ORDER BY rowid").fetchall()


async def test_valid_output_is_returned_and_recorded(db):
    fake = FakeProvider([{"thought": "My head hurts. Where is this?", "mood": "afraid"}])
    out = await LLMGateway(fake, db).run(SMOKE_THOUGHT, agent_id="a", tick=3, situation="cold")
    assert out.mood == "afraid"
    assert ledger(db) == [(1, None)]
    assert "cold" in fake.requests[0].user


async def test_bad_json_is_retried_once(db):
    fake = FakeProvider(["not json", {"thought": "Smoke.", "mood": "uneasy"}])
    out = await LLMGateway(fake, db).run(SMOKE_THOUGHT, agent_id="a", tick=3, situation="x")
    assert out.thought == "Smoke."
    assert [v for v, _ in ledger(db)] == [0, 1]


async def test_meta_awareness_is_rejected(db):
    leak = {"thought": "This must be a simulation and I am an NPC.", "mood": "odd"}
    out = await LLMGateway(FakeProvider([leak, leak]), db).run(SMOKE_THOUGHT, agent_id="a", tick=1, situation="x")
    assert out is None
    assert all(err.startswith("meta_awareness") for _, err in ledger(db))


def test_guard_allows_ordinary_survival_language():
    ok = SmokeThought(thought="The deer trail leads toward the town. I pray the bridge holds.", mood="hopeful")
    assert reality_guard.check(ok) is None


def test_missing_context_is_a_loud_error():
    with pytest.raises(KeyError):
        SMOKE_THOUGHT.render()
```

## Check it works

```bash
pytest -q                            # → 17 passed
ollama ps                            # Ollama running (step 02)
python -m mind.tools.smoke_llm
```

Expected output from the smoke test (the wording will differ):
```
RESULT: thought='My head is pounding and the fire is long dead...' mood='uneasy'
LEDGER: ('smoke_thought', 'qwen3:8b', 1, None, 54, 2300)
```

Check these:
- `valid` is `1` and `error` is `None`.
- The thought is first person and mentions only the given situation.
- Latency is in line with your step 02 benchmark.
- Run it 5 times. If any run is rejected by the reality guard, read the
  `error` column. That is the guard working, but tell me what tripped it, so the
  prompt and the guard can be tuned.

**Honest note:** the unit tests and the fake provider were run while writing
this guide. The `OllamaProvider` against a real Ollama could not be run here
(there is no GPU in this environment), so step 12's smoke test is the first
time it meets your hardware.

## Common mistakes

- **Calling `httpx` or `ollama` directly from cognition code.** Everything goes
  through `LLMGateway.run()`. Otherwise you lose the guard, the retry, the
  ledger, and replay.
- **Trusting the model's JSON without validation.** `format` constrains the
  output a lot, but validation is what guarantees it.
- **Putting game words in prompts.** The system prompt never says "game",
  "character", "NPC", or "simulation". The guard only catches leaks *out*; good
  prompts prevent them going *in*.
- **Leaving `think` on for fast purposes.** That makes calls several times
  slower. Use your step 02 numbers.
