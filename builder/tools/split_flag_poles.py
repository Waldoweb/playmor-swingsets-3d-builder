#!/usr/bin/env python3
"""
Give each tower flag's pole a node of its own.

A flag is chosen on its own -- its colour is what the options then change --
and it can be taken off (Weldon, 2026-10-05). Its pole goes with it, in the
outline and when it is removed, and stays out of the tower's outline. But
every pole was drawn as part of the tower's white trim mesh (Cube138 on the
Play Tower, Cube201 on the King's), so there was nothing to show or hide.

This finds each pole -- a thin upright piece of the trim, 20 mm across and
about half a metre tall, standing under a flag -- and moves its triangles
into a node of its own beside the trim, named `pole_<flag>` (not "flag...",
which would make it a flag) and carrying, as glTF extras:
  flag_pole: the flag it holds up ("flag1")
  frame_as:  the trim's name, so frame colours treat it as the trim

Only the JSON chunk and a few appended index arrays change: the new node
reuses the trim's vertex data, so no geometry or texture is re-encoded. The
trim's own triangle list is rewritten without the poles. Running it again
finds no poles left in the trim and changes nothing.

Usage:  python3 tools/split_flag_poles.py [--dry-run] [STEM ...]
        (default: every tower with flags)
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
TOWERS = ["P-PT", "P-DPT", "P-WT", "P-WT-7", "P-ST", "P-DST", "P-DSMT", "P-KT", "P-KT-5"]

POLE_WIDTH = 0.03  # a pole is thinner than this across
POLE_HEIGHT = 0.3  # and taller than this
NEAR_FLAG = 0.15  # and stands within this of a flag, across the floor

COMPONENT_DTYPE = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}
TYPE_SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


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


def read_accessor(gltf, binary, index):
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    dtype = COMPONENT_DTYPE.get(accessor["componentType"], np.float32)
    if accessor["componentType"] == 5126:
        dtype = np.float32
    width = TYPE_SIZE[accessor["type"]]
    item = np.dtype(dtype).itemsize * width
    stride = view.get("byteStride", item)
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    count = accessor["count"]
    rows = np.frombuffer(binary, dtype=np.uint8, count=stride * (count - 1) + item, offset=offset)
    out = np.lib.stride_tricks.as_strided(rows, shape=(count, item), strides=(stride, 1)).copy()
    return out.view(dtype).reshape(count, width) if width > 1 else out.view(dtype).reshape(count)


def append_indices(gltf, binary, indices, component_type):
    """Add an index list to the binary chunk; returns its accessor index."""
    dtype = COMPONENT_DTYPE[component_type]
    data = np.asarray(indices, dtype=dtype).tobytes()
    while len(binary) % 4:
        binary.append(0)
    offset = len(binary)
    binary.extend(data)
    gltf["bufferViews"].append(
        {"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": 34963}
    )
    gltf["accessors"].append(
        {
            "bufferView": len(gltf["bufferViews"]) - 1,
            "componentType": component_type,
            "count": int(len(indices)),
            "type": "SCALAR",
        }
    )
    gltf["buffers"][0]["byteLength"] = len(binary)
    return len(gltf["accessors"]) - 1


def components(triangles, positions):
    """Group triangles that share a corner, by position (the export does not
    share vertices between faces with different normals)."""
    keys = {}
    vertex_key = np.empty(len(positions), dtype=np.int64)
    for i, p in enumerate(np.round(positions, 5)):
        vertex_key[i] = keys.setdefault(tuple(p), len(keys))
    parent = list(range(len(keys)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for tri in triangles:
        a, b, c = (find(vertex_key[v]) for v in tri)
        parent[b] = a
        parent[find(c)] = find(a)
    groups = {}
    for t, tri in enumerate(triangles):
        groups.setdefault(find(vertex_key[tri[0]]), []).append(t)
    return list(groups.values())


def split(stem, dry_run):
    paths = glob.glob(os.path.join(MODELS, stem + ".*.glb"))
    assert len(paths) == 1, (stem, paths)
    path = paths[0]
    gltf, binary = read_glb(path)
    nodes = gltf["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def world(i):
        m = local_matrix(nodes[i])
        while i in parent:
            i = parent[i]
            m = local_matrix(nodes[i]) @ m
        return m

    def node_box(i):
        m = world(i)
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for primitive in gltf["meshes"][nodes[i]["mesh"]]["primitives"]:
            a = gltf["accessors"][primitive["attributes"]["POSITION"]]
            for cx in (0, 1):
                for cy in (0, 1):
                    for cz in (0, 1):
                        corner = [(a["min"], a["max"])[c][k] for k, c in enumerate((cx, cy, cz))]
                        p = (m @ np.array(corner + [1.0]))[:3]
                        lo, hi = np.minimum(lo, p), np.maximum(hi, p)
        return lo, hi

    flags = {}
    for i, n in enumerate(nodes):
        name = n.get("name", "")
        if "mesh" in n and name.lower().split(",")[0].startswith("flag"):
            flags[name.split(",")[0]] = node_box(i)

    print(os.path.basename(path), "flags:", ", ".join(sorted(flags)) or "none")
    changed = False
    for i, n in enumerate(list(nodes)):
        name = n.get("name", "")
        if "mesh" not in n or name.lower().startswith(("flag", "pole_", "joint")):
            continue
        m = world(i)
        mesh = gltf["meshes"][n["mesh"]]
        for p_index, primitive in enumerate(mesh["primitives"]):
            if "indices" not in primitive or primitive.get("mode", 4) != 4:
                continue
            local = read_accessor(gltf, binary, primitive["attributes"]["POSITION"]).astype(float)
            positions = (m[:3, :3] @ local.T).T + m[:3, 3]
            index_accessor = gltf["accessors"][primitive["indices"]]
            triangles = read_accessor(gltf, binary, primitive["indices"]).reshape(-1, 3)
            poles = {}
            for group in components(triangles, positions):
                pts = positions[np.unique(triangles[group].ravel())]
                lo, hi = pts.min(axis=0), pts.max(axis=0)
                size = hi - lo
                if size[0] > POLE_WIDTH or size[2] > POLE_WIDTH or size[1] < POLE_HEIGHT:
                    continue
                centre = (lo + hi) / 2
                for flag, (flo, fhi) in flags.items():
                    if (
                        flo[0] - NEAR_FLAG < centre[0] < fhi[0] + NEAR_FLAG
                        and flo[2] - NEAR_FLAG < centre[2] < fhi[2] + NEAR_FLAG
                        and hi[1] > flo[1] - 0.05
                    ):
                        poles.setdefault(flag, []).extend(group)
                        break
            if not poles:
                continue
            for flag, group in sorted(poles.items()):
                print("  %s: pole for %s in %s (%d triangles)" % (stem, flag, name, len(group)))
            if dry_run:
                continue
            taken = set(t for group in poles.values() for t in group)
            keep = [t for t in range(len(triangles)) if t not in taken]
            ctype = index_accessor["componentType"]
            primitive["indices"] = append_indices(gltf, binary, triangles[keep].ravel(), ctype)
            for flag, group in sorted(poles.items()):
                pole_primitive = {k: v for k, v in primitive.items() if k != "indices"}
                pole_primitive["indices"] = append_indices(gltf, binary, triangles[group].ravel(), ctype)
                gltf["meshes"].append({"name": "pole_" + flag, "primitives": [pole_primitive]})
                pole_node = {
                    "name": "pole_" + flag,
                    "mesh": len(gltf["meshes"]) - 1,
                    "extras": {"flag_pole": flag, "frame_as": name},
                }
                for key in ("translation", "rotation", "scale", "matrix"):
                    if key in n:
                        pole_node[key] = n[key]
                nodes.append(pole_node)
                new_index = len(nodes) - 1
                if i in parent:
                    nodes[parent[i]].setdefault("children", []).append(new_index)
                else:
                    scene = gltf["scenes"][gltf.get("scene", 0)]
                    scene["nodes"].append(new_index)
            changed = True

    if dry_run or not changed:
        return
    data = write_glb(gltf, binary)
    digest = hashlib.sha256(data).hexdigest()[:8]
    out = os.path.join(MODELS, "%s.%s.glb" % (stem, digest))
    with open(out, "wb") as f:
        f.write(data)
    if os.path.abspath(out) != os.path.abspath(path):
        os.remove(path)
    print("  ->", os.path.basename(out))


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")] or TOWERS
    for stem in wanted:
        split(stem, dry)
