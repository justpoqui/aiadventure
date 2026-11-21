# 00 — Overview & Architecture Review

> Status: **Architecture review draft v0.2**: review round 1 decisions are
> folded in (2D/3D-ready, 8 GB GPU, acts of god, no death, hidden past). No
> implementation until this is signed off.

## 1. What we are building

A persistent, single-player **observation simulation**. The player watches; the
player does not command. One amnesiac survivor wakes at a forest campsite near
an abandoned town and, driven only by needs, perception, beliefs, memories,
emotions, and personality, decides what to do with their existence.

There are no quests, objective markers, or scripted outcomes. "Restore the town"
is not a goal anywhere in the codebase. If it happens, it happens because the
survivor *concluded* it was worth doing.

## 2. Non-negotiable principles

| # | Principle | How the architecture enforces it |
|---|-----------|----------------------------------|
| P1 | **Perception ≠ reality.** The mind never reads world truth. | The mind runs in a **separate process** (Python) that has no access to the world database. Only `Percept` messages cross the boundary. It cannot cheat because nothing is there to cheat with. |
| P2 | **Act on beliefs.** | The GOAP planner's world state is built **only** from the belief store. Action outcomes are resolved against truth in Godot, and a gap between expectation and outcome becomes *surprise*. |
| P3 | **No developer commands.** | The mind→world API only offers *primitive bodily actions* (`move_to`, `inspect`, `pick_up`, `chop`…). Nothing in the protocol sets goals. |
| P4 | **Being wrong is a feature.** | Perception has fidelity levels and noise. Reasoning-derived beliefs have capped confidence. Belief history is append-only. |
| P5 | **The LLM is a cortex, not a puppeteer.** | The LLM *proposes* interpretations, beliefs, and goals as schema-validated JSON. Deterministic systems decide what is adopted and what is executed. |
| P6 | **Multi-agent from day one.** | Every mind-side row carries `agent_id`. No shared belief tables. Communication is modeled as perception. |
| P7 | **Years of save life.** | SQLite is the canonical store with numbered migrations. ChromaDB is a **derived, rebuildable index**. Memories are consolidated and faded over time. |

## 3. Architecture review — weaknesses found in the brief

As lead architect, these are the places where the brief as written would hurt
scalability, realism, or emergence. Each has a decision attached.

### W1. A per-tick LLM loop will not work
The cognitive loop as listed (observe → … → journal → repeat) implies an LLM
call per cycle. Qwen3 14B on consumer hardware produces roughly 30–60 tokens/s.
One structured reasoning call takes 3–15 s. Ten agents would need minutes per
"thought", and the body would freeze while it waited.

**Decision — layered cognition (see `03-cognition.md`):**

| Layer | Runs | Technology | Example |
|-------|------|------------|---------|
| L0 Reflex | every tick | Python rules | Flinch away from falling debris |
| L1 Reactive | every tick / on event | Utility scoring + GOAP | Thirst is high → plan to drink |
| L2 Deliberative | on salient events, budgeted | LLM (fast, no-think) | "This tower might hold water" |
| L3 Reflective | sleep / major events | LLM (thinking, or 32B) | Journal, consolidation, life goals |

The body **never waits** for the LLM. It keeps executing its current intention
while L2/L3 think asynchronously. The loop in the brief is kept, but it is
spread across these four time scales instead of run in sequence.

### W2. Subjective properties were placed in objective reality
The brief gives every building a *Utility Value*, *Historical Significance*, and
*Potential Future Uses*. Those are **opinions**. If they live in world truth,
either the mind reads them, which breaks P1, or they are dead data.

**Decision:** World truth stores only *physical facts and affordances*:
components, condition, contents, documents, and capabilities such as
`provides: shelter_if_roof>0.6`. Utility, significance, and future use exist
only as **beliefs**, so two survivors can disagree about whether the town hall
matters.

### W3. Belief IDs named after truth (`water_tower_001`)
If the mind receives the handle `water_tower`, it already knows what the object
*is*, which is world truth leaking through a string.

**Decision:** The mind receives **opaque entity handles** (`e_7f3a`) plus
appearance descriptors ("tall rusted metal structure on legs"). The survivor
assigns its own label ("the water tower"), which is stored per agent. Belief IDs
are UUIDs.

### W4. Free-text-only beliefs cannot drive a planner
"The water tower likely contains usable water" is readable by an LLM but not by
GOAP.

**Decision — dual belief representation:**
- **Propositional beliefs**: `(subject, predicate, object, confidence)` drawn
  from a registered predicate vocabulary. The planner can use these.
- **Narrative beliefs**: free text such as "the town hall seems important".
  Only the LLM reads them. They shape which goals the LLM proposes, and a
  proposed goal must then be grounded into propositions before it can be
  planned.

Both forms share one table, one confidence model, and one revision history.

### W5. Flat GOAP cannot plan "restore the farmhouse"
GOAP's A* search breaks down on plans that need dozens of steps over several
days, and it replans the entire plan whenever a belief changes.

**Decision — hierarchical intentions:** Aspiration → Project → Objective → Task.
The LLM and reflection decompose aspirations and projects. GOAP only solves
**Objectives**, which are short-horizon symbolic goal states of about 3–15
actions. This is the HTN-over-GOAP pattern.

### W6. ChromaDB as the memory system of record
ChromaDB is not transactional with SQLite. Its on-disk format has changed
between major versions, and embeddings depend on which embedding model was
used. "Saves must work for years" is incompatible with Chroma being canonical.

**Decision:** SQLite holds the canonical memory text and metadata. Chroma holds
only vectors keyed by `memory_id`. A transactional **outbox** table drives
indexing. Each save manifest records the embedding model, and the index can be
**rebuilt** from SQLite at any time, for example after a model change.

### W7. Needs as both truth and mind state
If the mind owns `hunger = 0.7`, nothing models feeling sick from bad water
without knowing why.

**Decision:** The **body** (physiology) is world truth and lives in Godot. The
mind receives **interoception percepts**: "stomach cramping", "very thirsty".
These are mostly accurate but can be noisy or ambiguous. Needs in the mind are
*perceived* needs.

### W8. The LLM knows it is in a game
An LLM has read thousands of survival-game walkthroughs. Prompted carelessly,
it will "quest": "I should repair buildings to restore the town!" That is
emergence contaminated by genre knowledge.

**Decision:** Prompts are first-person inner monologue with strict rules:
never mention games, simulations, players, quests, or "restoring the town";
only reference entities from the provided context. A **groundedness
validator** rejects outputs that reference unknown entities or facts.

### W9. LLM hallucinations becoming facts
If the LLM says "the garage contains a generator" and that becomes a belief at
0.9 confidence, the mind is corrupted by a hallucination.

**Decision:** Source-weighted confidence. Beliefs whose source is
`reasoning`/`inference` are capped at 0.6 and flagged `hypothesis`. Only
`observation`/`experience` can push confidence above 0.85. Hypotheses generate
**questions**, which feed curiosity, which feeds goals.

### W10. Unbounded memory over years
At ~200 memories per in-game day, 5 in-game years is about 365k memories.
Retrieval quality and the context window both collapse.

**Decision:** Memory lifecycle with strength decay, **sleep consolidation**
(episodic → semantic), hierarchical summaries (day → week → season → year), and
fading (detail dropped, gist kept). Memories are archived, never hard-deleted,
for debugging. See `03-cognition.md §6`.

### W11. Emergence you cannot measure is indistinguishable from randomness
**Decision:** Observability is a first-class subsystem. Every LLM call is logged
with its prompt version and its inputs and outputs. There is a **Truth vs Belief
diff view** in the Godot inspector, along with emergence metrics such as
routine stability, belief accuracy over time, goal-origin distribution, and
personality drift. LLM I/O recording makes runs **replayable**.

### W12. Personality drift driven by LLM whim
**Decision:** Trait drift is computed by deterministic rules from tagged
experiences, for example repeated success under risk lowering fear and raising
risk tolerance. Drift is bounded per in-game week and pulled elastically toward
a baseline. The LLM may *narrate* change but may not set traits.

### W13. Context window budgeting
Qwen3 14B has a large nominal context, but quality and latency degrade well
before it is full, and a busy agent could pull 300 memories.

**Decision:** A **Context Assembler** with a token budget per call purpose
(e.g. interpretation ≈ 2.5k tokens, reflection ≈ 8k), filled in priority order:
needs/emotion → current intention → percepts → top-k beliefs → top-k memories.

### W14. Qwen3 14B does not fit on an 8 GB GPU (RTX 5060 Ti 8 GB)
Qwen3 14B Q4_K_M is about 9.3 GB of weights before the KV cache and before
Godot's own VRAM use. On 8 GB it partially offloads to the CPU and drops to
single-digit tokens per second, which is too slow for L2.

**Decision (ADR-013):** the primary model is **Qwen3 8B Q4_K_M** (~5.2 GB).
14B is optional for overnight L3 reflection with CPU offload. 32B is ruled out
on this hardware. The embedding model runs on the CPU. See
`01-system-architecture.md §6`.

## 4. Key decisions (ADR summary)

| ADR | Decision | Alternatives rejected |
|-----|----------|-----------------------|
| 001 | Godot 4 is authoritative for **world truth, physics, time, perception, action resolution** | Python world sim (loses Godot tooling, needs a second renderer bridge) |
| 002 | Python **Mind Service** owns all cognition, as a separate process | GDScript cognition (no ML ecosystem); GDExtension embedding Python (fragile) |
| 003 | Local **WebSocket** (JSON, versioned envelope; msgpack later) | HTTP polling (no push); gRPC (no first-class Godot support) |
| 004 | **Two databases**: `world.sqlite` (Godot) and `mind.sqlite` (Python) | One shared DB (makes cheating possible, breaks P1) |
| 005 | ChromaDB is a **derived index**; SQLite is canonical | Chroma-as-truth |
| 006 | Layered cognition L0–L3; the LLM is async and budgeted | LLM-per-tick |
| 007 | Dual belief representation (propositional + narrative) | Text-only; symbolic-only |
| 008 | Hierarchical goals; GOAP only at the Objective level | Flat GOAP; pure LLM planning |
| 009 | Godot is the clock master; sim time ≠ real time; time dilation when minds lag | Real-time-locked sim |
| 010 | **2D top-down now, 3D-ready**: simulation in metres with `Vector3` positions; presentation is a swappable View layer; spatial queries and navigation behind interfaces. *Confirmed in review round 3:* ground painted by a shader from an editable terrain-map PNG (world truth), with lush top-down tree canopies. | 3D now (content cost); 2D-only data model (blocks 3D later); tilemap autotiling (visible grid, more art) |
| 011 | Opaque entity handles in the mind; self-assigned labels | Truth-named IDs |
| 012 | Player is an observer plus an **unseen higher power** whose acts are limited by the survivor's belief power | Player avatar; unlimited god tools |
| 013 | Qwen3 8B primary on 8 GB VRAM; 14B optional for overnight reflection; embeddings on CPU | 14B primary (doesn't fit) |
| 014 | `belief_power` scalar is the **only** mind→world-rule channel (feeds DivinitySystem) | Divinity reading the mind DB |
| 015 | **No death**: knockout → wake at last resting place; world is not rewound; mind reframes the incident as a nightmare | Permadeath; world rewind |
| 016 | Survivor's past is **generated truth**, hidden in gated, ambiguous, diegetic clues and recollections; worldgen is world-side only | No past; authored single story; LLM-improvised past |
| 017 | **Reality guard**: meta-awareness filter on all LLM output; the survivor must never learn it is simulated | Prompt discipline only |

## 5. Document map

| Doc | Contents |
|-----|----------|
| `01-system-architecture.md` | Architecture diagram, process model, communication flow, protocol, Python service architecture |
| `02-project-structure.md` | Full folder structure and Godot scene hierarchy |
| `03-cognition.md` | Cognitive loop, needs, personality, emotion, **belief system**, **memory lifecycle**, reflection |
| `04-planning.md` | **Goal lifecycle**, hierarchical intentions, GOAP |
| `05-world-simulation.md` | World, perception fidelity, resources, buildings, skills |
| `06-data-architecture.md` | SQLite schemas (world and mind), ChromaDB design, **save system** |
| `07-scalability.md` | Multi-agent, social, and town-scale support |
| `08-roadmap.md` | Phased development roadmap with exit criteria |
| `09-divinity-knockout-lore.md` | Acts of God and belief power, knockouts, the hidden past, the reality guard |
