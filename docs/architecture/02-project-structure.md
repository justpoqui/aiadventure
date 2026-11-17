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
│   │   ├── regions/               ← forest.tscn, campsite.tscn, trail.tscn, town.tscn
│   │   └── world.tscn
│   ├── data/definitions/          ← .tres Resources: entity types, materials, observables
│   ├── ui/
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
│   └── ActionSystem (Node)                  owns per-agent ActionRunner
├── Camera2D (observer camera)
└── UI (CanvasLayer)
    ├── ObserverHUD
    ├── TimeControls
    ├── MindInspector
    ├── TruthBeliefDiff (debug, toggle)
    └── JournalViewer
```

### Reusable scenes

```
AgentBody (CharacterBody2D)
├── Sprite / AnimatedSprite2D
├── CollisionShape2D
├── NavigationAgent2D
├── Physiology (Node)              hunger, thirst, fatigue, temperature, health, injuries
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
