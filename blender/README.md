# Forest world — Blender render pipeline (Windows)

Pre-renders the top-down 2D forest Wren will live in: a terrain tile atlas for a Godot 4
`TileMapLayer` (Match Corners and Sides), object sprites, and wildlife sprites. Every
render uses the same camera, sun, sky and colour management, so seams and lighting match.

## Setup (once)

1. Install Blender:
   ```powershell
   winget install BlenderFoundation.Blender
   ```
   Blender for Windows comes with its own Python and numpy; nothing else to install.
2. Check it works (close and reopen PowerShell after installing):
   ```powershell
   blender --version
   ```
   If it isn't found, `render_all.ps1` also looks in `C:\Program Files\Blender Foundation\`,
   or pass the path: `.\blender\render_all.ps1 -Blender "D:\Blender\blender.exe"`.

## Render everything

From the repo root:
```powershell
.\blender\render_all.ps1
```
Blender runs in the background (no window) and uses your GPU for EEVEE.

| Script | Output |
|--------|--------|
| `build_scene.py` | shared scene: camera, sun, sky, AgX, procedural materials (imported by the others) |
| `render_tiles.py` | `renders\tiles\forest_atlas.png` + `forest_atlas.json` |
| `render_objects.py` | `renders\sprites\` *(coming next)* |
| `render_wildlife.py` | `renders\wildlife\` *(coming next)* |

## Conventions

- 1 Blender unit = 1 tile = 64 px = 2 m in the world.
- Camera looks straight down (rotation 0,0,0): image-up is north.
- Sun 30° off vertical from the north-west; shadows fall south-east.
- Tile size is `TILE_PX` at the top of `build_scene.py`.

## Blender versions

Written for Blender 4.0+, including 4.2+ (where EEVEE became "EEVEE Next" and some render
settings were renamed). `build_scene.py` only applies settings that exist in the running
version. **Not yet tested on 4.2+**: if a render fails, send the PowerShell output.
