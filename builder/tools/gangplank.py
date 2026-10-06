#!/usr/bin/env python3
"""
Fit each gang plank to the tower's deck, and give it posts at its top end.

Weldon (2026-10-06): the top of the plank should be level with the top of
the tower floor, and its end should meet the face of the floor's rim board.
Measured in the builder with each plank fitted to every tower that takes
it, the plank's top end stood 2.3-2.6 cm above a 5 ft deck (4.8 on the
King's Tower 5 ft, whose deck is lower) and 3.7-4.8 cm above the DX Play
Tower's 4 ft deck, and ran 0.8 cm (5 ft) and 2.6 cm (4 ft) into the rim.

So the plank is brought down at its top end and not at all at its foot,
which stays on the ground -- each point drops in proportion to how far up
the plank it is -- and moved out along its length so the end of its deck
boards is on the rim's face (the side rails, 8 mm longer, tuck in behind). Uprights stay upright. Every mesh but the joint moves; the joint, which
places the plank on the tower, does not.

Then (Weldon, 2026-10-06, with a PlayMor photo) the real plank has a third
pair of upright posts at the top, standing against the tower's floor frame,
and the ropes attach to those. The model had posts only down the slope; its
ropes ran on to two rings fixed to the tower. So:
  - two posts like the others (the same 2x4 section, on the same line each
    side, in the trim colour), their back faces on the rim's face, from the
    bottom of the frame -- 0.2 below the deck -- up to the rail over the
    opening (Weldon). That rail is at a different height on each tower, so
    the posts are a node of their own, `top_posts`, drawn to just past the
    top rope, which the builder stretches to the rail's top once the plank
    is on a tower (index.html, Fit_top_posts); its extras say where the
    posts stand;
  - the ropes' ends, and the little loop joining the two ropes there, now
    finish inside these posts, so the ropes are tied to them;
  - the four rings that held the ropes to the tower come off.

Run it on the planks as they were (it checks): it is not meant to be run
twice.

Usage:  python3 tools/gangplank.py [--dry-run] [P-GP-10] [P-GP-12]
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

# The deck top and the rim's face, in the plank's own space (its foot at 0,
# its top end about -3.32 along z), taken across the towers: 5 ft decks are
# 1.519-1.523 (the King's Tower 5 ft's 1.497 aside) with the rim at
# -3.315..-3.320; the DX Play Tower's 4 ft deck is 1.190 at the front and
# 1.202 at the sides, its rim at -3.302 and -3.296. Midway in each.
FIT = {
    "P-GP-12": {"deck": 1.5206, "face": -3.317},
    "P-GP-10": {"deck": 1.1957, "face": -3.299},
}
BELOW_DECK = 0.20  # post foot below the deck: the frame's bottom
ABOVE_ROPE = 0.045  # post top above the top rope's end
POST_DEPTH = 0.1016  # along the plank, as the other posts (a 2x4's 4")
TOP_POSTS = "top_posts"  # the node the builder stretches (index.html, Fit_top_posts)

COMPONENT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_glb(path):
    data = open(path, "rb").read()
    length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20 : 20 + length])
    rest = data[20 + length :]
    bin_length = struct.unpack("<I", rest[:4])[0]
    return gltf, rest[8 : 8 + bin_length]


def write_glb(gltf, binary):
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary = bytes(binary) + b"\0" * (-len(binary) % 4)
    return (
        struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(text) + 8 + len(binary))
        + struct.pack("<I4s", len(text), b"JSON") + text
        + struct.pack("<I4s", len(binary), b"BIN\0") + binary
    )


def read_accessor(gltf, binary, index):
    a = gltf["accessors"][index]
    v = gltf["bufferViews"][a["bufferView"]]
    assert "byteStride" not in v and not a.get("byteOffset")
    arr = np.frombuffer(binary, dtype=COMPONENT[a["componentType"]], count=a["count"] * WIDTH[a["type"]],
                        offset=v.get("byteOffset", 0))
    return arr.reshape(-1, WIDTH[a["type"]]) if WIDTH[a["type"]] > 1 else arr.copy()


def parts(position, index):
    """Label each vertex with its loose part (vertices welded by position)."""
    _, weld = np.unique(np.round(position, 4), axis=0, return_inverse=True)
    weld = weld.ravel()
    parent = list(range(weld.max() + 1))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in index.reshape(-1, 3):
        ra = find(weld[a])
        parent[find(weld[b])] = ra
        parent[find(weld[c])] = ra
    return np.array([find(w) for w in weld])


def box(x0, x1, y0, y1, z0, z1):
    """A box as 24 vertices (flat faces), its normals, UVs and triangles."""
    faces = [
        ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
        ((-1, 0, 0), [(x0, y0, z1), (x0, y1, z1), (x0, y1, z0), (x0, y0, z0)]),
        ((0, 1, 0), [(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)]),
        ((0, -1, 0), [(x0, y0, z1), (x0, y0, z0), (x1, y0, z0), (x1, y0, z1)]),
        ((0, 0, 1), [(x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (x0, y0, z1)]),
        ((0, 0, -1), [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)]),
    ]
    pos, nrm, uv, tri = [], [], [], []
    for normal, corners in faces:
        base = len(pos)
        for k, c in enumerate(corners):
            pos.append(c)
            nrm.append(normal)
            uv.append(((k in (2, 3)) * 1.0, (k in (1, 2)) * 1.0))
        # Wound so the face looks along its normal.
        a, b, c = (np.array(corners[i]) for i in (0, 1, 2))
        if np.dot(np.cross(b - a, c - a), normal) > 0:
            tri += [base, base + 1, base + 2, base, base + 2, base + 3]
        else:
            tri += [base, base + 2, base + 1, base, base + 3, base + 2]
    return np.array(pos, np.float32), np.array(nrm, np.float32), np.array(uv, np.float32), np.array(tri)


def rebuild(stem, dry_run):
    found = glob.glob(os.path.join(MODELS, stem + ".*.glb"))
    assert len(found) == 1, found
    gltf, binary = read_glb(found[0])
    nodes, meshes, materials = gltf["nodes"], gltf["meshes"], gltf["materials"]

    def node_with(material_prefix):
        for n in nodes:
            if "mesh" in n:
                prim = meshes[n["mesh"]]["primitives"][0]
                if materials[prim["material"]]["name"].startswith(material_prefix):
                    return n
        raise KeyError(material_prefix)

    posts_prim = meshes[node_with("White base")["mesh"]]["primitives"][0]
    rope_prim = meshes[node_with("Polyerster")["mesh"]]["primitives"][0]
    metal_prim = meshes[node_with("Metal")["mesh"]]["primitives"][0]
    # The deck boards: the larger of the two wood meshes (the other is the
    # side rails).
    boards_prim = max(
        (meshes[n["mesh"]]["primitives"][0] for n in nodes if "mesh" in n
         and materials[meshes[n["mesh"]]["primitives"][0]["material"]]["name"].startswith("Wood")),
        key=lambda prim: gltf["accessors"][prim["attributes"]["POSITION"]]["count"],
    )

    replace = {}  # accessor index -> new array
    current = lambda index: replace[index] if index in replace else read_accessor(gltf, binary, index)

    if any(n.get("name") == TOP_POSTS for n in nodes):
        print("%s: already done (it has its top posts)" % stem)
        return

    # Fit to the deck. Every mesh sits straight under the root, untransformed,
    # so its coordinates are the plank's own.
    root = next(i for i, n in enumerate(nodes) if n.get("children") and not any(i in m.get("children", []) for m in nodes))
    for i, n in enumerate(nodes):
        if i != root:
            assert not any(k in n for k in ("translation", "rotation", "scale", "matrix")) or n["name"].lower().startswith("joint"), n["name"]
    prims = [prim for n in nodes if "mesh" in n and not n["name"].lower().startswith("joint")
             for prim in meshes[n["mesh"]]["primitives"]]
    # The deck boards' end is what is seen meeting the rim; the side rails
    # run 8 mm further and tuck in behind the rim's face.
    boards = read_accessor(gltf, binary, boards_prim["attributes"]["POSITION"])
    end_z = boards[:, 2].min()
    top_end = boards[boards[:, 2] < boards[:, 2].min() + 0.05][:, 1].max()
    dy, dz = FIT[stem]["deck"] - top_end, FIT[stem]["face"] - end_z
    print("%s: top end %.4f at z %.4f -> down %.4f at the top, out %.4f" % (stem, top_end, end_z, -dy, dz))
    for prim in prims:
        key = prim["attributes"]["POSITION"]
        moved = read_accessor(gltf, binary, key).copy()
        share = np.clip(moved[:, 2] / end_z, 0, 1)
        moved[:, 1] += dy * share
        moved[:, 2] += dz
        replace[key] = moved

    # The top posts: their own node, so the builder can stretch them to the
    # rail over the opening, which is at a different height on each tower.
    # The mesh stands on the node's origin, the node at the posts' foot; the
    # height drawn is the least they ever need -- just past the top rope.
    pos = current(posts_prim["attributes"]["POSITION"])
    rope = current(rope_prim["attributes"]["POSITION"])
    rope_top = rope[rope[:, 2] < -3.2][:, 1].max()
    z1 = FIT[stem]["face"]
    y0, y1 = FIT[stem]["deck"] - BELOW_DECK, rope_top + ABOVE_ROPE
    xs = np.unique(np.round(np.abs(pos[:, 0]), 4))
    x_in, x_out = float(xs.min()), float(xs.max())
    print("  posts z %.3f..%.3f, from %.3f, at least to %.3f (rope top %.3f), x %.4f..%.4f" % (
        z1, z1 + POST_DEPTH, y0, y1, rope_top, x_in, x_out))
    tp = [np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32), np.zeros((0, 2), np.float32)]
    tidx = np.zeros(0, np.int64)
    for x0, x1 in ((-x_out, -x_in), (x_in, x_out)):
        p, n, u, t = box(x0, x1, 0.0, y1 - y0, z1, z1 + POST_DEPTH)
        tidx = np.concatenate([tidx, t + len(tp[0])])
        tp = [np.vstack([tp[0], p]), np.vstack([tp[1], n]), np.vstack([tp[2], u])]
    added = []  # (accessor dict, array) for the new mesh

    def accessor(arr, kind, component, minmax=False):
        a = {"componentType": component, "count": len(arr), "type": kind}
        if minmax:
            a["min"] = [float(x) for x in arr.min(axis=0)]
            a["max"] = [float(x) for x in arr.max(axis=0)]
        added.append((a, arr))
        return len(gltf["accessors"]) + len(added) - 1

    prim = {
        "attributes": {
            "POSITION": accessor(tp[0], "VEC3", 5126, True),
            "NORMAL": accessor(tp[1], "VEC3", 5126),
            "TEXCOORD_0": accessor(tp[2], "VEC2", 5126),
        },
        "indices": accessor(tidx.astype(np.uint16), "SCALAR", 5123),
        "material": posts_prim["material"],
    }
    meshes.append({"name": TOP_POSTS, "primitives": [prim]})
    nodes.append({
        "name": TOP_POSTS,
        "mesh": len(meshes) - 1,
        "translation": [0.0, float(y0), 0.0],
        # Coloured as the other posts; and where the builder finds the
        # tower's rail, in the plank's own space.
        "extras": {"frame_as": nodes[[i for i, n in enumerate(nodes) if n.get("mesh") is not None
                                      and meshes[n["mesh"]]["primitives"][0] is posts_prim][0]]["name"],
                   "post_face": float(z1), "post_x": float((x_in + x_out) / 2),
                   "post_depth": POST_DEPTH, "post_deck": float(FIT[stem]["deck"])},
    })
    nodes[root].setdefault("children", []).append(len(nodes) - 1)

    # The rings at the tower end.
    mpos = current(metal_prim["attributes"]["POSITION"])
    midx = read_accessor(gltf, binary, metal_prim["indices"]).astype(np.int64)
    label = parts(mpos, midx)
    drop = {l for l in np.unique(label) if mpos[label == l][:, 2].max() < -3.2}
    if drop:
        keep = np.array([l not in drop for l in label])
        remap = np.cumsum(keep) - 1
        tris = midx.reshape(-1, 3)
        tris = tris[keep[tris].all(axis=1)]
        print("  rings off: %d parts, %d of %d vertices kept" % (len(drop), keep.sum(), len(keep)))
        for key in metal_prim["attributes"]:
            replace[metal_prim["attributes"][key]] = current(metal_prim["attributes"][key])[keep]
        replace[metal_prim["indices"]] = remap[tris].reshape(-1).astype(
            COMPONENT[gltf["accessors"][metal_prim["indices"]]["componentType"]])

    # Write the views out again in order, the changed ones with their new data.
    blob = bytearray()
    owner = {gltf["accessors"][i]["bufferView"]: i for i in range(len(gltf["accessors"]))}
    for vi, view in enumerate(gltf["bufferViews"]):
        if vi in owner and owner[vi] in replace:
            data = np.ascontiguousarray(replace[owner[vi]]).tobytes()
            a = gltf["accessors"][owner[vi]]
            arr = replace[owner[vi]]
            a["count"] = len(arr)
            if "min" in a:
                a["min"] = [float(x) for x in np.atleast_1d(arr.min(axis=0))]
                a["max"] = [float(x) for x in np.atleast_1d(arr.max(axis=0))]
        else:
            data = binary[view.get("byteOffset", 0) : view.get("byteOffset", 0) + view["byteLength"]]
        while len(blob) % 4:
            blob.append(0)
        view["byteOffset"] = len(blob)
        view["byteLength"] = len(data)
        blob.extend(data)
    for a, arr in added:
        data = np.ascontiguousarray(arr).tobytes()
        while len(blob) % 4:
            blob.append(0)
        gltf["bufferViews"].append({
            "buffer": 0, "byteOffset": len(blob), "byteLength": len(data),
            "target": 34963 if a["type"] == "SCALAR" else 34962,
        })
        blob.extend(data)
        a["bufferView"] = len(gltf["bufferViews"]) - 1
        gltf["accessors"].append(a)
    gltf["buffers"] = [{"byteLength": len(blob)}]
    if dry_run:
        return
    data = write_glb(gltf, blob)
    out = os.path.join(MODELS, "%s.%s.glb" % (stem, hashlib.sha256(data).hexdigest()[:8]))
    with open(out, "wb") as fh:
        fh.write(data)
    if os.path.abspath(out) != os.path.abspath(found[0]):
        os.remove(found[0])
    print("  ->", os.path.basename(out), "%d KB" % (len(data) // 1024))


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for stem in [a for a in sys.argv[1:] if not a.startswith("--")] or ["P-GP-10", "P-GP-12"]:
        rebuild(stem, dry)
