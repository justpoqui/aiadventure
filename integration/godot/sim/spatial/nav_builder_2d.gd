class_name NavBuilder2D
## Builds the 2D navigation mesh from world truth: water is impassable (except the bridge
## deck), and objects that block movement (trunks, rocks, logs, buildings) are obstacles.
## (A NavBuilder3D will do the same from the same truth later.)


static func build(terrain: SimTerrain, objects: WorldObjects, region: NavigationRegion2D,
		agent_radius_m: float = 0.3) -> void:
	var ppm := SimUnits.PIXELS_PER_METRE
	var cell_px := terrain.cell_m * ppm
	var poly := NavigationPolygon.new()
	poly.agent_radius = agent_radius_m * ppm
	var src := NavigationMeshSourceGeometryData2D.new()
	var size := SimUnits.to_screen(terrain.size_m())
	src.add_traversable_outline(PackedVector2Array([Vector2.ZERO, Vector2(size.x, 0), size, Vector2(0, size.y)]))
	# Terrain: one rectangle per horizontal run of blocked cells.
	for cz in terrain.depth:
		var cx := 0
		while cx < terrain.width:
			if terrain.is_walkable_cell(cx, cz):
				cx += 1
				continue
			var start := cx
			while cx < terrain.width and not terrain.is_walkable_cell(cx, cz):
				cx += 1
			src.add_obstruction_outline(_rect(Vector2(start * cell_px, cz * cell_px), Vector2(cx * cell_px, (cz + 1) * cell_px)))
	# Objects.
	for o in objects.objects:
		if not o["blocks_movement"]:
			continue
		var c := SimUnits.to_screen(o["position"])
		var fp: Dictionary = o["footprint"]
		if fp.has("trunk_radius_m"):
			src.add_obstruction_outline(_circle(c, float(fp["trunk_radius_m"]) * ppm))
		elif fp.has("rect_m"):
			var half := Vector2(float(fp["rect_m"][0]), float(fp["rect_m"][1])) * ppm / 2.0
			src.add_obstruction_outline(_rect(c - half, c + half))
		elif fp.has("length_m"):
			# Fallen log: angle is counter-clockwise from east with north up; screen y points south.
			var ang := -deg_to_rad(float(fp.get("angle_deg", 0.0)))
			var half_len := float(fp["length_m"]) * ppm / 2.0
			var half_w := float(fp.get("width_m", 0.6)) * ppm / 2.0
			var along := Vector2(cos(ang), sin(ang))
			var across := Vector2(-along.y, along.x)
			src.add_obstruction_outline(PackedVector2Array([
					c - along * half_len - across * half_w, c + along * half_len - across * half_w,
					c + along * half_len + across * half_w, c - along * half_len + across * half_w]))
		elif fp.has("radius_m"):
			src.add_obstruction_outline(_circle(c, float(fp["radius_m"]) * 0.7 * ppm))
	NavigationServer2D.bake_from_source_geometry_data(poly, src)
	region.navigation_polygon = poly


static func _rect(a: Vector2, b: Vector2) -> PackedVector2Array:
	return PackedVector2Array([a, Vector2(b.x, a.y), b, Vector2(a.x, b.y)])


static func _circle(c: Vector2, r: float, n: int = 8) -> PackedVector2Array:
	var pts := PackedVector2Array()
	for i in n:
		var a := TAU * i / n
		pts.append(c + Vector2(cos(a), sin(a)) * r)
	return pts
