extends Node2D
## Loads the forest world (terrain, objects, wildlife) from world_data/ and the Blender renders,
## builds navigation from it, and dresses it with the 2D views.

const DATA := "res://world/forest/"          # terrain.txt, objects.json, wildlife.json, places.json
const ART := "res://art/"                     # tiles/, sprites/, wildlife/ from renders/
const CELL_M := 2.0                           # metres per tile

@onready var _nav_region: NavigationRegion2D = $NavigationRegion2D
@onready var _tiles: TerrainTiles2D = $TerrainTiles2D
@onready var _objects_view: ObjectLayer2D = $ObjectLayer2D
@onready var _wildlife: WildlifeSystem = $WildlifeSystem


func _ready() -> void:
	var terrain := SimTerrain.load_from(DATA + "terrain.txt", CELL_M)
	var objects := WorldObjects.load_from(DATA + "objects.json")
	Spatial.terrain = terrain
	Spatial.objects = objects
	NavBuilder2D.build(terrain, objects, _nav_region)
	_tiles.show_terrain(terrain, ART + "tiles/forest_atlas.png", ART + "tiles/forest_atlas.json")
	_objects_view.populate(objects, ART + "sprites/sprites.json", ART)
	# The navigation server syncs maps in the background; a big map can take many frames,
	# and the first sync may not include our region yet. Wait until the map answers a query
	# at a spot we know is walkable, never a fixed number of frames.
	var map := get_world_2d().get_navigation_map()
	var probe := SimUnits.to_screen(_open_ground(terrain, objects))
	var frames := 0
	while true:
		await get_tree().physics_frame
		frames += 1
		if NavigationServer2D.map_get_iteration_id(map) > 0 \
				and NavigationServer2D.map_get_closest_point(map, probe).distance_to(probe) < 1.0:
			break
	Spatial.install(SimNavigation2D.new(map), SimSpatialQuery.new())
	_wildlife.populate(DATA + "wildlife.json", ART + "wildlife/wildlife.json", ART)
	print("World: %dx%d m forest, %d objects, navigation ready after %d frames" % [
		terrain.size_m().x, terrain.size_m().z, objects.objects.size(), frames])


## A cell whose whole neighbourhood is walkable and free of objects.
static func _open_ground(terrain: SimTerrain, objects: WorldObjects) -> Vector3:
	for cz in range(1, terrain.depth - 1):
		for cx in range(1, terrain.width - 1):
			var open := true
			for dz in range(-1, 2):
				for dx in range(-1, 2):
					open = open and terrain.is_walkable_cell(cx + dx, cz + dz)
			if open and objects.in_radius(terrain.cell_center(cx, cz), 3.0).is_empty():
				return terrain.cell_center(cx, cz)
	push_error("World: no open ground found")
	return Vector3.ZERO
