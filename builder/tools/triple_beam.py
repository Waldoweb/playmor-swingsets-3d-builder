"""triple_beam.py -- make a swing beam three boards wide, in Blender.

PlayMor sell two beams (Weldon, 2026-10-05). The Eco Beam is two boards
under a cedar cap and goes on the Play Tower and DX Play Tower only, in the
3 and 4 position, 8 ft. The Swing Beam is three boards wide and goes on
every other tower, in the 3, 4 and Extended, 8 and 10 ft. The models were
all drawn as Eco Beams: two 51 mm boards side by side under a cap 154 mm
wide -- three boards' width already.

So the boards move out to the cap's edges and a third goes in the middle,
copied from the left one. The A-frame legs and the metal brackets that
meet the beam's sides move out by the same 25 mm a side, and the cross
brace between the legs grows by as much at each end. The joints are not
touched, so swings hang exactly where they did.

Run from builder/:
  /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/triple_beam.py -- \
      models/P-AB-3-10.<hash>.glb /tmp/P-AB-3-10.triple.glb
Then put the node order back and install, as for any Blender round trip:
  python3 tools/glb_reorder_nodes.py models/P-AB-3-10.<hash>.glb /tmp/P-AB-3-10.triple.glb /tmp/out.glb
  install as models/<stem>.<first 8 hex of sha256>.glb; node tools/build_models.js
"""
import bpy, sys, bmesh
from mathutils import Vector

BOARD = 0.0515  # one board's width, and the most a board face reaches from the middle
SHIFT = 0.0255  # how far each side moves out: half a board
OLD_SIDE = 0.045  # just inside the two-board beam's sides (51 mm from the middle)

argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src, merge_vertices=True)

moved = {"boards": 0, "middle": 0, "sides": 0, "braces": 0}


def loose_parts(bm):
    seen, parts = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, comp = [v], []
        seen.add(v.index)
        while stack:
            a = stack.pop()
            comp.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index)
                    stack.append(b)
        parts.append(comp)
    return parts


for obj in [o for o in bpy.data.objects if o.type == "MESH"]:
    world = obj.matrix_world
    back = world.inverted().to_3x3()
    # A move of `dx` across the world, said in the mesh's own space.
    local = lambda dx: back @ Vector((dx, 0, 0))
    wx = lambda v: (world @ v.co).x

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    is_trim = "_colorize_" in obj.name

    # The boards: long faces of the trim within a board's width of the middle.
    if is_trim:
        side = lambda xs: (
            "left" if min(xs) >= -BOARD - 0.001 and max(xs) <= 0.0006
            else "right" if min(xs) >= -0.0006 and max(xs) <= BOARD + 0.001
            else None
        )
        # The boards' height, from their long faces; then every face of
        # theirs, the end grain included, by where it sits.
        zs = []
        for f in bm.faces:
            ws = [world @ v.co for v in f.verts]
            if max(w.y for w in ws) - min(w.y for w in ws) >= 1.5 and side([w.x for w in ws]):
                zs += [w.z for w in ws]
        left, right = [], []
        for f in bm.faces if zs else []:
            ws = [world @ v.co for v in f.verts]
            if min(w.z for w in ws) < min(zs) - 0.002 or max(w.z for w in ws) > max(zs) + 0.002:
                continue
            which = side([w.x for w in ws])
            if which == "left":
                left.append(f)
            elif which == "right":
                right.append(f)
        if left and right:
            # The middle board first, copied from the left before it moves.
            copy = bmesh.ops.duplicate(bm, geom=left)
            new_verts = [g for g in copy["geom"] if isinstance(g, bmesh.types.BMVert)]
            bmesh.ops.translate(bm, verts=new_verts, vec=local(SHIFT))
            moved["middle"] += len(new_verts)
            lv = {v for f in left for v in f.verts}
            rv = {v for f in right for v in f.verts}
            bmesh.ops.translate(bm, verts=list(lv), vec=local(-SHIFT))
            bmesh.ops.translate(bm, verts=list(rv), vec=local(SHIFT))
            moved["boards"] += len(lv) + len(rv)
            done = lv | rv | set(new_verts)
        else:
            done = set()
    else:
        done = set()

    # Everything else: a part wholly to one side moves out with that side;
    # a brace across the middle stretches at its ends.
    bm.verts.ensure_lookup_table()
    for part in loose_parts(bm):
        if any(v in done for v in part):
            continue
        xs = [wx(v) for v in part]
        if min(xs) >= 0.03:
            bmesh.ops.translate(bm, verts=part, vec=local(SHIFT))
            moved["sides"] += 1
        elif max(xs) <= -0.03:
            bmesh.ops.translate(bm, verts=part, vec=local(-SHIFT))
            moved["sides"] += 1
        else:
            # Across the middle. The cap runs the beam's length and is
            # already three boards wide; anything shorter -- the cross
            # brace, the bracket plate wrapped round the beam's end, a
            # swivel hanger's strap -- widens by as much as the beam did,
            # everything outside the old beam's sides moving out.
            ys = [(world @ v.co).y for v in part]
            if max(ys) - min(ys) > 1.5:
                continue
            stretched = False
            for v in part:
                x = wx(v)
                if abs(x) > OLD_SIDE:
                    v.co += local(SHIFT if x > 0 else -SHIFT)
                    stretched = True
            moved["braces"] += stretched

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

print("TRIPLE-STATS", moved)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True,
                          export_image_format="AUTO", export_extras=False, export_animations=False)
