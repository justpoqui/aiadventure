# 07 — Scalability: From One Survivor to a Town of Minds

None of these systems are built before Phase 4. This document exists so that
nothing built in Phases 1–3 blocks them.

## 1. Rules already enforced in Phase 1

| Rule | Why it matters later |
|------|----------------------|
| `agent_id` on every mind row; no singletons in cognition | N minds share one service |
| Minds are actors with private inboxes | Parallelism without locks |
| No shared belief table | Independent worldviews are the default, not a retrofit |
| Opaque handles and self-labels | Two agents can call the same building different names |
| Communication must be a percept | Speech, rumors, and deception fall out of the belief system |
| Belief `source_type` includes `testimony` | Trust weighting is already a confidence input |
| Cognitive LOD + scheduler | LLM cost scales sub-linearly with population |
| Agents identified by handle in other minds | Recognition is learned ("the tall one who came from the north") |

## 2. Social cognition (Phase 4)

- **Speech acts:** `say(target, content)` is a primitive action. Godot delivers
  it as an `auditory/speech` percept to every agent within earshot, so
  eavesdropping is free. Content is structured, as
  `{utterance_text, claims:[proposition], intent}`. Claims enter the listener's
  belief store as `testimony`, weighted by `trust(listener→speaker)`.
- **Rumors:** testimony about testimony carries a provenance chain
  (`source_ref` → chain). Confidence degrades per hop and distortion can occur
  when the LLM paraphrases. That is how rumors happen.
- **Deception:** the speaker's claim ≠ the speaker's belief. Detection comes
  through later contradicting evidence, which lowers trust (`social_models`).
- **Shared knowledge** is not a shared table. It is many private beliefs
  converging. "Cultural knowledge" is a measured property (belief overlap
  across agents), and later possibly an emergent `tradition` memory kind.
- **Trust/Reputation:** per-pair `social_models`. Reputation is A's belief
  about how others regard B, so it is another belief.
- **Relationships, families, leadership:** relationship memories plus
  social-model dimensions. Leadership emerges as others adopting goals
  proposed by an agent; tracked as `goal.origin_type = 'persuasion'`.
- **Governance, economy, factions:** later layers built on shared intentions
  (joint goals with multiple committed agents), ownership beliefs, and
  exchange actions. Ownership is a *belief* that can be disputed. There is no
  ownership truth, except that a physical possession truth exists.

## 3. Performance envelope

| Agents | Strategy |
|--------|----------|
| 1–5 | All `focus` LOD; single Ollama; real-time at 1× |
| 5–30 | Focus/active/background LOD; coalesced L2; L3 staggered across the night |
| 30–200 | Multiple Ollama backends (router round-robin); background agents L1-only by day; batched sleep reflection; possibly a smaller model for background minds |
| 200+ | Mind Service sharded by agent range (multiple processes); Godot spatial partitioning for perception; consider a headless world server |

L1 cost target: under 1 ms per agent per tick (Python), so 200 agents stay
under 200 ms per tick at 1×.
Perception cost: a spatial hash plus per-agent attention caps (at most 30 attended
entities per batch).

## 4. Things to avoid now that would hurt later
- Hard-coding "the survivor" anywhere (`get_node("Survivor")`, a global
  `Player` autoload).
- UI that reads mind state from anything other than telemetry.
- Prompt templates that assume solitude ("you are alone"). Instead, solitude
  is a belief that is currently true.
- Agent-specific Chroma collections. Use metadata filters.
