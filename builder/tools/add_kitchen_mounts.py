#!/usr/bin/env python3
"""
Give the towers a Kitchen Kit mount at the ends where one fits.

The Kitchen Kit stands in a tower's end bay, at the spot an end rail goes,
with its awning just under the deck. Weldon (2026-10-05): it goes on 5 ft and
7 ft towers alike. Until now only the DX Sky, DX Summit and 7 ft King's
Towers had the mount, and the 5 ft King's had its taken out because the
kitchen's awning came up through the lower deck.

Each mount is a joint node beside the end rail's, at the same place and
facing (so the two share one opening), named like it with the layer
`kitchen`. On a 5 ft deck the name ends `,short`: the app hangs the Kitchen
Kit's short version there (Morph_target_for), built by
`raise_tower.py KK__short`, whose awning is 0.64 m lower -- the same step
there is between a tower's 5 ft and 7 ft decks.

Which ends:
  P-PT        both ends (5 ft)
  P-DPT       the back, under its 5 ft deck; the front is under the 4 ft
              deck, which even the short kitchen will not fit under
  P-WT        all four sides (5 ft)
  P-WT-7      all four sides (7 ft)
  P-KT-5      the left end: its old mount, taken out as disabled_..., is put
              back as a short one (and dropped from sockets.config
              remove_joints)

New nodes are appended, so no existing node moves and saved designs keep
their joints. Only the JSON chunk changes. Running it again adds nothing.

Usage:  python3 tools/add_kitchen_mounts.py [--dry-run]
Then:   node tools/build_models.js
"""

import glob
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "..", "models")

# tower: (end rail joints to pair with a kitchen mount, short kitchen?)
TOWERS = {
    "P-PT": (["joint_back", "joint_front"], True),
    "P-DPT": (["joint_back"], True),
    "P-WT": (["joint_back", "joint_front", "joint_left", "joint_right"], True),
    "P-WT-7": (["joint_back", "joint_front", "joint_left", "joint_right"], False),
    "P-KT-5": ([], True),
}
# Old mounts taken out by set_joint_layers.js that are wanted back.
RESTORE = {"P-KT-5": {"disabled_joint_left,3,kitchen": "joint_left,3,kitchen,short"}}


def read_glb(path):
    data = open(path, "rb").read()
    length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + length]), data[20 + length :]


def write_glb(gltf, rest):
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + len(rest)
    return struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(text), b"JSON") + text + rest


def mount(stem, ends, short, dry_run):
    paths = glob.glob(os.path.join(MODELS, stem + ".*.glb"))
    assert len(paths) == 1, (stem, paths)
    path = paths[0]
    gltf, rest = read_glb(path)
    nodes = gltf["nodes"]
    names = {n.get("name", "") for n in nodes}
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    changed = False

    for old, new in RESTORE.get(stem, {}).items():
        for n in nodes:
            if n.get("name") == old:
                n["name"] = new
                print("  %s: %s -> %s" % (stem, old, new))
                changed = True

    for i, n in enumerate(list(nodes)):
        fields = n.get("name", "").split(",")
        if len(fields) < 3 or fields[2] != "end_rail" or fields[0] not in ends:
            continue
        name = "%s,%s,kitchen%s" % (fields[0], fields[1], ",short" if short else "")
        if name in names:
            continue
        copy = {k: v for k, v in n.items() if k in ("translation", "rotation", "scale", "matrix")}
        copy["name"] = name
        nodes.append(copy)
        if i in parent:
            nodes[parent[i]]["children"].append(len(nodes) - 1)
        else:
            gltf["scenes"][gltf.get("scene", 0)]["nodes"].append(len(nodes) - 1)
        names.add(name)
        print("  %s: + %s" % (stem, name))
        changed = True

    if dry_run or not changed:
        return
    data = write_glb(gltf, rest)
    digest = hashlib.sha256(data).hexdigest()[:8]
    out = os.path.join(MODELS, "%s.%s.glb" % (stem, digest))
    with open(out, "wb") as f:
        f.write(data)
    if os.path.abspath(out) != os.path.abspath(path):
        os.remove(path)
    print("  ->", os.path.basename(out))


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for stem, (ends, short) in TOWERS.items():
        mount(stem, ends, short, dry)
