"""baby_swing_bucket.py -- give the Baby Swing a toddler bucket with a front bar.

Run from builder/:
  /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/baby_swing_bucket.py -- \
      models/BS__b8.<hash>.glb /tmp/BS__b8.glb

Weldon asked 2026-10-03 for the baby swing to look like the one PlayMor
sells: a bucket with a tall back, sides that wrap forward and fall to a bar
across the front at arm height, a post from the bar down to the seat
between the legs, and four chains -- the front pair from the ends of the bar
up to the hanger, the back pair from the top corners of the back. The old
model was a flat chair with a back and no sides.

What is kept: the hanger hooks, the back chains, the joint, the seat's
object, name and material (so its colour can still be chosen), and the seat
bottom and back top heights, so the swing hangs exactly where it did. What
is new: the seat's mesh, and the front chains -- the old ones were a short
branch off the back chain; the new ones run from the ends of the bar to the
hanger, laid from copies of the back chain's links. Then run
tools/glb_reorder_nodes.py.
"""
import bpy, bmesh, math, sys
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]

# The seat, in the model's frame (Blender: x forward, y across, z up).
# Proportions from PlayMor's photos: a bucket a little narrower at the
# bottom than the top, its back leaning back, its bar about 40% of the way
# up, and its sides falling in a concave sweep from the top of the back to
# the bar. The back's top edge and the seat's underside stay where the old
# seat had them, so the back chains still hook on and nothing hangs lower.
BACK_X_TOP, BACK_X_BOTTOM = 0.007, 0.045   # the back leans back by this much
FRONT_X = 0.278
HW_TOP, HW_BOTTOM = 0.208, 0.172           # half the width, top and bottom
BOTTOM_Z, BACK_TOP_Z = 0.694, 1.099
WALL, FLOOR = 0.026, 0.032
CORNER = 0.06                              # the outline's corner radius
BAR_Z = 0.862                              # centre of the front bar
RIM_R = 0.021                              # the rolled rim, bar included
RIM_BACK_Z = BACK_TOP_Z - RIM_R            # the rim's centre along the top of the back
POST_W = 0.062                             # the post between the legs
SLOT_Y, SLOT_W, SLOT_Z = 0.065, 0.016, (0.86, 0.94)   # the two strap slots in the back


def half_width(z):
    return HW_BOTTOM + (HW_TOP - HW_BOTTOM) * (z - BOTTOM_Z) / (BACK_TOP_Z - BOTTOM_Z)


def back_x(z):
    return BACK_X_BOTTOM + (BACK_X_TOP - BACK_X_BOTTOM) * (z - BOTTOM_Z) / (BACK_TOP_Z - BOTTOM_Z)


def rim_profile(x):
    """The rim's height along the sides: level at the back, falling steeply
    and then easing out level into the bar, as on the real seat."""
    t = min(1.0, max(0.0, (x - X_BACK) / (X_FRONT - X_BACK)))
    return BAR_Z + (RIM_BACK_Z - BAR_Z) * (1 + math.cos(math.pi * t ** 0.6)) / 2


X_BACK, X_FRONT = back_x(RIM_BACK_Z) + CORNER, FRONT_X - CORNER
RC = CORNER - WALL / 2                     # the rim's radius round a corner, on the wall's centre

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src, merge_vertices=True)
seat = next(o for o in bpy.data.objects if "colorize" in o.name)
chain = max((o for o in bpy.data.objects if o.name.startswith("Torus")), key=lambda o: len(o.data.vertices))
chain_name = chain.name
coll = seat.users_collection[0]


def rounded_box(name, x0, x1, y0, y1, z0, z1, radius, segments=5):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    o.name = name
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    o.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if radius > 0:
        bm = bmesh.new(); bm.from_mesh(o.data)
        bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:], offset=radius, segments=segments,
                        profile=0.5, affect="EDGES", clamp_overlap=True)
        bm.to_mesh(o.data); bm.free()
    return o


def boolean(target, cutter, op, self_intersecting=False):
    m = target.modifiers.new("b", "BOOLEAN")
    m.operation, m.object, m.solver = op, cutter, "EXACT"
    m.use_self = self_intersecting
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=m.name)
    print("BOOLEAN %s %s -> %d verts" % (op, cutter.name, len(target.data.vertices)))
    bpy.data.objects.remove(cutter, do_unlink=True)


def tapered_box(name, z0, z1, inset, front, radius, segments=6):
    """The bucket's outline between two heights, drawn in by `inset`."""
    bm = bmesh.new()
    corners = {}
    for zi, z in enumerate((z0, z1)):
        for yi, sy in enumerate((-1, 1)):
            for xi in range(2):
                x = back_x(z) + inset if xi == 0 else front
                corners[(xi, yi, zi)] = bm.verts.new((x, sy * (half_width(z) - inset), z))
    v = corners
    for face in (
        [v[0, 0, 0], v[1, 0, 0], v[1, 1, 0], v[0, 1, 0]],
        [v[0, 0, 1], v[0, 1, 1], v[1, 1, 1], v[1, 0, 1]],
        [v[0, 0, 0], v[0, 0, 1], v[1, 0, 1], v[1, 0, 0]],
        [v[0, 1, 0], v[1, 1, 0], v[1, 1, 1], v[0, 1, 1]],
        [v[0, 0, 0], v[0, 1, 0], v[0, 1, 1], v[0, 0, 1]],
        [v[1, 0, 0], v[1, 0, 1], v[1, 1, 1], v[1, 1, 0]],
    ):
        bm.faces.new(face)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:], offset=radius, segments=segments,
                    profile=0.5, affect="EDGES", clamp_overlap=True)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    return o


# ---------------------------------------------------------------- the bucket
shell = tapered_box("shell", BOTTOM_Z, BACK_TOP_Z, 0.0, FRONT_X, 0.06, 8)

# Hollow it: open at the top and all the way through the front.
cavity = tapered_box("cavity", BOTTOM_Z + FLOOR, BACK_TOP_Z + 0.4, WALL, FRONT_X + 0.3, 0.045, 8)
boolean(shell, cavity, "DIFFERENCE")

# The sides fall from the top of the back to the bar along the rim's profile:
# everything above it goes, the back trimmed level to take the rim too.
samples = [X_BACK + (X_FRONT - X_BACK) * i / 48 for i in range(49)]
outline = ([(back_x(BACK_TOP_Z) - 0.2, RIM_BACK_Z)] + [(x, rim_profile(x)) for x in samples]
           + [(FRONT_X + 0.3, BAR_Z), (FRONT_X + 0.3, BACK_TOP_Z + 0.5), (back_x(BACK_TOP_Z) - 0.2, BACK_TOP_Z + 0.5)])
bm = bmesh.new()
near = [bm.verts.new((x, -0.5, z)) for x, z in outline]
far = [bm.verts.new((x, 0.5, z)) for x, z in outline]
bm.faces.new(near[::-1])
bm.faces.new(far)
for i in range(len(outline)):
    j = (i + 1) % len(outline)
    bm.faces.new([near[i], near[j], far[j], far[i]])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bmesh.ops.triangulate(bm, faces=bm.faces[:])
cut_mesh = bpy.data.meshes.new("cut")
bm.to_mesh(cut_mesh)
bm.free()
cut = bpy.data.objects.new("cut", cut_mesh)
bpy.context.collection.objects.link(cut)
boolean(shell, cut, "DIFFERENCE")

# The two strap slots through the back.
for side in (-1, 1):
    slot = rounded_box("slot", -0.1, back_x(SLOT_Z[0]) + WALL + 0.02, side * SLOT_Y - SLOT_W / 2,
                       side * SLOT_Y + SLOT_W / 2, SLOT_Z[0], SLOT_Z[1], 0.0075, 3)
    boolean(shell, slot, "DIFFERENCE")

# Soft edges where the booleans left sharp ones -- before the rim goes on,
# so the bevel does not chew at the joins -- then smooth shading that keeps
# the creases.
bev = shell.modifiers.new("bevel", "BEVEL")
bev.width, bev.segments, bev.limit_method, bev.angle_limit = 0.011, 4, "ANGLE", math.radians(40)
bpy.context.view_layer.objects.active = shell
bpy.ops.object.modifier_apply(modifier=bev.name)

# ---------------------------------------------------------- the rolled rim
# One tube round the whole top: across the back, down each side along the
# profile, round the front corners and across the front as the safety bar.
# It sits on the centre of the wall, a little proud of both faces, so the
# sides are moulded into the bar with no seam -- the way the real seat is.
def corner(cx, cy, start_angle, z, steps=12):
    return [Vector((cx + RC * math.cos(math.radians(start_angle + 90 * i / steps)),
                    cy + RC * math.sin(math.radians(start_angle + 90 * i / steps)), z))
            for i in range(steps + 1)]


hw_b, hw_f = half_width(RIM_BACK_Z), half_width(BAR_Z)
path = []
path += [Vector((x, -(half_width(rim_profile(x)) - WALL / 2), rim_profile(x))) for x in samples]
path += corner(X_FRONT, -(hw_f - CORNER), -90, BAR_Z)[1:]            # left front corner
path += [Vector((FRONT_X - WALL / 2, -(hw_f - CORNER) + 2 * (hw_f - CORNER) * i / 12, BAR_Z))
         for i in range(1, 12)]                                         # the bar
path += corner(X_FRONT, hw_f - CORNER, 0, BAR_Z)                       # right front corner
path += [Vector((x, half_width(rim_profile(x)) - WALL / 2, rim_profile(x))) for x in reversed(samples)][1:]
path += corner(X_BACK, hw_b - CORNER, 90, RIM_BACK_Z)[1:]              # right back corner
path += [Vector((X_BACK - RC, (hw_b - CORNER) - 2 * (hw_b - CORNER) * i / 12, RIM_BACK_Z))
         for i in range(1, 12)]                                         # across the back
path += corner(X_BACK, -(hw_b - CORNER), 180, RIM_BACK_Z)[:-1]         # left back corner

curve = bpy.data.curves.new("rim", "CURVE")
curve.dimensions = "3D"
curve.bevel_depth, curve.bevel_resolution = RIM_R, 6
spline = curve.splines.new("POLY")
spline.points.add(len(path) - 1)
for p, v in zip(spline.points, path):
    p.co = (v.x, v.y, v.z, 1)
spline.use_cyclic_u = True
rim = bpy.data.objects.new("rim", curve)
bpy.context.collection.objects.link(rim)
bpy.ops.object.select_all(action="DESELECT")
rim.select_set(True)
bpy.context.view_layer.objects.active = rim
bpy.ops.object.convert(target="MESH")
rim = bpy.context.active_object
# A curve's bevel comes out facing either way; the union needs it outward.
bm = bmesh.new()
bm.from_mesh(rim.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(rim.data)
bm.free()
# The tube brushes itself where it turns hard at the back corners, which the
# exact solver only copes with when told to look for it.
boolean(shell, rim, "UNION", self_intersecting=True)

# The post between the legs, from the bar down to the floor.
post_x = FRONT_X - WALL / 2
post = rounded_box("post", post_x - 0.017, post_x + 0.013, -POST_W / 2, POST_W / 2,
                   BOTTOM_Z + FLOOR - 0.004, BAR_Z, 0.015, 5)
boolean(shell, post, "UNION")

bpy.ops.object.select_all(action="DESELECT")
shell.select_set(True)
bpy.context.view_layer.objects.active = shell
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))

# Into the seat object, under its own name and material.
old_mesh = seat.data
new_mesh = shell.data
new_mesh.materials.clear()
new_mesh.materials.append(old_mesh.materials[0])
inv = seat.matrix_world.inverted()
new_mesh.transform(inv @ shell.matrix_world)
seat.data = new_mesh
bpy.data.objects.remove(shell, do_unlink=True)
for m in seat.modifiers:
    seat.modifiers.remove(m)

# ----------------------------------------------------------------- chains
# Each side was a Y: one chain plumb from the hanger to the top corner of the
# back, and a branch leaving it 14 cm above that for the front of the seat.
# The photo is a V -- the front chain runs all the way up to the hanger -- so
# the branch comes off and a new front chain is laid from the end of the bar
# to the hanger, link by link, from copies of the plumb chain's own links.
bpy.ops.object.select_all(action="DESELECT")
chain.select_set(True)
bpy.context.view_layer.objects.active = chain
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.separate(type="LOOSE")
bpy.ops.object.mode_set(mode="OBJECT")
links = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(chain_name)]


def measure(o):
    w = [o.matrix_world @ v.co for v in o.data.vertices]
    centre = sum(w, Vector()) / len(w)
    return centre, max(v.z for v in w) - min(v.z for v in w)


info = {o.name: measure(o) for o in links}
# A plumb link stands 3.4 cm tall; the branch's links, leaning, 3.0.
branch = [o for o in links if info[o.name][1] < 0.032 and info[o.name][0].z < 1.4]
links = [o for o in links if o not in branch]
removed = len(branch)
for o in branch:
    bpy.data.objects.remove(o, do_unlink=True)

plumb = sorted((o for o in links if info[o.name][0].y > 0), key=lambda o: info[o.name][0].z)
pitch = (info[plumb[-1].name][0].z - info[plumb[0].name][0].z) / (len(plumb) - 1)
patterns = []
for o in plumb[10:12]:
    m = o.data.copy()
    m.transform(Matrix.Translation(-info[o.name][0]) @ o.matrix_world)
    patterns.append(m)
top = info[plumb[-1].name][0]

new_links = []
for side in (1, -1):
    # On top of the rim where the side turns into the bar.
    a = math.radians(45)
    start = Vector((X_FRONT + RC * math.sin(a), side * (half_width(BAR_Z) - CORNER + RC * math.cos(a)),
                    BAR_Z + RIM_R + 0.012))
    end = Vector((top.x + 0.014, side * (abs(top.y) + 0.004), top.z - 0.03))
    d = end - start
    n = max(1, round(d.length / pitch))
    turn = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    for i in range(n + 1):
        m = patterns[i % 2].copy()
        m.transform(Matrix.Translation(start + d * (i / n)) @ turn)
        o = bpy.data.objects.new("link", m)
        coll.objects.link(o)
        new_links.append(o)

bpy.ops.object.select_all(action="DESELECT")
for o in links + new_links:
    o.select_set(True)
bpy.context.view_layer.objects.active = links[0]
bpy.ops.object.join()
links[0].name = chain_name
print("BUCKET-STATS removed %d branch links, laid %d, pitch %.4f, seat %d verts"
      % (removed, len(new_links), pitch, len(seat.data.vertices)))

bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True,
                          export_image_format="AUTO", export_extras=False, export_animations=False)
