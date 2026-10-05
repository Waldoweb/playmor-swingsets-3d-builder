#!/usr/bin/env python3
"""
Set the two outer deck joints on a tower side just clear of the centre slat.

A 5 ft side carries three deck joints: left, centre, right. Two ladders or
slides on the outer pair should leave the centre rail slat standing between
them, and sit close to it. What decides "clear" is the cut-out on the part's
joint -- the box that hides any slat it touches -- not the part's visible
width: a 5 ft ladder's is 0.60 wide, about 3 cm wider than its rails.

So each outer joint goes CUT[layer] + MARGIN beyond the edge of the centre
slat, measured from the slat itself rather than the centre joint (on a few
towers the two are a centimetre apart, which left one ladder closer than the
other). Several towers had the joints at 0.29-0.31 and lost every slat.

Only the JSON chunk of each GLB is rewritten -- the outer joints' translation,
worked out in model space and converted back through the parent's transform --
so geometry, node order and joint names are untouched and old saves still
line up.

Usage:  python3 tools/spread_side_joints.py [--dry-run]
Then:   node tools/build_models.js
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

# Half the widest cut-out among the ladders and slides each deck height takes:
# 4 ft gang plank, 5 ft ladder, 7 ft DX wave slide.
CUT = {"5": 0.285, "6": 0.30, "8": 0.285}
MARGIN = 0.005
DECK_LAYERS = set(CUT)
TOWERS = ["P-PT", "P-DPT", "P-WT", "P-WT-7", "P-ST", "P-DST", "P-DSMT", "P-KT-5", "P-KT"]
# The DX Play Tower's sides along z are 4 ft, with six slats and no centre
# one to keep.
SKIP = {("P-DPT", "z")}


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


def world_matrices(gltf):
    nodes = gltf["nodes"]
    out = [None] * len(nodes)

    def visit(index, parent):
        out[index] = parent @ local_matrix(nodes[index])
        for child in nodes[index].get("children", []):
            visit(child, out[index])

    for scene in gltf.get("scenes", []):
        for root in scene.get("nodes", []):
            visit(root, np.eye(4))
    return out


def parent_of(gltf):
    parents = {}
    for i, node in enumerate(gltf["nodes"]):
        for child in node.get("children", []):
            parents[child] = i
    return parents


def deck_joints(gltf, world):
    """Index and model-space position of every deck-height joint."""
    joints = []
    for i, node in enumerate(gltf["nodes"]):
        name = node.get("name", "")
        fields = name.split(",")
        if not name.lower().startswith("joint") or len(fields) < 3:
            continue
        if fields[2] not in DECK_LAYERS or world[i] is None:
            continue
        joints.append((i, fields[2], world[i][:3, 3].copy()))
    return joints


def sides(joints):
    """
    Group joints into tower sides: same layer, same height, same face plane.
    Yields (axis along the side, plane coordinate, [joints]).
    """
    groups = {}
    for joint in joints:
        _, layer, p = joint
        for along, across in (("x", 2), ("z", 0)):
            key = (layer, round(p[1], 1), along, round(p[across] / 0.05))
            groups.setdefault(key, []).append(joint)
    for (layer, _, along, _), members in groups.items():
        yield layer, along, members


def clusters(members, axis):
    """Merge joints within 0.1 along the side into openings, sorted."""
    out = []
    for joint in sorted(members, key=lambda j: j[2][axis]):
        if out and abs(joint[2][axis] - out[-1][-1][2][axis]) <= 0.1:
            out[-1].append(joint)
        else:
            out.append([joint])
    return out


def fence_boxes(gltf, world):
    """Model-space bounding box of every rail slat, from the accessor bounds."""
    boxes = []
    for i, node in enumerate(gltf["nodes"]):
        if "fence" not in node.get("name", "").lower() or "mesh" not in node:
            continue
        for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
            accessor = gltf["accessors"][primitive["attributes"]["POSITION"]]
            lo, hi = accessor["min"], accessor["max"]
            corners = np.array(
                [[x, y, z, 1.0] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
            )
            points = (world[i] @ corners.T).T[:, :3]
            boxes.append((points.min(axis=0), points.max(axis=0)))
    return boxes


def centre_slat(boxes, centre_joint, axis):
    """The slat the centre joint sits in front of: (middle, half width)."""
    across = 2 if axis == 0 else 0
    best = None
    for lo, hi in boxes:
        middle = (lo + hi) / 2
        if abs(middle[across] - centre_joint[across]) > 0.1:
            continue
        # Rail height, not a ground-level panel under the deck.
        if not (lo[1] - 0.6 < centre_joint[1] < hi[1] + 0.6):
            continue
        d = abs(middle[axis] - centre_joint[axis])
        if d < 0.06 and (best is None or d < best[0]):
            best = (d, middle[axis], (hi[axis] - lo[axis]) / 2)
    return best and best[1:]


def spread(stem, dry_run):
    path = glob.glob(os.path.join(MODELS, stem + ".*.glb"))[0]
    gltf, rest = read_glb(path)
    world = world_matrices(gltf)
    parents = parent_of(gltf)
    boxes = fence_boxes(gltf, world)
    changed = []

    for layer, along, members in sides(deck_joints(gltf, world)):
        if (stem, along) in SKIP:
            continue
        axis = 0 if along == "x" else 2
        openings = clusters(members, axis)
        if len(openings) != 3:
            continue
        slat = centre_slat(boxes, openings[1][0][2], axis)
        if not slat:
            print("  no centre slat for", openings[1][0], "-- left alone")
            continue
        middle, half = slat
        offset = half + CUT[layer] + MARGIN
        for sign, opening in ((-1, openings[0]), (1, openings[2])):
            for index, _, p in opening:
                target = p.copy()
                target[axis] = middle + sign * offset
                parent = world[parents[index]] if index in parents else np.eye(4)
                local = np.linalg.inv(parent) @ np.append(target, 1.0)
                node = gltf["nodes"][index]
                before = abs(p[axis] - middle)
                node["translation"] = [float(v) for v in local[:3]]
                changed.append(
                    "  %-28s layer %s  %.3f -> %.3f from the slat"
                    % (node["name"], layer, before, offset)
                )

    print(os.path.basename(path))
    print("\n".join(changed) if changed else "  (nothing to move)")
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
    for stem in TOWERS:
        spread(stem, dry)
