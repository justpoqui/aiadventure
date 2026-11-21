# Step 07 — Godot project skeleton

**Goal:** a Godot project where the **simulation layer** (metres, game
minutes, `Vector3`) is fully separate from the **2D view layer** (pixels,
sprites), and a body can walk on a navigation mesh.

**This is the step that makes 3D possible later.** Take your time with it.

## 7.1 Create the project

1. Open Godot → **Create** → folder `<repo>/godot`, name `aiadventure`.
2. Renderer: **Compatibility**. It uses the least VRAM, and the GPU belongs to
   the LLM.
3. Delete the default `icon.svg` only if you have your own sprite. Otherwise
   keep it as the placeholder body sprite.

## 7.2 Install godot-sqlite

1. **AssetLib** tab → search **"Godot SQLite"** (by 2shady4u) → Download →
   Install. It goes into `addons/godot-sqlite/`.
2. Restart the editor.
3. Check: create a test script containing `var db = SQLite.new()`. If there is
   no "unknown class" error, it is installed.

If AssetLib is unavailable, download `demo.zip` from the godot-sqlite GitHub
releases and copy its `demo/addons/godot-sqlite` folder into `godot/addons/`.
(This guide was tested with Godot **4.6** and godot-sqlite **v4.6**.)

## 7.3 Folder layout inside `godot/`

```
autoload/   sim/core/   sim/spatial/   sim/persistence/migrations/
entities/agent/   views/view2d/   world/   scenes/   dev/
```

## 7.4 Core simulation scripts

The only place metres meet pixels:

`godot/sim/core/sim_units.gd`
```gdscript
class_name SimUnits
## The ONLY place where metres and pixels meet.
## Sim space: x = east, z = south, y = up (elevation). Screen: x right, y down.

const PIXELS_PER_METRE := 16.0


static func to_screen(p: Vector3) -> Vector2:
	return Vector2(p.x, p.z) * PIXELS_PER_METRE


static func to_sim(v: Vector2, elevation: float = 0.0) -> Vector3:
	return Vector3(v.x / PIXELS_PER_METRE, elevation, v.y / PIXELS_PER_METRE)
```

`godot/sim/core/ids.gd`
```gdscript
class_name Ids
## ULIDs: sortable, unique ids for messages and records.

const _ALPHABET := "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


static func ulid() -> String:
	var ms := int(Time.get_unix_time_from_system() * 1000.0)
	var time_part := ""
	for i in 10:
		time_part = _ALPHABET[ms & 31] + time_part
		ms = ms >> 5
	var rand_part := ""
	for i in 16:
		rand_part += _ALPHABET[randi() % 32]
	return time_part + rand_part


## Opaque handle shown to minds. Reveals nothing about what the entity is.
static func handle() -> String:
	return "e_%08x" % randi()
```

`godot/sim/core/cmd_args.gd`
```gdscript
class_name CmdArgs
## Reads user arguments passed after "--", e.g.  godot --path godot -- --slot=test --speed=16


static func all() -> Dictionary:
	var out := {}
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--"):
			var kv := arg.substr(2).split("=", true, 1)
			out[kv[0]] = kv[1] if kv.size() > 1 else "true"
	return out
```

The base of every world object. Notice that it has **no 2D types**:

`godot/sim/core/sim_entity.gd`
```gdscript
class_name SimEntity
extends Node
## Authority for one world object. Holds its TRUE state in sim units (metres).
## Views only mirror it. Nothing in this script may use pixels or 2D types.

signal moved(position: Vector3)

@export var entity_id: String = ""
@export var type_id: String = ""

var public_handle: String = ""   # opaque id that minds see
var created_tick: int = 0
var sim_position: Vector3 = Vector3.ZERO:
	set(value):
		sim_position = value
		moved.emit(value)


func _ready() -> void:
	assert(entity_id != "", "%s needs an entity_id" % name)
	if not SaveManager.restore_entity(self):
		# First time this entity has existed: take its editor placement from the view.
		var view := get_node_or_null("View2D") as Node2D
		if view != null:
			sim_position = SimUnits.to_sim(view.position)
		public_handle = Ids.handle()
		created_tick = SimClock.tick
	WorldRegistry.register(self)


func _exit_tree() -> void:
	WorldRegistry.unregister(self)


## True state beyond position. Subclasses override both.
func get_state() -> Dictionary:
	return {}


func apply_state(_state: Dictionary) -> void:
	pass
```

The view, which only copies the entity's position to the screen:

`godot/views/view2d/view_2d.gd`
```gdscript
class_name View2D
extends Node2D
## Cosmetic only: mirrors its parent SimEntity onto the 2D screen.
## In 3D this node is replaced by a View3D; the SimEntity does not change.


func _ready() -> void:
	var entity := get_parent() as SimEntity
	assert(entity != null, "View2D must be a direct child of a SimEntity")
	# Don't set position here: the entity's _ready may still read our editor placement.
	entity.moved.connect(_on_moved)


func _on_moved(p: Vector3) -> void:
	position = SimUnits.to_screen(p)
```

## 7.5 Spatial interfaces (2D implementation now, 3D later)

`godot/sim/spatial/sim_navigation.gd`
```gdscript
class_name SimNavigation
extends RefCounted
## Pathfinding in sim space (metres). SimNavigation2D now; SimNavigation3D later.


func path(_from: Vector3, _to: Vector3) -> PackedVector3Array:
	push_error("SimNavigation.path() is not implemented")
	return PackedVector3Array()
```

`godot/sim/spatial/sim_navigation_2d.gd`
```gdscript
class_name SimNavigation2D
extends SimNavigation

var _map: RID


func _init(map: RID) -> void:
	_map = map


func path(from: Vector3, to: Vector3) -> PackedVector3Array:
	var p2 := NavigationServer2D.map_get_path(_map, SimUnits.to_screen(from), SimUnits.to_screen(to), true)
	var out := PackedVector3Array()
	for v in p2:
		out.append(SimUnits.to_sim(v))
	return out
```

`godot/sim/spatial/sim_spatial_query.gd`
```gdscript
class_name SimSpatialQuery
extends RefCounted
## Line of sight and proximity in sim space. Real line of sight arrives in Phase 1.


func line_of_sight(_from: Vector3, _to: Vector3) -> bool:
	return true


func entities_in_radius(center: Vector3, radius_m: float) -> Array:
	var out := []
	for e in WorldRegistry.all():
		if e.sim_position.distance_to(center) <= radius_m:
			out.append(e)
	return out
```

## 7.6 Autoloads

The clock:

`godot/autoload/sim_clock.gd`
```gdscript
extends Node
## Master clock for the whole simulation.
## 1 tick = 1 game minute. `speed` = game minutes per real second (1.0 = a day takes 24 real minutes).

signal ticked(tick: int)

const MINUTES_PER_DAY := 1440

var tick: int = 0
var speed: float = 1.0
var paused: bool = false
var _accum: float = 0.0


func _physics_process(delta: float) -> void:
	if paused or speed <= 0.0:
		return
	_accum += delta * speed
	# Re-check `paused` every tick: a listener (e.g. a checkpoint) may pause mid-frame.
	while _accum >= 1.0 and not paused:
		_accum -= 1.0
		tick += 1
		ticked.emit(tick)


## Game minutes that pass during `delta` real seconds (0 while paused).
func sim_minutes(delta: float) -> float:
	return 0.0 if paused else delta * speed


func day() -> int:
	return floori(tick / float(MINUTES_PER_DAY))
```

`godot/autoload/world_registry.gd`
```gdscript
extends Node
## Every SimEntity in the world, by entity_id.

var _entities: Dictionary = {}


func register(e: SimEntity) -> void:
	assert(not _entities.has(e.entity_id), "duplicate entity_id: " + e.entity_id)
	_entities[e.entity_id] = e


func unregister(e: SimEntity) -> void:
	_entities.erase(e.entity_id)


func get_entity(entity_id: String) -> SimEntity:
	return _entities.get(entity_id)


func all() -> Array:
	return _entities.values()
```

`godot/autoload/spatial.gd`
```gdscript
extends Node
## Holds the active spatial implementations (2D now, 3D later) and the terrain truth.
## Simulation code calls Spatial.nav / Spatial.query / Spatial.terrain and never touches 2D APIs directly.

signal nav_ready

var nav: SimNavigation
var query: SimSpatialQuery
var terrain: SimTerrain


func install(new_nav: SimNavigation, new_query: SimSpatialQuery) -> void:
	nav = new_nav
	query = new_query
	nav_ready.emit()
```

**Temporary stand-ins.** These have the same API as the real files and are
replaced in steps 08 and 09. They let you run the project now.

`godot/autoload/mind_bridge.gd   (stub)`
```gdscript
extends Node
## TEMPORARY STUB (steps 07–08). Same API as the real MindBridge; does nothing.
## Replaced by the real file in step 09.

signal connected
signal disconnected
signal message(env: Dictionary)

const PROTOCOL_VERSION := 1

var mind_schema: int = 0


func is_ready() -> bool:
	return false


func send(_type: String, _payload: Dictionary, _agent_id: String = "") -> void:
	pass


func close() -> void:
	pass
```

`godot/autoload/save_manager.gd   (stub)`
```gdscript
extends Node
## TEMPORARY STUB (step 07 only). Same API as the real SaveManager; saves nothing.
## Replaced by the real file in step 08.

var slot_dir: String = "user://saves/default"
var world_seed: int = 1


func restore_entity(_e: SimEntity) -> bool:
	return false


func flush() -> void:
	pass


func close() -> void:
	pass


func checkpoint(_label: String) -> bool:
	return false
```

**Project → Project Settings → Globals → Autoload.** Add them **in exactly this
order**, because later ones use earlier ones:

| # | Name | Path |
|---|------|------|
| 1 | `SimClock` | `res://autoload/sim_clock.gd` |
| 2 | `WorldRegistry` | `res://autoload/world_registry.gd` |
| 3 | `Spatial` | `res://autoload/spatial.gd` |
| 4 | `MindBridge` | `res://autoload/mind_bridge.gd` |
| 5 | `SaveManager` | `res://autoload/save_manager.gd` |

## 7.7 The body

`godot/entities/agent/agent_body.gd`
```gdscript
class_name AgentBody
extends SimEntity
## The survivor's BODY. There is no brain here: decisions come from the mind service.

@export var agent_id: String = "a_0001"
```

`godot/entities/agent/locomotion.gd`
```gdscript
class_name Locomotion
extends Node
## Walks the parent SimEntity along a path, in sim time.

signal arrived
signal failed(reason: String)

@export var walk_speed_m_per_min: float = 80.0   # a brisk walk

var _path := PackedVector3Array()
var _index := 0

@onready var _body: SimEntity = get_parent()


func move_to(target: Vector3) -> void:
	if Spatial.nav == null:
		failed.emit("navigation_not_ready")
		return
	_path = Spatial.nav.path(_body.sim_position, target)
	_index = 0
	if _path.is_empty():
		failed.emit("no_path")


func stop() -> void:
	_path = PackedVector3Array()


func is_moving() -> bool:
	return not _path.is_empty()


func _physics_process(delta: float) -> void:
	if _path.is_empty():
		return
	var budget := walk_speed_m_per_min * SimClock.sim_minutes(delta)
	while budget > 0.0 and _index < _path.size():
		var target := _path[_index]
		var dist := _body.sim_position.distance_to(target)
		if dist <= budget:
			_body.sim_position = target
			budget -= dist
			_index += 1
		else:
			_body.sim_position = _body.sim_position.move_toward(target, budget)
			budget = 0.0
	if _index >= _path.size():
		_path = PackedVector3Array()
		arrived.emit()
```

**Build `entities/agent/agent_body.tscn` in the editor:**
```
AgentBody (Node)            script: agent_body.gd · entity_id = "agent_a_0001" · type_id = "human" · agent_id = "a_0001"
├── Locomotion (Node)       script: locomotion.gd
└── View2D (Node2D)         script: view_2d.gd
    └── Sprite2D            texture: icon.svg · scale 0.25
```

`AgentBody` is a **plain Node**, not a CharacterBody2D. That is deliberate: the
authority must not be a 2D type. The ActionRunner node is added in step 10.

## 7.8 The world and main scenes

This is a **temporary** world script for this step's hand-drawn navigation area. Step 07b replaces it with the terrain-map world.

`godot/world/world.gd   (step 07 version)`
```gdscript
extends Node2D
## STEP 07 VERSION (temporary): uses the hand-drawn NavigationRegion2D.
## Replaced in step 07b by the terrain-map world.


func _ready() -> void:
	var region := $NavigationRegion2D as NavigationRegion2D
	var poly := region.navigation_polygon
	# A point we know is navigable: the centre of the mesh's first polygon.
	var probe := Vector2.ZERO
	var first := poly.get_polygon(0)
	for i in first:
		probe += poly.get_vertices()[i]
	probe /= first.size()
	# The navigation server syncs in the background. Never wait a fixed number of frames:
	# wait until the map really answers a query at the probe point.
	var map := get_world_2d().get_navigation_map()
	while true:
		await get_tree().physics_frame
		if NavigationServer2D.map_get_iteration_id(map) > 0 \
				and NavigationServer2D.map_get_closest_point(map, probe).distance_to(probe) < 1.0:
			break
	Spatial.install(SimNavigation2D.new(map), SimSpatialQuery.new())
	print("World: navigation ready")
```

**Build `world/world.tscn`:**
```
World (Node2D)                       script: world.gd
├── NavigationRegion2D               draw an outline, then Bake NavigationPolygon
└── Agents (Node2D)
    └── AgentBody (instance of agent_body.tscn)
```

To make the navigation mesh, select NavigationRegion2D → in the inspector, New
NavigationPolygon → use the toolbar to draw a big rectangle (at least −160,−160
to 480,400 px, which is −10..30 m by −10..25 m) → **Bake NavigationPolygon**.
Optionally draw a second outline inside it as an obstacle, to see pathing go
around it.

`godot/scenes/main.gd`
```gdscript
extends Node
## Root of the running game: time controls, manual save, clean shutdown.
## Dev args (after "--"):  --slot=NAME  --restore=LABEL  --speed=N  --quit-after=SECONDS

var _quitting := false


func _ready() -> void:
	get_tree().auto_accept_quit = false     # we must flush and tell the mind before quitting
	var args := CmdArgs.all()
	if args.has("speed"):
		SimClock.speed = float(args["speed"])
	if args.has("quit-after"):
		await get_tree().create_timer(float(args["quit-after"])).timeout
		_shutdown()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_shutdown()


func _unhandled_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	match key.keycode:
		KEY_SPACE:
			SimClock.paused = not SimClock.paused
		KEY_EQUAL:
			SimClock.speed = minf(SimClock.speed * 4.0, 64.0)
		KEY_MINUS:
			SimClock.speed = maxf(SimClock.speed / 4.0, 1.0)
		KEY_F5:
			SaveManager.checkpoint("manual_%d" % SimClock.tick)


func _shutdown() -> void:
	if _quitting:
		return
	_quitting = true
	SimClock.paused = true                   # freeze time first, or the saved tick goes stale
	SaveManager.flush()
	MindBridge.send("shutdown", {})
	await get_tree().create_timer(0.3).timeout   # give the socket time to deliver
	MindBridge.close()
	SaveManager.close()
	print("Main: clean shutdown at tick %d" % SimClock.tick)
	get_tree().quit()
```

**Build `scenes/main.tscn`** and set it as the main scene (Project Settings →
Application → Run → Main Scene):
```
Main (Node)                script: main.gd
├── World (instance of world.tscn)
├── Camera2D               position (160, 120)
└── DevClickToWalk (Node)  script: dev/dev_click_to_walk.gd    ← temporary
```

`godot/dev/dev_click_to_walk.gd`
```gdscript
extends Node
## TEMPORARY (steps 07–08 only): left-click anywhere to make the body walk there.
## This is a developer test tool, not gameplay. Delete it in step 10.


func _unhandled_input(event: InputEvent) -> void:
	var click := event as InputEventMouseButton
	if click == null or not click.pressed or click.button_index != MOUSE_BUTTON_LEFT:
		return
	var agent := WorldRegistry.get_entity("agent_a_0001")
	var world_px := get_viewport().get_canvas_transform().affine_inverse() * click.position
	agent.get_node("Locomotion").move_to(SimUnits.to_sim(world_px))
```

## Check it works

1. Press **F5** (run). The output shows `World: navigation ready`.
2. **Left-click** somewhere on the mesh. The sprite walks there along the mesh,
   and around your obstacle if you drew one.
3. **Space** pauses: a click then starts a path, but the body doesn't move until
   you unpause.
4. Press **=** a few times. The body walks 4×, then 16× faster, because movement
   uses sim minutes.
5. **3D-readiness self-check:** search `sim/` for `Vector2`. It may appear only
   in `sim_units.gd` and `sim_navigation_2d.gd` (and, after step 07b,
   `nav_builder_2d.gd`).

## Common mistakes

- **Making AgentBody a CharacterBody2D "to get collisions".** Collisions and
  pathing come from navigation. The authority stays a plain Node.
- **Setting the View2D position in its `_ready`.** That overwrites the editor
  placement before the entity reads it. The comment in `view_2d.gd` explains
  this.
- **Waiting a fixed number of frames for navigation.** The navigation server
  syncs in the background, and a big map can take a dozen or more frames.
  `world.gd` waits until the map *answers a query*. (An earlier version of this
  guide waited two frames. It worked on the small test area and failed on the
  real map in step 07b.)
- **Wrong autoload order.** You get `Identifier not found: SimClock` at
  startup.
