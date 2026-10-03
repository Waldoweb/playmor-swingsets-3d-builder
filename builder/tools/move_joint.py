#!/usr/bin/env python3
"""
Move one joint in a model file by a distance in model space.

    python3 tools/move_joint.py <stem> <joint name> <dx> <dy> <dz>
    python3 tools/move_joint.py <stem> <joint name> --level-with <other joint>

`stem` is the file name before the hash, e.g. P-AB-DS-8 or DS-KR__b8.
`--level-with` moves the joint up or down to the height of another joint in
the same file and prints the distance it moved, so a part hung there can be
given the opposite move.

Like spread_side_joints.py, only the joint's translation in the JSON chunk
changes, converted through its parent's transform; the binary chunk, node
order and names are untouched. Then run: node tools/build_models.js
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spread_side_joints import (  # noqa: E402
    MODELS, glob, hashlib, parent_of, read_glb, world_matrices, write_glb,
)


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    stem, name = argv[0], argv[1]
    path = glob.glob(os.path.join(MODELS, stem + ".*.glb"))[0]
    gltf, rest = read_glb(path)
    world = world_matrices(gltf)
    parents = parent_of(gltf)
    index_of = {n.get("name"): i for i, n in enumerate(gltf["nodes"])}
    if name not in index_of:
        sys.exit("%s has no joint %r" % (os.path.basename(path), name))
    index = index_of[name]
    here = world[index][:3, 3]

    if argv[2] == "--level-with":
        other = world[index_of[argv[3]]][:3, 3]
        delta = np.array([0.0, other[1] - here[1], 0.0])
    else:
        delta = np.array([float(v) for v in argv[2:5]])

    parent = world[parents[index]] if index in parents else np.eye(4)
    local = np.linalg.inv(parent) @ np.append(here + delta, 1.0)
    gltf["nodes"][index]["translation"] = [float(v) for v in local[:3]]

    data = write_glb(gltf, rest)
    target = os.path.join(MODELS, "%s.%s.glb" % (stem, hashlib.sha256(data).hexdigest()[:8]))
    with open(target, "wb") as f:
        f.write(data)
    if os.path.abspath(target) != os.path.abspath(path):
        os.remove(path)
    print("%s  %s  moved %s  -> %s" % (
        os.path.basename(path), name, " ".join("%.4f" % v for v in delta), os.path.basename(target)))


if __name__ == "__main__":
    main(sys.argv[1:])
