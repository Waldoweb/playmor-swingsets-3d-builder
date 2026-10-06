#!/usr/bin/env python3
"""
Rebuild the Wave Slide - 5ft (WS-10) to the shape of PlayMor's slide.

Weldon (2026-10-06, with two photos of the real slide): the old model was
too deep all the way down, and its walls stood full height right up to the
deck and stopped there in a square cut. The real slide is shallower, and at
the top its walls slope down into the lip that lies on the deck.

So this keeps the old model's run -- the same wave, the same 22" width, the
same reach out from the tower, its exit curling down to the ground -- and
sweeps a new cross-section along it:

  - a rounded U with a flattish bed, its walls 7" above the bed (were ~10"),
    each topped by a rim that rolls outward as in the photos;
  - a 20 mm shell, inner and outer surfaces joined round the rims;
  - at the top, the walls ease down over the level run at the deck until
    only a shallow dish is left where the lip rests on the deck.

The bed line is the old model's, measured down its middle in the builder
(world x out from the Play Tower's face, bed height); the Play Tower deck is
1.522 high there and the slide's joint sits 0.762 out.

Only the slide's own mesh changes. The joint node -- name, mesh, place --
and the root node are kept, so saved designs keep their connection; the
mesh node keeps its `,_colorize_` name and material for the colour picker.

Usage:  python3 tools/wave_slide.py [--dry-run]
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
STEM = "WS-10"

# ---------------------------------------------------------------- the shape

FACE_Z = 2.7276  # model z of the tower face (the joint's middle)
DECK = 1.522  # top of a 5 ft deck, in the slide's model space
HALF_OUT = 0.282  # half the slide's width over the rims (was 0.282)
DEPTH = 0.178  # bed to the top of the rim, full height (was ~0.26)
WALL = 0.020  # shell thickness
POWER = 2.6  # how flat the bed is: higher is flatter with steeper walls
FLARE_R = 0.028  # the rim rolling outward at the top of each wall
LIP_OUT = 0.010  # flat of the rim beyond the roll
ON_DECK = 0.07  # how far the lip lies over the deck
LOW_WALLS = 0.14  # wall height left at the lip, as a share of DEPTH
RAMP_END = 0.42  # walls reach full height this far out from the face
EXIT_TURN = math.radians(75)  # the curl down at the exit, from level
EXIT_LOW = 0.022  # where the curl leaves the bed's middle, off the ground
ACROSS = 9  # points across each half of the U
ALONG_STEP = 0.05
CAP = 3  # points round each rim's edge, between inner and outer

# The bed's middle, (out from the face, height of the bed's top surface).
# The first few points are the level run at the deck; the rest are the old
# model's wave as measured, up to where its exit curls down: the curl here
# starts a little sooner so the rims, which follow it, stay inside the old
# model's reach.
BED = [
    (-ON_DECK, DECK + WALL),
    (0.00, DECK + WALL),
    (0.10, DECK + WALL - 0.003),
    (0.24, DECK + WALL - 0.012),
    (0.30, 1.514),
    (0.398, 1.475),
    (0.498, 1.387),
    (0.598, 1.308),
    (0.698, 1.235),
    (0.798, 1.175),
    (0.898, 1.119),
    (0.998, 1.075),
    (1.098, 1.036),
    (1.198, 1.002),
    (1.298, 0.960),
    (1.398, 0.916),
    (1.498, 0.856),
    (1.598, 0.796),
    (1.698, 0.718),
    (1.798, 0.633),
    (1.898, 0.550),
    (1.998, 0.474),
    (2.098, 0.414),
    (2.198, 0.357),
    (2.298, 0.314),
    (2.398, 0.274),
    (2.460, 0.258),
]


def pchip(xs, ys, x):
    """Monotone cubic through (xs, ys): no overshoot on the level runs."""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros_like(ys)
    for k in range(1, len(xs) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0], m[-1] = d[0], d[-1]
    k = np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2)
    t = (x - xs[k]) / h[k]
    h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
    h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
    return h00 * ys[k] + h10 * h[k] * m[k] + h01 * ys[k + 1] + h11 * h[k] * m[k + 1]


def path():
    """Stations along the bed line: (u out, y up) and the distance along."""
    us, uys = zip(*BED)
    u = np.arange(us[0], us[-1], ALONG_STEP / 2)
    u = np.append(u, us[-1])
    pts = [np.array([a, pchip(us, uys, a)]) for a in u]
    # The curl: an arc carrying on from the wave's last slope, turning down
    # to EXIT_TURN below level, its radius chosen to end EXIT_LOW up.
    end = pts[-1]
    a0 = math.atan2(pts[-2][1] - end[1], end[0] - pts[-2][0])  # below level
    r = (end[1] - EXIT_LOW) / (math.cos(a0) - math.cos(EXIT_TURN))
    steps = max(4, int(r * (EXIT_TURN - a0) / (ALONG_STEP / 4)))
    for i in range(1, steps + 1):
        a = a0 + (EXIT_TURN - a0) * i / steps
        pts.append(end + r * np.array([math.sin(a) - math.sin(a0), math.cos(a) - math.cos(a0)]))
    pts = np.array(pts)
    # Resample evenly along its length.
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = int(s[-1] / ALONG_STEP) + 1
    want = np.linspace(0, s[-1], n)
    out = np.stack([np.interp(want, s, pts[:, 0]), np.interp(want, s, pts[:, 1])], axis=1)
    return out


def wall_share(u):
    """How much of the full wall height stands at u: low at the lip, easing up."""
    t = np.clip((u + ON_DECK) / (RAMP_END + ON_DECK), 0, 1)
    t = t * t * (3 - 2 * t)
    return LOW_WALLS + (1 - LOW_WALLS) * t


def half_section(share):
    """The inner surface from the bed's middle out over the right rim: (b, n)."""
    # The roll at the top: an arc of FLARE_R that leaves the wall and ends
    # level, heading outward. Fit the wall below it so the rim's far edge
    # lands at HALF_OUT and its top at DEPTH (scaled by share).
    depth = DEPTH * share
    top_inner = HALF_OUT - WALL / 2 - LIP_OUT  # where the level lip starts
    # Wall end (bw, dw) and its slope there decide the arc; solve bw by
    # fixed-point so the arc's end lands at top_inner.
    bw, dw = top_inner - FLARE_R, depth - FLARE_R * 0.5
    for _ in range(30):
        slope = POWER * dw / bw
        d = np.array([1.0, slope]) / math.hypot(1.0, slope)
        centre = np.array([bw, dw]) + FLARE_R * np.array([d[1], -d[0]])
        end = centre + np.array([0.0, FLARE_R])
        bw += top_inner - end[0]
        dw += depth - end[1]
        dw = max(dw, 1e-4)
    pts = []
    for i in range(ACROSS + 1):
        b = bw * i / ACROSS
        pts.append((b, dw * (b / bw) ** POWER))
    a0 = math.atan2(bw - centre[0], dw - centre[1])  # from straight up, toward +b
    # Angles measured from up, clockwise toward +b: the wall point sits at
    # a0 (negative, to the left of the centre), the arc ends at 0 (on top).
    for i in range(1, 4):
        a = a0 * (1 - i / 3)
        pts.append((centre[0] + FLARE_R * math.sin(a), centre[1] + FLARE_R * math.cos(a)))
    pts.append((top_inner + LIP_OUT, centre[1] + FLARE_R))
    return pts


def section(share):
    """Closed loop round the shell: inner left rim -> bed -> inner right rim,
    round the right rim's edge, outer surface back, round the left rim."""
    half = half_section(share)
    inner = [(-b, n) for b, n in half[::-1]] + half[1:]
    inner = np.array(inner)
    # Offset by WALL toward the outside (below the inner surface).
    t = np.gradient(inner, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    normal = np.stack([t[:, 1], -t[:, 0]], axis=1)  # right of travel: downward/outward
    outer = inner + WALL * normal
    cap_r = WALL / 2
    right_cap, left_cap = [], []
    for i in range(1, CAP + 1):
        a = math.pi * i / (CAP + 1)
        # Round the end from the inner top to the outer, bulging outward.
        c = (inner[-1] + outer[-1]) / 2
        right_cap.append(c + cap_r * np.array([math.sin(a), math.cos(a)]))
        c = (inner[0] + outer[0]) / 2
        left_cap.append(c + cap_r * np.array([-math.sin(a), -math.cos(a)]))
    loop = list(inner) + right_cap + list(outer[::-1]) + left_cap
    return np.array(loop), len(inner)


class Mesh:
    def __init__(self):
        self.v, self.f = [], []

    def add(self, pts):
        base = len(self.v)
        self.v.extend(np.asarray(p, float) for p in pts)
        return base


def build():
    pts = path()
    tang = np.gradient(pts, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    up = np.stack([-tang[:, 1], tang[:, 0]], axis=1)  # (u, y) normal, upward
    mesh = Mesh()
    rings = []
    for j, p in enumerate(pts):
        loop, n_inner = section(wall_share(p[0]))
        # (b, n) -> model (x, y, z): b across is model x; n along `up`.
        world_un = p[None, :] + loop[:, 1:2] * up[j][None, :]
        verts = np.stack([loop[:, 0], world_un[:, 1], FACE_Z - world_un[:, 0]], axis=1)
        rings.append(mesh.add(verts))
    L = len(loop)
    for j in range(len(rings) - 1):
        a, b = rings[j], rings[j + 1]
        for i in range(L):
            i2 = (i + 1) % L
            mesh.f.append((a + i, b + i, b + i2))
            mesh.f.append((a + i, b + i2, a + i2))
    # End caps: the shell's cut face, inner point k to outer point k.
    for j, flip in ((0, False), (len(rings) - 1, True)):
        base = rings[j]
        ring = [mesh.v[base + i] for i in range(L)]
        cap = mesh.add(ring)  # own vertices: a hard edge round the cut
        outer_start = n_inner + CAP
        for k in range(n_inner - 1):
            i0, i1 = k, k + 1
            o0, o1 = outer_start + (n_inner - 1 - k), outer_start + (n_inner - 2 - k)
            tri = [(cap + i0, cap + i1, cap + o1), (cap + i0, cap + o1, cap + o0)]
            for t in tri:
                mesh.f.append(t[::-1] if flip else t)
        # The rims' round ends: fans from their middles.
        for start, count in ((n_inner - 1, CAP + 2), (L - CAP - 1, CAP + 2)):
            idx = [(start + q) % L for q in range(count)]
            mid = mesh.add([np.mean([ring[q] for q in idx], axis=0)])
            for q in range(count - 1):
                t = (mid, cap + idx[q], cap + idx[q + 1])
                mesh.f.append(t[::-1] if flip else t)
    v = np.array(mesh.v)
    f = np.array(mesh.f, dtype=np.int64)
    # Face the sweep outward: the bed's top surface must face up.
    mid_ring = rings[len(rings) // 3]
    k = n_inner // 2  # the bed's middle on the inner surface
    probe = [i for i, t in enumerate(f) if t[0] == mid_ring + k]
    a, b, c = v[f[probe[0]]]
    if np.cross(b - a, c - a)[1] < 0:
        f = f[:, ::-1]
    return v, f


def normals(v, f):
    n = np.zeros_like(v)
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return n


# --------------------------------------------------------------------- glb


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


def local_matrix(node):
    m = np.eye(4)
    m[:3, :3] = np.diag(node.get("scale", [1, 1, 1]))
    assert "rotation" not in node and "matrix" not in node, node.get("name")
    m[:3, 3] = node.get("translation", [0, 0, 0])
    return m


def rebuild(dry_run):
    found = glob.glob(os.path.join(MODELS, STEM + ".*.glb"))
    assert len(found) == 1, found
    gltf, binary = read_glb(found[0])
    nodes = gltf["nodes"]
    root = next(i for i, n in enumerate(nodes) if "children" in n)
    slide = next(i for i, n in enumerate(nodes) if "_colorize_" in n.get("name", ""))
    to_model = local_matrix(nodes[root]) @ local_matrix(nodes[slide])

    v, f = build()
    inv = np.linalg.inv(to_model)
    pos = (inv[:3, :3] @ v.T).T + inv[:3, 3]
    # Normals from the local positions, so the root's squash across (its
    # 0.76 x scale) comes out right after three.js's normal matrix.
    nrm = normals(pos, f)
    uv = np.stack([pos[:, 0], pos[:, 1] + pos[:, 2]], axis=1)
    print("%s: %d verts, %d tris; model x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f" % (
        STEM, len(v), len(f), *(val for k in range(3) for val in (v[:, k].min(), v[:, k].max()))))

    # Rebuild the binary: the joint's mesh as it was, the slide's new.
    blob = bytearray()
    views, accessors = [], []

    def push(array, target, kind, component, minmax=False):
        data = np.ascontiguousarray(array).tobytes()
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        acc = {"bufferView": len(views) - 1, "componentType": component, "count": len(array), "type": kind}
        if minmax:
            acc["min"] = [float(x) for x in array.min(axis=0)]
            acc["max"] = [float(x) for x in array.max(axis=0)]
        accessors.append(acc)
        return len(accessors) - 1

    def copy_accessor(index):
        a = dict(gltf["accessors"][index])
        bv = gltf["bufferViews"][a["bufferView"]]
        data = binary[bv.get("byteOffset", 0) : bv.get("byteOffset", 0) + bv["byteLength"]]
        while len(blob) % 4:
            blob.append(0)
        nv = {k: val for k, val in bv.items() if k != "byteOffset"}
        nv["byteOffset"] = len(blob)
        blob.extend(data)
        views.append(nv)
        a["bufferView"] = len(views) - 1
        accessors.append(a)
        return len(accessors) - 1

    meshes = []
    for i, n in enumerate(nodes):
        if "mesh" not in n:
            continue
        old = gltf["meshes"][n["mesh"]]
        if i == slide:
            prim = old["primitives"][0]
            attributes = {
                "POSITION": push(pos.astype(np.float32), 34962, "VEC3", 5126, True),
                "NORMAL": push(nrm.astype(np.float32), 34962, "VEC3", 5126),
                "TEXCOORD_0": push(uv.astype(np.float32), 34962, "VEC2", 5126),
            }
            assert len(pos) < 65536
            indices = push(f.reshape(-1).astype(np.uint16), 34963, "SCALAR", 5123)
            new = {"primitives": [{"mode": 4, "attributes": attributes, "indices": indices, "material": prim["material"]}]}
            if "name" in old:
                new["name"] = old["name"]
        else:
            prims = []
            for prim in old["primitives"]:
                p = json.loads(json.dumps(prim))
                p["attributes"] = {k: copy_accessor(a) for k, a in prim["attributes"].items()}
                if "indices" in prim:
                    p["indices"] = copy_accessor(prim["indices"])
                prims.append(p)
            new = {k: val for k, val in old.items() if k != "primitives"} | {"primitives": prims}
        meshes.append(new)
        n["mesh"] = len(meshes) - 1
    assert not gltf.get("images"), "WS-10 has no textures to carry"

    gltf["meshes"] = meshes
    gltf["accessors"] = accessors
    gltf["bufferViews"] = views
    gltf["buffers"] = [{"byteLength": len(blob)}]
    if dry_run:
        return
    data = write_glb(gltf, blob)
    out = os.path.join(MODELS, "%s.%s.glb" % (STEM, hashlib.sha256(data).hexdigest()[:8]))
    with open(out, "wb") as fh:
        fh.write(data)
    if os.path.abspath(out) != os.path.abspath(found[0]):
        os.remove(found[0])
    print("  ->", os.path.basename(out), "%d KB" % (len(data) // 1024))


if __name__ == "__main__":
    rebuild("--dry-run" in sys.argv)
