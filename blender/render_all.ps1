# Renders the whole forest world on Windows: tiles, then object sprites, then wildlife.
# Usage (PowerShell, from the repo root):   .\blender\render_all.ps1
# Optional:                                  .\blender\render_all.ps1 -Blender "D:\Blender\blender.exe"
param([string]$Blender = "")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

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
Write-Host "Using $Blender"
& $Blender --version | Select-Object -First 1

foreach ($dir in "renders\tiles", "renders\sprites", "renders\wildlife", "renders\preview", "world_data") {
    New-Item -ItemType Directory -Force -Path (Join-Path $root $dir) | Out-Null
}

$steps = "render_tiles.py", "render_objects.py", "render_wildlife.py"
foreach ($step in $steps) {
    $script = Join-Path $root "blender\$step"
    if (-not (Test-Path $script)) { Write-Host "skip $step (not written yet)"; continue }
    Write-Host "=== $step ==="
    $start = Get-Date
    & $Blender -b --factory-startup -P $script
    if ($LASTEXITCODE -ne 0) { Write-Error "$step failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
    Write-Host ("{0} done in {1:n0} s" -f $step, ((Get-Date) - $start).TotalSeconds)
}
Write-Host "All renders finished. Outputs are in renders\ and world_data\."
