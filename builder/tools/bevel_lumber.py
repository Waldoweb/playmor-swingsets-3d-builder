"""bevel_lumber.py -- round the lumber edges of one model, in Blender.

Run from builder/:
  /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/bevel_lumber.py -- \
      models/P-PT.<hash>.glb /tmp/P-PT.bevel.glb 0.007 3

Arguments after `--`: input GLB, output GLB, bevel width in metres, segments.
A fifth argument lists the material-name prefixes that mark lumber
(default: wood). Slabs thinner than 5 cm, like the deck floor, are left
square. Square flag poles are swapped for cylinders in every mesh.

Then put the nodes back in the original order (Blender sorts siblings by
name, and joint order is honoured by old saved designs):
  python3 tools/glb_reorder_nodes.py models/P-PT.<old>.glb /tmp/P-PT.bevel.glb /tmp/P-PT.ordered.glb
Install it as models/P-PT.<first 8 hex of sha256>.glb, delete the old file,
and run `node tools/build_models.js` to refresh the manifest.

Lessons from the first run (2026-09-08):
- The importer keeps every face on its own vertices, so the bevel finds no
  shared edge to round unless the mesh is welded first.
- shade_smooth() acts on the whole selection, and the import leaves every
  object selected. Deselect first or the fence slats go round too.
- Harden Normals on the bevel keeps the big flat faces flat, so smooth
  shading only shows on the rounded strip.
"""
import bpy, sys, math, json, bmesh
from mathutils import Matrix


def round_poles(obj):
    """Replace square flag poles with cylinders.

    A flag pole is drawn as a plain box, 35 mm square and about half a metre
    tall, sitting loose inside the frame mesh. The real ones are round. Any
    loose part that is a square prism no more than 50 mm across, at least
    four times taller than it is wide, with only a box's eight vertices, is
    taken out and a 16-sided cylinder of the same height, POLE_DIAMETER
    across, put in its place on the same material. Returns how many were swapped.
    """
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    # Faces arrive on their own vertices; a box is eight only once welded.
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bm.verts.ensure_lookup_table()
    seen = set()
    poles = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, comp = [v], []
        while stack:
            x = stack.pop()
            if x.index in seen:
                continue
            seen.add(x.index)
            comp.append(x)
            for e in x.link_edges:
                stack.append(e.other_vert(x))
        if len(comp) != 8:
            continue
        xs = [c.co.x for c in comp]; ys = [c.co.y for c in comp]; zs = [c.co.z for c in comp]
        dx, dy, dz = max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)
        if dx > 0.05 or dy > 0.05 or abs(dx - dy) > 0.1 * max(dx, dy) or dz < 4 * max(dx, dy):
            continue
        faces = {f for c in comp for f in c.link_faces}
        material = next(iter(faces)).material_index if faces else 0
        poles.append((comp, faces, ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, (max(zs) + min(zs)) / 2), POLE_DIAMETER / 2, dz, material))
    # The object may be scaled by its parent; undo that so the pole stays
    # round in the world rather than in the mesh.
    sx, sy, sz = obj.matrix_world.to_scale()
    mean = (sx + sy) / 2
    for comp, faces, centre, radius, height, material in poles:
        bmesh.ops.delete(bm, geom=list(faces), context="FACES")
        made = bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=16,
            radius1=radius, radius2=radius, depth=height,
            matrix=Matrix.Translation(centre) @ Matrix.Diagonal((mean / sx, mean / sy, 1, 1)),
        )
        for f in {f for v in made["verts"] for f in v.link_faces}:
            f.material_index = material
            # Round in the shading too; the caps stay flat.
            f.smooth = abs(f.normal.z) < 0.5
    if poles:
        bm.to_mesh(me)
    bm.free()
    return len(poles)

argv = sys.argv[sys.argv.index("--") + 1:]
inp, out, width, segments = argv[0], argv[1], float(argv[2]), int(argv[3])
# Which materials mark lumber, by name prefix. The posts and floor are "Wood";
# the frame, fence slats and corner trim are poly-coated lumber and carry the
# "Poly ..." names. Roof, flags, metal and glass are left square.
prefixes = [s.strip().lower() for s in (argv[4] if len(argv) > 4 else "wood").split(",")]
# Anything thinner than this in some direction is a slab -- the deck floor --
# and stays square. Rounding it costs triangles for an edge nobody sees, and
# Weldon found the frame's rounding alone was enough to drag the frame rate.
MIN_THICKNESS = 0.05
# The flag poles are drawn 35 mm square; the real ones are thin tubes. The
# cylinder that replaces each one gets this diameter, whatever the box was.
POLE_DIAMETER = 0.02
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=inp, merge_vertices=True)
# The import leaves everything selected, and shade_smooth acts on the whole
# selection -- the first build rounded the fence slats along with the posts.
bpy.ops.object.select_all(action="DESELECT")
stats = {"objects": 0, "beveled": [], "skipped": []}
for obj in list(bpy.data.objects):
    if obj.type != "MESH":
        continue
    stats["objects"] += 1
    mats = [s.material.name for s in obj.material_slots if s.material]
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    before = len(obj.data.polygons)

    # Poles are looked for in every mesh: the Play Tower keeps its flag poles
    # inside the frame, which is not lumber that gets rounded.
    poles = round_poles(obj)
    if poles:
        stats["poles"] = stats.get("poles", 0) + poles

    is_lumber = any(m.lower().startswith(pfx) for m in mats for pfx in prefixes)
    is_slab = min(obj.dimensions) < MIN_THICKNESS
    if not is_lumber or is_slab:
        stats["skipped"].append([obj.name, mats, "slab" if is_lumber else "not lumber"])
        continue

    # Only the lumber from here on. The importer keeps every face on its own
    # vertices, so no edge is shared and the bevel finds nothing to round.
    # Weld them by position first; UV seams survive because Blender keeps UVs
    # per face corner. Then smooth shading, so the rounded strip is lit as a
    # curve -- Harden Normals on the bevel keeps the big flat faces flat.
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0005)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.shade_smooth()
    welded = (len(obj.data.vertices), len(obj.data.edges))

    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30)
    mod.harden_normals = True
    mod.miter_outer = "MITER_ARC"
    bpy.ops.object.modifier_apply(modifier=mod.name)
    obj.select_set(False)
    stats["beveled"].append([obj.name, mats, before, len(obj.data.polygons), welded])
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True, export_image_format="AUTO", export_extras=False, export_animations=False)
print("PILOT-STATS " + json.dumps(stats))
