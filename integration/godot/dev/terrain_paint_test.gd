extends SceneTree
## Compares our tile choice with Godot's own terrain painter (set_cells_terrain_connect),
## which is what you'd get painting by hand in the editor. Compares terrain + peering bits
## (variants with identical bits are interchangeable).

func _bits(ts: TileSet, layer: TileMapLayer, cell: Vector2i) -> String:
	var src := ts.get_source(layer.get_cell_source_id(cell)) as TileSetAtlasSource
	var td := src.get_tile_data(layer.get_cell_atlas_coords(cell), 0)
	var s := str(td.terrain) + ":"
	for nb in [TileSet.CELL_NEIGHBOR_TOP_SIDE, TileSet.CELL_NEIGHBOR_TOP_RIGHT_CORNER, TileSet.CELL_NEIGHBOR_RIGHT_SIDE,
			TileSet.CELL_NEIGHBOR_BOTTOM_RIGHT_CORNER, TileSet.CELL_NEIGHBOR_BOTTOM_SIDE, TileSet.CELL_NEIGHBOR_BOTTOM_LEFT_CORNER,
			TileSet.CELL_NEIGHBOR_LEFT_SIDE, TileSet.CELL_NEIGHBOR_TOP_LEFT_CORNER]:
		s += str(td.get_terrain_peering_bit(nb))
	return s

func _initialize():
	var terrain := SimTerrain.load_from("res://world/forest/terrain.txt", 2.0)
	var ours := TerrainTiles2D.new()
	root.add_child(ours)
	ours.show_terrain(terrain, "res://art/tiles/forest_atlas.png", "res://art/tiles/forest_atlas.json")
	var godot := TileMapLayer.new()
	godot.tile_set = ours.tile_set
	root.add_child(godot)
	var groups := {}
	for cz in terrain.depth:
		for cx in terrain.width:
			var t: int = SimTerrain.TILE_TERRAIN[terrain.at_cell(cx, cz)]
			if not groups.has(t): groups[t] = []
			groups[t].append(Vector2i(cx, cz))
	for t in [0, 1, 2, 3]:
		godot.set_cells_terrain_connect(groups.get(t, []), 0, t, false)
	var same := 0; var diff := 0; var interior_diff := 0; var examples := []
	for cz in terrain.depth:
		for cx in terrain.width:
			var c := Vector2i(cx, cz)
			var a := _bits(ours.tile_set, ours, c)
			var b := _bits(godot.tile_set, godot, c)
			if a == b: same += 1
			else:
				diff += 1
				var edge := cx == 0 or cz == 0 or cx == terrain.width - 1 or cz == terrain.depth - 1
				if not edge: interior_diff += 1
				if examples.size() < 4 and not edge: examples.append("%s ours=%s godot=%s" % [c, a, b])
	print("TERRAIN PAINT CHECK: %d cells identical, %d differ (%d away from the map border)" % [same, diff, interior_diff])
	for e in examples: print("   ", e)
	quit()
