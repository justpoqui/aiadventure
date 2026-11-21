class_name WorldObjects
extends RefCounted
## WORLD TRUTH: every tree, bush, rock, log, prop and building, from world_data/objects.json.
## Each object keeps its full meaning (truth + appearance) for perception later.
## Wren's mind never reads this: perception turns `meaning.appearance` into percepts.

var objects: Array = []          # Array of Dictionary (see objects.json)
var _by_bucket: Dictionary = {}  # Vector2i -> Array of indices
const BUCKET_M := 16.0


static func load_from(path: String) -> WorldObjects:
	var data = JSON.parse_string(FileAccess.get_file_as_string(path))
	assert(data is Dictionary, "cannot read " + path)
	var w := WorldObjects.new()
	for o in data["objects"]:
		o["position"] = Vector3(float(o["pos_m"][0]), 0.0, float(o["pos_m"][1]))
		w.objects.append(o)
		var key := Vector2i(floori(o["position"].x / BUCKET_M), floori(o["position"].z / BUCKET_M))
		if not w._by_bucket.has(key):
			w._by_bucket[key] = []
		w._by_bucket[key].append(w.objects.size() - 1)
	return w


func in_radius(center: Vector3, radius_m: float, filter: Callable = Callable()) -> Array:
	var out := []
	var r := int(ceil(radius_m / BUCKET_M))
	var c := Vector2i(floori(center.x / BUCKET_M), floori(center.z / BUCKET_M))
	for dx in range(-r, r + 1):
		for dz in range(-r, r + 1):
			for i in _by_bucket.get(c + Vector2i(dx, dz), []):
				var o: Dictionary = objects[i]
				if o["position"].distance_to(center) <= radius_m and (not filter.is_valid() or filter.call(o)):
					out.append(o)
	return out


func nearest(center: Vector3, radius_m: float, filter: Callable) -> Dictionary:
	var best := {}
	var best_d := INF
	for o in in_radius(center, radius_m, filter):
		var d: float = o["position"].distance_to(center)
		if d < best_d:
			best_d = d
			best = o
	return best


static func is_tree(o: Dictionary) -> bool:
	return o["meaning"].get("kind", "") == "tree"
