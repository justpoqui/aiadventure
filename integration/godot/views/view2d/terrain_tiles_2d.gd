class_name TerrainTiles2D
extends TileMapLayer
## Draws SimTerrain with the pre-rendered forest tiles. A cell of terrain T takes the blob
## tile whose side bits are "neighbour is T" and whose corner bits are "corner is T and both
## adjacent sides are T" (the same rule as Godot's terrain painter and render_preview.py).
## The map edge counts as T, so no shoreline is drawn along the border.

const BITS := ["TOP_SIDE", "TOP_RIGHT_CORNER", "RIGHT_SIDE", "BOTTOM_RIGHT_CORNER",
		"BOTTOM_SIDE", "BOTTOM_LEFT_CORNER", "LEFT_SIDE", "TOP_LEFT_CORNER"]
const SIDE_D := {"TOP_SIDE": Vector2i(0, -1), "RIGHT_SIDE": Vector2i(1, 0),
		"BOTTOM_SIDE": Vector2i(0, 1), "LEFT_SIDE": Vector2i(-1, 0)}
const CORNERS := {"TOP_RIGHT_CORNER": ["TOP_SIDE", "RIGHT_SIDE", Vector2i(1, -1)],
		"BOTTOM_RIGHT_CORNER": ["BOTTOM_SIDE", "RIGHT_SIDE", Vector2i(1, 1)],
		"BOTTOM_LEFT_CORNER": ["BOTTOM_SIDE", "LEFT_SIDE", Vector2i(-1, 1)],
		"TOP_LEFT_CORNER": ["TOP_SIDE", "LEFT_SIDE", Vector2i(-1, -1)]}

var _options: Dictionary = {}   # key -> Array of [atlas Vector2i, probability]


func show_terrain(terrain: SimTerrain, atlas_png: String, atlas_json: String) -> void:
	tile_set = ForestTileSet.build(atlas_png, atlas_json)
	_index(atlas_json)
	var tid := func(cx: int, cz: int) -> int:
		if cx < 0 or cz < 0 or cx >= terrain.width or cz >= terrain.depth:
			return -1
		return SimTerrain.TILE_TERRAIN[terrain.at_cell(cx, cz)]
	for cz in terrain.depth:
		for cx in terrain.width:
			var t: int = tid.call(cx, cz)
			set_cell(Vector2i(cx, cz), ForestTileSet.SOURCE_ID, _pick(_key_for(cx, cz, t, tid), cx, cz))


func _key_for(cx: int, cz: int, t: int, tid: Callable) -> int:
	if t == 0:
		return 0
	var bits := {}
	for s in SIDE_D:
		var n: int = tid.call(cx + SIDE_D[s].x, cz + SIDE_D[s].y)
		bits[s] = n == -1 or n == t
	for c in CORNERS:
		var spec: Array = CORNERS[c]
		var n: int = tid.call(cx + spec[2].x, cz + spec[2].y)
		bits[c] = bits[spec[0]] and bits[spec[1]] and (n == -1 or n == t)
	var mask := 0
	for i in BITS.size():
		if bits[BITS[i]]:
			mask |= 1 << i
	return t * 256 + mask


func _index(atlas_json: String) -> void:
	var meta = JSON.parse_string(FileAccess.get_file_as_string(atlas_json))
	_options.clear()
	for c in meta["cells"]:
		var t := int(c["terrain"])
		var key := 0
		if t != 0:
			var mask := 0
			for i in BITS.size():
				if int(c["peering"][BITS[i]]) == t:
					mask |= 1 << i
			key = t * 256 + mask
		if not _options.has(key):
			_options[key] = []
		_options[key].append([Vector2i(int(c["atlas"][0]), int(c["atlas"][1])), float(c["probability"])])


## Stable per-cell variant choice weighted by probability (same world -> same look).
func _pick(key: int, cx: int, cz: int) -> Vector2i:
	var opts: Array = _options[key]
	var total := 0.0
	for o in opts:
		total += o[1]
	var r := float(((cx * 73856093) ^ (cz * 19349663)) % 10007) / 10007.0 * total
	for o in opts:
		r -= o[1]
		if r <= 0.0:
			return o[0]
	return opts[-1][0]
