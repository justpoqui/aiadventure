extends Node
## Holds the active spatial implementations (2D now, 3D later) and the world truth.
## Simulation code calls Spatial.nav / .query / .terrain / .objects and never touches 2D APIs.

signal nav_ready

var nav: SimNavigation
var query: SimSpatialQuery
var terrain: SimTerrain
var objects: WorldObjects


func install(new_nav: SimNavigation, new_query: SimSpatialQuery) -> void:
	nav = new_nav
	query = new_query
	nav_ready.emit()
