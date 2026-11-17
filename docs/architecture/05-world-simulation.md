# 05 — World Simulation: Perception, Resources, Buildings, Skills

## 1. Objective reality (Godot)

The world is a set of entities. Each entity has components, and each component
has true state. All state is persisted in `world.sqlite`. The world evolves on
its own: weather, decay of unmaintained buildings, food spoilage, tree
regrowth, stream flow by season. Every change is written to `world_events`.

## 2. Perception: the translator from truth to appearance

### 2.1 Fidelity levels

| Fidelity | Triggered by | Reveals |
|----------|--------------|---------|
| `glimpse` | in range, peripheral, low light | category hint, rough size |
| `look` | in view cone, attended | descriptors, visible condition cues |
| `inspect` | `inspect` action adjacent | component-level cues, contents of open containers, readable text |
| `interact` | performing an action on it | experiential outcomes (weight, sturdiness, yield) |
| `expert` | `inspect` + skill ≥ threshold | quantified cues ("rafters rotted; needs ~6 boards") |

### 2.2 Observable mapping (per entity type, data-driven)

```yaml
water_tower:
  tank:
    truth: water_level            # 0..1
    cues:
      look:    []                 # cannot see inside from ground
      inspect: {requires: climbed, map: {0: "dry, dusty tank", "<0.3": "a little stagnant water", ">=0.3": "water sloshes inside"}}
  legs:
    truth: condition
    cues:
      look: {"<0.4": ["heavy rust streaks"], ">=0.4": ["sturdy-looking legs"]}
bridge:
  deck:
    truth: structural_integrity
    cues:
      look: {any: ["weathered planks"]}             # rot is NOT visible at a glance
      inspect: {"<0.3": ["planks soft and spongy underfoot"], ">=0.3": ["planks feel solid"]}
      expert(construction>=0.4): {"<0.3": ["support beams rotted through"]}
```

- **Noise:** each cue has a misperception probability scaled by light, weather,
  fatigue, and attention. This is how "the bridge appears stable" happens
  honestly.
- **Ambiguity is deliberate.** Descriptors are evidence, not facts. The mind
  turns them into beliefs through interpretation.

### 2.3 Modalities
Vision (cone + raycast occlusion + light), hearing (sounds with direction and
loudness, e.g. creaking, running water, an animal), interoception (needs,
pain, illness), proprioception (falling, slipping, weight carried), thermal
(cold/warm), and later **speech** (Phase 4, modeled as an auditory percept with
content).

## 3. Action resolution

Godot executes primitives against truth and returns outcomes **as percepts**.

| Primitive | Truth-side resolution |
|-----------|------------------------|
| `move_to(handle|point)` | navmesh pathing; terrain cost; may trigger traversal hazards (bridge) |
| `inspect(handle[, part])` | emits `inspect`/`expert` fidelity percepts |
| `pick_up / drop / store / take_from` | inventory & container transfer, capacity limits |
| `chop / quarry / scavenge / forage` | yield = f(node state, tool, skill, rng); depletes node |
| `repair(part, materials)` | consumes materials; condition += f(skill, tool, material quality); may fail |
| `build_fire / eat / drink / sleep / rest` | physiology effects (bad water → delayed illness) |
| `craft(recipe)` | only recipes the world supports; agent may *attempt* unsupported ones → failure percept |
| `write_journal` | flavour action; journal content itself comes from the mind |

An agent **can attempt anything in its known actions**. Truth decides what
happens. Attempting to drink from an empty tank yields
`{"event":"nothing_came_out"}`.

## 4. Resource system

| Resource | Physical form | Truth properties |
|----------|---------------|------------------|
| Wood | logs, planks, sticks | quality, moisture (wet wood burns badly) |
| Stone | rocks, slabs | size |
| Metal | scrap, sheets, nails | rust |
| Food | berries, canned goods, game, crops | nutrition, spoilage, **toxicity** |
| Water | stream, rain barrel, tank | **potability** (hidden; boiling helps; some sources contaminated) |
| Fuel | wood, gasoline cans | amount |
| Tools | axe, saw, hammer, shovel | durability, effectiveness |
| Repair materials | planks, nails, tar, glass | quality |

- **Everything is an entity with a location.** There is no global inventory.
  Stockpiles are containers at places, and transport is a planning concern
  (weight and volume capacity).
- Hidden properties (potability, toxicity, spoilage) exist only in truth and
  must be learned, sometimes painfully.

## 5. Building system

### 5.1 Components and derived stage

```
Building
  components: roof, walls, foundation, openings(door/windows), utility(optional)
  each: condition 0..1, material, repair_recipe (truth), decay_rate
stage (derived, truth):
  Ruined    min(structural) < 0.2
  Damaged   < 0.5
  Usable    all structural ≥ 0.5 and roof ≥ 0.6
  Restored  all ≥ 0.85
  Enhanced  Restored + ≥1 upgrade component (rain catcher, workbench, stove…)
```

### 5.2 What truth stores vs what the mind believes

| Brief's field | Stored in truth as | Exists in the mind as |
|---------------|--------------------|-----------------------|
| State | component conditions → derived stage | `condition(…)` beliefs (possibly wrong) |
| Damage Level | per-component condition | condition cues → beliefs |
| Repair Requirements | `repair_recipe` per component | `requires_for_repair` beliefs, discovered via inspect/expert |
| Discoveries | containers, items, documents physically inside | memories and beliefs after finding them |
| **Utility Value** | **affordances** (`provides shelter if roof ≥ 0.6`) | `useful_for`/narrative beliefs (subjective) |
| **Historical Significance** | documents, artifacts (text, photos, ledgers) | narrative beliefs and identity beliefs from reading them |
| **Potential Future Uses** | — (not truth) | narrative beliefs and aspirations |

### 5.3 Initial buildings (truth sketch; designers tune the values)

| Building | Notable truth | Possible survivor misreads |
|----------|---------------|----------------------------|
| Town Hall | Records room, town map, ledger of residents, a locked safe | "Seems important" / "a government facility" |
| Farmhouse | Walls OK, roof 0.3, a hearth, cellar with preserves (some spoiled) | "Could be a home" |
| General Store | Mostly looted; back room has a few cans, rope, nails | "Picked clean" (may stop searching too early) |
| Garage | Tools (saw, hammer, wrench), gasoline can, an unfinished vehicle | "Could fix the truck and leave?" |
| Water Tower | Tank empty; pipe cracked; ladder partly broken | "Likely has water" |
| Bridge (trail) | Deck integrity 0.25 | "Appears stable" |

These are *opportunities*, not objectives. Nothing references them in mind
code.

## 6. Skills system

| Skill | Practiced by | Effect |
|-------|--------------|--------|
| Woodcutting | chop | yield, time, injury risk |
| Construction | repair/build structural | repair quality, `expert` fidelity on structures |
| Repair | repair non-structural, tools | durability restored |
| Exploration | moving through unknown areas | perception range, path efficiency, less getting lost |
| Scavenging | search containers | find chance for hidden items |
| Farming | plant/tend/harvest | crop yield, `expert` fidelity on plants and soil |
| Maintenance | routine upkeep | slows building decay |
| Planning | completing multi-step plans | planner budget, decomposition quality hint |

- **Truth vs perception split again:** the true skill level lives in the body
  (Godot) and determines outcomes. The mind keeps a *self-assessed* proficiency
  belief, updated from performance feedback. A survivor can be under- or
  over-confident, which matters for latent skills and identity.
- XP has diminishing returns: `level = 1 − exp(−xp/k)`, with slow rust when a
  skill is unused.
- Skill enters planner cost (§04 3.3), so the survivor naturally gravitates
  toward what they are good at. That is where professions and identity come
  from.
