"""Renders object sprites (trees, plants, rocks, logs, lily pads) and the named places
(campsite props, bridge, town buildings) with baked soft shadows on a transparent background.

Windows only. From the repo root in PowerShell:
    .\\blender\\render_all.ps1
or just this step:
    blender -b --factory-startup -P blender\\render_objects.py

Outputs
  renders/sprites/<id>.png      one sprite per object variant
  renders/sprites/sprites.json  size, anchor (ground point under the object), footprint, meaning

Every model is procedural low-poly geometry built here. Same camera, sun and sky as the
tiles (build_scene.py), at the same 64 px per tile, so sprites sit naturally on the map.
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import build_scene as bs  # noqa: E402

PX = bs.TILE_PX
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "renders", "sprites")
SHADOW_OPACITY = 0.55
PAD = 0.15                         # tiles of empty margin around each sprite
ONLY = os.environ.get("SPRITES_ONLY", "")   # comma-separated ids, for quick re-renders

# --------------------------------------------------------------------------- materials

_mats = {}
EXTRA = {}                         # builders may record extra facts about the model (e.g. log angle)
ALBEDO = 0.35                      # AgX lifts light colours a lot; keep man-made materials earthy


def noise_mat(name, stops, scale=4.0, rough=0.8, detail=4.0, metallic=0.0):
    """Principled material coloured by 3D object-space noise through a colour ramp."""
    if name in _mats:
        return _mats[name]
    mat = bpy.data.materials.new(name)
    N = bs.Nodes(mat)
    tc = N.new('ShaderNodeTexCoord')
    nz = N.new('ShaderNodeTexNoise')
    N.link(tc.outputs['Object'], nz.inputs['Vector'])
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = detail
    col = N.ramp(nz.outputs['Fac'], [(pos, tuple(c * ALBEDO for c in rgb)) for pos, rgb in stops])
    col = N.dapple(col, N.position())
    p = N.principled(col, rough=rough, normal=N.bump(nz.outputs['Fac'], 0.25, 0.05))
    p.inputs['Metallic'].default_value = metallic
    _mats[name] = mat
    return mat


def leaf_mat(name, stops, scale=14.0):
    """Foliage: clusters of leaves (voronoi cells) with darker gaps, per-cluster tint."""
    if name in _mats:
        return _mats[name]
    mat = bpy.data.materials.new(name)
    N = bs.Nodes(mat)
    tc = N.new('ShaderNodeTexCoord')
    vor = N.new('ShaderNodeTexVoronoi')
    N.link(tc.outputs['Object'], vor.inputs['Vector'])
    vor.inputs['Scale'].default_value = scale
    sep = N.new('ShaderNodeSeparateColor')
    N.link(vor.outputs['Color'], sep.inputs[0])
    col = N.ramp(sep.outputs[0], stops)
    gaps = N.smooth(0.05, 0.35, vor.outputs['Distance'])
    col = N.mul_rgb(col, N.math('ADD', N.math('MULTIPLY', N.math('SUBTRACT', 1.0, gaps), 0.55), 0.45))
    N.principled(N.dapple(col, N.position()), rough=0.75, normal=N.bump(vor.outputs['Distance'], 0.6, 0.05))
    _mats[name] = mat
    return mat


def log_mat():
    """Bark with only a little moss along the top (logs should read as wood, not as rock)."""
    name = "log_bark"
    if name in _mats:
        return _mats[name]
    mat = bpy.data.materials.new(name)
    N = bs.Nodes(mat)
    geo = N.new('ShaderNodeNewGeometry')
    sep = N.new('ShaderNodeSeparateXYZ')
    N.link(geo.outputs['Normal'], sep.inputs[0])
    tc = N.new('ShaderNodeTexCoord')
    wave = N.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='X')
    N.link(tc.outputs['Object'], wave.inputs['Vector'])
    wave.inputs['Scale'].default_value = 6.0
    wave.inputs['Distortion'].default_value = 6.0
    bark = N.ramp(wave.outputs['Fac'], [(0.2, (0.03, 0.02, 0.012)), (0.6, (0.075, 0.05, 0.03)), (0.9, (0.11, 0.08, 0.05))])
    nz = N.new('ShaderNodeTexNoise')
    N.link(tc.outputs['Object'], nz.inputs['Vector'])
    nz.inputs['Scale'].default_value = 5.0
    moss_amt = N.math('MULTIPLY', N.smooth(0.85, 0.97, sep.outputs['Z']), N.smooth(0.55, 0.68, nz.outputs['Fac']))
    col = N.mix_rgb(moss_amt, bark, (0.03, 0.05, 0.014))
    N.principled(N.dapple(col, geo.outputs['Position']), rough=0.9, normal=N.bump(wave.outputs['Fac'], 0.5, 0.04))
    _mats[name] = mat
    return mat


def shingle_mat(name, rgb):
    """Roofing in rows (wave bands across the slope), with weathered, uneven tiles."""
    if name in _mats:
        return _mats[name]
    mat = bpy.data.materials.new(name)
    N = bs.Nodes(mat)
    tc = N.new('ShaderNodeTexCoord')
    wave = N.new('ShaderNodeTexWave', wave_type='BANDS', bands_direction='Y', wave_profile='SAW')
    N.link(tc.outputs['Object'], wave.inputs['Vector'])
    wave.inputs['Scale'].default_value = 3.2
    wave.inputs['Distortion'].default_value = 0.4
    vor = N.new('ShaderNodeTexVoronoi')
    N.link(tc.outputs['Object'], vor.inputs['Vector'])
    vor.inputs['Scale'].default_value = 9.0
    sep = N.new('ShaderNodeSeparateColor')
    N.link(vor.outputs['Color'], sep.inputs[0])
    tone = N.math('ADD', N.math('MULTIPLY', sep.outputs[0], 0.5), 0.75)
    rows = N.math('ADD', N.math('MULTIPLY', wave.outputs['Fac'], 0.45), 0.6)
    fac = N.math('MULTIPLY', tone, rows)
    comb = N.new('ShaderNodeCombineXYZ')
    for c in 'XYZ':
        N.link(fac, comb.inputs[c])
    rgbn = N.new('ShaderNodeRGB')
    rgbn.outputs[0].default_value = (*rgb, 1.0)
    col = N.mul_rgb(rgbn.outputs[0], comb.outputs[0])
    N.principled(N.dapple(col, N.position()), rough=0.9, normal=N.bump(wave.outputs['Fac'], 0.4, 0.05))
    _mats[name] = mat
    return mat


def mossy_mat(name, seed=0.0):
    if name in _mats:
        return _mats[name]
    mat = bpy.data.materials.new(name)
    N = bs.Nodes(mat)
    geo = N.new('ShaderNodeNewGeometry')
    sep = N.new('ShaderNodeSeparateXYZ')
    N.link(geo.outputs['Normal'], sep.inputs[0])
    col, h = bs.mossy_stone(N, geo.outputs['Position'], sep.outputs['Z'], seed=seed)
    N.principled(N.dapple(col, geo.outputs['Position']), rough=0.9, normal=N.bump(h, 0.5, 0.05))
    _mats[name] = mat
    return mat


def flat_mat(name, rgb, rough=0.8, metallic=0.0):
    if name in _mats:
        return _mats[name]
    mat = bpy.data.materials.new(name)
    N = bs.Nodes(mat)
    rgbn = N.new('ShaderNodeRGB')
    rgbn.outputs[0].default_value = (*(c * ALBEDO for c in rgb), 1.0)
    p = N.principled(N.dapple(rgbn.outputs[0], N.position()), rough=rough)
    p.inputs['Metallic'].default_value = metallic
    _mats[name] = mat
    return mat


def calibrate_lit_ground():
    """Measure how bright fully-lit ground is under THIS Blender's sun and sky, so the shadow
    catcher can turn 'darker than lit' into alpha. Robust across EEVEE versions."""
    scene = bpy.context.scene
    saved = (scene.view_settings.view_transform, scene.view_settings.look, scene.render.film_transparent,
             scene.render.resolution_x, scene.render.resolution_y)
    mat = bpy.data.materials.new("Calibrate")
    N = bs.Nodes(mat)
    diff = N.new('ShaderNodeBsdfDiffuse')
    diff.inputs['Color'].default_value = (1, 1, 1, 1)
    to_rgb = N.new('ShaderNodeShaderToRGB')
    N.link(diff.outputs[0], to_rgb.inputs[0])
    em = N.new('ShaderNodeEmission')
    N.link(N.math('MULTIPLY', N.math('ADD', to_rgb.outputs['Color'], 0.0), 0.1), em.inputs['Strength'])
    out = N.new('ShaderNodeOutputMaterial')
    N.link(em.outputs[0], out.inputs['Surface'])
    me = bpy.data.meshes.new("CalPlane")
    me.from_pydata([(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("CalPlane", me)
    ob.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.render.film_transparent = False
    bs.camera(0, 0, 0.25, px_per_unit=16)
    path = os.path.join(OUT, "_calibrate.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    px = list(img.pixels[:4])
    bpy.data.images.remove(img)
    os.remove(path)
    bpy.data.objects.remove(ob, do_unlink=True)
    srgb = sum(px[:3]) / 3
    linear = ((srgb + 0.055) / 1.055) ** 2.4 if srgb > 0.04045 else srgb / 12.92
    lit = linear / 0.1
    (scene.view_settings.view_transform, scene.view_settings.look, scene.render.film_transparent,
     scene.render.resolution_x, scene.render.resolution_y) = saved
    print(f"calibrated lit ground luminance = {lit:.3f}", flush=True)
    return lit


def shadow_catcher_mat(lit):
    """Ground that is invisible where lit and darkens where shadowed (alpha from lighting)."""
    mat = bpy.data.materials.new("ShadowCatcher")
    bs._set(mat, "blend_method", 'BLEND')
    bs._set(mat, "surface_render_method", 'BLENDED')
    bs._set(mat, "shadow_method", 'NONE')
    N = bs.Nodes(mat)
    diff = N.new('ShaderNodeBsdfDiffuse')
    diff.inputs['Color'].default_value = (1, 1, 1, 1)
    to_rgb = N.new('ShaderNodeShaderToRGB')
    N.link(diff.outputs[0], to_rgb.inputs[0])
    lum = N.math('ADD', to_rgb.outputs['Color'], 0.0)
    darkness = N.math('SUBTRACT', 1.0, N.math('DIVIDE', lum, lit))
    alpha = N.math('MULTIPLY', N.smooth(0.06, 0.7, darkness), SHADOW_OPACITY)
    transp = N.new('ShaderNodeBsdfTransparent')
    shade = N.new('ShaderNodeEmission')
    shade.inputs['Color'].default_value = (0.02, 0.025, 0.04, 1)
    mix = N.new('ShaderNodeMixShader')
    N.link(alpha, mix.inputs['Fac'])
    N.link(transp.outputs[0], mix.inputs[1])
    N.link(shade.outputs[0], mix.inputs[2])
    out = N.new('ShaderNodeOutputMaterial')
    N.link(mix.outputs[0], out.inputs['Surface'])
    return mat


# --------------------------------------------------------------------------- geometry helpers

def _finish(obj, mat, loc=None, rot=None, scale=None):
    if loc is not None:
        obj.location = loc
    if rot is not None:
        obj.rotation_euler = rot
    if scale is not None:
        obj.scale = scale
    if mat is not None:
        obj.data.materials.append(mat)
    obj["sprite_part"] = True
    return obj


def ico(r, loc, mat, subdiv=2, scale=(1, 1, 1), rough=0.0, seed=0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=r, location=loc)
    obj = bpy.context.active_object
    if rough > 0:
        tex = bpy.data.textures.new(f"disp{seed}", type='CLOUDS')
        tex.noise_scale = 0.6 * r
        mod = obj.modifiers.new("Displace", 'DISPLACE')
        mod.texture = tex
        mod.strength = rough * r
        mod.texture_coords = 'GLOBAL'
        obj.location = loc
    return _finish(obj, mat, scale=scale)


def cyl(r, depth, loc, mat, rot=(0, 0, 0), verts=8, r2=None):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=depth, location=loc, rotation=rot)
    return _finish(bpy.context.active_object, mat)


def cone(r, depth, loc, mat, verts=9, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=0, depth=depth, location=loc, rotation=rot)
    return _finish(bpy.context.active_object, mat)


def box(size, loc, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.scale = size
    return _finish(obj, mat)


def mesh_obj(name, verts, faces, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return _finish(obj, mat)


def gable_roof(w, d, h, z, mat, loc=(0, 0), ridge_axis='x', hole=None):
    """Gable roof over a w x d footprint. hole=(cx, cy, r) removes faces near that point."""
    x0, y0 = loc
    if ridge_axis == 'x':
        verts = [(x0 - w / 2, y0 - d / 2, z), (x0 + w / 2, y0 - d / 2, z), (x0 + w / 2, y0 + d / 2, z),
                 (x0 - w / 2, y0 + d / 2, z), (x0 - w / 2, y0, z + h), (x0 + w / 2, y0, z + h)]
        quads = [(0, 1, 5, 4), (2, 3, 4, 5)]
        tris = [(0, 4, 3), (1, 2, 5)]
    else:
        verts = [(x0 - w / 2, y0 - d / 2, z), (x0 + w / 2, y0 - d / 2, z), (x0 + w / 2, y0 + d / 2, z),
                 (x0 - w / 2, y0 + d / 2, z), (x0, y0 - d / 2, z + h), (x0, y0 + d / 2, z + h)]
        quads = [(1, 2, 5, 4), (3, 0, 4, 5)]
        tris = [(0, 1, 4), (2, 3, 5)]
    obj = mesh_obj("roof", verts, quads + tris, mat)
    sub = obj.modifiers.new("sub", 'SUBSURF')            # finer faces so a hole can be cut
    sub.subdivision_type = 'SIMPLE'
    sub.levels = sub.render_levels = 4
    if hole is not None:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier="sub")
        me = obj.data
        hx, hy, hr = hole
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        rng = random.Random(7)
        kill = [f for f in bm.faces
                if (Vector((f.calc_center_median().x, f.calc_center_median().y)) - Vector((hx, hy))).length
                < hr * (0.75 + 0.5 * rng.random())]
        bmesh.ops.delete(bm, geom=kill, context='FACES')
        bm.to_mesh(me)
        bm.free()
    return obj


# --------------------------------------------------------------------------- models

def leafy_crown(rng, center, radius, height, n, mats, clump=(0.2, 0.32), core_mat=None):
    """Many small, rough leaf clusters around a dark core: lumpy canopy with shadowed gaps."""
    if core_mat is not None:
        ico(radius * 0.72, (center[0], center[1], height - 0.15 * radius), core_mat, subdiv=2,
            scale=(1, 1, 0.6), rough=0.3, seed=rng.randint(0, 9999))
    for i in range(n):
        a = rng.uniform(0, math.tau)
        d = radius * (rng.random() ** 0.6) * 0.82
        r = radius * rng.uniform(*clump)
        z = height + (1 - d / radius) * 0.45 * radius + rng.uniform(-0.1, 0.12) * radius
        ico(r, (center[0] + math.cos(a) * d, center[1] + math.sin(a) * d, z), rng.choice(mats),
            subdiv=2, scale=(1, 1, 0.7), rough=0.6, seed=rng.randint(0, 9999))


def m_oak(seed):
    rng = random.Random(seed)
    bark = noise_mat("bark", [(0.3, (0.08, 0.055, 0.035)), (0.7, (0.17, 0.12, 0.07))], 8)
    leaves = [leaf_mat(f"oak_leaf{i}", s) for i, s in enumerate([
        [(0.2, (0.012, 0.03, 0.006)), (0.8, (0.05, 0.10, 0.015))],
        [(0.2, (0.010, 0.027, 0.008)), (0.8, (0.04, 0.085, 0.02))],
        [(0.2, (0.018, 0.035, 0.006)), (0.8, (0.07, 0.115, 0.018))]])]
    core = leaf_mat("leaf_core", [(0.3, (0.006, 0.014, 0.004)), (0.7, (0.02, 0.04, 0.01))])
    h = rng.uniform(3.2, 3.8)
    cyl(0.16, h, (0, 0, h / 2), bark, verts=7)
    leafy_crown(rng, (0, 0), rng.uniform(1.4, 1.7), h + 0.4, rng.randint(22, 28), leaves, core_mat=core)


def m_pine(seed):
    rng = random.Random(seed)
    bark = noise_mat("bark_pine", [(0.3, (0.09, 0.06, 0.04)), (0.7, (0.18, 0.11, 0.07))], 8)
    needles = [leaf_mat("pine_needle", [(0.2, (0.006, 0.02, 0.012)), (0.8, (0.025, 0.06, 0.035))], scale=22),
               leaf_mat("pine_needle2", [(0.2, (0.008, 0.024, 0.014)), (0.8, (0.03, 0.07, 0.04))], scale=22)]
    h = rng.uniform(5.0, 6.0)
    cyl(0.12, h, (0, 0, h / 2), bark, verts=6)
    layers = 6
    for i in range(layers):
        t = i / (layers - 1)
        r = 1.3 * (1 - t) + 0.2
        z = 1.0 + t * (h - 1.0)
        star_cone(rng, r, 1.2, z, rng.choice(needles), points=rng.choice((11, 12, 13)))


def star_cone(rng, r, depth, z, mat, points=12):
    """A cone with a jagged star-shaped base: from above, layers of drooping branch tips."""
    verts = [(0, 0, z + depth)]
    rot = rng.uniform(0, math.tau)
    for k in range(points * 2):
        a = rot + k * math.pi / points
        rr = r * (1.0 if k % 2 == 0 else rng.uniform(0.55, 0.7)) * rng.uniform(0.9, 1.08)
        verts.append((math.cos(a) * rr, math.sin(a) * rr, z - (0.12 if k % 2 == 0 else 0.0)))
    n = points * 2
    faces = [(0, 1 + k, 1 + (k + 1) % n) for k in range(n)]
    faces.append(tuple(range(n, 0, -1)))
    return mesh_obj("pine_layer", verts, faces, mat)


def m_birch(seed):
    rng = random.Random(seed)
    bark = noise_mat("birch_bark", [(0.4, (0.55, 0.55, 0.52)), (0.6, (0.12, 0.11, 0.1)), (0.7, (0.62, 0.61, 0.58))], 14)
    leaves = [leaf_mat("birch_leaf", [(0.2, (0.03, 0.055, 0.01)), (0.8, (0.10, 0.15, 0.03))]),
              leaf_mat("birch_leaf2", [(0.2, (0.04, 0.065, 0.012)), (0.8, (0.13, 0.17, 0.04))])]
    core = leaf_mat("birch_core", [(0.3, (0.01, 0.02, 0.005)), (0.7, (0.03, 0.05, 0.012))])
    h = rng.uniform(3.6, 4.2)
    cyl(0.09, h, (0, 0, h / 2), bark, verts=6)
    leafy_crown(rng, (0.1, 0), rng.uniform(1.0, 1.2), h + 0.2, rng.randint(14, 18), leaves,
                clump=(0.18, 0.28), core_mat=core)


def m_snag(seed):
    rng = random.Random(seed)
    dead = noise_mat("deadwood", [(0.3, (0.16, 0.14, 0.12)), (0.7, (0.32, 0.29, 0.25))], 9)
    h = rng.uniform(3.0, 3.8)
    cyl(0.17, h, (0, 0, h / 2), dead, verts=6, r2=0.08)
    for i in range(rng.randint(4, 6)):
        a = rng.uniform(0, math.tau)
        z = rng.uniform(1.5, h - 0.3)
        L = rng.uniform(0.6, 1.2)
        tilt = rng.uniform(0.6, 1.1)
        dx, dy = math.cos(a) * math.sin(tilt) * L / 2, math.sin(a) * math.sin(tilt) * L / 2
        cyl(0.05, L, (dx, dy, z + math.cos(tilt) * L / 2), dead, verts=5, r2=0.015,
            rot=(0, tilt, a))


def m_berry_bush(seed):
    rng = random.Random(seed)
    leaf = leaf_mat("bush_leaf", [(0.2, (0.012, 0.03, 0.01)), (0.8, (0.045, 0.09, 0.02))])
    berry = flat_mat("berry_red" if seed % 2 == 0 else "berry_dark",
                     (0.45, 0.03, 0.05) if seed % 2 == 0 else (0.12, 0.05, 0.22), rough=0.35)
    parts = []
    for i in range(rng.randint(5, 7)):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0, 0.35)
        r = rng.uniform(0.25, 0.38)
        parts.append((math.cos(a) * d, math.sin(a) * d, 0.3 + rng.uniform(0, 0.15), r))
        ico(r, parts[-1][:3], leaf, subdiv=2, scale=(1, 1, 0.8), rough=0.4, seed=rng.randint(0, 9999))
    for i in range(26):
        px, py, pz, r = rng.choice(parts)
        a, e = rng.uniform(0, math.tau), rng.uniform(0.3, 1.2)
        ico(0.045, (px + math.cos(a) * math.cos(e) * r, py + math.sin(a) * math.cos(e) * r,
                    pz + math.sin(e) * r * 0.8), berry, subdiv=1)


def m_fern(seed):
    rng = random.Random(seed)
    frond = noise_mat("fern", [(0.2, (0.02, 0.05, 0.012)), (0.8, (0.06, 0.12, 0.025))], 8)
    n = rng.randint(8, 11)
    for i in range(n):
        a = i / n * math.tau + rng.uniform(-0.2, 0.2)
        L = rng.uniform(0.55, 0.8)
        verts, faces = [], []
        segs = 6
        for s in range(segs + 1):
            t = s / segs
            w = 0.12 * math.sin(math.pi * min(1, t * 1.1)) + 0.01
            z = 0.05 + 0.35 * math.sin(math.pi * t * 0.8)
            verts += [(t * L, -w, z), (t * L, w, z)]
            if s:
                k = 2 * s
                faces.append((k - 2, k - 1, k + 1, k))
        o = mesh_obj("frond", verts, faces, frond)
        o.rotation_euler = (0, 0, a)


def m_mushrooms(seed):
    rng = random.Random(seed)
    stem = flat_mat("mush_stem", (0.62, 0.58, 0.48), rough=0.6)
    if seed % 2 == 0:
        cap = noise_mat("cap_red", [(0.55, (0.42, 0.04, 0.03)), (0.62, (0.75, 0.72, 0.62)), (0.7, (0.42, 0.04, 0.03))], 22)
    else:
        cap = noise_mat("cap_brown", [(0.3, (0.22, 0.13, 0.06)), (0.8, (0.40, 0.26, 0.12))], 6)
    for i in range(rng.randint(3, 6)):
        a, d = rng.uniform(0, math.tau), rng.uniform(0, 0.22)
        x, y = math.cos(a) * d, math.sin(a) * d
        h = rng.uniform(0.07, 0.16)
        r = rng.uniform(0.05, 0.1)
        cyl(r * 0.3, h, (x, y, h / 2), stem, verts=6)
        ico(r, (x, y, h), cap, subdiv=2, scale=(1, 1, 0.55))


def m_rock(seed):
    rng = random.Random(seed)
    mat = mossy_mat(f"mossy_stone{seed % 3}", seed=float(seed))
    r = rng.uniform(0.45, 0.8)
    ico(r, (0, 0, r * 0.25), mat, subdiv=3, scale=(1.0, rng.uniform(0.7, 0.95), 0.6), rough=0.45, seed=seed)
    for i in range(rng.randint(1, 3)):
        a = rng.uniform(0, math.tau)
        rr = r * rng.uniform(0.25, 0.45)
        ico(rr, (math.cos(a) * r * 1.0, math.sin(a) * r * 0.9, rr * 0.2), mat, subdiv=2,
            scale=(1, 0.85, 0.6), rough=0.4, seed=seed + i + 1)


def m_log(seed, size=1.0):
    rng = random.Random(seed)
    bark = log_mat()
    end = noise_mat("end_grain", [(0.3, (0.30, 0.20, 0.10)), (0.5, (0.42, 0.30, 0.16)), (0.7, (0.26, 0.17, 0.09))], 18)
    L = rng.uniform(2.2, 2.8) * size
    r = rng.uniform(0.2, 0.28) * size
    ang = rng.uniform(-0.4, 0.4)
    EXTRA["footprint"] = {"length_m": round(L * bs.WORLD_METRES_PER_TILE, 2),
                          "width_m": round(2 * r * bs.WORLD_METRES_PER_TILE, 2),
                          "angle_deg": round(math.degrees(ang), 1)}     # counter-clockwise from east
    cyl(r, L, (0, 0, r * 0.85), bark, rot=(0, math.pi / 2, ang), verts=9)
    for sgn in (-1, 1):
        cx, cy = sgn * math.cos(ang) * L / 2, sgn * math.sin(ang) * L / 2
        cyl(r * 0.92, 0.02, (cx, cy, r * 0.85), end, rot=(0, math.pi / 2, ang), verts=9)
    for i in range(2):
        t = rng.uniform(-0.3, 0.3) * L
        cyl(0.05, 0.4, (math.cos(ang) * t, math.sin(ang) * t + 0.15, r * 1.5), bark,
            rot=(0.6, 0, ang), verts=5, r2=0.02)


def m_lily_pads(seed):
    rng = random.Random(seed)
    pad = noise_mat("lily_pad", [(0.2, (0.025, 0.07, 0.02)), (0.8, (0.06, 0.13, 0.03))], 9, rough=0.4)
    petal = flat_mat("lily_flower", (0.85, 0.80, 0.82), rough=0.5)
    for i in range(rng.randint(4, 6)):
        a, d = rng.uniform(0, math.tau), rng.uniform(0, 0.45)
        r = rng.uniform(0.12, 0.2)
        notch = rng.uniform(0, math.tau)
        verts = [(0, 0, 0)]
        steps = 16
        for s in range(steps + 1):
            t = notch + 0.35 + s / steps * (math.tau - 0.7)
            verts.append((math.cos(t) * r, math.sin(t) * r, 0))
        faces = [(0, k, k + 1) for k in range(1, steps + 1)]
        o = mesh_obj("pad", verts, faces, pad)
        o.location = (math.cos(a) * d, math.sin(a) * d, 0.01)
    if seed % 2 == 0:
        for k in range(7):
            t = k / 7 * math.tau
            cone(0.045, 0.06, (0.05 + math.cos(t) * 0.04, 0.05 + math.sin(t) * 0.04, 0.05), petal,
                 verts=4, rot=(math.cos(t) * 0.9, math.sin(t) * 0.9, 0))


# ---- named places: the campsite ------------------------------------------------------

def m_fire_pit(seed):
    rng = random.Random(seed)
    stone = mossy_mat("pit_stone", seed=9.0)
    ash = noise_mat("ash", [(0.3, (0.08, 0.075, 0.07)), (0.7, (0.30, 0.29, 0.27))], 10)
    char = noise_mat("charcoal", [(0.3, (0.02, 0.02, 0.02)), (0.7, (0.10, 0.08, 0.07))], 12)
    cyl(0.42, 0.02, (0, 0, 0.01), ash, verts=16)
    for k in range(10):
        t = k / 10 * math.tau + rng.uniform(-0.1, 0.1)
        ico(rng.uniform(0.11, 0.15), (math.cos(t) * 0.52, math.sin(t) * 0.52, 0.05), stone, subdiv=2,
            scale=(1, 0.85, 0.7), rough=0.3, seed=k)
    for k in range(4):
        a = k / 4 * math.pi + rng.uniform(-0.2, 0.2)
        cyl(0.04, 0.55, (0, 0, 0.06), char, rot=(0, math.pi / 2 - 0.25, a), verts=6)


def m_collapsed_tent(seed):
    canvas = noise_mat("tent_canvas", [(0.3, (0.19, 0.24, 0.17)), (0.7, (0.29, 0.33, 0.24))], 5, rough=0.9)
    pole = flat_mat("tent_pole", (0.3, 0.3, 0.3), rough=0.4, metallic=0.6)
    # Ridge tent with one end collapsed: the ridge drops from 0.55 to 0.08.
    verts = [(-0.9, -0.55, 0.0), (0.9, -0.55, 0.0), (0.9, 0.55, 0.0), (-0.9, 0.55, 0.0),
             (-0.9, 0.0, 0.55), (0.9, 0.0, 0.08), (0.0, -0.62, 0.02), (0.0, 0.62, 0.03)]
    faces = [(0, 6, 4), (6, 1, 5, 4), (3, 4, 7), (7, 4, 5, 2), (0, 4, 3)]
    o = mesh_obj("tent", verts, faces, canvas)
    sub = o.modifiers.new("sub", 'SUBSURF')
    sub.levels = sub.render_levels = 2
    tex = bpy.data.textures.new("tentwrinkle", type='CLOUDS')
    tex.noise_scale = 0.25
    d = o.modifiers.new("wrinkle", 'DISPLACE')
    d.texture = tex
    d.strength = 0.05
    cyl(0.015, 0.6, (-0.95, 0, 0.28), pole, verts=5)


def m_bedroll(seed):
    roll = noise_mat("bedroll", [(0.3, (0.22, 0.10, 0.06)), (0.7, (0.34, 0.16, 0.09))], 7)
    strap = flat_mat("strap", (0.08, 0.07, 0.06))
    cyl(0.13, 0.75, (0, 0, 0.13), roll, rot=(0, math.pi / 2, 0.3), verts=10)
    for t in (-0.2, 0.2):
        cyl(0.14, 0.04, (math.cos(0.3) * t, math.sin(0.3) * t, 0.13), strap, rot=(0, math.pi / 2, 0.3), verts=10)


def m_backpack(seed):
    pack = noise_mat("pack", [(0.3, (0.12, 0.14, 0.10)), (0.7, (0.20, 0.22, 0.15))], 6)
    strap = flat_mat("strap", (0.08, 0.07, 0.06))
    o = box((0.4, 0.28, 0.2), (0, 0, 0.1), pack, rot=(0, 0, 0.5))
    o.modifiers.new("bevel", 'BEVEL').width = 0.05
    box((0.3, 0.06, 0.04), (0.05, -0.12, 0.2), strap, rot=(0, 0, 0.5))


def m_log_seat(seed):
    m_log(seed + 100, size=0.55)


# ---- named places: the bridge --------------------------------------------------------

def m_bridge(seed, along='x'):
    """Old plank footbridge over the stream, 4 tiles (8 m) long. Weathered; two planks missing."""
    rng = random.Random(seed)
    wood = noise_mat("bridge_wood", [(0.3, (0.16, 0.11, 0.07)), (0.7, (0.30, 0.22, 0.14))], 6)
    wood_old = noise_mat("bridge_wood_old", [(0.3, (0.12, 0.10, 0.08)), (0.7, (0.24, 0.20, 0.16))], 6)
    L, W = 4.0, 1.1
    missing = {5, 13}
    n = 20
    for i in range(n):
        if i in missing:
            continue
        t = -L / 2 + (i + 0.5) * L / n
        rot = rng.uniform(-0.04, 0.04)
        size = (L / n * 0.86, W, 0.06) if along == 'x' else (W, L / n * 0.86, 0.06)
        loc = (t, 0, 0.35) if along == 'x' else (0, t, 0.35)
        box(size, loc, rng.choice((wood, wood_old)), rot=(0, 0, rot))
    for side in (-1, 1):
        for i in range(5):
            t = -L / 2 + i * L / 4
            loc = (t, side * W / 2, 0.55) if along == 'x' else (side * W / 2, t, 0.55)
            box((0.1, 0.1, 0.5), loc, wood_old)
        if not (side == 1):                     # one rail fell into the stream
            size = (L, 0.07, 0.07) if along == 'x' else (0.07, L, 0.07)
            loc = (0, side * W / 2, 0.8) if along == 'x' else (side * W / 2, 0, 0.8)
            box(size, loc, wood_old)


# ---- named places: the abandoned town ------------------------------------------------

def _walls(w, d, h, mat):
    box((w, d, h), (0, 0, h / 2), mat)


def m_town_hall(seed):
    wall = noise_mat("hall_wall", [(0.3, (0.42, 0.38, 0.32)), (0.7, (0.55, 0.50, 0.42))], 3)
    slate = noise_mat("slate", [(0.3, (0.13, 0.14, 0.16)), (0.7, (0.24, 0.25, 0.27))], 14)
    _walls(6.0, 4.6, 2.6, wall)
    # Hip roof: a squashed pyramid.
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=4.1, radius2=1.2, depth=1.6, location=(0, 0, 3.4),
                                    rotation=(0, 0, math.pi / 4))
    roof = _finish(bpy.context.active_object, slate)
    roof.scale = (1.0, 0.77, 1.0)
    # Bell cupola.
    box((0.7, 0.7, 0.8), (0, 0, 4.6), wall)
    cone(0.6, 0.6, (0, 0, 5.3), slate, verts=4, rot=(0, 0, math.pi / 4))
    # Front steps (south).
    for k in range(3):
        box((1.6 - 0.2 * k, 0.3, 0.12 * (k + 1)), (0, -2.45 - 0.3 * (2 - k), 0.06 * (k + 1)), wall)


def m_farmhouse(seed):
    wall = noise_mat("farm_wall", [(0.3, (0.40, 0.36, 0.30)), (0.7, (0.52, 0.47, 0.38))], 3)
    shingle = shingle_mat("shingle", (0.075, 0.052, 0.04))
    dark = flat_mat("interior_dark", (0.03, 0.025, 0.02))
    rafter = flat_mat("rafter", (0.22, 0.15, 0.09))
    _walls(5.0, 3.6, 2.2, wall)
    box((4.9, 3.5, 0.02), (0, 0, 2.23), dark)                         # attic floor, seen through the hole
    # Roof condition ~0.3: a ragged hole on the south slope, rafters showing.
    gable_roof(5.4, 4.0, 1.6, 2.2, shingle, ridge_axis='x', hole=(1.2, -0.9, 0.9))
    for k in range(4):
        x = 0.5 + k * 0.5
        box((0.08, 2.0, 0.08), (x, -1.0, 2.95), rafter, rot=(-math.atan2(1.6, 2.0), 0, 0))
    box((0.5, 0.5, 1.2), (-1.6, 0.6, 3.6), noise_mat("chimney_stone", [(0.3, (0.05, 0.045, 0.042)), (0.7, (0.10, 0.09, 0.085))], 20))
    # Porch on the south side.
    box((3.0, 0.9, 0.1), (0, -2.3, 0.15), rafter)
    gable_roof(3.2, 1.0, 0.2, 1.9, shingle, loc=(0, -2.3), ridge_axis='x')


def m_general_store(seed):
    wall = noise_mat("store_wall", [(0.3, (0.36, 0.31, 0.24)), (0.7, (0.48, 0.41, 0.31))], 3)
    tar = noise_mat("tar_roof", [(0.3, (0.07, 0.07, 0.07)), (0.6, (0.14, 0.13, 0.12)), (0.8, (0.22, 0.2, 0.17))], 5, rough=0.6)
    awning = noise_mat("awning", [(0.45, (0.45, 0.14, 0.10)), (0.5, (0.65, 0.60, 0.52)), (0.55, (0.45, 0.14, 0.10))], 40)
    _walls(5.0, 3.6, 2.6, wall)
    box((5.0, 3.6, 0.1), (0, 0, 2.65), tar)
    for sx in (-1, 1):
        box((0.12, 3.6, 0.35), (sx * 2.45, 0, 2.8), wall)               # parapet
    box((5.0, 0.12, 0.35), (0, 1.75, 2.8), wall)
    box((5.0, 0.12, 0.6), (0, -1.75, 2.9), wall)                        # false front
    # Torn awning over the front (south): one section sags.
    box((1.6, 0.9, 0.04), (-1.5, -2.2, 2.0), awning, rot=(0.25, 0, 0))
    box((1.6, 0.9, 0.04), (0.2, -2.2, 2.0), awning, rot=(0.25, 0, 0))
    box((1.4, 0.9, 0.04), (1.7, -2.15, 1.6), awning, rot=(0.7, 0.1, 0))


def m_garage(seed):
    wall = noise_mat("garage_wall", [(0.3, (0.33, 0.33, 0.31)), (0.7, (0.45, 0.44, 0.41))], 3)
    tin = noise_mat("corrugated", [(0.35, (0.30, 0.31, 0.32)), (0.55, (0.36, 0.20, 0.10)), (0.75, (0.40, 0.41, 0.42))], 3, rough=0.5, metallic=0.5)
    stain = flat_mat("oil", (0.03, 0.03, 0.03), rough=0.2)
    _walls(5.0, 4.0, 2.4, wall)
    for k in range(20):                                               # corrugation ridges
        x = -2.6 + k * 0.27
        box((0.12, 4.4, 0.06), (x, 0, 2.5 + 0.04 * (k % 2)), tin, rot=(0.12, 0, 0))
    box((3.0, 0.6, 0.01), (0, -2.4, 0.005), stain)                     # oil-stained apron


def m_water_tower(seed):
    steel = noise_mat("tower_steel", [(0.3, (0.20, 0.13, 0.08)), (0.5, (0.34, 0.33, 0.30)), (0.8, (0.42, 0.40, 0.36))], 5, rough=0.55, metallic=0.4)
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        cyl(0.07, 5.0, (sx * 0.65, sy * 0.65, 2.5), steel, verts=6, rot=(sy * 0.07, -sx * 0.07, 0))
    cyl(0.95, 1.6, (0, 0, 5.8), steel, verts=16)
    cone(1.05, 0.7, (0, 0, 6.95), steel, verts=16)
    for k in range(10):                                               # ladder (rungs missing near top)
        if k in (8, 9):
            continue
        box((0.3, 0.03, 0.03), (0.98, 0, 0.5 + k * 0.5), steel, rot=(0, 0, math.pi / 2))


# --------------------------------------------------------------------------- catalogue
# id -> builder, seeds, meaning. `truth` is world truth (Wren never reads it);
# `appearance` is what perception can reveal, by fidelity (see docs/architecture/05 §2).

def V(look, inspect=None, glimpse=None):
    a = {"look": look}
    if inspect:
        a["inspect"] = inspect
    if glimpse:
        a["glimpse"] = glimpse
    return a


CATALOG = [
    # id, builder, seeds, layer, footprint (metres), blocks, meaning
    ("oak", m_oak, [1, 2, 3], "canopy", {"trunk_radius_m": 0.35}, True,
     {"kind": "tree", "species": "oak", "truth": {"wood_yield": 6, "shade": True},
      "affordances": ["chop", "shelter_from_sun"], "appearance": V(["broad leafy tree"], ["rough bark", "acorns underfoot"], ["tree"])}),
    ("pine", m_pine, [1, 2, 3], "canopy", {"trunk_radius_m": 0.3}, True,
     {"kind": "tree", "species": "pine", "truth": {"wood_yield": 5, "resin": True},
      "affordances": ["chop", "gather_kindling"], "appearance": V(["tall dark conifer"], ["sticky resin", "pine needles"], ["tree"])}),
    ("birch", m_birch, [1, 2], "canopy", {"trunk_radius_m": 0.2}, True,
     {"kind": "tree", "species": "birch", "truth": {"wood_yield": 3, "bark_is_tinder": True},
      "affordances": ["chop", "strip_bark"], "appearance": V(["slender pale-barked tree"], ["papery white bark"], ["tree"])}),
    ("snag", m_snag, [1, 2], "canopy", {"trunk_radius_m": 0.35}, True,
     {"kind": "tree", "species": "dead_snag", "truth": {"wood_yield": 4, "dry_wood": True, "may_fall": 0.02},
      "affordances": ["chop", "gather_firewood"], "appearance": V(["dead grey tree, bare branches"], ["dry cracked wood"], ["tree"])}),
    ("berry_bush", m_berry_bush, [1, 2, 3], "ground", {"radius_m": 0.8}, True,
     {"kind": "plant", "species": "berry_bush", "truth": {"edible": None, "note": "seed 1,3: red (edible raspberry-like); seed 2: dark (mildly toxic)"},
      "affordances": ["forage"], "appearance": V(["low bush with small berries"], ["red berries", "thorny stems"])}),
    ("fern", m_fern, [1, 2, 3], "ground", {"radius_m": 0.5}, False,
     {"kind": "plant", "species": "fern", "truth": {"edible": False},
      "affordances": [], "appearance": V(["fern fronds"])}),
    ("mushrooms", m_mushrooms, [1, 2], "ground", {"radius_m": 0.3}, False,
     {"kind": "fungus", "species": "mushrooms", "truth": {"edible": None, "note": "seed 2 red-spotted: toxic; seed 1 brown: edible"},
      "affordances": ["forage"], "appearance": V(["cluster of mushrooms"], ["caps and gills", "earthy smell"])}),
    ("mossy_rock", m_rock, [1, 2, 3], "ground", {"radius_m": 1.2}, True,
     {"kind": "rock", "truth": {"material": "granite"},
      "affordances": ["sit", "climb", "gather_stones"], "appearance": V(["moss-covered boulder"], ["cold damp stone"])}),
    ("fallen_log", m_log, [1, 2], "ground", {"length_m": 5.0, "radius_m": 0.5}, True,
     {"kind": "deadwood", "truth": {"wood_yield": 3, "rotten": 0.4, "insects": True},
      "affordances": ["sit", "gather_firewood", "search_under"], "appearance": V(["fallen mossy log"], ["soft rotting wood", "beetles"])}),
    ("lily_pads", m_lily_pads, [1, 2], "water_surface", {"radius_m": 1.0}, False,
     {"kind": "plant", "species": "water_lily", "truth": {"edible_roots": True},
      "affordances": [], "appearance": V(["floating round leaves"], ["white flower"])}),
    # Named places
    ("campsite_fire_pit", m_fire_pit, [1], "ground", {"radius_m": 1.2}, False,
     {"kind": "prop", "place": "campsite", "truth": {"ash_age_hours": 10},
      "affordances": ["build_fire", "warm_up"], "appearance": V(["ring of stones around ash"], ["ash still faintly warm"])}),
    ("campsite_tent", m_collapsed_tent, [1], "ground", {"rect_m": [3.6, 2.2]}, True,
     {"kind": "prop", "place": "campsite", "truth": {"condition": 0.3, "repairable": True},
      "affordances": ["search", "repair", "shelter"], "appearance": V(["half-collapsed green tent"], ["one pole snapped"])}),
    ("campsite_bedroll", m_bedroll, [1], "ground", {"radius_m": 0.6}, False,
     {"kind": "prop", "place": "campsite", "truth": {"damp": True}, "affordances": ["sleep", "pick_up"],
      "appearance": V(["rolled bedroll"])}),
    ("campsite_backpack", m_backpack, [1], "ground", {"radius_m": 0.4}, False,
     {"kind": "container", "place": "campsite", "truth": {"contains_lore_clues": True},
      "affordances": ["search", "pick_up"], "appearance": V(["worn backpack"], ["soaked inside"])}),
    ("campsite_log_seat", m_log_seat, [1], "ground", {"length_m": 2.8, "radius_m": 0.3}, False,
     {"kind": "prop", "place": "campsite", "affordances": ["sit"], "appearance": V(["short log used as a seat"])}),
    ("bridge_ew", lambda s: m_bridge(s, 'x'), [1], "ground", {"rect_m": [8.0, 2.2]}, False,
     {"kind": "structure", "place": "bridge", "truth": {"integrity": 0.25, "walkable": True, "may_collapse": True},
      "affordances": ["cross", "repair"], "appearance": V(["old plank footbridge"], ["planks soft and spongy", "two planks missing"])}),
    ("bridge_ns", lambda s: m_bridge(s, 'y'), [1], "ground", {"rect_m": [2.2, 8.0]}, False,
     {"kind": "structure", "place": "bridge", "truth": {"integrity": 0.25, "walkable": True, "may_collapse": True},
      "affordances": ["cross", "repair"], "appearance": V(["old plank footbridge"], ["planks soft and spongy", "two planks missing"])}),
    ("town_hall", m_town_hall, [1], "building", {"rect_m": [12.0, 9.2]}, True,
     {"kind": "building", "place": "town_hall", "truth": {"stage": "damaged", "records_room_locked": True},
      "affordances": ["enter", "search", "repair"], "appearance": V(["large stone building with a bell cupola"], ["records room door locked"])}),
    ("farmhouse", m_farmhouse, [1], "building", {"rect_m": [10.0, 7.2]}, True,
     {"kind": "building", "place": "farmhouse", "truth": {"stage": "damaged", "roof_condition": 0.3, "walls_condition": 0.7},
      "affordances": ["enter", "search", "repair", "shelter"], "appearance": V(["farmhouse with a hole in the roof"], ["rafters exposed", "hearth inside"])}),
    ("general_store", m_general_store, [1], "building", {"rect_m": [10.0, 7.2]}, True,
     {"kind": "building", "place": "general_store", "truth": {"stage": "damaged", "back_room_door_jammed": True},
      "affordances": ["enter", "search", "repair"], "appearance": V(["shop with a torn striped awning"], ["shelves mostly empty"])}),
    ("garage", m_garage, [1], "building", {"rect_m": [10.0, 8.0]}, True,
     {"kind": "building", "place": "garage", "truth": {"stage": "damaged", "contains_tools": True},
      "affordances": ["enter", "search", "repair"], "appearance": V(["garage with a rusty corrugated roof"], ["smell of old oil"])}),
    ("water_tower", m_water_tower, [1], "building", {"rect_m": [3.0, 3.0]}, True,
     {"kind": "structure", "place": "water_tower", "truth": {"tank_water_level": 0.0, "main_pipe_cracked": True, "ladder_top_broken": True},
      "affordances": ["climb", "inspect", "repair"], "appearance": V(["tall water tower on four legs"], ["rust streaks", "ladder rungs missing near the top"])}),
]


# --------------------------------------------------------------------------- rendering

def clear_parts():
    for o in list(bpy.context.scene.objects):
        if o.get("sprite_part"):
            bpy.data.objects.remove(o, do_unlink=True)


def bounds():
    deps = bpy.context.evaluated_depsgraph_get()
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for o in bpy.context.scene.objects:
        if not o.get("sprite_part"):
            continue
        ev = o.evaluated_get(deps)
        for c in ev.bound_box:
            w = ev.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def frame_and_render(path):
    lo, hi = bounds()
    shadow = max(hi.z, 0.0) * math.tan(math.radians(bs.SUN_TILT_DEG)) * 0.7071
    x0, x1 = lo.x - PAD, hi.x + shadow + PAD
    y0, y1 = lo.y - shadow - PAD, hi.y + PAD
    w = math.ceil((x1 - x0) * PX) / PX
    h = math.ceil((y1 - y0) * PX) / PX
    cx, cy = x0 + w / 2, y0 + h / 2
    bs.camera(cx, cy, w, px_per_unit=PX, span_y_units=h)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    wpx, hpx = int(round(w * PX)), int(round(h * PX))
    anchor = [round((0 - x0) * PX, 1), round((y1 - 0) * PX, 1)]     # ground point under the object
    return {"size_px": [wpx, hpx], "anchor_px": anchor, "height_m": round(hi.z * bs.WORLD_METRES_PER_TILE, 2)}


def main():
    os.makedirs(OUT, exist_ok=True)
    bs.reset_scene()
    plane = bpy.data.meshes.new("Ground")
    plane.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
    ground = bpy.data.objects.new("Ground", plane)
    ground.data.materials.append(shadow_catcher_mat(calibrate_lit_ground()))
    bpy.context.scene.collection.objects.link(ground)
    only = set(filter(None, ONLY.split(",")))
    index_path = os.path.join(OUT, "sprites.json")
    entries = {}
    if only and os.path.exists(index_path):
        entries = {e["id"]: e for e in json.load(open(index_path))["sprites"]}
    for sid, builder, seeds, layer, footprint, blocks, meaning in CATALOG:
        if only and sid not in only:
            continue
        for v, seed in enumerate(seeds):
            clear_parts()
            EXTRA.clear()
            builder(seed)
            name = f"{sid}_{v + 1}" if len(seeds) > 1 else sid
            info = frame_and_render(os.path.join(OUT, name + ".png"))
            entries[name] = {"id": name, "type": sid, "variant": v + 1, "file": f"sprites/{name}.png",
                             "layer": layer, "footprint": EXTRA.get("footprint", footprint), "blocks_movement": blocks,
                             **info, "meaning": meaning}
            print(f"sprite {name} {info['size_px']}", flush=True)
    doc = {"px_per_tile": PX, "world_metres_per_tile": bs.WORLD_METRES_PER_TILE,
           "anchor_note": "anchor_px = pixel (from top-left) of the ground point under the object; place it on the object's world position",
           "layers": {"ground": "under agents", "water_surface": "on water, under everything", "canopy": "above agents (fade when under)", "building": "y-sorted with agents"},
           "sprites": sorted(entries.values(), key=lambda e: e["id"])}
    with open(index_path, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"SPRITES_OK {len(entries)}", flush=True)


if __name__ == "__main__":
    main()
