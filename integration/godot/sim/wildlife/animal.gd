class_name Animal
extends SimEntity
## A wild animal: WORLD TRUTH, not a mind. Simple, believable habits per species:
## a daily activity rhythm, wandering a home range, grazing, resting, fleeing from people,
## hiding (squirrels climb, frogs dive, fish go deep), deer drinking at dusk, birds perching.
## Times use sim seconds, so behaviour scales with the game clock.

signal sound(animal: Animal, kind: String)

const MOVE_FRAMES := {
	"fish": ["swim_1", "swim_2", "swim_3", "swim_4"], "rabbit": ["hop_1", "hop_2"],
	"deer": ["walk_1", "walk_2"], "bird": ["fly_1", "fly_2"], "squirrel": ["run_1", "run_2"], "frog": ["jump"],
}
const IDLE_FRAME := {"fish": "swim_2", "rabbit": "sit", "deer": "stand", "bird": "perch", "squirrel": "sit", "frog": "sit"}
const HOME_RADIUS_M := {"fish": 14.0, "rabbit": 18.0, "deer": 45.0, "bird": 30.0, "squirrel": 14.0, "frog": 10.0}

var species := ""
var cfg: Dictionary = {}           # behaviour block from renders/wildlife/wildlife.json
var meaning: Dictionary = {}       # truth + appearance, for perception later
var home := Vector3.ZERO
var group := ""
var system: Node                   # WildlifeSystem (for herd alarms)

var state := "idle"                # idle, move, flee, rest, hide, drink, perch
var frame_name := "sit"
var heading := 0.0                 # radians, 0 = facing north (screen up)
var hidden := false
var elevated := false              # perched in a tree crown or flying
var _path := PackedVector3Array()
var _path_i := 0
var _speed := 1.0
var _timer := 0.0                  # sim seconds left in the current state
var _drank_day := -1
var _rng := RandomNumberGenerator.new()


func setup(spec: Dictionary, species_cfg: Dictionary, world_system: Node) -> void:
	species = spec["species"]
	entity_id = spec["id"]
	type_id = "animal_" + species
	cfg = species_cfg["behaviour"]
	meaning = species_cfg["meaning"]
	home = Vector3(float(spec["home_tile"][0]) * 2.0, 0.0, float(spec["home_tile"][1]) * 2.0)
	group = str(spec["group"]) if spec["group"] != null else ""
	system = world_system
	sim_position = Vector3(float(spec["pos_m"][0]), 0.0, float(spec["pos_m"][1]))
	_rng.seed = hash(entity_id)
	frame_name = IDLE_FRAME[species]
	_timer = _rng.randf_range(5.0, 60.0)


func _physics_process(delta: float) -> void:
	var dt := SimClock.sim_minutes(delta) * 60.0
	if dt <= 0.0 or Spatial.nav == null:
		return
	var threat := _nearest_threat()
	if threat != null and state not in ["flee", "hide"]:
		_start_flee(threat)
		if system and group != "":
			system.alarm(self, threat)
	_timer -= dt
	match state:
		"move", "flee", "drink_walk":
			_advance(dt)
		_:
			if _timer <= 0.0:
				_decide()
	if species in ["bird", "frog", "fish"] and _rng.randf() < dt / 600.0:
		_maybe_sing()


# ---------------------------------------------------------------- decisions

func _decide() -> void:
	hidden = false
	if not _is_active():
		if sim_position.distance_to(home) > 6.0 and species != "bird":
			_go_to(home, float(cfg["speed_mps"]), "move")
		else:
			state = "rest"
			elevated = species == "bird"
			frame_name = IDLE_FRAME[species]
			_timer = _rng.randf_range(300.0, 1200.0)
		return
	var hour := _hour()
	if species == "deer" and hour >= 18.0 and hour < 20.0 and _drank_day != SimClock.day():
		var shore := _find_cell(func(t, cx, cz): return t == SimTerrain.T.FOREST_FLOOR and _touches_water(cx, cz), 60.0)
		if shore != Vector3.INF:
			_drank_day = SimClock.day()
			_go_to(shore, float(cfg["speed_mps"]), "drink_walk")
			return
	var r := _rng.randf()
	if r < 0.45:
		_wander()
	else:
		state = "idle"
		elevated = species == "bird" and elevated
		frame_name = "graze" if species in ["deer", "rabbit"] and r < 0.8 else IDLE_FRAME[species]
		_timer = _rng.randf_range(20.0, 120.0)


func _wander() -> void:
	var speed := float(cfg["speed_mps"])
	match species:
		"fish":
			var p := _find_cell(func(t, cx, cz): return t == SimTerrain.T.WATER, HOME_RADIUS_M["fish"], home)
			if p != Vector3.INF and _straight_in_water(sim_position, p):
				_set_path(PackedVector3Array([p]), speed, "move")
			else:
				_timer = 5.0
		"bird":
			if _rng.randf() < 0.55:
				var tree := Spatial.objects.nearest(sim_position + Vector3(_rng.randf_range(-20, 20), 0, _rng.randf_range(-20, 20)),
						15.0, WorldObjects.is_tree)
				if not tree.is_empty():
					elevated = true
					_set_path(PackedVector3Array([tree["position"]]), float(cfg["fly_speed_mps"]), "move")
					return
			var g := _find_cell(func(t, cx, cz): return SimTerrain.WALKABLE[t], 10.0)
			if g != Vector3.INF:
				elevated = true          # flies down; lands at the end of the move
				_set_path(PackedVector3Array([g]), float(cfg["fly_speed_mps"]), "move")
		"frog":
			var s := _find_cell(func(t, cx, cz): return t == SimTerrain.T.FOREST_FLOOR and _touches_water(cx, cz), HOME_RADIUS_M["frog"], home)
			if s != Vector3.INF:
				_set_path(PackedVector3Array([sim_position.move_toward(s, float(cfg["jump_m"]))]), 2.5, "move")
		_:
			var prefer: Array = cfg.get("prefers", [])
			var target := Vector3.INF
			for attempt in 6:
				var p := _find_cell(func(t, cx, cz): return SimTerrain.WALKABLE[t] and t != SimTerrain.T.BRIDGE,
						HOME_RADIUS_M[species], home)
				if p == Vector3.INF:
					continue
				target = p
				if prefer.is_empty() or SimTerrain.NAMES[Spatial.terrain.at(p)] == prefer[0]:
					break
			if species == "deer" and group != "" and system:
				var leader: Animal = system.leader_of(self)
				if leader != self and leader.sim_position.distance_to(sim_position) > 8.0:
					target = leader.sim_position + Vector3(_rng.randf_range(-4, 4), 0, _rng.randf_range(-4, 4))
			if target != Vector3.INF:
				_go_to(target, speed, "move")


func _start_flee(threat: Node) -> void:
	var away: Vector3 = (sim_position - threat.sim_position)
	away.y = 0
	away = away.normalized() if away.length() > 0.01 else Vector3(1, 0, 0)
	match species:
		"squirrel":
			var tree := Spatial.objects.nearest(sim_position, 25.0, WorldObjects.is_tree)
			if not tree.is_empty():
				_go_to(tree["position"], float(cfg["flee_speed_mps"]), "flee")
				_after_flee = "hide"
				return
		"frog":
			var w := _find_cell(func(t, cx, cz): return t == SimTerrain.T.WATER, 6.0)
			if w != Vector3.INF:
				_set_path(PackedVector3Array([w]), 3.0, "flee")
				_after_flee = "hide"
				return
		"fish":
			var deep := _find_cell(func(t, cx, cz): return t == SimTerrain.T.WATER and not _touches_land(cx, cz), 12.0, sim_position + away * 6.0)
			if deep != Vector3.INF and _straight_in_water(sim_position, deep):
				_set_path(PackedVector3Array([deep]), float(cfg["dart_speed_mps"]), "flee")
				_after_flee = "hide"
				return
		"bird":
			var tree := Spatial.objects.nearest(sim_position + away * 25.0, 20.0, WorldObjects.is_tree)
			elevated = true
			var dest: Vector3 = tree["position"] if not tree.is_empty() else sim_position + away * 25.0
			_set_path(PackedVector3Array([dest]), float(cfg["fly_speed_mps"]), "flee")
			_after_flee = "perch"
			return
	var target := sim_position + away * _rng.randf_range(20.0, 35.0)
	_go_to(target, float(cfg.get("flee_speed_mps", 3.0)), "flee")
	_after_flee = "alert"


var _after_flee := "alert"


func on_alarm(threat: Node) -> void:
	if state not in ["flee", "hide"]:
		_start_flee(threat)


# ---------------------------------------------------------------- movement

func _go_to(target: Vector3, speed: float, new_state: String) -> void:
	var path := Spatial.nav.path(sim_position, target)
	if path.is_empty():
		state = "idle"
		_timer = _rng.randf_range(5.0, 20.0)
		return
	_set_path(path, speed, new_state)


func _set_path(path: PackedVector3Array, speed: float, new_state: String) -> void:
	_path = path
	_path_i = 0
	_speed = speed
	state = new_state
	hidden = false


func _advance(dt: float) -> void:
	var budget := _speed * dt
	while budget > 0.0 and _path_i < _path.size():
		var target := _path[_path_i]
		var to := target - sim_position
		to.y = 0
		var dist := to.length()
		if dist > 0.001:
			heading = atan2(to.x, -to.z)
		if dist <= budget:
			sim_position = target
			budget -= dist
			_path_i += 1
		else:
			sim_position += to / dist * budget
			budget = 0.0
	if _path_i >= _path.size():
		_arrive()


func _arrive() -> void:
	match state:
		"flee":
			if _after_flee == "hide":
				state = "hide"
				hidden = true
				_timer = _rng.randf_range(60.0, 240.0)
			elif _after_flee == "perch":
				state = "perch"
				elevated = true
				frame_name = "perch"
				_timer = _rng.randf_range(60.0, 300.0)
			else:
				state = "idle"
				frame_name = "alert" if species == "deer" else IDLE_FRAME[species]
				_timer = _rng.randf_range(30.0, 90.0)
		"drink_walk":
			state = "drink"
			frame_name = "graze"
			_timer = _rng.randf_range(60.0, 180.0)
		_:
			state = "idle"
			if species == "bird":
				var on_tree := not Spatial.objects.in_radius(sim_position, 0.5, WorldObjects.is_tree).is_empty()
				elevated = on_tree
				frame_name = "perch"
			else:
				frame_name = IDLE_FRAME[species]
			_timer = _rng.randf_range(10.0, 60.0)


func is_moving() -> bool:
	return state in ["move", "flee", "drink_walk"]


# ---------------------------------------------------------------- senses and helpers

func _nearest_threat() -> Node:
	var radius := float(cfg["flee_radius_m"]) * (0.7 if not _is_daylight() else 1.0)
	if state == "rest":
		radius *= 0.6
	for e in WorldRegistry.all():
		if e is AgentBody and e.sim_position.distance_to(sim_position) < radius:
			return e
	return null


func _is_active() -> bool:
	var h := _hour()
	var spans = cfg["active_hours"]
	if spans.size() == 2 and not (spans[0] is Array):
		spans = [spans]
	for s in spans:
		if h >= float(s[0]) and h < float(s[1]):
			return true
	return false


func _hour() -> float:
	return float(SimClock.tick % SimClock.MINUTES_PER_DAY) / 60.0


func _is_daylight() -> bool:
	var h := _hour()
	return h >= 6.0 and h < 20.0


func _maybe_sing() -> void:
	var spans = cfg.get("sings_at", cfg.get("croaks_at", []))
	var h := _hour()
	for s in spans:
		if h >= float(s[0]) and h < float(s[1]) and not hidden:
			sound.emit(self, "birdsong" if species == "bird" else "croak")
			return


func _find_cell(pred: Callable, radius_m: float, around: Vector3 = Vector3.INF) -> Vector3:
	var c := around if around != Vector3.INF else sim_position
	var t := Spatial.terrain
	for attempt in 24:
		var p := c + Vector3(_rng.randf_range(-radius_m, radius_m), 0, _rng.randf_range(-radius_m, radius_m))
		var cell := t.cell_of(p)
		if pred.call(t.at_cell(cell.x, cell.z), cell.x, cell.z):
			return t.cell_center(cell.x, cell.z) + Vector3(_rng.randf_range(-0.6, 0.6), 0, _rng.randf_range(-0.6, 0.6))
	return Vector3.INF


func _touches_water(cx: int, cz: int) -> bool:
	for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
		if Spatial.terrain.at_cell(cx + d.x, cz + d.y) == SimTerrain.T.WATER:
			return true
	return false


func _touches_land(cx: int, cz: int) -> bool:
	for dz in range(-1, 2):
		for dx in range(-1, 2):
			if Spatial.terrain.at_cell(cx + dx, cz + dz) != SimTerrain.T.WATER:
				return true
	return false


func _straight_in_water(a: Vector3, b: Vector3) -> bool:
	var n := int(a.distance_to(b) / 0.5) + 1
	for i in n + 1:
		if Spatial.terrain.at(a.lerp(b, float(i) / n)) != SimTerrain.T.WATER:
			return false
	return true


func get_state() -> Dictionary:
	return {"species": species, "state": state}
