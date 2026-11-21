# Godot integration for the forest world

Same folder layout as the Godot project from the Phase 0 guide: copy this folder's contents
over `godot\` (overwrite when asked). Then copy the generated content as described in
`docs\world\forest_world.md` §7.

| File | Role |
|------|------|
| `sim\terrain\sim_terrain.gd` | terrain truth from `terrain.txt` (replaces the PNG version) |
| `sim\world\world_objects.gd` | every object (truth + meaning) from `objects.json` |
| `sim\spatial\nav_builder_2d.gd` | navigation from terrain + object obstacles |
| `sim\wildlife\animal.gd`, `wildlife_system.gd` | animals and their habits |
| `sim\core\sim_units.gd` | now 32 px per metre (64 px tiles = 2 m) |
| `autoload\spatial.gd` | adds `Spatial.objects` |
| `views\view2d\forest_tileset.gd` | builds the TileSet (terrain set + peering bits) from the atlas |
| `views\view2d\terrain_tiles_2d.gd` | the TileMapLayer, filled from the terrain |
| `views\view2d\object_layer_2d.gd` | object sprites in draw order, canopy fade |
| `views\view2d\animal_view_2d.gd` | animal sprites, rotation, soft shadows |
| `world\world.gd`, `world.tscn` | loads everything; the survivor spawns at the campsite |
| `dev\forest_test.gd` | optional headless behaviour test (add to `main.tscn` temporarily) |
| `dev\terrain_paint_test.gd` | optional: compares our tiles with Godot's terrain painter. Run: `godot --headless --path godot -s res://dev/terrain_paint_test.gd` |

Also in `entities\agent\agent_body.tscn`: set **View2D → Z Index = 4**.
Delete `views\view2d\terrain_view_2d.gd`, `tree_layer_2d.gd` and `terrain.gdshader` from step 07b.
