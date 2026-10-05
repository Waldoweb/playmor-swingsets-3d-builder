#!/usr/bin/env python3
"""
Build a taller tower from a shorter one: the same tower on longer legs.

PlayMor sells some towers at two deck heights -- 5 ft and 7 ft -- and the
only difference is the legs under the floor. So the 7 ft model is made from
the 5 ft one rather than drawn again: everything above a cut between the
ground frame and the floor (floor, rails, slats, upper posts, roof, flags,
and every joint up there) is raised, and the legs, the one thing crossing the
cut, stretch to meet it. Ground-level parts -- base frame, bottom brackets,
the floor-kit, picnic and end-rail mounts -- stay where they are.

The raised joints change layer with the deck: a slide or ladder for a 5 ft
deck is layer 6 and one for 7 ft is layer 8, and the swing-beam mount goes
from an 8 ft beam (b8) to a 10 ft one (b10). The rest of each joint's name is
kept, so its direction and the toy mounts read as before.

How far: 0.640 m, a little over 2 ft (0.610), so the beam mount lands at
3.200 like every other 10 ft-beam tower's and a 10 ft beam's feet meet the
ground; the deck joints land at 2.425, inside the 2.42-2.49 the 7 ft slides
and ladders ask for (the DX Sky Tower's 7 ft deck is 2.452).

The source file is only read. The output is written as
models/<target>.<hash>.glb, replacing an earlier build of the same target.

Usage:  python3 tools/raise_tower.py [--dry-run]
Then:   python3 tools/spread_side_joints.py   (sets the taller deck's joints
                                             clear of the centre slat for
                                             its layer's cut-out)
        node tools/build_models.js
"""

import glob
import hashlib
import json
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "..", "models")

# source stem, target stem, cut height, how far up, joint layer renames.
TOWERS = [
    ("P-WT", "P-WT-7", 0.7, 0.640, {"6": "8", "b8": "b10"}),
]


def read_glb(path):
    data = open(path, "rb").read()
    length = struct.unpack("<I", data[12:16])[0]
    rest = data[20 + length :]
    bin_length, kind = struct.unpack("<I4s", rest[:8])
    assert kind == b"BIN\x00", path
    return json.loads(data[20 : 20 + length]), bytearray(rest[8 : 8 + bin_length])


def write_glb(gltf, binary):
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary = bytes(binary) + b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(text) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(text), b"JSON")
        + text
        + struct.pack("<I4s", len(binary), b"BIN\x00")
        + binary
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


def rename_layer(name, renames):
    """joint,<direction>,<layer>,... with the layer swapped, if it is one to swap."""
    fields = name.split(",")
    if fields[0].startswith("joint") and len(fields) > 2 and fields[2] in renames:
        fields[2] = renames[fields[2]]
    return ",".join(fields)


def raise_tower(source, target, cut, rise, renames, dry_run):
    paths = glob.glob(os.path.join(MODELS, source + ".*.glb"))
    assert len(paths) == 1, (source, paths)
    gltf, binary = read_glb(paths[0])
    nodes = gltf["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def worlds():
        out = {}

        def visit(i, above):
            out[i] = above @ local_matrix(nodes[i])
            for c in nodes[i].get("children", []):
                visit(c, out[i])

        for root in gltf["scenes"][gltf.get("scene", 0)]["nodes"]:
            visit(root, np.eye(4))
        return out

    old = worlds()

    # Empties (joints, groups) above the cut go up; the rest keep their place
    # in the world even if a parent moved. Parents first, so each child is
    # placed against its parent's new position.
    order = []

    def walk(i):
        order.append(i)
        for c in nodes[i].get("children", []):
            walk(c)

    for root in gltf["scenes"][gltf.get("scene", 0)]["nodes"]:
        walk(root)

    new = {}
    moved_joints, renamed = 0, 0
    for i in order:
        node = nodes[i]
        above = new[parent[i]] if i in parent else np.eye(4)
        if "mesh" not in node:
            target_world = old[i].copy()
            if old[i][1, 3] > cut:
                target_world[1, 3] += rise
                moved_joints += node.get("name", "").startswith("joint")
            local = np.linalg.inv(above) @ target_world
            if not np.allclose(local, local_matrix(node), atol=1e-9):
                assert "matrix" not in node, node.get("name")
                node["translation"] = [float(v) for v in local[:3, 3]]
        new[i] = above @ local_matrix(node)
        if "name" in node:
            renamed_name = rename_layer(node["name"], renames)
            renamed += renamed_name != node["name"]
            node["name"] = renamed_name

    # Every vertex above the cut goes up, worked out in the world and put back
    # in its mesh's own space against the node's new place.
    done = set()
    stretched = []
    for i, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
            index = primitive["attributes"]["POSITION"]
            assert index not in done, "a position accessor shared between nodes"
            done.add(index)
            accessor = gltf["accessors"][index]
            view = gltf["bufferViews"][accessor["bufferView"]]
            offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            stride = view.get("byteStride", 12)
            count = accessor["count"]
            assert accessor["componentType"] == 5126 and accessor["type"] == "VEC3"
            rows = np.frombuffer(binary, dtype=np.uint8, count=stride * count, offset=offset)
            rows = rows.reshape(count, stride)[:, :12].copy()
            local = rows.view(np.float32).reshape(count, 3).astype(float)
            world = (old[i][:3, :3] @ local.T).T + old[i][:3, 3]
            up = world[:, 1] > cut
            if up.any() and not up.all():
                stretched.append(node.get("name"))
            world[up, 1] += rise
            back = np.linalg.inv(new[i])
            local = (back[:3, :3] @ world.T).T + back[:3, 3]
            packed = local.astype(np.float32)
            for k in range(count):
                start = offset + k * stride
                binary[start : start + 12] = packed[k].tobytes()
            accessor["min"] = [float(v) for v in packed.min(axis=0)]
            accessor["max"] = [float(v) for v in packed.max(axis=0)]

    print("%s -> %s: up %.3f above %.2f" % (source, target, rise, cut))
    print("  joints raised: %d, joints relayered: %d" % (moved_joints, renamed))
    print("  stretched across the cut: %s" % ", ".join(stretched))
    if dry_run:
        return
    data = write_glb(gltf, binary)
    digest = hashlib.sha256(data).hexdigest()[:8]
    out = os.path.join(MODELS, "%s.%s.glb" % (target, digest))
    for previous in glob.glob(os.path.join(MODELS, target + ".*.glb")):
        if os.path.abspath(previous) != os.path.abspath(out):
            os.remove(previous)
    with open(out, "wb") as f:
        f.write(data)
    print("  ->", os.path.basename(out))


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for args in TOWERS:
        raise_tower(*args, dry)
