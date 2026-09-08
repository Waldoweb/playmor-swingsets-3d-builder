"""lengthen_chains.py -- drop a swing's seat by stretching its coated chain.

Run from builder/:
  /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/lengthen_chains.py -- \
      models/SS__b8.<hash>.glb /tmp/SS__b8.glb 0.42 1.70

Arguments after `--`: input GLB, output GLB, how far to lower the seat in
metres, and the height (model z, before export) that separates what moves
from what stays.

The sling swing's chain is real links at the top and bottom with a plain
plastic-coated tube between them. Everything below the tube's top ring --
the seat, the lower links, the tube's lower rings -- moves straight down,
so the tube stretches and no link is deformed. The hanger clips and the
upper links stay where they are, so the joint that hangs it from the beam
is untouched. Then run tools/glb_reorder_nodes.py on the result as usual.

Weldon asked for it 2026-09-08: the seat hung 0.87 m up, about 34 inches;
a child wants 16 to 18.
"""
import bpy, sys, json

argv = sys.argv[sys.argv.index("--") + 1:]
inp, out, delta, threshold = argv[0], argv[1], float(argv[2]), float(argv[3])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=inp, merge_vertices=True)
bpy.ops.object.select_all(action="DESELECT")
stats = {}
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    # Vertices are in mesh space; the threshold is given in the model's
    # space, so bring it across through the object's world matrix.
    inv = obj.matrix_world.inverted()
    moved = 0
    for v in obj.data.vertices:
        if (obj.matrix_world @ v.co).z < threshold:
            v.co = inv @ ((obj.matrix_world @ v.co) - __import__("mathutils").Vector((0, 0, delta)))
            moved += 1
    if moved:
        obj.data.update()
        stats[obj.name] = {"moved": moved, "of": len(obj.data.vertices)}
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True, export_yup=True, export_image_format="AUTO", export_extras=False, export_animations=False)
print("CHAIN-STATS " + json.dumps(stats))
