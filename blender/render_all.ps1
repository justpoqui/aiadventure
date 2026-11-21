# Builds the whole forest world on Windows:
#   1. Blender renders: terrain tiles, object sprites, wildlife sheets
#   2. Python: lays out the world (terrain, objects, places, wildlife)
#   3. Blender: composites preview images of the finished world
#
# Usage (PowerShell, from the repo root):   .\blender\render_all.ps1
# Options:  -Blender "D:\Blender\blender.exe"   use a specific Blender
#           -Only tiles,objects                 run only some steps (tiles, objects, wildlife, world, preview)
#           -Seed 12345                         a different world layout
param([string]$Blender = "", [string[]]$Only = @(), [int]$Seed = 20261121)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
function Want($step) { return ($Only.Count -eq 0) -or ($Only -contains $step) }

# Find blender.exe: explicit argument, then PATH, then the newest default install.
if (-not $Blender) {
    $cmd = Get-Command blender.exe -ErrorAction SilentlyContinue
    if ($cmd) { $Blender = $cmd.Source }
}
if (-not $Blender) {
    $found = Get-ChildItem "C:\Program Files\Blender Foundation\Blender*\blender.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($found) { $Blender = $found.FullName }
}
if (-not $Blender) {
    Write-Error "blender.exe not found. Install it with:  winget install BlenderFoundation.Blender"
    exit 1
}
# Python for the world builder (standard library only).
$python = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
$pyArgs = @("-3")
if (-not $python) { $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source; $pyArgs = @() }

Write-Host "Blender: $Blender"
& $Blender --version | Select-Object -First 1
foreach ($dir in "renders\tiles", "renders\sprites", "renders\wildlife", "renders\preview", "world_data") {
    New-Item -ItemType Directory -Force -Path (Join-Path $root $dir) | Out-Null
}

function Run-Blender($step, $script) {
    if (-not (Want $step)) { return }
    Write-Host "=== $step ($script) ==="
    $start = Get-Date
    & $Blender -b --factory-startup -P (Join-Path $root "blender\$script")
    if ($LASTEXITCODE -ne 0) { Write-Error "$script failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
    Write-Host ("{0} done in {1:n0} s" -f $step, ((Get-Date) - $start).TotalSeconds)
}

Run-Blender "tiles" "render_tiles.py"
Run-Blender "objects" "render_objects.py"
Run-Blender "wildlife" "render_wildlife.py"

if (Want "world") {
    if (-not $python) { Write-Error "Python not found. Install it with:  winget install Python.Python.3.12"; exit 1 }
    Write-Host "=== world (build_world.py, seed $Seed) ==="
    & $python @pyArgs (Join-Path $root "world_data\build_world.py") --seed $Seed
    if ($LASTEXITCODE -ne 0) { Write-Error "build_world.py failed"; exit $LASTEXITCODE }
}

Run-Blender "preview" "render_preview.py"
Write-Host "All done. Renders: renders\   World data: world_data\   Previews: renders\preview\"
