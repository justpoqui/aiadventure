# 08 — Development Roadmap

Each phase ends with **exit criteria** that prove behaviour, not features.

## Phase 0 — Foundations (no AI yet)
- Repo scaffolding, `tools/run_dev.sh`, CI (Python tests + headless Godot tests).
- `shared/protocol/v1` schemas; MindBridge ↔ transport handshake; ping/tick.
- `world.sqlite` + `mind.sqlite` migrations `0001`; save manifest + checkpoint protocol.
- LLM gateway with **fake provider** + ledger; Ollama provider with schema output.
- Godot: SimClock, empty world, AgentBody moving on navmesh via `action_command`.

**Exit:** a scripted fake mind walks the body to points. Save → quit → load
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
9. UI: observer camera, time controls, Mind Inspector, **Truth/Belief Diff**, Journal Viewer.

**Exit:** over 10 in-game days and 5 different seeds, the survivor stays alive
and finds water and food without scripted direction. They hold at least one
false belief that is later corrected via evidence, with the revision history
visible. Journals reference real events only (the groundedness check passes on
100%). Seeds produce measurably different exploration orders.

## Phase 2 — Making Things
- Resources as physical entities, containers, transport capacity.
- Skills (true + self-assessed), XP, skill-weighted planner costs.
- Building components, repair recipes discovered via inspect/expert, repair actions, decay.
- Hierarchical goals: aspirations, projects, decomposition (templates + LLM).
- Tools, crafting from world-supported recipes; learned action models.

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

## Open questions for you (decisions needed before Phase 0)
1. **2D top-down presentation:** confirm (ADR-010), or is 3D required?
2. **Hardware target:** which GPU and VRAM? This decides whether 32B can be
   used for reflection, and the LLM budget per in-game hour.
3. **Observer powers:** pure observer, or limited "act of god" tools (weather,
   drop an item) for experiments?
4. **Death:** is it permanent? (It affects whether safety beliefs matter.)
5. **Lore depth:** should the survivor's true past exist in the world as
   discoverable truth, or remain forever unknown?
