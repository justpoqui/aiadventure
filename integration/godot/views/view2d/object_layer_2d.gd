class_name ObjectLayer2D
extends Node2D
## Cosmetic: one sprite per world object, layered for a top-down view:
##   water_surface (lily pads) z1 · ground (rocks, logs, plants, props) z2 · building z3
##   agents and land animals z4 · canopy (tree crowns) z6 · flying/perched birds z7
## Canopies fade when an agent or animal of interest walks underneath.

const Z := {"water_surface": 1, "ground": 2, "building": 3, "canopy": 6}
const FADE_RADIUS_M := 3.0
const FADED_ALPHA := 0.35
const BUCKET_M := 8.0

var _canopy_buckets: Dictionary = {}
var _faded: Array = []
var _timer := 0.0


func populate(objects: WorldObjects, sprites_json: String, art_root: String) -> void:
	var index := {}
	for s in JSON.parse_string(FileAccess.get_file_as_string(sprites_json))["sprites"]:
		index[s["id"]] = s
	var textures := {}
	for o in objects.objects:
		var s: Dictionary = index[o["sprite"]]
		if not textures.has(s["file"]):
			textures[s["file"]] = load(art_root.path_join(s["file"]))
		var sp := Sprite2D.new()
		sp.texture = textures[s["file"]]
		sp.centered = false
		sp.offset = -Vector2(float(s["anchor_px"][0]), float(s["anchor_px"][1]))
		sp.position = SimUnits.to_screen(o["position"])
		sp.z_index = Z[o["layer"]]
		add_child(sp)
		if o["layer"] == "canopy":
			var key := Vector2i(floori(o["position"].x / BUCKET_M), floori(o["position"].z / BUCKET_M))
			if not _canopy_buckets.has(key):
				_canopy_buckets[key] = []
			_canopy_buckets[key].append([sp, o["position"]])


func _process(delta: float) -> void:
	_timer -= delta
	if _timer > 0.0:
		return
	_timer = 0.1
	for sp in _faded:
		sp.modulate.a = 1.0
	_faded.clear()
	for e in WorldRegistry.all():
		if not e is AgentBody:
			continue
		var key := Vector2i(floori(e.sim_position.x / BUCKET_M), floori(e.sim_position.z / BUCKET_M))
		for dx in range(-1, 2):
			for dz in range(-1, 2):
				for entry in _canopy_buckets.get(key + Vector2i(dx, dz), []):
					if entry[1].distance_to(e.sim_position) < FADE_RADIUS_M + 2.5:
						entry[0].modulate.a = FADED_ALPHA
						_faded.append(entry[0])
