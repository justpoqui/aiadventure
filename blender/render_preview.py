"""Composites the whole world into preview images, exactly as Godot will draw it.

Windows only. From the repo root in PowerShell (run render_all.ps1 and build_world.py first):
    blender -b --factory-startup -P blender\\render_preview.py

Outputs
  renders/preview/forest_preview.png   whole map, scaled down
  renders/preview/<place>.png          full-resolution close-ups of the named places
  renders/preview/tile_choices.json    the atlas cell chosen for every map cell (what Godot should match)

Tile choice: a cell of terrain T takes the 47-blob tile whose side bits are "neighbour is T"
and whose corner bits are "corner is T and both adjacent sides are T". The map edge counts
as T, so no banks appear along the border. Full tiles pick a variant by probability,
seeded by position so the result is stable.
"""
import json
import math
import os
import sys

import bpy
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import build_scene as bs  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TILES = os.path.join(ROOT, "renders", "tiles")
SPRITES = os.path.join(ROOT, "renders")
WORLD = os.path.join(ROOT, "world_data")
OUT = os.path.join(ROOT, "renders", "preview")
TP = bs.TILE_PX
CHAR_TERRAIN = {".": 0, "~": 1, "B": 1, "=": 2, ",": 3}
SIDES = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
CORNERS = {"NE": ("N", "E"), "SE": ("S", "E"), "SW": ("S", "W"), "NW": ("N", "W")}
CORNER_D = {"NE": (1, -1), "SE": (1, 1), "SW": (-1, 1), "NW": (-1, -1)}
BITS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
LAYER_ORDER = {"water_surface": 0, "ground": 1, "building": 2, "animal": 3, "canopy": 4}


def load_rgba(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return (px.reshape(h, w, 4)[::-1] * 255 + 0.5).astype(np.uint8)    # rows top -> bottom


def save_rgba(arr, path):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.pixels.foreach_set((arr[::-1].astype(np.float32) / 255.0).ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def resize(arr, scale):
    """Area-average downscale / bilinear-ish upscale, enough for previews and small sprites."""
    h, w = arr.shape[:2]
    nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    ys = (np.arange(nh) + 0.5) / scale - 0.5
    xs = (np.arange(nw) + 0.5) / scale - 0.5
    if scale < 1:
        f = int(round(1 / scale))
        hh, ww = (h // f) * f, (w // f) * f
        a = arr[:hh, :ww].astype(np.float32).reshape(hh // f, f, ww // f, f, -1).mean(axis=(1, 3))
        return a.astype(np.uint8)
    yi = np.clip(np.round(ys).astype(int), 0, h - 1)
    xi = np.clip(np.round(xs).astype(int), 0, w - 1)
    return arr[yi][:, xi]


def blit(dst, src, x, y):
    """Alpha-composite src onto dst with its top-left at (x, y); clips to dst."""
    h, w = src.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.shape[1], x + w), min(dst.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    d = dst[y0:y1, x0:x1].astype(np.float32)
    a = s[..., 3:4] / 255.0
    d[..., :3] = s[..., :3] * a + d[..., :3] * (1 - a)
    d[..., 3:4] = np.maximum(d[..., 3:4], s[..., 3:4])
    dst[y0:y1, x0:x1] = d.astype(np.uint8)


def choose_tiles(grid, atlas):
    h, w = len(grid), len(grid[0])
    terr = [[CHAR_TERRAIN[c] for c in row] for row in grid]
    by_key = {}
    for c in atlas["cells"]:
        if c["terrain"] == 0:
            key = (0, None)
        else:
            key = (c["terrain"], tuple(c["blob_bits"][k] for k in BITS))
        by_key.setdefault(key, []).append((tuple(c["atlas"]), c["probability"]))

    def same(x, y, t):
        return True if not (0 <= x < w and 0 <= y < h) else terr[y][x] == t

    choice = [[None] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            t = terr[y][x]
            if t == 0:
                key = (0, None)
            else:
                b = {s: int(same(x + dx, y + dy, t)) for s, (dx, dy) in SIDES.items()}
                for c, (s1, s2) in CORNERS.items():
                    dx, dy = CORNER_D[c]
                    b[c] = int(b[s1] and b[s2] and same(x + dx, y + dy, t))
                key = (t, tuple(b[k] for k in BITS))
            opts = by_key[key]
            r = ((x * 73856093) ^ (y * 19349663)) % 10007 / 10007.0 * sum(p for _, p in opts)
            for cell, p in opts:
                r -= p
                if r <= 0:
                    break
            choice[y][x] = cell
    return choice


def main():
    os.makedirs(OUT, exist_ok=True)
    bs.reset_scene()
    atlas = json.load(open(os.path.join(TILES, "forest_atlas.json")))
    atlas_img = load_rgba(os.path.join(TILES, "forest_atlas.png"))
    grid = [line.rstrip("\n") for line in open(os.path.join(WORLD, "terrain.txt")) if line.strip()]
    h, w = len(grid), len(grid[0])
    choice = choose_tiles(grid, atlas)
    with open(os.path.join(OUT, "tile_choices.json"), "w") as f:
        json.dump({"size": [w, h], "atlas_coords": choice}, f)

    canvas = np.zeros((h * TP, w * TP, 4), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            ax, ay = choice[y][x]
            canvas[y * TP:(y + 1) * TP, x * TP:(x + 1) * TP] = atlas_img[ay * TP:(ay + 1) * TP, ax * TP:(ax + 1) * TP]
    print("terrain composed", flush=True)

    sprites = {s["id"]: s for s in json.load(open(os.path.join(SPRITES, "sprites", "sprites.json")))["sprites"]}
    cache = {}
    objs = json.load(open(os.path.join(WORLD, "objects.json")))["objects"]
    draw = []
    for o in objs:
        s = sprites[o["sprite"]]
        draw.append((LAYER_ORDER[o["layer"]], o["tile"][1], "sprite", o, s))
    wild = json.load(open(os.path.join(SPRITES, "wildlife", "wildlife.json")))
    for a in json.load(open(os.path.join(WORLD, "wildlife.json")))["animals"]:
        layer = "water_surface" if a["species"] == "fish" else "animal"
        draw.append((LAYER_ORDER[layer], a["tile"][1], "animal", a, wild["species"][a["species"]]))
    draw.sort(key=lambda d: (d[0], d[1]))
    for _, _, kind, o, s in draw:
        if kind == "sprite":
            img = cache.get(s["file"])
            if img is None:
                img = cache[s["file"]] = load_rgba(os.path.join(SPRITES, s["file"]))
            ax, ay = s["anchor_px"]
            blit(canvas, img, int(round(o["tile"][0] * TP - ax)), int(round(o["tile"][1] * TP - ay)))
        else:
            key = "wild:" + o["species"]
            if key not in cache:
                sheet = load_rgba(os.path.join(SPRITES, s["sheet"]))
                frame = sheet[:, :s["frame_px"]]
                if o["species"] == "fish":
                    frame = frame.copy()
                    frame[..., 3] = (frame[..., 3] * 0.55).astype(np.uint8)   # seen through water
                cache[key] = resize(frame, s["scale"])
            img = cache[key]
            blit(canvas, img, int(o["tile"][0] * TP - img.shape[1] / 2), int(o["tile"][1] * TP - img.shape[0] / 2))
    print("objects composed", flush=True)

    save_rgba(resize(canvas, 0.25), os.path.join(OUT, "forest_preview.png"))
    places = json.load(open(os.path.join(WORLD, "places.json")))["places"]
    for p in places:
        if p["id"] not in ("campsite", "bridge", "pond", "town", "north_meadow", "stream"):
            continue
        cx, cy = p["center_tile"]
        if p["id"] == "stream":
            cy = 30
        cw, ch = 1600, 1000
        x0 = int(np.clip(cx * TP - cw / 2, 0, w * TP - cw))
        y0 = int(np.clip(cy * TP - ch / 2, 0, h * TP - ch))
        save_rgba(canvas[y0:y0 + ch, x0:x0 + cw], os.path.join(OUT, f"{p['id']}.png"))
    print("PREVIEW_OK", flush=True)


if __name__ == "__main__":
    main()
