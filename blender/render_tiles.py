"""Renders the forest terrain atlas for a Godot 4 TileMapLayer (Match Corners and Sides).

Windows only. From the repo root in PowerShell:
    .\blender\render_all.ps1            (runs every render step in order)
or just this step:
    blender -b --factory-startup -P blender\render_tiles.py

Outputs
  renders/tiles/forest_atlas.png    the atlas, TILES_PER_ROW tiles wide
  renders/tiles/forest_atlas.json   per atlas cell: terrain, peering bits, probability, meaning

Terrain set (one set, MATCH_CORNERS_AND_SIDES):
  0 forest_floor   1 water   2 path   3 grass
Transitions exist only between forest_floor and each of the others (47-tile blob each),
so paint a ring of forest floor between water/path/grass when they would otherwise touch.

How seams stay perfect: each blob tile's shape is a signed-distance field S built from its
8 neighbour bits. Bands, notches and corners are defined so two tiles that share an edge
compute identical S along it (edge wobble uses 1-periodic functions), and every texture is
tile-periodic (see build_scene.torus). Variants differ only in the tile interior.
"""
import json
import math
import os
import sys
from itertools import product

import bpy
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import build_scene as bs  # noqa: E402

TILE_PX = bs.TILE_PX                 # 64 — change it in build_scene.py
TILES_PER_ROW = 16
MARGIN = 0.125                       # plane/field extends past the tile so AA filtering sees real terrain
FIELD_RES = 128                      # resolution of the S field image over [-MARGIN, 1+MARGIN]
BASE_VARIANTS = 4                    # variants of each full water/path/grass tile
FLOOR_VARIANTS = 6                   # forest floor covers most of the map: more variants, less repetition
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "renders", "tiles")
PARTS = os.path.join(OUT, "_parts")

TERRAINS = {0: "forest_floor", 1: "water", 2: "path", 3: "grass"}
PAIRS = [1, 2, 3]                    # each paired with forest_floor (0)
BANK_W = 0.075                       # mud bank width (in tiles) between floor and water

# Bit order used everywhere below.
BITS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
GODOT_NEIGHBOR = {                   # names of TileSet.CellNeighbor constants
    "N": "TOP_SIDE", "NE": "TOP_RIGHT_CORNER", "E": "RIGHT_SIDE", "SE": "BOTTOM_RIGHT_CORNER",
    "S": "BOTTOM_SIDE", "SW": "BOTTOM_LEFT_CORNER", "W": "LEFT_SIDE", "NW": "TOP_LEFT_CORNER",
}

# Machine-readable meaning of each terrain (world truth + what it looks like). Wren never
# reads `truth`; perception turns `appearance` into percepts (docs/architecture/05 §2).
TERRAIN_MEANING = {
    "forest_floor": {"walkable": True, "move_cost": 1.2, "truth": {"surface": "leaf_litter"},
                     "appearance": {"look": ["leaf litter", "moss patches", "dark soil"]}},
    "water": {"walkable": False, "move_cost": None, "truth": {"surface": "water", "fishable": True,
              "potability": "unknown_untreated"},
              "appearance": {"look": ["water", "ripples"], "inspect": ["clear near the edge", "dark where deep"]}},
    "path": {"walkable": True, "move_cost": 0.8, "truth": {"surface": "packed_dirt", "worn_by": "animals"},
             "appearance": {"look": ["bare packed dirt", "narrow worn track"]}},
    "grass": {"walkable": True, "move_cost": 1.0, "truth": {"surface": "grass"},
              "appearance": {"look": ["open grass", "sunlit clearing"]}},
}


# --------------------------------------------------------------------------- blob logic

def blob_configs():
    """The 47 neighbour configurations where a corner only counts if both its sides do."""
    out = []
    for bits in product((0, 1), repeat=8):
        b = dict(zip(BITS, bits))
        ok = all(not b[c] or (b[s1] and b[s2]) for c, s1, s2 in
                 (("NE", "N", "E"), ("SE", "S", "E"), ("SW", "S", "W"), ("NW", "N", "W")))
        if ok:
            out.append(b)
    assert len(out) == 47, len(out)
    out.sort(key=lambda b: (sum(b[s] for s in "NESW"), [b[k] for k in BITS]))
    return out


D0 = 0.25                            # band width at tile corners (fixed: makes every variant fit)
EDGE_VARIANTS = 2                    # random shoreline curves per edge tile


def edge_profile(t, a):
    """Band width along one tile edge. Pinned to D0 with zero slope at both corners
    (t = 0 and t = 1), so any variant meets any neighbour; free to meander in between."""
    bump = np.sin(math.pi * t)
    return np.clip(D0 + bump * (a[0] * np.sin(math.pi * t) + a[1] * np.sin(2 * math.pi * t)
                                + a[2] * np.sin(3 * math.pi * t)), 0.06, 0.46)


def edge_params(rng):
    """Random curve for each of the four edges of one tile variant."""
    return {e: (rng.uniform(-0.17, 0.17), rng.uniform(-0.08, 0.08), rng.uniform(-0.04, 0.04))
            for e in "NESW"}


def smin(a, b, k=0.22):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k=0.22):
    return -smin(-a, -b, k)


def s_field(b, edges=None, res=FIELD_RES):
    """Signed distance into the tile's own terrain (positive = inside). Rows go south -> north.
    edges: per-edge curve parameters from edge_params(); None = straight bands at D0."""
    edges = edges or {e: (0.0, 0.0, 0.0) for e in "NESW"}
    coords = np.linspace(-MARGIN, 1 + MARGIN, res)
    u, v = np.meshgrid(coords, coords)            # v increases with row index (north)
    d = {"N": edge_profile(u, edges["N"]), "S": edge_profile(u, edges["S"]),
         "E": edge_profile(v, edges["E"]), "W": edge_profile(v, edges["W"])}
    comps = []
    if not b["N"]: comps.append((1 - v) - d["N"])
    if not b["S"]: comps.append(v - d["S"])
    if not b["E"]: comps.append((1 - u) - d["E"])
    if not b["W"]: comps.append(u - d["W"])
    for c, sx, sy in (("NE", "E", "N"), ("NW", "W", "N"), ("SE", "E", "S"), ("SW", "W", "S")):
        if b[sx] and b[sy] and not b[c]:
            dx = (1 - u) if sx == "E" else u
            dy = (1 - v) if sy == "N" else v
            comps.append(smax(dx - d[sx], dy - d[sy]))
    s = np.full(u.shape, 1.0)
    for c in comps:
        s = smin(s, c)
    return np.minimum(s, 1.0)


def peering(b, center, other=0):
    return {GODOT_NEIGHBOR[k]: (center if b[k] else other) for k in BITS}


# --------------------------------------------------------------------------- Blender side

def field_image(name, s):
    img = bpy.data.images.get(name) or bpy.data.images.new(name, s.shape[1], s.shape[0],
                                                             alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    rgba = np.zeros((s.shape[0], s.shape[1], 4), dtype=np.float32)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = s
    rgba[..., 3] = 1.0
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    return img


def tile_plane():
    mesh = bpy.data.meshes.new("TilePlane")
    lo, hi = -MARGIN, 1 + MARGIN
    mesh.from_pydata([(lo, lo, 0), (hi, lo, 0), (hi, hi, 0), (lo, hi, 0)], [], [(0, 1, 2, 3)])
    uv = mesh.uv_layers.new(name="UVMap")
    for loop, co in zip(uv.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = co
    obj = bpy.data.objects.new("Tile", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def interior_window(N, pos):
    """0 at the tile border, 1 in the middle: variants only change the interior."""
    sep = N.new('ShaderNodeSeparateXYZ')
    N.link(pos, sep.inputs[0])
    x, y = sep.outputs['X'], sep.outputs['Y']
    m = N.math('MINIMUM', N.math('MINIMUM', x, N.math('SUBTRACT', 1.0, x)),
               N.math('MINIMUM', y, N.math('SUBTRACT', 1.0, y)))
    return N.smooth(0.0, 0.14, m)


def variant_switch(N, pos, window):
    """Crisp, ragged switch from the canonical pattern (edges) to the variant (interior).
    A hard-ish switch keeps leaves and pebbles whole; a soft crossfade would smear them."""
    wobble = N.math('MULTIPLY', N.math('SUBTRACT', N.pnoise(pos, 9.0, 2.0, 0.5, seed=88.0), 0.5), 0.7)
    return N.smooth(0.47, 0.53, N.math('ADD', window, wobble))


def surface(N, fn, pos, variant, window, *extra):
    """fn() at the canonical seed near edges, the variant's seed in the interior."""
    c0, h0 = fn(N, pos, *extra, seed=0.0) if extra else fn(N, pos, seed=0.0)
    if variant == 0:
        return c0, h0
    cv, hv = fn(N, pos, *extra, seed=float(variant) * 13.0) if extra else fn(N, pos, seed=float(variant) * 13.0)
    sw = variant_switch(N, pos, window)
    return N.mix_rgb(sw, c0, cv), N.math('ADD', N.math('MULTIPLY', h0, N.math('SUBTRACT', 1.0, sw)),
                                       N.math('MULTIPLY', hv, sw))


def tile_material(pair, img, variant):
    mat = bpy.data.materials.new(f"tile_{pair}_{variant}")
    N = bs.Nodes(mat)
    pos = N.position()
    window = interior_window(N, pos)
    tex = N.new('ShaderNodeTexImage', interpolation='Linear', extension='EXTEND')
    tex.image = img
    uvn = N.new('ShaderNodeUVMap')
    N.link(uvn.outputs['UV'], tex.inputs['Vector'])
    s_raw = tex.outputs['Color']
    s_val = N.math('ADD', s_raw, 0.0)                      # colour -> float
    jitter = N.math('MULTIPLY', N.math('SUBTRACT', N.pnoise(pos, 5.0, 3.0, 0.55, seed=77.0), 0.5), 0.1)
    s = N.math('ADD', s_val, jitter)

    floor_c, floor_h = surface(N, bs.forest_floor, pos, variant, window)
    rough = None
    if pair == 1:
        mud_c, mud_h = surface(N, bs.mud_bank, pos, variant, window)
        depth = N.smooth(BANK_W + 0.03, 0.45, s)
        wat_c, wat_h = water_surface(N, pos, variant, window, depth)
        wet = N.smooth(-0.09, 0.0, s)
        bank = N.smooth(-0.01, 0.02, s)
        wmask = N.smooth(BANK_W, BANK_W + 0.035, s)
        col = N.mul_rgb(floor_c, N.math('SUBTRACT', 1.0, N.math('MULTIPLY', wet, 0.3)))
        col = N.mix_rgb(bank, col, mud_c)
        col = N.mix_rgb(wmask, col, wat_c)
        level = N.math('MULTIPLY', N.smooth(0.0, BANK_W + 0.12, s), -1.0)
        detail = N.math('ADD', N.math('MULTIPLY', floor_h, N.math('SUBTRACT', 1.0, bank)),
                        N.math('MULTIPLY', mud_h, bank))
        rough = N.math('SUBTRACT', 0.88, N.math('MULTIPLY', wmask, 0.55))   # wet but not mirror-like: no hot glints
    elif pair == 2:
        path_c, path_h = surface(N, bs.dirt_path, pos, variant, window)
        edge = N.math('MULTIPLY', N.math('SUBTRACT', N.pnoise(pos, 14.0, 2.0, 0.5, seed=78.0), 0.5), 0.09)
        pmask = N.smooth(-0.015, 0.02, N.math('ADD', s, edge))
        litter_on_path = N.math('MULTIPLY', N.smooth(0.12, 0.0, s), 0.45)
        col = N.mix_rgb(pmask, floor_c, N.mix_rgb(litter_on_path, path_c, floor_c))
        level = N.math('MULTIPLY', pmask, -0.25)
        detail = N.math('ADD', N.math('MULTIPLY', floor_h, N.math('SUBTRACT', 1.0, pmask)),
                        N.math('MULTIPLY', path_h, pmask))
    else:
        grass_c, grass_h = surface(N, bs.clearing_grass, pos, variant, window)
        creep = N.math('MULTIPLY', N.math('SUBTRACT', N.pnoise(pos, 20.0, 2.0, 0.6, seed=79.0), 0.5), 0.16)
        gmask = N.smooth(-0.03, 0.05, N.math('ADD', s, creep))
        col = N.mix_rgb(gmask, floor_c, grass_c)
        level = N.math('MULTIPLY', gmask, 0.12)
        detail = N.math('ADD', N.math('MULTIPLY', floor_h, N.math('SUBTRACT', 1.0, gmask)),
                        N.math('MULTIPLY', grass_h, gmask))
    height = N.math('ADD', N.math('MULTIPLY', level, 0.6), N.math('MULTIPLY', detail, 0.08))
    col = N.dapple(col, pos)
    p = N.principled(col, normal=N.bump(height, strength=0.55, distance=0.12))
    if rough is not None:
        N.link(rough, p.inputs['Roughness'])
    return mat


def water_surface(N, pos, variant, window, depth):
    c0, h0 = bs.water(N, pos, depth, seed=0.0)
    if variant == 0:
        return c0, h0
    cv, _ = bs.water(N, pos, depth, seed=float(variant) * 13.0)
    return N.mix_rgb(window, c0, cv), h0          # water has no small shapes: a soft blend is right


def render_tile(obj, pair, s, variant, path):
    img = field_image("S", s)
    old = obj.data.materials[:]
    mat = tile_material(pair, img, variant)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for m in old:
        bpy.data.materials.remove(m)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def read_png(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)                      # rows bottom -> top


def main():
    os.makedirs(PARTS, exist_ok=True)
    bs.reset_scene()
    bpy.context.scene.render.film_transparent = False   # tiles are opaque
    bs.camera(0.5, 0.5, 1.0, px_per_unit=TILE_PX)
    obj = tile_plane()
    configs = blob_configs()
    quick = os.environ.get("TILES_QUICK")           # e.g. "12": only the first N blob configs per pair
    cells = []                                         # (part_path, meta)

    def add(pair, b, center, variant, s, kind, probability=1.0):
        name = f"{TERRAINS[center]}_{kind}_{len(cells):03d}.png"
        path = os.path.join(PARTS, name)
        render_tile(obj, pair, s, variant, path)
        meta = {"terrain": center, "terrain_name": TERRAINS[center], "kind": kind, "variant": variant,
                "probability": probability,
                "peering": peering(b, center) if b is not None else {GODOT_NEIGHBOR[k]: center for k in BITS}}
        if b is not None:
            meta["blob_bits"] = {k: b[k] for k in BITS}
        cells.append((path, meta))
        print(f"tile {len(cells):3d}: {name}", flush=True)

    # Base forest floor: all neighbours floor. S = -1 everywhere -> pure floor.
    floor_s = np.full((FIELD_RES, FIELD_RES), -1.0)
    for v in range(FLOOR_VARIANTS):
        add(1, None, 0, v, floor_s, "base", probability=1.0)
    import random
    for pair in PAIRS:
        for i, b in enumerate(configs[:int(quick)] if quick else configs):
            if all(b.values()):
                add(pair, b, pair, 0, s_field(b), "full")
                continue
            for ev in range(EDGE_VARIANTS):
                rng = random.Random(pair * 100003 + i * 101 + ev)
                # Each edge-tile variant: its own shoreline curve and its own floor interior.
                add(pair, b, pair, 1 + (i + ev) % (FLOOR_VARIANTS - 1), s_field(b, edge_params(rng)),
                    "blob", probability=1.0)
        full_b = {k: 1 for k in BITS}
        for v in range(1, BASE_VARIANTS):                # extra variants of the full tile
            add(pair, full_b, pair, v, s_field(full_b), "full", probability=0.6)

    # Assemble the atlas (rows top -> bottom in the final image).
    n = len(cells)
    rows = math.ceil(n / TILES_PER_ROW)
    atlas = np.zeros((rows * TILE_PX, TILES_PER_ROW * TILE_PX, 4), dtype=np.float32)
    meta_out = []
    for i, (path, meta) in enumerate(cells):
        ax, ay = i % TILES_PER_ROW, i // TILES_PER_ROW
        tile = read_png(path)[::-1]                    # flip to rows top -> bottom
        atlas[ay * TILE_PX:(ay + 1) * TILE_PX, ax * TILE_PX:(ax + 1) * TILE_PX] = tile
        meta_out.append({"atlas": [ax, ay], **meta})
    img = bpy.data.images.new("forest_atlas", atlas.shape[1], atlas.shape[0], alpha=True)
    img.pixels.foreach_set(atlas[::-1].ravel())        # Blender wants rows bottom -> top
    img.filepath_raw = os.path.join(OUT, "forest_atlas.png")
    img.file_format = 'PNG'
    img.save()

    doc = {
        "tile_px": TILE_PX, "tiles_per_row": TILES_PER_ROW, "rows": rows,
        "world_metres_per_tile": bs.WORLD_METRES_PER_TILE,
        "terrain_set": {"mode": "MATCH_CORNERS_AND_SIDES", "terrains": [
            {"id": k, "name": v, **TERRAIN_MEANING[v]} for k, v in TERRAINS.items()]},
        "neighbor_names": "TileSet.CellNeighbor constant names, without the CELL_NEIGHBOR_ prefix",
        "transitions": "forest_floor <-> water (mud bank), forest_floor <-> path, forest_floor <-> grass",
        "lighting": {"sun_tilt_deg": bs.SUN_TILT_DEG, "sun_azimuth_deg": bs.SUN_AZIMUTH_DEG,
                     "note": "light from the north-west; shadows fall south-east"},
        "cells": meta_out,
    }
    with open(os.path.join(OUT, "forest_atlas.json"), "w") as f:
        json.dump(doc, f, indent=1)
    print(f"ATLAS_OK {n} tiles, {TILES_PER_ROW}x{rows}", flush=True)


if __name__ == "__main__":
    main()
