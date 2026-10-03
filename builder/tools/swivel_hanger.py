"""swivel_hanger.py -- hang the Disc Swing from a swivel hanger instead of through the beam.

Run from builder/:
  /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/swivel_hanger.py -- \
      models/DS-KR__b8.<hash>.glb models/MTS__b8.<hash>.glb /tmp/DS-KR__b8.glb 2.62 0.03

Arguments after `--`: the disc swing, the donor whose hanger hardware is
copied (the Tire Swing), the output, the height (model z, before export)
above which the rope is cut away, and how far above the joint the rope's
cut end goes -- inside the bracket.

The disc swing's rope went up through a hole in the beam: the plain cord,
then a hex stopper, a neck and an end knot that sat on top of the beam.
Since 2026-10-03 it hangs from a swivel hanger under the beam, like the
Tire Swing on the same Extended Beam, and Weldon wants the stopper and knot
gone. So:

  - everything above the cut -- stopper, neck, knot -- is deleted, the cord's
    top ring is moved up or down to just inside the bracket, and the open
    end is capped;
  - the Tire Swing's hanger bracket and pin are copied in, placed where they
    sit relative to the Tire Swing's joint, measured from the disc swing's.

The joint and the disc do not move, so the swing hangs exactly where it did.
Then run tools/glb_reorder_nodes.py on the result as usual.
"""
import bpy, bmesh, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
disc_path, donor_path, out = argv[0], argv[1], argv[2]
cut, top_above_joint = float(argv[3]), float(argv[4])
HARDWARE = {"Plane039": "swivel_hanger_bracket", "Cylinder015": "swivel_hanger_pin"}

bpy.ops.wm.read_factory_settings(use_empty=True)

# The donor's hanger hardware, and where its joint is.
bpy.ops.import_scene.gltf(filepath=donor_path, merge_vertices=True)
donor_joint = next(o for o in bpy.data.objects if o.name.startswith("joint"))
donor_joint_z = donor_joint.matrix_world.translation.z
hardware = []
for o in list(bpy.data.objects):
    if o.name in HARDWARE:
        world = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = world
        o.name = HARDWARE[o.name]
        hardware.append(o)
    else:
        bpy.data.objects.remove(o, do_unlink=True)
assert len(hardware) == 2, [o.name for o in hardware]

# The disc swing.
bpy.ops.import_scene.gltf(filepath=disc_path, merge_vertices=True)
joint = next(o for o in bpy.data.objects if o.name.startswith("joint") and o not in hardware)
root = joint.parent
lift = joint.matrix_world.translation.z - donor_joint_z
for o in hardware:
    world = o.matrix_world.copy()
    world.translation += Vector((0, 0, lift))
    o.parent = root
    o.matrix_world = world

rope = next(o for o in bpy.data.objects if o.name.startswith("Cylinder014"))
world, inv = rope.matrix_world, rope.matrix_world.inverted()
bm = bmesh.new()
bm.from_mesh(rope.data)
before = len(bm.verts)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if (world @ v.co).z > cut], context="VERTS")

# The cord's top ring, now its end: to just inside the bracket, then capped.
ring_z = max((world @ v.co).z for v in bm.verts)
ring = [v for v in bm.verts if (world @ v.co).z > ring_z - 0.002]
top = joint.matrix_world.translation.z + top_above_joint
for v in ring:
    w = world @ v.co
    v.co = inv @ Vector((w.x, w.y, top))
edges = [e for e in bm.edges if e.is_boundary and all(v in ring for v in e.verts)]
bmesh.ops.holes_fill(bm, edges=edges, sides=0)
bm.to_mesh(rope.data)
bm.free()
rope.data.update()

bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True,
                          export_image_format="AUTO", export_extras=False, export_animations=False)
print("SWIVEL-STATS rope %d -> %d verts, end ring %d at %.3f (was %.3f); hardware lifted %.4f"
      % (before, len(rope.data.vertices), len(ring), top, ring_z, lift))
