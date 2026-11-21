"""Builds the forest world Wren will live in: terrain, objects, named places and wildlife.

Windows only. Plain Python 3.10+ (standard library only). From the repo root in PowerShell:
    py world_data\\build_world.py              (or: python world_data\\build_world.py)

Outputs (all in world_data\\):
  terrain.txt   the map, one character per tile (2 m). Edit it in Notepad if you like:
                  .  forest floor      ~  water        =  path (worn dirt)
                  ,  grass (clearing)  B  bridge deck (water underneath, walkable)
  objects.json  every tree, bush, rock, log, prop and building: sprite, position, meaning
  places.json   the named places (INTERNAL names: Wren never receives them; it names places itself)
  wildlife.json initial animals: species, position, home range
  world.json    summary: size, units, seed, legend, file list

Rules the generator enforces (so Godot's autotiling always has a matching tile):
  * water is always ringed by forest floor;
  * path and grass never touch water, and never touch each other;
  * the trail stops one tile short of the stream; the bridge sprite spans the gap.
Rerunning with the same --seed gives the same world.
"""
import argparse
import json
import math
import os
import random

W, H = 160, 120                 # tiles; 1 tile = 2 m -> 320 m x 240 m
M_PER_TILE = 2.0
HERE = os.path.dirname(os.path.abspath(__file__))
SPRITES_JSON = os.path.join(HERE, "..", "renders", "sprites", "sprites.json")

FLOOR, WATER, PATH, GRASS, BRIDGE = ".", "~", "=", ",", "B"


# --------------------------------------------------------------------------- helpers

class Grid:
    def __init__(self, fill=FLOOR):
        self.c = [[fill] * W for _ in range(H)]

    def inb(self, x, y):
        return 0 <= x < W and 0 <= y < H

    def get(self, x, y):
        return self.c[y][x] if self.inb(x, y) else None

    def set(self, x, y, v):
        if self.inb(x, y):
            self.c[y][x] = v

    def disc(self, cx, cy, r, v, only=None):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and (only is None or self.get(x, y) in only):
                    self.set(x, y, v)

    def blob(self, rng, cx, cy, r, v, wobble=0.35, only=None):
        """Irregular round area: radius varies smoothly with angle."""
        ph = [rng.uniform(0, math.tau) for _ in range(3)]
        for y in range(int(cy - r * 1.6), int(cy + r * 1.6) + 1):
            for x in range(int(cx - r * 1.6), int(cx + r * 1.6) + 1):
                a = math.atan2(y - cy, x - cx)
                rr = r * (1 + wobble * (0.5 * math.sin(2 * a + ph[0]) + 0.3 * math.sin(3 * a + ph[1])
                                        + 0.2 * math.sin(5 * a + ph[2])))
                if (x - cx) ** 2 + (y - cy) ** 2 <= rr * rr and (only is None or self.get(x, y) in only):
                    self.set(x, y, v)

    def line(self, pts, width, v, rng, only=None):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = int(max(abs(x1 - x0), abs(y1 - y0)) * 3) + 1
            for i in range(n + 1):
                t = i / n
                self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, width / 2, v, only)

    def neighbours8(self, x, y):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    yield self.get(x + dx, y + dy)


def wiggle(rng, pts, amount, steps=4):
    """Insert jittered midpoints so paths and streams meander."""
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for s in range(1, steps):
            t = s / steps
            nx, ny = -(y1 - y0), (x1 - x0)
            ln = math.hypot(nx, ny) or 1
            j = rng.uniform(-amount, amount) * math.sin(math.pi * t)
            out.append((x0 + (x1 - x0) * t + nx / ln * j, y0 + (y1 - y0) * t + ny / ln * j))
        out.append((x1, y1))
    return out


def connect_diagonals(g, kind):
    """Blob tiles only join through sides: where two cells of `kind` touch only by a corner,
    fill one shared side so paths and streams don't render as a chain of dots."""
    for y in range(H):
        for x in range(W):
            if g.get(x, y) != kind:
                continue
            for dx, dy in ((1, 1), (1, -1)):
                if g.get(x + dx, y + dy) == kind and g.get(x + dx, y) != kind and g.get(x, y + dy) != kind:
                    g.set(x + dx, y, kind)


def sanitize(g, bridge_cells):
    """Enforce the terrain-transition rules. Repeats until stable."""
    for kind in (WATER, PATH, GRASS):
        connect_diagonals(g, kind)
    changed = True
    while changed:
        changed = False
        for y in range(H):
            for x in range(W):
                t = g.get(x, y)
                if t in (PATH, GRASS):
                    for n in g.neighbours8(x, y):
                        if n in (WATER, BRIDGE) or (n in (PATH, GRASS) and n != t):
                            g.set(x, y, FLOOR)
                            changed = True
                            break
    for (x, y) in bridge_cells:
        g.set(x, y, BRIDGE)
    # Sanitizing can break a diagonal link again; reconnect, then drop any path cell that now
    # touches water or grass (rare), keeping the rules intact.
    connect_diagonals(g, PATH)
    for y in range(H):
        for x in range(W):
            if g.get(x, y) == PATH and any(n in (WATER, BRIDGE, GRASS) for n in g.neighbours8(x, y)):
                g.set(x, y, FLOOR)


# --------------------------------------------------------------------------- the world

def build(seed):
    rng = random.Random(seed)
    g = Grid()
    places = []

    def place(pid, kind, cx, cy, rx, ry, what):
        places.append({"id": pid, "kind": kind, "center_tile": [round(cx, 1), round(cy, 1)],
                       "center_m": [round(cx * M_PER_TILE, 1), round(cy * M_PER_TILE, 1)],
                       "radius_tiles": [rx, ry], "contains": what})

    # Clearings (grass).
    camp = (34, 70)
    meadow = (62, 26)
    town = (128, 62)
    g.blob(rng, *camp, 8.5, GRASS, 0.25)
    g.blob(rng, *meadow, 11, GRASS, 0.4)
    g.blob(rng, 52, 98, 6, GRASS, 0.45)                      # small south glade
    g.blob(rng, *town, 20, GRASS, 0.2)
    place("forest", "region", 70, 60, 70, 60, "dense mixed woodland of oak, pine and birch")
    place("campsite", "clearing", *camp, 9, 9, "fire pit, collapsed tent, bedroll, backpack, log seat")
    place("north_meadow", "clearing", *meadow, 11, 11, "open grass where deer graze at dawn and dusk")
    place("south_glade", "clearing", 52, 98, 6, 6, "small sunny glade with berry bushes")

    # Stream: from the north edge, meandering south into the pond.
    pond = (92, 92)
    stream = wiggle(rng, [(96, -2), (101, 18), (94, 38), (98, 55), (93, 70), (91, 82)], 4.0, 5)
    g.line(stream, 2.6, WATER, rng)
    g.blob(rng, *pond, 9, WATER, 0.3)
    outflow = wiggle(rng, [(97, 100), (104, 110), (101, 122)], 2.0, 4)
    g.line(outflow, 1.6, WATER, rng)
    place("stream", "water", 96, 40, 4, 42, "shallow winding stream with fish; feeds the pond")
    place("pond", "water", *pond, 10, 10, "deep pond with lily pads, frogs on the shore, fish")

    # Town: ground is grass, roads are worn dirt on a floor ring (grass may not touch path).
    buildings = {
        "town_hall": (128, 50), "general_store": (114, 62), "garage": (142, 62),
        "farmhouse": (125, 80), "water_tower": (139, 47),
    }
    for bid, (bx, by) in buildings.items():
        place(bid, "building", bx, by, 3, 3, bid.replace("_", " "))
    place("town", "settlement", *town, 21, 21, "abandoned town: town hall, general store, garage, farmhouse, water tower")

    # Trail: campsite -> east through the forest -> stream (bridge) -> town square.
    y_cross = 63
    cols = [x for x in range(W) if g.get(x, y_cross) == WATER and 80 < x < 110]
    s_w, s_e = min(cols), max(cols)
    trail_w = wiggle(rng, [(camp[0] + 6, camp[1]), (52, 67), (66, 64), (s_w - 2, y_cross)], 2.5, 4)
    trail_e = wiggle(rng, [(s_e + 2, y_cross), (110, 62), (122, 62)], 1.5, 3)
    road_ns = [(128, 46), (128, 84)]
    road_ew = [(118, 62), (146, 62)]
    for pts, wdt in ((trail_w, 1.6), (trail_e, 1.6), (road_ns, 2.2), (road_ew, 2.2)):
        g.line(pts, wdt + 2.2, FLOOR, rng)                  # floor margin around every path
        g.line(pts, wdt, PATH, rng)
    # Deck only over the water itself (one cell = 2 m wide, like the plank sprite); the banks
    # either side stay forest floor so the shoreline tiles stay clean.
    bridge = [(x, y_cross) for x in range(s_w, s_e + 1)]
    place("trail", "path", 66, 64, 34, 4, "worn trail from the campsite to the stream and on to the town")
    place("bridge", "structure", (s_w + s_e) / 2 + 0.5, y_cross + 0.5, (s_e - s_w) / 2 + 2, 1.0,
          "old plank footbridge over the stream (weak: integrity 0.25)")

    # Animal paths: thin tracks between water and clearings.
    for pts in ([(meadow[0] + 6, meadow[1] + 8), (78, 50), (90, 52)],
                [(camp[0] + 2, camp[1] + 8), (44, 88), (52, 98)],
                [(58, 100), (74, 96), (82, 92)],
                [(meadow[0] - 8, meadow[1] + 4), (36, 40), (camp[0] - 2, camp[1] - 8)]):
        g.line(wiggle(rng, pts, 3.0, 4), 0.9, PATH, rng, only={FLOOR, GRASS})
    place("animal_paths", "path", 60, 60, 40, 40, "narrow tracks worn by deer between water and clearings")

    sanitize(g, bridge)
    return rng, g, places, buildings, (s_w, s_e, y_cross), pond, stream


# --------------------------------------------------------------------------- objects

def load_sprite_index():
    with open(SPRITES_JSON) as f:
        return {s["id"]: s for s in json.load(f)["sprites"]}


def populate(rng, g, places, buildings, crossing, pond, stream, sprites):
    objs = []
    taken = []                                              # (x, y, r) in tiles

    def free(x, y, r):
        return all((x - ox) ** 2 + (y - oy) ** 2 >= (r + orr) ** 2 for ox, oy, orr in taken)

    def variants(kind):
        return sorted(k for k, s in sprites.items() if s["type"] == kind)

    def add(kind, x, y, r_tiles, place_id=None, sprite=None):
        sid = sprite or rng.choice(variants(kind))
        s = sprites[sid]
        objs.append({"id": f"{kind}_{len(objs):05d}", "type": kind, "sprite": sid,
                     "tile": [round(x, 2), round(y, 2)], "pos_m": [round(x * M_PER_TILE, 2), round(y * M_PER_TILE, 2)],
                     "layer": s["layer"], "blocks_movement": s["blocks_movement"], "footprint": s["footprint"],
                     "place": place_id, "meaning": s["meaning"]})
        taken.append((x, y, r_tiles))

    # Named places first.
    cx, cy = 34, 70
    for kind, dx, dy, r in (("campsite_fire_pit", 0, 0, 1.0), ("campsite_tent", -3.5, -2.5, 1.8),
                            ("campsite_bedroll", -1.5, -1.0, 0.5), ("campsite_backpack", -2.2, 0.2, 0.4),
                            ("campsite_log_seat", 0.5, 1.8, 1.0)):
        add(kind, cx + dx, cy + dy, r, "campsite", sprite=kind)
    s_w, s_e, yc = crossing
    add("bridge_ew", (s_w + s_e + 1) / 2, yc + 0.5, 3.0, "bridge", sprite="bridge_ew")
    for bid, (bx, by) in buildings.items():
        add(bid, bx, by, 5.0 if bid != "water_tower" else 2.0, bid, sprite=bid)

    # Understory and ground clutter.
    def scatter(kind, count, r, ok):
        tries = 0
        n = 0
        while n < count and tries < count * 60:
            tries += 1
            x, y = rng.uniform(1, W - 1), rng.uniform(1, H - 1)
            if ok(int(x), int(y)) and free(x, y, r):
                add(kind, x, y, r)
                n += 1

    def is_floor(x, y):
        return g.get(x, y) == FLOOR and not any(n in (WATER, BRIDGE, PATH) for n in g.neighbours8(x, y))

    def clearing_edge(x, y):
        return g.get(x, y) == FLOOR and any(n == GRASS for n in g.neighbours8(x, y))

    scatter("fallen_log", 45, 1.4, is_floor)
    for _ in range(16):                                     # rock clusters
        x, y = rng.uniform(5, W - 5), rng.uniform(5, H - 5)
        for _ in range(rng.randint(1, 4)):
            rx, ry = x + rng.uniform(-2, 2), y + rng.uniform(-2, 2)
            if is_floor(int(rx), int(ry)) and free(rx, ry, 0.7):
                add("mossy_rock", rx, ry, 0.7)

    # Trees: species by zone, spacing by crown size. Never on water, paths or clearings.
    def tree_kind(x, y):
        r = rng.random()
        north = y < 40
        if r < 0.025:
            return "snag", 1.2
        if north:
            return ("pine", 1.4) if r < 0.65 else ("oak", 1.8) if r < 0.85 else ("birch", 1.3)
        return ("oak", 1.8) if r < 0.55 else ("birch", 1.3) if r < 0.8 else ("pine", 1.4)

    cells = [(x, y) for y in range(H) for x in range(W) if g.get(x, y) == FLOOR]
    rng.shuffle(cells)
    for x, y in cells:
        if any(n in (WATER, BRIDGE, PATH) for n in g.neighbours8(x, y)):
            continue
        near_grass = sum(n == GRASS for n in g.neighbours8(x, y))
        if near_grass >= 3 or rng.random() > 0.9:
            continue
        kind, r = tree_kind(x, y)
        px, py = x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9)
        # Crowns overlap in a real forest: only the trunks need room (about 40% of the crown).
        if free(px, py, r * 0.42):
            add(kind, px, py, r * 0.42)

    scatter("berry_bush", 60, 0.6, clearing_edge)
    scatter("fern", 260, 0.3, is_floor)
    scatter("mushrooms", 70, 0.2, is_floor)
    # Lily pads: deep in the pond, away from the bank.
    px, py = pond
    for _ in range(9):
        x, y = px + rng.uniform(-6, 6), py + rng.uniform(-5, 5)
        if all(g.get(int(x) + dx, int(y) + dy) == WATER for dx in (-2, 0, 2) for dy in (-2, 0, 2)) and free(x, y, 0.8):
            add("lily_pads", x, y, 0.8, "pond")
    return objs


def wildlife(rng, g, places, pond, stream):
    animals = []

    def add(species, x, y, home, group=None):
        animals.append({"id": f"{species}_{len(animals):03d}", "species": species,
                        "tile": [round(x, 2), round(y, 2)], "pos_m": [round(x * M_PER_TILE, 2), round(y * M_PER_TILE, 2)],
                        "home_tile": [round(home[0], 1), round(home[1], 1)], "group": group})

    def find(pred, near, spread):
        for _ in range(500):
            x, y = near[0] + rng.uniform(-spread, spread), near[1] + rng.uniform(-spread, spread)
            if g.inb(int(x), int(y)) and pred(g.get(int(x), int(y)), int(x), int(y)):
                return x, y
        return near

    land = lambda t, x, y: t in (FLOOR, GRASS, PATH)
    water = lambda t, x, y: t == WATER
    shore = lambda t, x, y: t == FLOOR and any(n == WATER for n in g.neighbours8(x, y))
    for herd, home in enumerate(((62, 26), (52, 98))):
        for _ in range(rng.randint(2, 4)):
            add("deer", *find(land, home, 5), home, group=f"herd_{herd}")
    for home in ((34, 70), (62, 26), (52, 98), (128, 62), (75, 45)):
        for _ in range(rng.randint(1, 2)):
            add("rabbit", *find(land, home, 6), home)
    for _ in range(10):
        home = (rng.uniform(10, 150), rng.uniform(10, 110))
        add("squirrel", *find(land, home, 3), home)
    for _ in range(14):
        home = (rng.uniform(10, 150), rng.uniform(10, 110))
        add("bird", *find(land, home, 3), home, group=f"flock_{rng.randint(0, 4)}")
    for _ in range(7):
        add("frog", *find(shore, pond, 11), pond)
    for _ in range(8):
        add("fish", *find(water, pond, 7), pond)
    for (x, y) in stream[2:-1:2]:
        add("fish", *find(water, (x, y), 3), (x, y))
    return animals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261121)
    a = ap.parse_args()
    rng, g, places, buildings, crossing, pond, stream = build(a.seed)
    sprites = load_sprite_index()
    objs = populate(rng, g, places, buildings, crossing, pond, stream, sprites)
    animals = wildlife(rng, g, places, pond, stream)
    with open(os.path.join(HERE, "terrain.txt"), "w", newline="\n") as f:
        f.write("\n".join("".join(r) for r in g.c) + "\n")
    with open(os.path.join(HERE, "objects.json"), "w") as f:
        json.dump({"objects": objs}, f, indent=1)
    with open(os.path.join(HERE, "places.json"), "w") as f:
        json.dump({"note": "INTERNAL names for tools and debugging. Wren never receives these; "
                           "it perceives appearances and names places itself.", "places": places}, f, indent=1)
    with open(os.path.join(HERE, "wildlife.json"), "w") as f:
        json.dump({"animals": animals}, f, indent=1)
    counts = {}
    for o in objs:
        counts[o["type"]] = counts.get(o["type"], 0) + 1
    with open(os.path.join(HERE, "world.json"), "w") as f:
        json.dump({"size_tiles": [W, H], "metres_per_tile": M_PER_TILE, "size_m": [W * M_PER_TILE, H * M_PER_TILE],
                   "seed": a.seed, "origin": "tile (0,0) is the north-west corner; +x east, +y south",
                   "legend": {FLOOR: "forest_floor", WATER: "water", PATH: "path", GRASS: "grass",
                              BRIDGE: "bridge (water tile underneath, walkable deck)"},
                   "files": ["terrain.txt", "objects.json", "places.json", "wildlife.json"],
                   "object_counts": counts, "animal_count": len(animals)}, f, indent=1)
    print(f"world {W}x{H} tiles, {len(objs)} objects, {len(animals)} animals, {len(places)} places")
    print("objects:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
