#!/usr/bin/env python3
"""
Turn the mailbox and the telephone to the inside of the rail.

The toys that mount on a tower's toy joints -- steering wheel, ship's wheel,
scope, mailbox, telephone -- share one convention: the joint sits on the rail
and the toy hangs off it toward the model's -Z, which the builder turns to
face into the tower. The wheels and the scope were drawn that way. The
mailbox and the telephone were drawn toward +Z, so they went on the outside
of the rail facing out (Weldon, 2026-10-04).

The fix turns each one's mesh half a turn about the vertical through its
joint. The joint itself is not touched, so where a toy mounts, its joint's
name and every saved design stay as they were. Only the JSON chunk of the GLB
is rewritten; the geometry bytes are unchanged. A toy already on the -Z side
is left alone, so running this twice does nothing the second time.

Usage:  python3 tools/turn_mount_toys.py [--dry-run]
Then:   node tools/build_models.js
"""

import glob
import hashlib
import json
import math
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "..", "models")
TOYS = ["MAIL", "TEL"]


def read_glb(path):
    data = open(path, "rb").read()
    length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + length]), data[20 + length :]


def write_glb(gltf, rest):
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + len(rest)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(text), b"JSON")
        + text
        + rest
    )


def local_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    tx, ty, tz = node.get("translation", [0, 0, 0])
    qx, qy, qz, qw = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    r = np.array(
        [
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
            [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
            [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
        ]
    )
    m = np.eye(4)
    m[:3, :3] = r * np.array([sx, sy, sz])
    m[:3, 3] = [tx, ty, tz]
    return m


def quaternion(r):
    """A rotation matrix as a glTF [x, y, z, w] quaternion."""
    w = math.sqrt(max(0.0, 1 + r[0, 0] + r[1, 1] + r[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0.0, 1 + r[0, 0] - r[1, 1] - r[2, 2])) / 2, r[2, 1] - r[1, 2])
    y = math.copysign(math.sqrt(max(0.0, 1 - r[0, 0] + r[1, 1] - r[2, 2])) / 2, r[0, 2] - r[2, 0])
    z = math.copysign(math.sqrt(max(0.0, 1 - r[0, 0] - r[1, 1] + r[2, 2])) / 2, r[1, 0] - r[0, 1])
    return [round(v, 12) + 0.0 for v in (x, y, z, w)]


def turn(stem, dry_run):
    paths = glob.glob(os.path.join(MODELS, stem + ".*.glb"))
    assert len(paths) == 1, (stem, paths)
    path = paths[0]
    gltf, rest = read_glb(path)
    nodes = gltf["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def world(i):
        m = local_matrix(nodes[i])
        while i in parent:
            i = parent[i]
            m = local_matrix(nodes[i]) @ m
        return m

    joint = next(i for i, n in enumerate(nodes) if n.get("name", "").startswith("joint"))
    origin = world(joint)[:3, 3]
    print(os.path.basename(path))

    changed = False
    for i, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        # Where the mesh sits along z, from the joint, in model space.
        w = world(i)
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
            accessor = gltf["accessors"][primitive["attributes"]["POSITION"]]
            for cx in (0, 1):
                for cy in (0, 1):
                    for cz in (0, 1):
                        corner = [
                            (accessor["min"], accessor["max"])[c][axis]
                            for axis, c in enumerate((cx, cy, cz))
                        ]
                        p = (w @ np.array(corner + [1.0]))[:3]
                        lo, hi = np.minimum(lo, p), np.maximum(hi, p)
        middle = (lo + hi) / 2 - origin
        print("  %-24s centre z %+.3f from the joint" % (node["name"], middle[2]))
        if middle[2] <= 0:
            continue

        # Half a turn about the vertical through the joint, said in the
        # mesh node's own parent frame.
        assert "matrix" not in node and "translation" not in node, node["name"]
        p = world(parent[i])[:3, :3]
        assert np.allclose(world(parent[i])[:3, 3], origin), "joint is not at the parent's origin"
        half_turn = np.diag([-1.0, 1.0, -1.0])
        own = local_matrix(node)[:3, :3]
        node["rotation"] = quaternion(np.linalg.inv(p) @ half_turn @ p @ own)
        print("  %-24s turned to the inside: rotation %s" % (node["name"], node["rotation"]))
        changed = True

    if dry_run or not changed:
        return
    data = write_glb(gltf, rest)
    digest = hashlib.sha256(data).hexdigest()[:8]
    target = os.path.join(MODELS, "%s.%s.glb" % (stem, digest))
    with open(target, "wb") as f:
        f.write(data)
    if os.path.abspath(target) != os.path.abspath(path):
        os.remove(path)
    print("  ->", os.path.basename(target))


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for stem in TOYS:
        turn(stem, dry)
