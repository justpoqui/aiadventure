class_name SimTerrain
extends RefCounted
## WORLD TRUTH: what the ground is, per 2 m cell, read from world_data/terrain.txt
## (one character per cell; see LEGEND). Dimension-agnostic: positions are sim metres.

enum T { FOREST_FLOOR, WATER, PATH, GRASS, BRIDGE }

const LEGEND := {".": T.FOREST_FLOOR, "~": T.WATER, "=": T.PATH, ",": T.GRASS, "B": T.BRIDGE}
const WALKABLE := {T.FOREST_FLOOR: true, T.WATER: false, T.PATH: true, T.GRASS: true, T.BRIDGE: true}
const NAMES := {T.FOREST_FLOOR: "forest_floor", T.WATER: "water", T.PATH: "path", T.GRASS: "grass", T.BRIDGE: "bridge"}
## Terrain ids in the tile atlas (forest_atlas.json). A bridge deck has water underneath.
const TILE_TERRAIN := {T.FOREST_FLOOR: 0, T.WATER: 1, T.PATH: 2, T.GRASS: 3, T.BRIDGE: 1}

var cell_m: float = 2.0
var width: int = 0     # cells along x (east)
var depth: int = 0     # cells along z (south)
var _cells := PackedByteArray()


static func load_from(path: String, cell_size_m: float) -> SimTerrain:
	var text := FileAccess.get_file_as_string(path)
	assert(text != "", "terrain map not found or empty: " + path)
	var rows := PackedStringArray()
	for line in text.replace("\r\n", "\n").split("\n"):
		if line.strip_edges() != "":
			rows.append(line.strip_edges())
	var t := SimTerrain.new()
	t.cell_m = cell_size_m
	t.width = rows[0].length()
	t.depth = rows.size()
	t._cells.resize(t.width * t.depth)
	for cz in t.depth:
		var row: String = rows[cz]
		assert(row.length() == t.width, "terrain.txt row %d has %d chars, expected %d" % [cz, row.length(), t.width])
		for cx in t.width:
			t._cells[cz * t.width + cx] = LEGEND.get(row[cx], T.FOREST_FLOOR)
	return t


## Out of bounds counts as WATER: the world edge is not walkable.
func at_cell(cx: int, cz: int) -> int:
	if cx < 0 or cz < 0 or cx >= width or cz >= depth:
		return T.WATER
	return _cells[cz * width + cx]


func at(pos: Vector3) -> int:
	return at_cell(floori(pos.x / cell_m), floori(pos.z / cell_m))


func is_walkable_cell(cx: int, cz: int) -> bool:
	return WALKABLE[at_cell(cx, cz)]


func is_walkable(pos: Vector3) -> bool:
	return WALKABLE[at(pos)]


func cell_of(pos: Vector3) -> Vector3i:
	return Vector3i(floori(pos.x / cell_m), 0, floori(pos.z / cell_m))


func cell_center(cx: int, cz: int) -> Vector3:
	return Vector3((cx + 0.5) * cell_m, 0.0, (cz + 0.5) * cell_m)


func size_m() -> Vector3:
	return Vector3(width * cell_m, 0.0, depth * cell_m)
