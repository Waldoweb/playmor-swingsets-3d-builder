#!/usr/bin/env python3
"""
Give the 5 ft decks that lacked one a Picnic Table Kit mount, and set every
tower's picnic mounts to the height that puts the seats 16" off the ground.

Weldon (2026-10-05): the picnic table also fits under 5 ft towers. The Sky
Tower (5 ft), the King's Tower (5 ft) and the DX Sky Tower's 5 ft bay already
had a mount; these did not:

  P-PT    Play Tower            the middle of its one bay
  P-DPT   DX Play Tower         the middle of its 5 ft bay (the back)
  P-ST    Summit Tower          the middle of its one bay
  P-DSMT  DX Summit Tower       the middle of its 5 ft bay

The mount's height sets the table's. They were drawn at two: on the ground
(0) on the Play, Sky and Summit Towers, and on the floor (0.153) on the
deluxe and King's towers -- seats 8.3" and 14.4" up. Weldon (2026-10-05):
the top of the seat is 16" from the ground, on every tower. The table hangs
by `joint,1,picnic`, 0.050 above its own origin, and its seat boards top out
at 0.262 in its own space, so every tower's picnic mount goes to
0.4064 - 0.262 + 0.050 = 0.194. (The dot is drawn 0.393 higher, at the table
top: sockets.config marker_offsets.) On the Summit towers the tire swing
hangs in the same spot; the room test lets one or the other in, not both.

The app puts a table in a saved design back onto its mount when it loads
(restoreConnections), so designs saved at the old heights come up at 16" too.

Each new mount is a joint node `joint_floor_center,0,picnic`, appended beside
the tower's other joints (same parent), so no existing node moves and saved
designs keep their joints. Then every `...,picnic` joint on every tower is
moved up or down to MOUNT_Y, keeping its place across the floor. Only the
JSON chunk changes. Running it again changes nothing.

Usage:  python3 tools/add_picnic_mounts.py [--dry-run]
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
NAME = "joint_floor_center,0,picnic"

SEAT = 0.4064  # 16", the top of the seat above the ground
SEAT_IN_TABLE = 0.262  # the seat boards' top in PT-K's own space
JOINT_IN_TABLE = 0.050  # PT-K's joint,1,picnic, in its own space
MOUNT_Y = round(SEAT - SEAT_IN_TABLE + JOINT_IN_TABLE, 4)

# tower: where the new mount goes across the floor, in the model's own space
# (x, z); its height is MOUNT_Y.
TOWERS = {
    "P-PT": (0.0, 0.0),
    "P-DPT": (0.0, -0.615),
    "P-ST": (0.0, 0.0),
    "P-DSMT": (0.0, -0.42),
}


def read_glb(path):
    data = open(path, "rb").read()
    length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + length]), data[20 + length :]


def write_glb(gltf, rest):
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + len(rest)
    return struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(text), b"JSON") + text + rest


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


def mount(stem, xz, dry_run):
    where = (xz[0], MOUNT_Y, xz[1])
    paths = glob.glob(os.path.join(MODELS, stem + ".*.glb"))
    assert len(paths) == 1, (stem, paths)
    path = paths[0]
    gltf, rest = read_glb(path)
    nodes = gltf["nodes"]
    existing = next((i for i, n in enumerate(nodes) if n.get("name") == NAME), None)
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def world(i):
        m = local_matrix(nodes[i])
        while i in parent:
            i = parent[i]
            m = local_matrix(nodes[i]) @ m
        return m

    # Beside an end rail joint, or any joint: the same parent, so the new
    # node lives in the same space as its neighbours.
    sibling = next(
        (i for i, n in enumerate(nodes) if n.get("name", "").lower().startswith("joint") and "end_rail" in n.get("name", "")),
        None,
    )
    if sibling is None:
        sibling = next(i for i, n in enumerate(nodes) if n.get("name", "").lower().startswith("joint"))
    up = world(parent[sibling]) if sibling in parent else np.eye(4)
    local = np.linalg.inv(up) @ np.array(list(where) + [1.0])
    translation = [float(v) for v in local[:3]]
    if existing is not None:
        # Already there: put it where it belongs, if it is not.
        if np.allclose(nodes[existing].get("translation", [0, 0, 0]), translation, atol=1e-6):
            print("  %s: %s already in place" % (stem, NAME))
            return
        print("  %s: %s moved to %s" % (stem, NAME, where))
        if dry_run:
            return
        nodes[existing]["translation"] = translation
    else:
        # An empty: its facing is the 0 in its name, not a rotation.
        print("  %s: + %s at %s" % (stem, NAME, where))
        if dry_run:
            return
        nodes.append({"name": NAME, "translation": translation})
        if sibling in parent:
            nodes[parent[sibling]]["children"].append(len(nodes) - 1)
        else:
            gltf["scenes"][gltf.get("scene", 0)]["nodes"].append(len(nodes) - 1)
    data = write_glb(gltf, rest)
    digest = hashlib.sha256(data).hexdigest()[:8]
    out = os.path.join(MODELS, "%s.%s.glb" % (stem, digest))
    with open(out, "wb") as f:
        f.write(data)
    if os.path.abspath(out) != os.path.abspath(path):
        os.remove(path)
    print("  ->", os.path.basename(out))


def level(path, dry_run):
    """Every picnic mount in this model to MOUNT_Y."""
    stem = os.path.basename(path).split(".")[0]
    gltf, rest = read_glb(path)
    nodes = gltf["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def world(i):
        m = local_matrix(nodes[i])
        while i in parent:
            i = parent[i]
            m = local_matrix(nodes[i]) @ m
        return m

    changed = False
    for i, n in enumerate(nodes):
        fields = n.get("name", "").split(",")
        if not fields[0].lower().startswith("joint") or len(fields) < 3 or fields[2] != "picnic":
            continue
        here = world(i)[:3, 3]
        if abs(here[1] - MOUNT_Y) < 1e-4:
            continue
        up = world(parent[i]) if i in parent else np.eye(4)
        local = np.linalg.inv(up) @ np.array([here[0], MOUNT_Y, here[2], 1.0])
        print("  %s: %s %.3f -> %.3f" % (stem, n["name"], here[1], MOUNT_Y))
        n["translation"] = [float(v) for v in local[:3]]
        changed = True
    if dry_run or not changed:
        return
    data = write_glb(gltf, rest)
    out = os.path.join(MODELS, "%s.%s.glb" % (stem, hashlib.sha256(data).hexdigest()[:8]))
    with open(out, "wb") as f:
        f.write(data)
    if os.path.abspath(out) != os.path.abspath(path):
        os.remove(path)
    print("  ->", os.path.basename(out))


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for stem, xz in TOWERS.items():
        mount(stem, xz, dry)
    # The towers' mounts, not the table's own joint.
    for path in sorted(glob.glob(os.path.join(MODELS, "P-*.glb"))):
        level(path, dry)
