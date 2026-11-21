"""Renders wildlife sprite sheets: fish, rabbit, deer, bird, squirrel, frog.

Windows only. From the repo root in PowerShell:
    .\\blender\\render_all.ps1
or just this step:
    blender -b --factory-startup -P blender\\render_wildlife.py

Animals are rendered FACING NORTH with NO baked shadow: Godot rotates the sprite to the
animal's heading and draws a separate soft shadow that always falls south-east (the sun).
They are rendered at DETAIL x the map's pixel density, so they stay crisp when the camera
zooms in; Godot scales them back to true size (see "scale" in wildlife.json).

Outputs
  renders/wildlife/<species>.png   horizontal strip of frames
  renders/wildlife/wildlife.json   frame size, frame names, scale, behaviour + meaning
"""
import json
import math
import os
import sys

import bpy
import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import build_scene as bs  # noqa: E402
import render_objects as ro  # noqa: E402  (reuses its geometry and material helpers)

DETAIL = 4                                   # pixels per map pixel
PX = bs.TILE_PX * DETAIL
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "renders", "wildlife")
PARTS = os.path.join(OUT, "_parts")


def fur(name, dark, light, scale=30.0):
    return ro.noise_mat(name, [(0.3, dark), (0.75, light)], scale, rough=0.9)


def ellipsoid(r, loc, mat, scale, rot=(0, 0, 0)):
    o = ro.ico(r, loc, mat, subdiv=3, scale=scale)
    o.rotation_euler = rot
    return o


# --------------------------------------------------------------------------- species
# Units: Blender units (1 = 2 m). Every model faces +Y (north). `pose` picks the frame.

def fish(pose):
    body = fur("fish_body", (0.012, 0.015, 0.01), (0.05, 0.055, 0.03), 40)
    fin = fur("fish_fin", (0.015, 0.018, 0.012), (0.04, 0.042, 0.025), 20)
    bend = {"swim_1": -0.35, "swim_2": 0.0, "swim_3": 0.35, "swim_4": 0.0}[pose]
    ellipsoid(0.05, (0, 0.03, 0), body, (0.55, 2.2, 0.5))
    ellipsoid(0.035, (math.sin(bend) * 0.03, -0.07, 0), body, (0.55, 1.6, 0.45), rot=(0, 0, bend * 0.6))
    tx, ty = math.sin(bend) * 0.08, -0.12
    ro.cone(0.03, 0.06, (tx, ty, 0), fin, verts=3, rot=(math.pi / 2, 0, bend))
    for s in (-1, 1):
        ellipsoid(0.012, (s * 0.03, 0.05, 0), fin, (2.2, 1.0, 0.3), rot=(0, 0, s * 0.5))


def rabbit(pose):
    coat = fur("rabbit", (0.09, 0.065, 0.045), (0.24, 0.18, 0.12))
    belly = fur("rabbit_tail", (0.45, 0.43, 0.40), (0.62, 0.6, 0.56))
    stretch = {"sit": 1.0, "hop_1": 1.35, "hop_2": 0.85, "graze": 1.1}[pose]
    head_y = {"sit": 0.085, "hop_1": 0.11, "hop_2": 0.07, "graze": 0.1}[pose]
    head_z = 0.07 if pose != "graze" else 0.035
    ellipsoid(0.06, (0, 0, 0.055), coat, (0.85, 1.05 * stretch, 0.8))
    ellipsoid(0.035, (0, head_y, head_z), coat, (0.85, 1.1, 0.85))
    ear_tilt = 0.25 if pose in ("sit", "graze") else 1.1
    for s in (-1, 1):
        ellipsoid(0.03, (s * 0.018, head_y - 0.02, head_z + 0.03), coat, (0.35, 1.4, 0.25),
                  rot=(ear_tilt, 0, s * 0.25))
    ellipsoid(0.018, (0, -0.06 * stretch, 0.06), belly, (1, 1, 1))


def deer(pose):
    coat = fur("deer", (0.13, 0.075, 0.035), (0.30, 0.19, 0.09), 20)
    dark = fur("deer_dark", (0.04, 0.03, 0.02), (0.09, 0.06, 0.04))
    white = fur("deer_tail", (0.5, 0.48, 0.44), (0.68, 0.65, 0.6))
    step = {"stand": 0.0, "walk_1": 0.06, "walk_2": -0.06, "graze": 0.0, "alert": 0.0}[pose]
    ellipsoid(0.16, (0, 0, 0.55), coat, (0.95, 2.3, 0.9))
    for sx, sy in ((-1, 1), (1, 1), (-1, -1), (1, -1)):
        off = step if sx * sy > 0 else -step
        ro.cyl(0.025, 0.5, (sx * 0.09, sy * 0.25 + off, 0.25), dark, verts=6)
    neck_y, neck_z, head_z, head_y = {
        "graze": (0.38, 0.38, 0.12, 0.5), "alert": (0.34, 0.8, 0.98, 0.42),
    }.get(pose, (0.36, 0.7, 0.82, 0.48))
    ro.cyl(0.06, 0.4, (0, neck_y, neck_z), coat, verts=7, rot=(-0.6 if pose != "graze" else -1.9, 0, 0))
    ellipsoid(0.07, (0, head_y, head_z), coat, (0.8, 1.6, 0.85))
    for s in (-1, 1):
        ellipsoid(0.03, (s * 0.07, head_y - 0.06, head_z + 0.05), coat, (1.6, 0.6, 0.4), rot=(0, 0, s * 0.4))
    ellipsoid(0.04, (0, -0.37, 0.62), white, (0.8, 1.0, 0.6))


def bird(pose):
    body = fur("bird", (0.05, 0.035, 0.025), (0.20, 0.13, 0.08), 40)
    breast = fur("bird_breast", (0.35, 0.13, 0.05), (0.55, 0.24, 0.1))
    beak = ro.flat_mat("beak", (0.35, 0.28, 0.1))
    ellipsoid(0.03, (0, 0, 0.03), body, (0.8, 1.4, 0.75))
    ellipsoid(0.02, (0, 0.02, 0.025), breast, (0.9, 1.0, 0.7))
    ellipsoid(0.018, (0, 0.04, 0.045), body, (1, 1, 1))
    ro.cone(0.006, 0.02, (0, 0.06, 0.045), beak, verts=4, rot=(-math.pi / 2, 0, 0))
    ellipsoid(0.02, (0, -0.045, 0.035), body, (0.5, 1.4, 0.2))
    if pose != "perch":
        lift = 0.6 if pose == "fly_1" else -0.35
        for s in (-1, 1):
            ellipsoid(0.03, (s * 0.04, 0.0, 0.04), body, (1.4, 0.65, 0.15), rot=(0, s * lift, s * 0.15))


def squirrel(pose):
    coat = fur("squirrel", (0.20, 0.07, 0.02), (0.42, 0.18, 0.06))
    run = pose != "sit"
    stretch = 1.3 if pose == "run_1" else (1.0 if pose == "run_2" else 0.9)
    ellipsoid(0.04, (0, 0, 0.04), coat, (0.8, 1.3 * stretch, 0.75))
    ellipsoid(0.025, (0, 0.05 * stretch, 0.05), coat, (0.9, 1.1, 0.9))
    for s in (-1, 1):
        ro.cone(0.008, 0.02, (s * 0.012, 0.045 * stretch, 0.075), coat, verts=4)
    if run:
        ellipsoid(0.026, (0, -0.075 * stretch, 0.05), coat, (0.9, 1.9, 0.7))
    else:
        ellipsoid(0.03, (0, -0.03, 0.09), coat, (0.9, 1.6, 1.0), rot=(0.9, 0, 0))   # tail curled up


def frog(pose):
    skin = fur("frog", (0.03, 0.07, 0.02), (0.11, 0.18, 0.05), 25)
    spot = ro.flat_mat("frog_spot", (0.02, 0.03, 0.015))
    ellipsoid(0.03, (0, 0, 0.02), skin, (1.0, 1.25, 0.55))
    for s in (-1, 1):
        ellipsoid(0.008, (s * 0.017, 0.028, 0.032), spot, (1, 1, 1))
    if pose == "jump":
        for s in (-1, 1):
            ellipsoid(0.012, (s * 0.03, -0.07, 0.015), skin, (0.6, 3.0, 0.4), rot=(0, 0, s * 0.2))
            ellipsoid(0.008, (s * 0.03, 0.05, 0.015), skin, (0.6, 1.8, 0.4), rot=(0, 0, -s * 0.3))
    else:
        for s in (-1, 1):
            ellipsoid(0.014, (s * 0.035, -0.015, 0.012), skin, (1.1, 1.8, 0.5), rot=(0, 0, s * 0.5))
            ellipsoid(0.008, (s * 0.025, 0.03, 0.01), skin, (1.0, 1.4, 0.5), rot=(0, 0, -s * 0.4))


# frame span (units), frames, size_m, display scale (>1 = slightly exaggerated so tiny animals
# stay readable at normal zoom), behaviour (used by Godot), meaning (truth vs appearance).
SPECIES = {
    "fish": (fish, 0.34, ["swim_1", "swim_2", "swim_3", "swim_4"], 0.3, 1.3, {
        "habitat": "water", "speed_mps": 0.8, "dart_speed_mps": 3.0, "flee_radius_m": 4.0,
        "active_hours": [0, 24], "group": [1, 3]},
        {"kind": "animal", "species": "fish", "truth": {"edible": True, "catchable_with": ["spear", "line", "hands_rarely"]},
         "appearance": {"glimpse": ["movement in the water"], "look": ["dark fish under the surface"]}}),
    "rabbit": (rabbit, 0.4, ["sit", "hop_1", "hop_2", "graze"], 0.4, 1.4, {
        "habitat": "land", "prefers": ["grass", "forest_floor"], "speed_mps": 1.2, "flee_speed_mps": 6.0,
        "flee_radius_m": 9.0, "active_hours": [[4, 10], [17, 22]], "group": [1, 2]},
        {"kind": "animal", "species": "rabbit", "truth": {"edible": True, "catchable_with": ["snare"]},
         "appearance": {"glimpse": ["small brown animal"], "look": ["rabbit", "long ears"]}}),
    "deer": (deer, 1.5, ["stand", "walk_1", "walk_2", "graze", "alert"], 1.8, 1.0, {
        "habitat": "land", "prefers": ["grass", "forest_floor"], "speed_mps": 1.0, "flee_speed_mps": 9.0,
        "flee_radius_m": 22.0, "active_hours": [[5, 9], [17, 21]], "drinks_at": "water_edge", "group": [2, 4]},
        {"kind": "animal", "species": "deer", "truth": {"edible": True, "dangerous": False},
         "appearance": {"glimpse": ["large brown animal"], "look": ["deer", "white tail flashing"]}}),
    "bird": (bird, 0.22, ["perch", "fly_1", "fly_2"], 0.15, 1.8, {
        "habitat": "air", "perches": ["trees", "ground"], "speed_mps": 0.6, "fly_speed_mps": 8.0,
        "flee_radius_m": 6.0, "active_hours": [5, 20], "group": [1, 5], "sings_at": [[5, 8], [18, 20]]},
        {"kind": "animal", "species": "songbird", "truth": {"edible": False},
         "appearance": {"glimpse": ["small bird"], "look": ["brown bird with a rusty breast"], "hear": ["birdsong"]}}),
    "squirrel": (squirrel, 0.38, ["sit", "run_1", "run_2"], 0.4, 1.5, {
        "habitat": "land", "near": "trees", "speed_mps": 1.5, "flee_speed_mps": 5.0, "flee_to": "tree",
        "flee_radius_m": 7.0, "active_hours": [6, 19], "group": [1, 1]},
        {"kind": "animal", "species": "squirrel", "truth": {"edible": True, "caches_nuts": True},
         "appearance": {"glimpse": ["quick red-brown animal"], "look": ["squirrel", "bushy tail"]}}),
    "frog": (frog, 0.26, ["sit", "jump"], 0.08, 2.0, {
        "habitat": "shore", "speed_mps": 0.3, "jump_m": 0.8, "flee_radius_m": 2.5, "flee_to": "water",
        "active_hours": [[19, 24], [0, 6]], "group": [1, 3], "croaks_at": [[20, 24], [0, 3]]},
        {"kind": "animal", "species": "frog", "truth": {"edible": True},
         "appearance": {"glimpse": ["something small hops"], "look": ["green frog"], "hear": ["croaking"]}}),
}


def main():
    os.makedirs(PARTS, exist_ok=True)
    bs.reset_scene()
    doc = {"detail": DETAIL, "px_per_metre_in_sheet": PX / bs.WORLD_METRES_PER_TILE,
           "facing": "north (up); rotate the sprite to the heading",
           "shadow": "none baked; draw a soft blob shadow offset to the south-east",
           "species": {}}
    for name, (builder, span, frames, size_m, display_scale, behaviour, meaning) in SPECIES.items():
        frame_px = int(round(span * PX))
        strip = np.zeros((frame_px, frame_px * len(frames), 4), dtype=np.float32)
        for i, pose in enumerate(frames):
            ro.clear_parts()
            builder(pose)
            bs.camera(0, 0, span, px_per_unit=PX)
            path = os.path.join(PARTS, f"{name}_{pose}.png")
            bpy.context.scene.render.filepath = path
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(path, check_existing=False)
            px = np.empty(frame_px * frame_px * 4, dtype=np.float32)
            img.pixels.foreach_get(px)
            bpy.data.images.remove(img)
            strip[:, i * frame_px:(i + 1) * frame_px] = px.reshape(frame_px, frame_px, 4)
            print(f"wildlife {name} {pose}", flush=True)
        out = bpy.data.images.new(name, strip.shape[1], strip.shape[0], alpha=True)
        out.pixels.foreach_set(strip.ravel())
        out.filepath_raw = os.path.join(OUT, f"{name}.png")
        out.file_format = 'PNG'
        out.save()
        doc["species"][name] = {
            "sheet": f"wildlife/{name}.png", "frame_px": frame_px, "frames": frames,
            "size_m": size_m, "display_scale": display_scale,
            "scale": round(display_scale / DETAIL, 4),
            "behaviour": behaviour, "meaning": meaning}
    with open(os.path.join(OUT, "wildlife.json"), "w") as f:
        json.dump(doc, f, indent=1)
    print(f"WILDLIFE_OK {len(SPECIES)}", flush=True)


if __name__ == "__main__":
    main()
