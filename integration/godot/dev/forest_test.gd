extends Node
## Headless behaviour test for the forest world.

func _animals() -> Array:
	var out := []
	for e in WorldRegistry.all():
		if e is Animal: out.append(e)
	return out

func _habitat_ok(a: Animal) -> bool:
	var t := Spatial.terrain.at(a.sim_position)
	if a.species == "fish": return t == SimTerrain.T.WATER
	if a.species == "bird" or a.species == "frog": return true      # birds fly; frogs dive into water
	return SimTerrain.WALKABLE[t]

func _ready():
	await Spatial.nav_ready
	await get_tree().process_frame
	var agent: AgentBody
	for e in WorldRegistry.all():
		if e is AgentBody: agent = e
	# 1. Navigation: campsite -> town square must cross the bridge and avoid water and buildings.
	var path := Spatial.nav.path(Vector3(70, 0, 140), Vector3(256, 0, 130))
	var wet := 0; var bridge := 0; var inside_building := 0; var length := 0.0
	var buildings := Spatial.objects.objects.filter(func(o): return o["layer"] == "building")
	for i in range(1, path.size()):
		length += path[i-1].distance_to(path[i])
		var n := int(path[i-1].distance_to(path[i]) / 0.5) + 1
		for s in n:
			var p := path[i-1].lerp(path[i], float(s) / n)
			var t := Spatial.terrain.at(p)
			if t == SimTerrain.T.WATER: wet += 1
			if t == SimTerrain.T.BRIDGE: bridge += 1
			for b in buildings:
				var half := Vector3(float(b["footprint"]["rect_m"][0]) / 2, 0, float(b["footprint"]["rect_m"][1]) / 2)
				var d: Vector3 = (p - b["position"]).abs()
				if d.x < half.x - 0.1 and d.z < half.z - 0.1: inside_building += 1
	print("NAV campsite->town: points=%d length=%.0fm water_samples=%d bridge_samples=%d inside_building_samples=%d" % [path.size(), length, wet, bridge, inside_building])
	# 2. Let the world run 6 game hours (dawn activity) and check habitats.
	print("ANIMALS: %d" % _animals().size())
	if CmdArgs.all().has("fear-only"):
		await _fear(agent)
		return
	SimClock.tick = 5 * 60
	SimClock.speed = 4.0
	var start_pos := {}
	for a in _animals(): start_pos[a] = a.sim_position
	await get_tree().create_timer(90.0).timeout
	var bad := []; var moved := 0; var states := {}
	for a in _animals():
		if not _habitat_ok(a): bad.append("%s at %s (%s)" % [a.entity_id, a.sim_position, SimTerrain.NAMES[Spatial.terrain.at(a.sim_position)]])
		if a.sim_position.distance_to(start_pos[a]) > 1.0: moved += 1
		states[a.state] = states.get(a.state, 0) + 1
	print("AFTER %.1f game hours (now %02d:00): moved=%d/%d  out_of_habitat=%d  states=%s" % [
		(SimClock.tick - 300) / 60.0, (SimClock.tick % 1440) / 60, moved, _animals().size(), bad.size(), states])
	for b in bad.slice(0, 5): print("   ", b)
	await _fear(agent)


func _fear(agent: AgentBody) -> void:
	# 3. Fear: freeze the survivor right next to each kind of animal and watch the reaction.
	agent.get_node("Locomotion").stop()
	SimClock.speed = 1.0
	SimClock.tick = 7 * 60
	for sp in ["deer", "rabbit", "squirrel", "frog", "fish", "bird"]:
		var a: Animal = null
		for x in _animals():
			if x.species == sp and x.state != "hide": a = x; break
		if a == null: print("FEAR %s: none available" % sp); continue
		var r := float(a.cfg["flee_radius_m"])
		var spot := a.sim_position + Vector3(r * 0.4, 0, 0)
		agent.get_node("Locomotion").stop()
		agent.sim_position = spot
		var seen := {}
		for i in 30:                                   # 30 frames = 30 game seconds at 1x
			await get_tree().physics_frame
			seen[a.state] = true
		print("FEAR %-8s flee_radius=%4.1fm  states seen=%s  now=%-5s hidden=%-5s  %4.1fm -> %4.1fm from the survivor" % [
			sp, r, seen.keys(), a.state, a.hidden, r * 0.4, a.sim_position.distance_to(spot)])
		agent.sim_position = Vector3(70, 0, 140)
		for i in 5: await get_tree().physics_frame
	print("FOREST_TEST_DONE")
	get_tree().quit()
