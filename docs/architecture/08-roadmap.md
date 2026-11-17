# 08 — Development Roadmap

Each phase ends with **exit criteria** that prove behaviour, not features.

## Phase 0 — Foundations (no AI yet)
- Repo scaffolding, `tools/run_dev.sh`, CI (Python tests + headless Godot tests).
- `shared/protocol/v1` schemas; MindBridge ↔ transport handshake; ping/tick.
- `world.sqlite` + `mind.sqlite` migrations `0001`; save manifest + checkpoint protocol.
- LLM gateway with **fake provider** + ledger; Ollama provider with schema output.
- **Hardware benchmark** on the RTX 5060 Ti 8 GB: tokens/s and VRAM for `qwen3:8b` (thinking on/off), `qwen3:14b` with offload, CPU embeddings, with Godot running. These numbers replace the estimates in `01 §6`.
- Reality guard (meta-awareness filter) in the gateway from day one.
- 3D-ready spatial interfaces (`sim/spatial/`) with 2D implementations; `SimEntity` + `View2D` split.
- Godot: SimClock, empty world, AgentBody moving on navmesh via `action_command`.

**Exit:** benchmark numbers recorded, and the LLM budget table updated. A scripted fake mind walks the body to points. Save → quit → load
resumes at the same tick. A protocol mismatch is rejected cleanly.

## Phase 1 — A Mind Wakes Up
1. World: forest, campsite, trail (with bridge), town with 5 building shells; Observable mappings; day/night; basic weather.
2. Body: physiology; interoception percepts.
3. Perception: vision fidelity glimpse/look/inspect; noise.
4. Mind L1: perceived needs, working memory, salience, rule interpretation, belief store + revision, GOAP with survival and inspect actions.
5. Mind L2: `interpret_percepts`, `inner_thought` with groundedness validation.
6. Memory: encoding, SQLite + outbox → Chroma, composite retrieval.
7. Affect: appraisal, emotions, mood.
8. L3: daily reflection + journal + consolidation (simple).
9. **Knockouts:** collapse → wake at last resting place; nightmare reframing; no world rewind.
10. **Divinity Tier 0–1:** belief power computation, power pool, dream motifs, light weather nudges, DivinePanel.
11. UI: observer camera, time controls, Mind Inspector, **Truth/Belief Diff**, Journal Viewer.

**Exit:** over 10 in-game days and 5 different seeds, the survivor keeps
themselves alive (knockouts allowed; at least one occurs and is journaled as a
nightmare) and finds water and food without scripted direction. They hold at least one
false belief that is later corrected via evidence, with the revision history
visible. Journals reference real events only (the groundedness check passes on
100%). Seeds produce measurably different exploration orders.

## Phase 2 — Making Things
- Resources as physical entities, containers, transport capacity.
- Skills (true + self-assessed), XP, skill-weighted planner costs.
- Building components, repair recipes discovered via inspect/expert, repair actions, decay.
- Hierarchical goals: aspirations, projects, decomposition (templates + LLM).
- Tools, crafting from world-supported recipes; learned action models.
- **Worldgen lore v1:** backstory skeletons, fact generation, constrained document prose, clue placement solver with gates. Clues exist and can be found, but recollections are not yet active.
- Divinity Tier 2–3 (providence items, signs, vision dreams); emergent `pray` action.

**Exit:** in at least 3 of 5 seeds, the survivor chooses a shelter building on
their own and raises it to `Usable` within 30 in-game days. The **choice of
building differs across personality profiles**. At least one project is
abandoned for a believable, logged reason.

## Phase 3 — Becoming Someone
- Routines (plan caching + habit discount); daily schedules emerge.
- Advanced reflection: questions, epiphanies, self-beliefs, identity (latent
  skills, found documents).
- Personality drift rules; mood-driven long-term behaviour (hope and despair arcs).
- Memory hierarchy (week/season/year summaries), forgetting, reconstructive recall.
- Seasons, farming, maintenance.
- **Recollections** (sensory fragments of the past); identity hypotheses; `identity_reconstruction_score` in the diff view.
- Divinity Tier 4; faith dynamics (unanswered prayers, habituation).
- Emergence metrics dashboard (routine stability, belief accuracy, goal-origin
  distribution, trait trajectories).

**Exit:** a 1-year headless run completes within the storage budget. Routines
are stable but adaptive (they change after a season shift). The survivor
adopts a self-name or a stable self-description through reflection. Journals
from day 300 reference day-20 events via retained gist.

## Phase 4 — Others
- Multiple agents, cognitive LOD, scheduler at scale.
- Speech acts, testimony, trust, rumors, deception.
- Social models, relationships, joint goals, emergent leadership.
- Later: economy, governance, factions, culture metrics.

**Exit:** two agents with conflicting beliefs about the same building
negotiate or diverge believably. A rumor propagates with measurable distortion.
Trust drops after a detected lie.

## Cross-cutting, every phase
- Scenario tests (fake world + recorded LLM) asserting *properties*, never
  exact action sequences.
- Prompt regression suite: replay ledgers, diff outputs on prompt change.
- Golden saves from each phase load in all later versions.
- Performance budgets tracked in CI (L1 ms/tick, tokens per in-game hour).

## Resolved in review round 1

| Question | Decision |
|----------|----------|
| 2D or 3D | 2D now, built to move to 3D later (ADR-010, `02 §2.1`) |
| Hardware | RTX 5060 Ti 8 GB: Qwen3 8B primary, 14B optional overnight (ADR-013, `01 §6`) |
| Observer powers | Acts of God limited by the survivor's belief power (ADR-012/014, `09 §1`) |
| Death | None. Knockout, then wake as if from a bad dream (ADR-015, `09 §2`) |
| Lore | Discoverable but very hard; the survivor must believe it is all real (ADR-016/017, `09 §3`) |

## Resolved in review round 2

| Question | Decision |
|----------|----------|
| Faith ceiling | Tier 4 miracles need extreme devotion (`09 §1.4`) |
| Backstories | Drafted by the architect: 4 templates in `worldgen/templates/backstories/` |
| Destroyed clues | Gone forever; the survivor keeps only memories of them (`09 §3.4`) |
