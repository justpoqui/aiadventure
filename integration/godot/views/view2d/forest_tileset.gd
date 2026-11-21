class_name ForestTileSet
## Builds the Godot TileSet from the Blender atlas (renders/tiles/forest_atlas.png + .json):
## one terrain set in MATCH_CORNERS_AND_SIDES mode with forest_floor, water, path and grass,
## and every tile's terrain + peering bits + probability. Works at runtime, and
## save_resource() writes a .tres you can open in the TileMap editor to paint by hand.

const NEIGHBOR := {
	"TOP_SIDE": TileSet.CELL_NEIGHBOR_TOP_SIDE, "TOP_RIGHT_CORNER": TileSet.CELL_NEIGHBOR_TOP_RIGHT_CORNER,
	"RIGHT_SIDE": TileSet.CELL_NEIGHBOR_RIGHT_SIDE, "BOTTOM_RIGHT_CORNER": TileSet.CELL_NEIGHBOR_BOTTOM_RIGHT_CORNER,
	"BOTTOM_SIDE": TileSet.CELL_NEIGHBOR_BOTTOM_SIDE, "BOTTOM_LEFT_CORNER": TileSet.CELL_NEIGHBOR_BOTTOM_LEFT_CORNER,
	"LEFT_SIDE": TileSet.CELL_NEIGHBOR_LEFT_SIDE, "TOP_LEFT_CORNER": TileSet.CELL_NEIGHBOR_TOP_LEFT_CORNER,
}
const TERRAIN_COLORS := [Color("4a3520"), Color("2f5d7a"), Color("9a7448"), Color("5d8a34")]
const SOURCE_ID := 0


static func build(atlas_png: String, atlas_json: String) -> TileSet:
	var meta = JSON.parse_string(FileAccess.get_file_as_string(atlas_json))
	assert(meta is Dictionary, "cannot read " + atlas_json)
	var tp := int(meta["tile_px"])
	var ts := TileSet.new()
	ts.tile_size = Vector2i(tp, tp)
	ts.add_terrain_set()
	ts.set_terrain_set_mode(0, TileSet.TERRAIN_MODE_MATCH_CORNERS_AND_SIDES)
	for t in meta["terrain_set"]["terrains"]:
		ts.add_terrain(0)
		var i := int(t["id"])
		ts.set_terrain_name(0, i, t["name"])
		ts.set_terrain_color(0, i, TERRAIN_COLORS[i])
	var src := TileSetAtlasSource.new()
	src.texture = load(atlas_png)
	src.texture_region_size = Vector2i(tp, tp)
	ts.add_source(src, SOURCE_ID)
	for c in meta["cells"]:
		var coords := Vector2i(int(c["atlas"][0]), int(c["atlas"][1]))
		src.create_tile(coords)
		var td := src.get_tile_data(coords, 0)
		td.terrain_set = 0
		td.terrain = int(c["terrain"])
		td.probability = float(c["probability"])
		for nb in c["peering"]:
			td.set_terrain_peering_bit(NEIGHBOR[nb], int(c["peering"][nb]))
	return ts


static func save_resource(atlas_png: String, atlas_json: String, out_path: String) -> int:
	return ResourceSaver.save(build(atlas_png, atlas_json), out_path)
