"""Shared Blender scene for every render in the forest pipeline.

Imported by render_tiles.py, render_objects.py and render_wildlife.py, so the camera,
sun, sky, colour management and materials are IDENTICAL across all renders, which is
what makes tile seams and sprite lighting match.

Conventions
-----------
* 1 Blender unit = 1 tile = 2 metres in the world (see WORLD_METRES_PER_TILE).
* +X = east, +Y = north. The camera looks straight down (rotation 0,0,0), so image-up = north.
* Sun comes from the north-west, 30 degrees off vertical; shadows fall to the south-east.
* Every procedural texture is *tile-periodic*: x and y are wrapped onto a torus and fed to
  4D noise/voronoi, so any tile edge meets any other tile edge seamlessly.

Platform: Windows only. Blender for Windows bundles its own Python and numpy.
Run on its own to sanity-check (PowerShell, from the repo root):
    blender -b --factory-startup -P blender\build_scene.py

Blender versions: works with 4.0+ (EEVEE) and 4.2+ (EEVEE Next). Settings that only exist in
one of them are applied only if present (see _set).
"""
import math

import bpy

TILE_PX = 64                    # final pixel size of one tile (and of 1 Blender unit)
WORLD_METRES_PER_TILE = 2.0
SUN_TILT_DEG = 30.0             # off vertical
SUN_AZIMUTH_DEG = 225.0         # light travels toward the south-east (comes from the NW)
SUN_COLOR = (1.0, 0.90, 0.76)   # warm late-morning light
SUN_ENERGY = 3.2
SUN_SOFTNESS_DEG = 6.0          # angular size of the sun -> soft shadow edges
SKY_COLOR = (0.40, 0.46, 0.54)  # cool fill from the sky
SKY_STRENGTH = 0.75
DAPPLE_STRENGTH = 0.13          # faint canopy-dappled light on everything

TAU = 2.0 * math.pi


# --------------------------------------------------------------------------- scene setup

def _set(obj, attr, value):
    """Set a setting only if this Blender version has it (EEVEE and EEVEE Next differ)."""
    if hasattr(obj, attr):
        setattr(obj, attr, value)


def _eevee_engine():
    ids = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items}
    return 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in ids else 'BLENDER_EEVEE'


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = _eevee_engine()
    ee = scene.eevee
    ee.taa_render_samples = 48
    _set(ee, "use_soft_shadows", True)          # EEVEE (4.0/4.1)
    _set(ee, "shadow_cube_size", '2048')
    _set(ee, "shadow_cascade_size", '4096')
    _set(ee, "use_shadow_high_bitdepth", True)
    _set(ee, "use_gtao", True)                  # soft contact occlusion under objects
    _set(ee, "gtao_distance", 0.6)
    _set(ee, "use_shadows", True)               # EEVEE Next (4.2+)
    _set(ee, "shadow_ray_count", 3)
    _set(ee, "shadow_step_count", 12)
    scene.render.film_transparent = True
    scene.render.filter_size = 0.75
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0.0
    scene.display_settings.display_device = 'sRGB'
    _world()
    _sun()
    return scene


def _world():
    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*SKY_COLOR, 1.0)
    bg.inputs["Strength"].default_value = SKY_STRENGTH
    bpy.context.scene.world = world


def _sun():
    data = bpy.data.lights.new("Sun", type='SUN')
    data.energy = SUN_ENERGY
    data.color = SUN_COLOR
    data.angle = math.radians(SUN_SOFTNESS_DEG)
    _set(data, "use_contact_shadow", True)       # EEVEE (4.0/4.1) only
    _set(data, "contact_shadow_distance", 0.3)
    sun = bpy.data.objects.new("Sun", data)
    sun.rotation_euler = (math.radians(SUN_TILT_DEG), 0.0, math.radians(SUN_AZIMUTH_DEG))
    bpy.context.scene.collection.objects.link(sun)


def camera(center_x, center_y, span_units, px_per_unit=TILE_PX, span_y_units=None):
    """Orthographic camera looking straight down, framing span_units (x) by span_y_units (y)."""
    span_y_units = span_y_units or span_units
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.get("TopDown") or bpy.data.cameras.new("TopDown")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(span_units, span_y_units)
    cam_data.clip_start = 0.1
    cam_data.clip_end = 100.0
    cam = bpy.data.objects.get("TopDown")
    if cam is None:
        cam = bpy.data.objects.new("TopDown", cam_data)
        scene.collection.objects.link(cam)
    cam.location = (center_x, center_y, 40.0)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    scene.camera = cam
    scene.render.resolution_x = int(round(span_units * px_per_unit))
    scene.render.resolution_y = int(round(span_y_units * px_per_unit))
    scene.render.resolution_percentage = 100
    return cam


# --------------------------------------------------------------------------- node helpers

class Nodes:
    """Tiny helper around a material node tree to keep material code readable."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def new(self, kind, **props):
        n = self.nt.nodes.new(kind)
        n.location = (self.x, 0)
        self.x += 40
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def value(self, v):
        n = self.new('ShaderNodeValue')
        n.outputs[0].default_value = v
        return n.outputs[0]

    def math(self, op, a, b=None, clamp=False):
        n = self.new('ShaderNodeMath', operation=op, use_clamp=clamp)
        for i, s in enumerate((a, b)):
            if s is None:
                continue
            if isinstance(s, (int, float)):
                n.inputs[i].default_value = s
            else:
                self.link(s, n.inputs[i])
        return n.outputs[0]

    def smooth(self, lo, hi, x):
        n = self.new('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
        n.inputs['From Min'].default_value = lo
        n.inputs['From Max'].default_value = hi
        self.link(x, n.inputs['Value'])
        return n.outputs['Result']

    def mix_rgb(self, fac, a, b):
        n = self.new('ShaderNodeMix', data_type='RGBA', blend_type='MIX', clamp_factor=True)
        for idx, s in ((0, fac), (6, a), (7, b)):
            if isinstance(s, (int, float)):
                n.inputs[idx].default_value = s
            elif isinstance(s, tuple):
                n.inputs[idx].default_value = (*s[:3], 1.0)
            else:
                self.link(s, n.inputs[idx])
        return n.outputs[2]

    def mul_rgb(self, col, fac):
        n = self.new('ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY', clamp_factor=True)
        n.inputs[0].default_value = 1.0
        self.link(col, n.inputs[6])
        if isinstance(fac, (int, float)):
            n.inputs[7].default_value = (fac, fac, fac, 1.0)
        else:
            self.link(fac, n.inputs[7])
        return n.outputs[2]

    def ramp(self, x, stops):
        n = self.new('ShaderNodeValToRGB')
        cr = n.color_ramp
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1.0)
        for pos, col in stops[1:]:
            e = cr.elements.new(pos)
            e.color = (*col, 1.0)
        self.link(x, n.inputs['Fac'])
        return n.outputs['Color']

    # ---- tile-periodic coordinates and textures ---------------------------------------

    def position(self):
        return self.new('ShaderNodeNewGeometry').outputs['Position']

    def torus(self, pos, radius=1.0, seed=0.0):
        """Map world (x, y) onto a torus -> (vec3, w). Any function of it repeats every 1 unit."""
        sep = self.new('ShaderNodeSeparateXYZ')
        self.link(pos, sep.inputs[0])
        ax = self.math('MULTIPLY', sep.outputs['X'], TAU)
        ay = self.math('MULTIPLY', sep.outputs['Y'], TAU)
        cx = self.math('MULTIPLY', self.math('COSINE', ax), radius)
        sx = self.math('MULTIPLY', self.math('SINE', ax), radius)
        cy = self.math('MULTIPLY', self.math('COSINE', ay), radius)
        sy = self.math('MULTIPLY', self.math('SINE', ay), radius)
        comb = self.new('ShaderNodeCombineXYZ')
        self.link(self.math('ADD', cx, seed * 7.31), comb.inputs['X'])
        self.link(self.math('ADD', sx, seed * 3.17), comb.inputs['Y'])
        self.link(self.math('ADD', cy, seed * 5.53), comb.inputs['Z'])
        return comb.outputs[0], self.math('ADD', sy, seed * 2.11)

    def pnoise(self, pos, scale, detail=3.0, rough=0.55, seed=0.0, radius=1.0):
        vec, w = self.torus(pos, radius, seed)
        n = self.new('ShaderNodeTexNoise', noise_dimensions='4D')
        self.link(vec, n.inputs['Vector'])
        self.link(w, n.inputs['W'])
        n.inputs['Scale'].default_value = scale
        n.inputs['Detail'].default_value = detail
        n.inputs['Roughness'].default_value = rough
        return n.outputs['Fac']

    def pvoronoi(self, pos, scale, seed=0.0, feature='F1', radius=1.0):
        vec, w = self.torus(pos, radius, seed)
        n = self.new('ShaderNodeTexVoronoi', voronoi_dimensions='4D', feature=feature)
        self.link(vec, n.inputs['Vector'])
        self.link(w, n.inputs['W'])
        n.inputs['Scale'].default_value = scale
        return n.outputs['Distance'], n.outputs['Color']

    def dapple(self, col, pos):
        """Faint canopy-dappled light: soft bright and dark patches, identical in every render."""
        n = self.pnoise(pos, 2.2, detail=2.0, rough=0.5, seed=91.0, radius=0.9)
        patches = self.smooth(0.42, 0.62, n)
        fac = self.math('ADD', self.math('MULTIPLY', patches, 2.0 * DAPPLE_STRENGTH), 1.0 - DAPPLE_STRENGTH)
        comb = self.new('ShaderNodeCombineXYZ')
        for c in 'XYZ':
            self.link(fac, comb.inputs[c])
        return self.mul_rgb(col, comb.outputs[0])

    def principled(self, color, rough=0.85, normal=None, alpha=None):
        p = self.new('ShaderNodeBsdfPrincipled')
        self.link(color, p.inputs['Base Color'])
        p.inputs['Roughness'].default_value = rough
        p.inputs['Specular IOR Level'].default_value = 0.25
        if normal is not None:
            self.link(normal, p.inputs['Normal'])
        if alpha is not None:
            self.link(alpha, p.inputs['Alpha'])
        out = self.new('ShaderNodeOutputMaterial')
        self.link(p.outputs['BSDF'], out.inputs['Surface'])
        return p

    def bump(self, height, strength=0.6, distance=0.05):
        b = self.new('ShaderNodeBump')
        b.inputs['Strength'].default_value = strength
        b.inputs['Distance'].default_value = distance
        self.link(height, b.inputs['Height'])
        return b.outputs['Normal']


# --------------------------------------------------------------------------- surface colours
# Each returns (color_socket, height_socket) for a surface, built from tile-periodic noise.
# `seed` changes the look; tiles blend a variant seed in the interior and seed 0 at edges.

def forest_floor(N, pos, seed=0.0):
    """Leaf litter over dark soil with moss patches and twigs."""
    leaves_d, leaves_c = N.pvoronoi(pos, 9.0, seed=seed)
    tone = N.math('ADD', N.math('MULTIPLY', leaves_c_to_value(N, leaves_c), 0.6),
                  N.math('MULTIPLY', N.pnoise(pos, 6.0, 4.0, 0.6, seed), 0.4))
    litter = N.ramp(tone, [(0.0, (0.10, 0.065, 0.035)), (0.35, (0.21, 0.13, 0.06)),
                           (0.6, (0.33, 0.21, 0.09)), (0.85, (0.42, 0.30, 0.12)), (1.0, (0.27, 0.22, 0.10))])
    gaps = N.smooth(0.02, 0.09, leaves_d)              # dark soil between leaves
    litter = N.mix_rgb(gaps, (0.07, 0.05, 0.03), litter)
    moss_mask = N.smooth(0.55, 0.68, N.pnoise(pos, 1.6, 3.0, 0.55, seed + 11.0))
    moss = N.ramp(N.pnoise(pos, 14.0, 2.0, 0.5, seed + 3.0),
                  [(0.3, (0.11, 0.17, 0.05)), (0.7, (0.22, 0.30, 0.08))])
    col = N.mix_rgb(moss_mask, litter, moss)
    height = N.math('ADD', N.math('MULTIPLY', gaps, 0.5), N.math('MULTIPLY', moss_mask, 0.3))
    return col, height


def leaves_c_to_value(N, color_socket):
    sep = N.new('ShaderNodeSeparateColor')
    N.link(color_socket, sep.inputs[0])
    return sep.outputs[0]


def clearing_grass(N, pos, seed=0.0):
    blades = N.pnoise(pos, 34.0, 2.0, 0.6, seed + 5.0)
    clumps = N.pnoise(pos, 3.5, 3.0, 0.55, seed + 6.0)
    tone = N.math('ADD', N.math('MULTIPLY', blades, 0.55), N.math('MULTIPLY', clumps, 0.45))
    col = N.ramp(tone, [(0.25, (0.10, 0.18, 0.05)), (0.5, (0.20, 0.31, 0.08)),
                        (0.72, (0.33, 0.42, 0.12)), (0.9, (0.46, 0.46, 0.18))])
    return col, N.math('MULTIPLY', blades, 0.8)


def dirt_path(N, pos, seed=0.0):
    base = N.pnoise(pos, 5.0, 4.0, 0.6, seed + 21.0)
    col = N.ramp(base, [(0.3, (0.20, 0.135, 0.075)), (0.55, (0.29, 0.20, 0.11)), (0.8, (0.36, 0.27, 0.16))])
    peb_d, peb_c = N.pvoronoi(pos, 26.0, seed=seed + 22.0)
    pebble = N.math('MULTIPLY', N.smooth(0.22, 0.12, peb_d),
                    N.smooth(0.6, 0.75, leaves_c_to_value(N, peb_c)))
    col = N.mix_rgb(pebble, col, (0.42, 0.38, 0.32))
    ruts = N.pnoise(pos, 2.0, 2.0, 0.5, seed + 23.0)
    col = N.mul_rgb(col, N.math('ADD', N.math('MULTIPLY', ruts, 0.25), 0.85))
    return col, N.math('ADD', N.math('MULTIPLY', pebble, 0.6), N.math('MULTIPLY', base, 0.3))


def mud_bank(N, pos, seed=0.0):
    n = N.pnoise(pos, 8.0, 4.0, 0.6, seed + 31.0)
    col = N.ramp(n, [(0.3, (0.09, 0.065, 0.04)), (0.6, (0.16, 0.11, 0.065)), (0.85, (0.23, 0.17, 0.10))])
    st_d, st_c = N.pvoronoi(pos, 18.0, seed=seed + 32.0)
    stone = N.math('MULTIPLY', N.smooth(0.25, 0.15, st_d), N.smooth(0.55, 0.7, leaves_c_to_value(N, st_c)))
    col = N.mix_rgb(stone, col, (0.33, 0.32, 0.29))
    return col, N.math('ADD', N.math('MULTIPLY', stone, 0.7), N.math('MULTIPLY', n, 0.3))


def water(N, pos, depth, seed=0.0):
    """depth: socket 0 (shallow, sandy bottom visible) .. 1 (deep, dark)."""
    ripple = N.pnoise(pos, 7.0, 3.0, 0.55, seed + 41.0)
    shallow = N.ramp(ripple, [(0.3, (0.17, 0.20, 0.14)), (0.7, (0.23, 0.27, 0.19))])
    deep = N.ramp(ripple, [(0.3, (0.035, 0.07, 0.08)), (0.7, (0.06, 0.11, 0.12))])
    col = N.mix_rgb(depth, shallow, deep)
    glint = N.smooth(0.70, 0.78, N.pnoise(pos, 16.0, 2.0, 0.5, seed + 42.0))
    col = N.mix_rgb(N.math('MULTIPLY', glint, 0.35), col, (0.55, 0.62, 0.62))
    return col, N.math('MULTIPLY', ripple, 0.15)


def mossy_stone(N, pos, normal_z, seed=0.0):
    """For rocks/logs: stone with moss on up-facing surfaces (normal_z socket)."""
    n = N.pnoise(pos, 4.0, 5.0, 0.6, seed + 51.0)
    stone = N.ramp(n, [(0.3, (0.17, 0.17, 0.16)), (0.6, (0.29, 0.28, 0.26)), (0.85, (0.40, 0.39, 0.36))])
    moss_amt = N.smooth(0.55, 0.85, N.math('ADD', normal_z, N.math('MULTIPLY', N.pnoise(pos, 3.0, 3.0, 0.5, seed + 52.0), 0.4)))
    moss = N.ramp(N.pnoise(pos, 12.0, 2.0, 0.5, seed + 53.0), [(0.3, (0.12, 0.19, 0.05)), (0.7, (0.24, 0.33, 0.09))])
    return N.mix_rgb(moss_amt, stone, moss), n


if __name__ == "__main__":
    reset_scene()
    camera(0.5, 0.5, 1.0)
    print("SCENE_OK", bpy.app.version_string, bpy.context.scene.render.engine,
          bpy.context.scene.view_settings.view_transform)
