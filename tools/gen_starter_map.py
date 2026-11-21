"""Generates the STARTER terrain map once. After that, the PNG is the source of truth:
edit it by hand in any image editor (one pixel = one 2 m cell).

    python tools/gen_starter_map.py --out godot/world/map/terrain_map.png
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

# Legend — must match SimTerrain.LEGEND in godot/sim/terrain/sim_terrain.gd
GRASS = (100, 170, 70)
FOREST = (40, 110, 50)
WATER = (50, 100, 180)
TRAIL = (160, 120, 70)
ROCK = (128, 128, 128)
GRAVEL = (200, 200, 190)
BRIDGE = (120, 70, 30)

W, H = 160, 120   # cells (2 m each) -> 320 m x 240 m


def smooth_noise(rng, w, h, cells):
    g = rng.random((cells + 2, cells + 2))
    ys, xs = np.linspace(0, cells, h), np.linspace(0, cells, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    fy, fx = ys - y0, xs - x0
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
    a = g[np.ix_(y0, x0)] * (1 - fx) + g[np.ix_(y0, x0 + 1)] * fx
    b = g[np.ix_(y0 + 1, x0)] * (1 - fx) + g[np.ix_(y0 + 1, x0 + 1)] * fx
    return a * (1 - fy)[:, None] + b * fy[:, None]


def disc(m, cx, cy, r, value):
    yy, xx = np.ogrid[:H, :W]
    m[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = value


def path(m, pts, width, value, rng):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        steps = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
        for t in np.linspace(0, 1, steps):
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            disc(m, x + rng.normal(0, 0.15), y + rng.normal(0, 0.15), width / 2, value)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    m = np.zeros((H, W), dtype=np.int8)   # 0 grass 1 forest 2 water 3 trail 4 rock 5 gravel 6 bridge

    # Forest: dense in the west and along the edges, thinning toward the town.
    dens = smooth_noise(rng, W, H, 10) * 0.6 + smooth_noise(rng, W, H, 24) * 0.4
    xs = np.arange(W)[None, :]
    bias = np.clip(1.0 - (xs - 40) / 90.0, 0.15, 1.0)
    m[dens * bias > 0.36] = 1
    edge = np.zeros((H, W), bool)
    edge[:6, :] = edge[-6:, :] = edge[:, :5] = edge[:, -5:] = True
    m[edge & (dens > 0.25)] = 1

    # Campsite clearing and town ground first (they remove forest).
    disc(m, 35, 70, 9, 0)
    town = np.zeros((H, W), bool)
    yy, xx = np.ogrid[:H, :W]
    town[((xx - 134) / 22.0) ** 2 + ((yy - 60) / 26.0) ** 2 <= 1] = True
    m[town & (m == 1)] = 0

    # Trail: campsite -> river -> town. Drawn before the river, which then cuts through it.
    path(m, [(39, 69), (52, 67), (64, 62), (80, 63), (96, 63), (110, 61), (118, 60)], 2.2, 3, rng)
    m[58:62, 114:156] = 5          # main street
    m[38:84, 131:135] = 5          # cross street

    # River running north-south, meandering, and a pond in the north-west.
    river = np.zeros((H, W), bool)
    for y in range(H):
        cx = 92 + 6 * np.sin(y / 14.0) + 3 * np.sin(y / 5.3)
        w = 3.2 + 1.2 * np.sin(y / 9.0)
        river[y, int(cx - w):int(cx + w) + 1] = True
    m[river] = 2
    disc(m, 24, 22, 7, 2)
    disc(m, 29, 25, 5, 2)

    # Bridge: wherever the river cuts the trail rows, plus a 1-cell overhang onto each bank.
    rows = (62, 63, 64)
    left = min(np.where(river[y])[0].min() for y in rows) - 1
    right = max(np.where(river[y])[0].max() for y in rows) + 1
    m[rows[0]:rows[-1] + 1, left:right + 1] = 6        # one clean rectangle

    # Rock outcrops (impassable).
    for (x, y, r) in [(58, 30, 3), (61, 33, 2), (70, 95, 3), (12, 90, 2.5), (104, 18, 3), (100, 104, 2.5)]:
        disc(m, x, y, r, 4)

    colors = np.array([GRASS, FOREST, WATER, TRAIL, ROCK, GRAVEL, BRIDGE], dtype=np.uint8)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(colors[m]).save(out)
    print(f"map {W}x{H} cells written to {out}; campsite centre cell (35, 70) = ({35*2}, {70*2}) m")


if __name__ == "__main__":
    main()
