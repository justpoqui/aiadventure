# 02 — Project Structure & Scene Hierarchy

## 1. Repository layout

```
aiadventure/
├── README.md
├── docs/
│   ├── architecture/              ← this package
│   └── adr/                       ← one file per architecture decision (from ADR table)
│
├── shared/                        ← contracts both processes obey (language-neutral)
│   ├── protocol/
│   │   ├── v1/envelope.schema.json
│   │   ├── v1/percept.schema.json
│   │   ├── v1/action_command.schema.json
│   │   └── v1/action_update.schema.json
│   └── vocab/
│       ├── action_types.yaml      ← names + params of primitive bodily actions ONLY
│       ├── modalities.yaml
│       └── descriptors.yaml       ← appearance descriptor vocabulary
│
├── godot/                         ← WORLD: objective reality
│   ├── project.godot
│   ├── addons/
│   │   ├── godot-sqlite/          ← GDExtension for world.sqlite
│   │   └── gdUnit4/               ← tests
│   ├── autoload/
│   │   ├── event_bus.gd
│   │   ├── sim_clock.gd
│   │   ├── world_registry.gd      ← entity_id → node, spatial index
│   │   ├── mind_bridge.gd         ← WebSocket client, envelope codec
│   │   └── save_manager.gd
│   ├── sim/
│   │   ├── terrain/               ← SimTerrain: ground truth per 2 m cell, read from world/map/terrain_map.png
│   │   ├── spatial/               ← SpatialQuery + Navigation interfaces; 2D impls (incl. NavBuilder2D) now, 3D later
│   │   ├── divinity/              ← DivinitySystem: power pool, act catalogue, plausibility validation
│   │   ├── lore/                  ← clue gates, recollection triggers (reads lore truth)
│   │   ├── perception/            ← vision, hearing, interoception, fidelity rules
│   │   ├── actions/               ← one resolver per primitive action
│   │   ├── body/                  ← physiology model
│   │   ├── environment/           ← weather, temperature, day/night, light
│   │   ├── world_state/           ← component models (condition, contents, affordances)
│   │   └── persistence/           ← world repo, migrations/*.sql
│   ├── entities/
│   │   ├── agent/                 ← AgentBody.tscn (no brain here!)
│   │   ├── buildings/             ← Building.tscn + component scenes
│   │   ├── items/
│   │   ├── resource_nodes/        ← trees, rock outcrops, springs, berry bushes
│   │   └── containers/
│   ├── world/
│   │   ├── map/terrain_map.png    ← paint the world: one pixel = one 2 m cell (legend in Phase 0 step 07b)
│   │   ├── regions/               ← forest.tscn, campsite.tscn, trail.tscn, town.tscn
│   │   └── world.tscn
│   ├── data/definitions/          ← .tres Resources: entity types, materials, observables
│   ├── views/
│   │   └── view2d/                ← terrain shader, tree canopies, day/night, observer camera, art/ (view3d/ added later)
│   ├── ui/
│   │   ├── character_panel/       ← brief card of the mind's self-report (key C)
│   │   ├── divine_panel/          ← acts of god, power pool, prayers heard
│   │   ├── observer_hud/
│   │   ├── mind_inspector/        ← beliefs, goals, thoughts, emotions (from telemetry)
│   │   ├── truth_belief_diff/     ← debug: belief vs truth, colour-coded
│   │   ├── journal_viewer/
│   │   └── time_controls/
│   ├── scenes/main.tscn
│   └── tests/
│
├── mind_service/                  ← MIND: subjective reality
│   ├── pyproject.toml
│   ├── src/mind/
│   │   ├── __main__.py
│   │   ├── config/                ← settings.toml schema, model routes, budgets
│   │   ├── transport/
│   │   ├── runtime/
│   │   ├── scheduler/
│   │   ├── cognition/
│   │   │   ├── perception/
│   │   │   ├── beliefs/
│   │   │   ├── memory/
│   │   │   ├── affect/
│   │   │   ├── needs/
│   │   │   ├── personality/
│   │   │   ├── goals/
│   │   │   ├── planning/
│   │   │   ├── execution/
│   │   │   ├── reflection/
│   │   │   └── skills/
│   │   ├── llm/
│   │   │   ├── gateway.py
│   │   │   ├── router.py
│   │   │   ├── providers/ollama.py
│   │   │   ├── prompts/<purpose>/v1.j2
│   │   │   ├── schemas/<purpose>.py
│   │   │   └── validation/groundedness.py
│   │   ├── embeddings/
│   │   ├── storage/
│   │   │   ├── migrations/0001_init.sql …
│   │   │   ├── repositories/
│   │   │   ├── outbox.py
│   │   │   └── vector_index.py
│   │   └── observability/
│   ├── data/                      ← the mind's *model* of how things work
│   │   ├── predicates.yaml        ← belief vocabulary
│   │   ├── action_models.yaml     ← EXPECTED preconditions/effects/costs (beliefs!)
│   │   ├── needs.yaml
│   │   ├── traits.yaml
│   │   ├── emotions.yaml
│   │   ├── skills.yaml
│   │   └── starting_mind.yaml     ← "I survived the night", procedural knowledge
│   └── tests/
│       ├── unit/
│       ├── scenario/              ← fake world + scripted LLM, assert emergent outcomes
│       └── fixtures/
│
├── worldgen/                      ← WORLD-SIDE Python: backstory/lore generation, clue placement
│   ├── templates/                 ← authored backstory skeletons
│   └── src/worldgen/              ← writes world.sqlite only; mind/ may NOT import this (CI-enforced)
│
└── tools/
    ├── run_dev.sh                 ← start ollama check, mind service, godot
    ├── save_inspector/            ← CLI: dump/diff save slots
    ├── reindex_memories.py        ← rebuild Chroma from mind.sqlite
    └── replay.py                  ← replay a run from the LLM ledger
```

**Note the deliberate split** between `godot/sim/actions/` (what actions
*really* do) and `mind_service/data/action_models.yaml` (what the survivor
*believes* actions do). They are allowed to disagree. For example, the survivor
may believe "boiling makes any water safe" while the world models chemical
contamination. Only names and parameters are shared, in `shared/vocab/`.

Do not create placeholder folders for Phase 4 systems (social, economy). They
are designed for in `07-scalability.md` and are added when they are built.

## 2. Godot scene hierarchy

```
Main (Node)                                   scenes/main.tscn
├── SimulationRoot (Node)
│   ├── Environment (Node)
│   │   ├── DayNightCycle
│   │   ├── WeatherSystem
│   │   └── TemperatureField
│   ├── World (Node2D)                        world/world.tscn
│   │   ├── TerrainLayers (TileMapLayer ×N: ground, paths, water, foliage)
│   │   ├── NavigationRegion2D
│   │   ├── Regions (Node2D)
│   │   │   ├── Forest (Node2D)
│   │   │   │   ├── ResourceNodes (trees, berry bushes, stream)
│   │   │   │   └── Campsite (Node2D)       firepit, tent remains, bedroll
│   │   │   ├── Trail (Node2D)              includes Bridge (Building w/ components)
│   │   │   └── Town (Node2D)
│   │   │       ├── TownHall      (Building)
│   │   │       ├── Farmhouse     (Building)
│   │   │       ├── GeneralStore  (Building)
│   │   │       ├── Garage        (Building)
│   │   │       └── WaterTower    (Building)
│   │   ├── Items (Node2D)                   loose world items (dynamic)
│   │   └── Agents (Node2D)
│   │       └── AgentBody "a_0001"           entities/agent/AgentBody.tscn
│   ├── PerceptionSystem (Node)              iterates agents, emits percepts
│   ├── ActionSystem (Node)                  owns per-agent ActionRunner
│   ├── DivinitySystem (Node)                power pool from belief_power; validates and applies acts
│   └── LoreSystem (Node)                    clue gates, recollection triggers
├── Camera2D (observer camera)
└── UI (CanvasLayer)
    ├── ObserverHUD
    ├── TimeControls
    ├── DivinePanel
    ├── CharacterPanel (CanvasLayer)   brief, player-facing; MindInspector is the deep debug view
    ├── MindInspector
    ├── TruthBeliefDiff (debug, toggle)
    └── JournalViewer
```

### 2.1 3D-readiness rules (ADR-010)

1. **The simulation is the authority; the view is cosmetic.** Every entity is a
   `SimEntity` (plain `Node`) holding `sim_position: Vector3` in **metres**
   (`y` = elevation, which is 0 in 2D). The 2D view projects `(x, z)` to pixels
   with a single `PIXELS_PER_METRE` constant.
2. **No simulation logic in `Node2D`/`CharacterBody2D` scripts.** Movement,
   line of sight, and pathing go through `sim/spatial/`:
   - `SpatialQuery.line_of_sight(a, b)`, `.entities_in_radius(p, r)`
   - `Navigation.path(from, to)`, `.traversal_cost(segment)`

   The 2D implementations wrap `PhysicsDirectSpaceState2D` and
   `NavigationServer2D`. 3D implementations replace them later without touching
   perception, actions, or the mind.
3. **Databases, protocol, and percepts already use 3D** (`x, y, z`,
   `distance_m`, `bearing_deg`, `elevation_deg`).
4. Assets are referenced by `type_id` through a view registry, so a 3D model
   can be registered for the same type later.

Migration to 3D later means writing `views/view3d/` and 3D spatial and
navigation implementations. The simulation, saves, and minds are untouched.

### 2.2 Reusable scenes

```
AgentBody (SimEntity : Node)               ← authority; no 2D types in its script
├── Physiology (Node)              hunger, thirst, fatigue, temperature, health, injuries, consciousness
├── Locomotion (Node)              uses sim/spatial Navigation; 2D adapter drives the view's body
├── View2D (CharacterBody2D)       Sprite, CollisionShape2D, NavigationAgent2D — swappable for View3D
├── Inventory (Node)               weight/volume capacity
├── VisionSensor (Area2D + RayCast2D pool)
├── HearingSensor (Area2D)
├── ActionRunner (Node)            executes ONE primitive at a time, reports progress
└── ThoughtBubble (debug label, fed by telemetry)

Building (Node2D)
├── Footprint / Sprite
├── Components (Node)
│   ├── Roof        (BuildingComponent: condition, material, repair recipe)
│   ├── Walls
│   ├── Foundation
│   ├── Door / Windows
│   └── Utility     (e.g. WaterTank, Generator — optional)
├── Interior (Node2D)              containers, documents, fixtures
├── Observable (Node)              maps true state → appearance by fidelity
└── InteractionPoints (Marker2D×N)
```

Every world entity has an `Observable` component. It is the **only** place
where truth is translated into appearance, which makes perception auditable.
