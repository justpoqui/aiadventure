"""Generates the placeholder 2D art for the world: tileable ground textures and tree canopies.
All art is procedural and original. Re-run to regenerate; swap any PNG for hand-made art later.

    python tools/gen_art.py --out godot/views/view2d/art --seed 7
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 256


def tile_noise(rng, size, cells):
    """Seamlessly tiling value noise in [0, 1]."""
    grid = rng.random((cells, cells))
    x = np.arange(size) * cells / size
    i0 = np.floor(x).astype(int) % cells
    i1 = (i0 + 1) % cells
    f = x - np.floor(x)
    f = f * f * (3 - 2 * f)
    a = grid[np.ix_(i0, i0)] * (1 - f)[None, :] + grid[np.ix_(i0, i1)] * f[None, :]
    b = grid[np.ix_(i1, i0)] * (1 - f)[None, :] + grid[np.ix_(i1, i1)] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def fbm(rng, size=SIZE, base=4, octaves=5, gain=0.5):
    total, amp, norm = np.zeros((size, size)), 1.0, 0.0
    for o in range(octaves):
        total += amp * tile_noise(rng, size, base * 2 ** o)
        norm += amp
        amp *= gain
    return total / norm


def lerp_colors(t, stops):
    """t: array in [0,1]; stops: list of (pos, (r,g,b))."""
    out = np.zeros(t.shape + (3,))
    pos = np.array([s[0] for s in stops])
    cols = np.array([s[1] for s in stops], dtype=float)
    for c in range(3):
        out[..., c] = np.interp(t, pos, cols[:, c])
    return out


def stretch(n):
    return (n - n.min()) / (n.max() - n.min() + 1e-9)


def speckle(rng, img, count, colors, radius=(0.5, 1.4), alpha=180):
    """Small soft dots (grass blades, pebbles). Drawn with wrap-around so the tile stays seamless."""
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        x, y = rng.random() * SIZE, rng.random() * SIZE
        r = rng.uniform(*radius)
        c = colors[rng.integers(len(colors))]
        for ox in (-SIZE, 0, SIZE):
            for oy in (-SIZE, 0, SIZE):
                d.ellipse([x + ox - r, y + oy - r, x + ox + r, y + oy + r], fill=c + (alpha,))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def save(img, out, name):
    img.convert("RGB").save(out / f"{name}.png")


def grass(rng):
    n = stretch(fbm(rng, base=4))
    patches = stretch(fbm(rng, base=2, octaves=3))
    col = lerp_colors(n, [(0, (38, 78, 30)), (0.5, (70, 122, 44)), (1, (112, 158, 62))])
    col = col * (0.9 + 0.2 * patches[..., None])
    col[..., 0] += 18 * (patches - 0.5)          # yellowish dry patches
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    img = speckle(rng, img, 2600, [(130, 175, 70), (50, 95, 35), (95, 145, 55)], (0.4, 1.1), 150)
    return img


def water(rng):
    n = stretch(fbm(rng, base=3, octaves=4))
    ripple = stretch(fbm(rng, base=16, octaves=3))
    col = lerp_colors(n, [(0, (62, 82, 98)), (0.6, (88, 110, 124)), (1, (112, 134, 146))])
    hi = np.clip((ripple - 0.72) * 4.0, 0, 1)[..., None]
    col = col * (1 - hi * 0.6) + np.array([205, 218, 224]) * hi * 0.6
    return Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))


def dirt(rng):
    n = stretch(fbm(rng, base=5))
    col = lerp_colors(n, [(0, (92, 66, 44)), (0.5, (128, 96, 64)), (1, (156, 122, 84))])
    img = Image.fromarray(col.astype(np.uint8))
    return speckle(rng, img, 500, [(150, 140, 128), (90, 80, 72), (175, 160, 140)], (0.6, 1.8), 200)


def bank(rng):
    n = stretch(fbm(rng, base=6))
    col = lerp_colors(n, [(0, (70, 56, 46)), (0.5, (104, 84, 66)), (1, (132, 116, 98))])
    img = Image.fromarray(col.astype(np.uint8))
    return speckle(rng, img, 700, [(120, 112, 104), (82, 74, 68), (150, 140, 128)], (1.0, 3.2), 230)


def rock(rng):
    n = stretch(fbm(rng, base=4, octaves=6, gain=0.6))
    crack = np.abs(tile_noise(rng, SIZE, 12) - 0.5) < 0.025
    col = lerp_colors(n, [(0, (78, 76, 72)), (0.5, (118, 115, 108)), (1, (156, 152, 142))])
    col[crack] *= 0.82
    return Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))


def gravel(rng):
    n = stretch(fbm(rng, base=8, octaves=3))
    col = lerp_colors(n, [(0, (132, 126, 114)), (1, (172, 166, 152))])
    img = Image.fromarray(col.astype(np.uint8))
    return speckle(rng, img, 3000, [(110, 104, 96), (190, 184, 170), (150, 142, 130)], (0.6, 1.5), 220)


def planks(rng):
    img = Image.new("RGB", (SIZE, SIZE))
    d = ImageDraw.Draw(img)
    board = SIZE // 8
    for i in range(8):
        base = np.array([112, 80, 52]) * rng.uniform(0.82, 1.1)
        d.rectangle([0, i * board, SIZE, (i + 1) * board - 1], fill=tuple(int(c) for c in base))
        d.line([0, i * board, SIZE, i * board], fill=(52, 36, 24), width=2)
    grain = stretch(fbm(rng, base=4, octaves=4))
    arr = np.asarray(img).astype(float) * (0.85 + 0.3 * np.repeat(grain[:, :1], SIZE, axis=1) * grain)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def noise_tex(rng):
    n = stretch(fbm(rng, base=4, octaves=5))
    return Image.fromarray((n * 255).astype(np.uint8), "L")


def tree(rng, size, palette):
    """Top-down leafy canopy: overlapping clumps, lit from the top-left."""
    s = size * 2                                     # draw at 2x, downsample for soft edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = s / 2
    R = s * 0.42
    clumps = []
    for _ in range(int(60 + size / 2)):
        ang, rad = rng.uniform(0, 2 * np.pi), R * np.sqrt(rng.random()) * 0.82
        clumps.append((c + np.cos(ang) * rad, c + np.sin(ang) * rad, R * rng.uniform(0.16, 0.3)))
    clumps.sort(key=lambda k: k[0] + k[1], reverse=True)   # bottom-right (shadowed) first
    for x, y, r in clumps:
        light = np.clip(1 - ((x - c) + (y - c)) / (2.2 * R) - 0.5, 0, 1)   # top-left lighter
        col = lerp_colors(np.array([light]), palette)[0]
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(int(v) for v in col) + (255,))
        hr = r * 0.45                                     # leaf highlight
        d.ellipse([x - r * 0.6 - hr, y - r * 0.6 - hr, x - r * 0.6 + hr, y - r * 0.6 + hr],
                  fill=tuple(int(min(255, v * 1.15)) for v in col) + (110,))
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    arr = np.asarray(img).astype(float)
    leaf = rng.random(arr.shape[:2])
    arr[..., :3] *= (0.88 + 0.24 * leaf)[..., None]     # leaf-level texture
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    return img.resize((size, size), Image.LANCZOS)


PALETTES = [
    [(0, (24, 58, 24)), (0.5, (52, 104, 38)), (1, (98, 150, 58))],      # broadleaf
    [(0, (20, 50, 30)), (0.5, (40, 88, 46)), (1, (78, 128, 64))],       # darker
    [(0, (34, 64, 22)), (0.5, (72, 118, 36)), (1, (128, 164, 62))],     # lighter, yellowish
    [(0, (18, 44, 32)), (0.5, (32, 76, 50)), (1, (62, 112, 74))],       # conifer-ish
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    for name, fn in [("grass", grass), ("water", water), ("dirt", dirt), ("bank", bank),
                     ("rock", rock), ("gravel", gravel), ("planks", planks)]:
        save(fn(rng), out, name)
    noise_tex(rng).save(out / "noise.png")
    for i, pal in enumerate(PALETTES):
        for v in range(2):
            tree(rng, 128, pal).save(out / f"tree_{i}_{v}.png")
    print("art written to", out)


if __name__ == "__main__":
    main()
