#!/usr/bin/env python3
"""
Build the Turbo Twister tubes, 7 ft and 5 ft, to PlayMor's shapes.

Weldon (2026-10-05, with photos): the old model was the wrong shape and its
exit came out in the wrong place. The real slide leaves the deck through a
square panel heading out; facing the slide, it swings to the right at the
top, then curves round to the left in one full loop, dropping all the way,
and comes out near the tower a little right of the entrance, its chute
pointing straight out again and resting on the ground. Its furthest left
goes not much past the edge of a 5 ft Sky Tower (0.79 m from the middle of
the face).

So the centreline here is, seen from above, an arc to the right starting at
the panel, an arc to the left that carries on round a full turn more -- its near side clear of the tower face -- and a straight chute out.
The 5 ft one (Weldon, 2026-10-05, with PlayMor's photo) twists the same
way -- right off the panel, then round to the left -- but stops a quarter
turn sooner: it comes back under its top lengths and out to the right as
you face the slide. Seven bolted lengths: the entrance, five round the
twist, and the exit.

The height falls on a smooth slope: nearly level at the deck, steepest
round the turn, easing off into the chute. Swept along it:

  - the tube, 0.66 m across with a 15 mm wall, belled out at the panel (the
    hood the photos show) with its floor kept level with the deck;
  - the chute: the last length opens from the top, a scoop with its bed
    0.18 m off the ground, standing on a tapered foot as in the photos;
  - the panel, square to the tower in the slide's colour, with the bell's
    opening through it;
  - a flange ring where each length joins, and a seam strip along the top;
  - bolts round the flanges and along the seam (Metal).

The tube, panel, rings and seam are one mesh in the slide colour (the node
named `,_colorize_`); the bolts replace the old Metal mesh. No clear window:
Weldon (2026-10-05) says it is an add-on, not how this slide comes, and the
"Turbo Twister (Clear) - 7ft" product was taken out of the catalogue.

Only the meshes change. The joint node -- its name, mesh, place -- and the
root node are kept as they are, so saved designs keep their connection, and
the builder still mirrors it by the `mirrorx` in the root's name.

Usage:  python3 tools/turbo_twister.py [--dry-run] [TTWS-7] [TTWS-5]
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

# ---------------------------------------------------------------- the shape

R_OUT = 0.33  # tube outside radius
WALL = 0.015
BELL_OUT = 0.40  # outside radius at the panel
BELL_LEN = 0.35  # how far out the bell runs
# Seen from above, facing the slide (w is to the left as you face it):
# The first length is one elbow, curving right from the panel itself: no
# straight run before it (Weldon, 2026-10-05).
SWING_R = 0.70  # the swing to the right at the top
SWING = math.radians(50)
TURN_R = 0.45  # the loop to the left: 0.82 m left of the entrance at most
CHUTE = 0.50  # straight run out at the bottom
EXIT_SECTION = 0.90  # the last length of tube: the chute and the loop's end
BED = 0.18  # height of the chute's bed at its end
FOOT_LEN = 0.34  # the foot under the chute's end, along it
FOOT_TOP = 0.36  # its width under the tube
FOOT_BOTTOM = 0.24  # and on the ground
OPEN_LEN = 0.42  # how far back from the end the top is open
OPEN_HALF = math.radians(100)  # half the open angle at the end, from the top
PANEL_W = 0.96
PANEL_BELOW = 0.04  # below the deck
PANEL_ABOVE = 0.96  # above the deck
PANEL_T = 0.015
# The lip where two lengths of tube bolt together: tall and narrow, as in
# PlayMor's photos (Weldon, 2026-10-05), bolted through its face.
FLANGE_W = 0.030
FLANGE_H = 0.030
FLANGE_BOLTS = 16
SEAM_W = 0.035
SEAM_H = 0.006
BOLT_R = 0.009
SIDES = 32  # round the tube
STEP = 0.05  # along it


# The 5 ft, seen from above: the 7 ft's swing right and loop left, the loop
# ending a quarter turn sooner so the chute faces right, under the top.
SWING_5_R = 0.70
SWING_5 = math.radians(60)
TURN_5_R = 0.42
CHUTE_5 = 0.50
ENTRANCE_5 = 0.45  # the first length, the bell's
EXIT_SECTION_5 = 0.75  # the last: the chute and the loop's end


def shape(stem):
    """The path seen from above as (length, curvature) pieces -- + turns
    left, toward +w -- and where each length of tube ends, from the total."""
    if stem == "TTWS-5":
        segments = [
            (SWING_5_R * SWING_5, -1 / SWING_5_R),
            (TURN_5_R * (SWING_5 + 1.5 * math.pi), 1 / TURN_5_R),
            (CHUTE_5, 0.0),
        ]

        def joins(total):
            # Seven lengths: the entrance, five the same round the twist,
            # and the exit.
            last = total - EXIT_SECTION_5
            return [ENTRANCE_5 + (last - ENTRANCE_5) * k / 5 for k in range(6)]

        return segments, joins, None
    # Four lengths of tube, as PlayMor's has (Weldon, 2026-10-05): a long
    # first one that leaves the panel already curving right (the bell is
    # its mouth) and runs on into the loop, two more down the loop, and the
    # exit -- the end of the loop and the open chute. The first three are
    # the same length.
    segments = [
        (SWING_R * SWING, -1 / SWING_R),
        (TURN_R * (SWING + 2 * math.pi), 1 / TURN_R),
        (CHUTE, 0.0),
    ]
    return segments, lambda total: [(total - EXIT_SECTION) * q for q in (1 / 3, 2 / 3, 1.0)], None


def path(deck, stem="TTWS-7"):
    """Centreline stations (u out from the panel, w to the left, y up, None, p
    along), the length, and where each length of tube ends (p)."""
    segments, joins_of, slope_of = shape(stem)
    total = sum(length for length, _ in segments)
    n = int(math.ceil(total / STEP))
    # Finer over the chute's opening, so the arch of its edge is drawn round:
    # closest together at its back, where the edge turns fastest.
    ps = np.linspace(0.0, total, n + 1)
    back = total - OPEN_LEN
    fine = back + OPEN_LEN * np.linspace(0.0, 1.0, 22) ** 2
    ps = np.union1d(ps[(ps < back - 0.02) | (ps > total)], np.concatenate([[back - 0.02], fine]))

    # Walk it finely, then read off the stations.
    fine = 0.002
    u = w = heading = 0.0
    walked = [(0.0, 0.0, 0.0)]
    for length, k in segments:
        steps = max(1, int(round(length / fine)))
        ds = length / steps
        for _ in range(steps):
            heading += k * ds / 2
            u += math.cos(heading) * ds
            w += math.sin(heading) * ds
            heading += k * ds / 2
            walked.append((walked[-1][0] + ds, u, w))
    walked = np.array(walked)
    us = np.interp(ps, walked[:, 0], walked[:, 1])
    ws = np.interp(ps, walked[:, 0], walked[:, 2])

    joins = joins_of(total)

    # Height: the slope eased in from level at the deck and out into the
    # chute, scaled so the floor starts at the deck and the bed ends at BED.
    # (the bell is raised on top of this so its floor stays at the deck: ring)
    start = deck + (R_OUT - WALL)
    end = BED + (R_OUT - WALL)
    ease_in, ease_out = 0.7, 0.9

    def slope(p):
        if slope_of:
            return slope_of(p, total)
        a = min(1.0, p / ease_in)
        b = min(1.0, (total - p) / ease_out)
        return (0.5 - 0.5 * math.cos(math.pi * a)) * (0.12 + 0.88 * (0.5 - 0.5 * math.cos(math.pi * b)))

    s = np.array([slope(p) for p in ps])
    drop = np.concatenate([[0.0], np.cumsum(0.5 * (s[1:] + s[:-1]) * np.diff(ps))])
    ys = start - drop * (start - end) / drop[-1]
    return [(u, w, y, None, p) for u, w, y, p in zip(us, ws, ys, ps)], total, joins


def radius_at(p):
    """Outside radius: belled at the panel."""
    if p >= BELL_LEN:
        return R_OUT
    t = 1 - p / BELL_LEN
    return R_OUT + (BELL_OUT - R_OUT) * t * t


def open_half_at(p, total):
    """Half the open angle at the top, from 0 (closed) to OPEN_HALF at the end.

    A quarter ellipse: the cut-out's back edge comes round in a smooth arch,
    square to the tube where it starts, with no point (Weldon, 2026-10-05).
    """
    back = total - p
    if back >= OPEN_LEN:
        return 0.0
    return OPEN_HALF * math.sqrt(1 - (back / OPEN_LEN) ** 2)


# ------------------------------------------------------------ mesh building


class Mesh:
    def __init__(self):
        self.v, self.f = [], []

    def add(self, points):
        base = len(self.v)
        self.v.extend(points)
        return base

    def quad(self, a, b, c, d):
        self.f.append((a, b, c))
        self.f.append((a, c, d))

    def grid(self, rows, flip=False):
        """rows: list of equal-length point lists; quads between neighbours.

        Unflipped, a quad faces (next row - this row) x (next point - this
        point): for a ring swept along the path, that is into the tube.
        """
        k = len(rows[0])
        base = len(self.v)
        for row in rows:
            self.v.extend(row)
        for j in range(len(rows) - 1):
            for i in range(k - 1):
                a = base + j * k + i
                if flip:
                    self.quad(a, a + 1, a + k + 1, a + k)
                else:
                    self.quad(a, a + k, a + k + 1, a + 1)

    def arrays(self):
        v = np.array(self.v, dtype=np.float64)
        f = np.array(self.f, dtype=np.uint32)
        # Smooth normals, area weighted; seams and rims have their own vertices.
        n = np.zeros_like(v)
        tri = v[f]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        for k in range(3):
            np.add.at(n, f[:, k], fn)
        length = np.linalg.norm(n, axis=1, keepdims=True)
        n = np.where(length > 1e-12, n / np.maximum(length, 1e-12), np.array([0.0, 1.0, 0.0]))
        return v, n, f


def frames(stations):
    """Tangent, up-ish normal and side vector at each station (u, w, y space)."""
    pts = np.array([(u, w, y) for u, w, y, _, _ in stations])
    t = np.gradient(pts, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    up = np.array([0.0, 0.0, 1.0])
    n = up - (t @ up)[:, None] * t
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    b = np.cross(t, n)
    return pts, t, n, b


def build(deck, stem="TTWS-7"):
    stations, total, joins = path(deck, stem)
    pts, T, N, B = frames(stations)
    # Work in (u, w, y); positions on the ring at angle a from the top.
    def ring(j, r, a0, a1, k, lift=0.0):
        p = stations[j][4]
        centre = pts[j].copy()
        # The bell keeps its floor level with the deck: widen it upward.
        centre[2] += radius_at(p) - R_OUT if p < BELL_LEN else 0.0
        out = []
        for i in range(k + 1):
            a = a0 + (a1 - a0) * i / k
            out.append(centre + (r + lift) * (math.cos(a) * N[j] + math.sin(a) * B[j]))
        return out

    tube, metal = Mesh(), Mesh()
    J = len(stations)

    # Walls: outer and inner, the top opened over the chute.
    spans = []  # per station: (a0, a1) of the wall
    for j in range(J):
        half = open_half_at(stations[j][4], total)
        spans.append((half, 2 * math.pi - half))

    for surface in ("outer", "inner"):
        rows = []
        for j in range(J):
            r = radius_at(stations[j][4]) - (WALL if surface == "inner" else 0.0)
            rows.append(ring(j, r, spans[j][0], spans[j][1], SIDES))
        tube.grid(rows, flip=surface == "outer")
    # Rims along the open edges, and the end rings at the panel and the exit.
    for side in (0, SIDES):
        rows = []
        for j in range(J):
            r = radius_at(stations[j][4])
            a = spans[j][0] if side == 0 else spans[j][1]
            rows.append([ring(j, r, a, a, 1)[0], ring(j, r - WALL, a, a, 1)[0]])
        tube.grid(rows, flip=side == SIDES)
    for j in (0, J - 1):
        r = radius_at(stations[j][4])
        tube.grid([ring(j, r, spans[j][0], spans[j][1], SIDES), ring(j, r - WALL, spans[j][0], spans[j][1], SIDES)], flip=j > 0)

    # Flanges where the lengths meet -- and one round the mouth, against the
    # panel -- and their bolts. Placed at their own point along the path,
    # between stations, so each is as narrow as it should be.
    ps = np.array([s[4] for s in stations])

    def frame_at(p):
        j = min(max(int(np.searchsorted(ps, p)) - 1, 0), J - 2)
        t = (p - ps[j]) / (ps[j + 1] - ps[j])
        centre = pts[j] + (pts[j + 1] - pts[j]) * t
        centre[2] += radius_at(p) - R_OUT if p < BELL_LEN else 0.0
        n = N[j] + (N[j + 1] - N[j]) * t
        b = B[j] + (B[j + 1] - B[j]) * t
        along = T[j] + (T[j + 1] - T[j]) * t
        return centre, n / np.linalg.norm(n), b / np.linalg.norm(b), along / np.linalg.norm(along)

    def circle(p, r):
        centre, n, b, _ = frame_at(p)
        return [centre + r * (math.cos(2 * math.pi * i / SIDES) * n + math.sin(2 * math.pi * i / SIDES) * b) for i in range(SIDES + 1)]

    joins = [PANEL_T + FLANGE_W / 2] + [p for p in joins if p < total - OPEN_LEN - 0.05]
    for p0 in joins:
        a_, b_ = p0 - FLANGE_W / 2, p0 + FLANGE_W / 2
        r = radius_at(p0)
        tube.grid([circle(a_, r), circle(a_, r + FLANGE_H), circle(b_, r + FLANGE_H), circle(b_, r)], flip=True)
        centre, n, b, along = frame_at(b_)
        for i in range(FLANGE_BOLTS):
            a = 2 * math.pi * (i + 0.5) / FLANGE_BOLTS
            radial = math.cos(a) * n + math.sin(a) * b
            bolt(metal, centre + (r + FLANGE_H * 0.55) * radial, along, radial)

    # The seam along the top, where the tube's halves are bolted together.
    seam_js = [j for j in range(J) if stations[j][4] > BELL_LEN + 0.08 and stations[j][4] < total - OPEN_LEN - 0.02]
    runs, run = [], []
    for j in seam_js:
        if run and j != run[-1] + 1:
            runs.append(run)
            run = []
        run.append(j)
    if run:
        runs.append(run)
    half = SEAM_W / 2 / R_OUT
    for run in runs:
        if len(run) < 2:
            continue
        tube.grid([
            [ring(j, R_OUT, -half, -half, 1)[0]] + ring(j, R_OUT, -half, half, 2, SEAM_H) + [ring(j, R_OUT, half, half, 1)[0]]
            for j in run
        ], flip=True)
        for j in run[::4]:
            bolt(metal, ring(j, R_OUT + SEAM_H, 0, 0, 1)[0], N[j], T[j])

    # The panel: a plate square to the tower, the bell's opening through it.
    j = 0
    centre = pts[0].copy()
    centre[2] += BELL_OUT - R_OUT
    hole_r = BELL_OUT - WALL
    edges = []
    for u in (0.0, PANEL_T):
        inner, outer = [], []
        for i in range(SIDES * 2 + 1):
            a = 2 * math.pi * i / (SIDES * 2)
            d = np.array([0.0, math.sin(a), math.cos(a)])  # (u, w, y): w right of the top
            hole = centre + hole_r * d
            hole[0] = u
            # Out along the same ray to the panel's edge.
            lo, hi = deck - PANEL_BELOW, deck + PANEL_ABOVE
            reach = []
            if abs(d[1]) > 1e-9:
                reach.append((PANEL_W / 2) / abs(d[1]))
            if d[2] > 1e-9:
                reach.append((hi - centre[2]) / d[2])
            if d[2] < -1e-9:
                reach.append((lo - centre[2]) / d[2])
            edge = centre + min(reach) * d
            edge[0] = u
            inner.append(hole)
            outer.append(edge)
        tube.grid([inner, outer], flip=u > 0)
        edges.append(outer)
    tube.grid(edges)

    # The foot: a tapered block under the chute's end, standing on the
    # ground, its top tucked up inside the tube's underside.
    ps = np.array([st[4] for st in stations])
    feet = [j for j in range(J) if total - 0.02 - FOOT_LEN <= ps[j] <= total - 0.02]
    first_face = len(tube.f)
    rows = []
    for j in feet:
        across = np.array([-T[j][1], T[j][0], 0.0])
        across /= np.linalg.norm(across)
        under = pts[j] - R_OUT * N[j]
        top = under + np.array([0.0, 0.0, 0.04])
        ground = np.array([under[0], under[1], 0.0])
        rows.append([
            top + across * FOOT_TOP / 2,
            ground + across * FOOT_BOTTOM / 2,
            ground - across * FOOT_BOTTOM / 2,
            top - across * FOOT_TOP / 2,
        ])
    tube.grid(rows)
    for row in (rows[0], rows[-1]):
        base = tube.add(row)
        tube.quad(base, base + 1, base + 2, base + 3)
    # Each face of the block turned outward from its middle.
    centre = np.mean([pt for row in rows for pt in row], axis=0)
    for i in range(first_face, len(tube.f)):
        a, b, c = (np.array(tube.v[k]) for k in tube.f[i])
        if np.dot(np.cross(b - a, c - a), (a + b + c) / 3 - centre) < 0:
            tube.f[i] = tube.f[i][::-1]
    return tube, metal


def bolt(mesh, at, normal, along, r=BOLT_R, h=0.006, k=6):
    side = np.cross(normal, along)
    ring = [at + r * (math.cos(2 * math.pi * i / k) * along + math.sin(2 * math.pi * i / k) * side) for i in range(k)]
    base = mesh.add(ring + [at + h * normal])
    for i in range(k):
        mesh.f.append((base + i, base + (i + 1) % k, base + k))


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
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    tx, ty, tz = node.get("translation", [0, 0, 0])
    qx, qy, qz, qw = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    r = np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
    ])
    m = np.eye(4)
    m[:3, :3] = r * np.array([sx, sy, sz])
    m[:3, 3] = [tx, ty, tz]
    return m


def world_matrices(gltf):
    nodes = gltf["nodes"]
    out = {}

    def visit(i, above):
        out[i] = above @ local_matrix(nodes[i])
        for c in nodes[i].get("children", []):
            visit(c, out[i])

    for root in gltf["scenes"][gltf.get("scene", 0)]["nodes"]:
        visit(root, np.eye(4))
    return out


def rebuild(stem, dry_run):
    path_in = glob.glob(os.path.join(MODELS, stem + ".*.glb"))
    assert len(path_in) == 1, path_in
    gltf, binary = read_glb(path_in[0])
    nodes = gltf["nodes"]
    world = world_matrices(gltf)

    joint = next(i for i, n in enumerate(nodes) if n.get("name", "").lower().startswith("joint"))
    tube = next(i for i, n in enumerate(nodes) if "_colorize_" in n.get("name", ""))
    metal_mat = next(i for i, m in enumerate(gltf["materials"]) if m.get("name") == "Metal")
    metal = next(i for i, n in enumerate(nodes) if "mesh" in n and gltf["meshes"][n["mesh"]]["primitives"][0].get("material") == metal_mat)

    # The joint's box: x is the tower face, its bottom the deck.
    jm = world[joint]
    corners = np.array([[x, y, z, 1] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)])
    jw = (jm @ corners.T).T[:, :3]
    face_x = jw[:, 0].mean()
    deck = jw[:, 1].min()
    face_z = jw[:, 2].mean()
    print("%s: face x %.3f, deck %.3f" % (stem, face_x, deck))

    tube_mesh, metal_mesh = build(deck, stem)

    def to_model(v):
        # (u out, w left facing the panel, y up) -> model space: out is -x,
        # and facing the panel from outside, left is -z.
        return np.stack([face_x - v[:, 0], v[:, 2], face_z - v[:, 1]], axis=1)

    def to_model_normal(n):
        return np.stack([-n[:, 0], n[:, 2], -n[:, 1]], axis=1)

    out_views, out_accessors = [], []
    blob = bytearray()

    def push(array, target, kind, component, minmax=False):
        data = np.ascontiguousarray(array).tobytes()
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            view["target"] = target
        blob.extend(data)
        out_views.append(view)
        acc = {"bufferView": len(out_views) - 1, "componentType": component, "count": len(array), "type": kind}
        if minmax:
            acc["min"] = [float(x) for x in array.min(axis=0)]
            acc["max"] = [float(x) for x in array.max(axis=0)]
        out_accessors.append(acc)
        return len(out_accessors) - 1

    # Keep what is not being replaced: copy each kept accessor's view.
    replaced = {tube, metal}
    keep_mesh = {}
    for i, n in enumerate(nodes):
        if "mesh" in n and i not in replaced:
            keep_mesh[n["mesh"]] = i
    view_map = {}

    def copy_view(index):
        if index not in view_map:
            v = gltf["bufferViews"][index]
            data = binary[v.get("byteOffset", 0) : v.get("byteOffset", 0) + v["byteLength"]]
            while len(blob) % 4:
                blob.append(0)
            nv = {k: val for k, val in v.items() if k != "byteOffset"}
            nv["byteOffset"] = len(blob)
            blob.extend(data)
            out_views.append(nv)
            view_map[index] = len(out_views) - 1
        return view_map[index]

    meshes = []
    mesh_map = {}
    for mi in sorted(keep_mesh):
        prims = []
        for prim in gltf["meshes"][mi]["primitives"]:
            np_ = json.loads(json.dumps(prim))
            for key, acc in list(prim["attributes"].items()) + [("indices", prim["indices"])]:
                a = dict(gltf["accessors"][acc])
                a["bufferView"] = copy_view(a["bufferView"])
                out_accessors.append(a)
                if key == "indices":
                    np_["indices"] = len(out_accessors) - 1
                else:
                    np_["attributes"][key] = len(out_accessors) - 1
            prims.append(np_)
        mesh_map[mi] = len(meshes)
        meshes.append({k: v for k, v in gltf["meshes"][mi].items() if k != "primitives"} | {"primitives": prims})
    images = gltf.get("images", [])
    for image in images:
        image["bufferView"] = copy_view(image["bufferView"])

    def new_mesh(node_index, mesh, material):
        v, n, f = mesh.arrays()
        inv = np.linalg.inv(world[node_index])
        pos = to_model(v)
        pos = (inv[:3, :3] @ pos.T).T + inv[:3, 3]
        nrm = (inv[:3, :3] @ to_model_normal(n).T).T
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        # Planar UVs: nothing in these materials is textured.
        uv = np.stack([pos[:, 0] + pos[:, 2], pos[:, 1]], axis=1)
        attributes = {
            "POSITION": push(pos.astype(np.float32), 34962, "VEC3", 5126, True),
            "NORMAL": push(nrm.astype(np.float32), 34962, "VEC3", 5126),
            "TEXCOORD_0": push(uv.astype(np.float32), 34962, "VEC2", 5126),
        }
        # to_model is a mirror (u, w, y -> -x, y, -z turns handedness), so
        # each triangle's corners go the other way round to face as before.
        indices = push(f[:, ::-1].reshape(-1).astype(np.uint32), 34963, "SCALAR", 5125)
        meshes.append({"primitives": [{"mode": 4, "attributes": attributes, "indices": indices, "material": material}]})
        return len(meshes) - 1, len(v), len(f)

    tube_mat = gltf["meshes"][nodes[tube]["mesh"]]["primitives"][0]["material"]
    for n in nodes:
        if "mesh" in n and n["mesh"] in mesh_map:
            n["mesh"] = mesh_map[n["mesh"]]
    nodes[tube]["mesh"], tv, tf = new_mesh(tube, tube_mesh, tube_mat)
    nodes[metal]["mesh"], mv, mf = new_mesh(metal, metal_mesh, metal_mat)
    print("  tube %d verts %d tris, bolts %d verts %d tris" % (tv, tf, mv, mf))

    gltf["meshes"] = meshes
    gltf["accessors"] = out_accessors
    gltf["bufferViews"] = out_views
    gltf["buffers"] = [{"byteLength": len(blob)}]
    if dry_run:
        return
    data = write_glb(gltf, blob)
    out = os.path.join(MODELS, "%s.%s.glb" % (stem, hashlib.sha256(data).hexdigest()[:8]))
    with open(out, "wb") as f:
        f.write(data)
    if os.path.abspath(out) != os.path.abspath(path_in[0]):
        os.remove(path_in[0])
    print("  ->", os.path.basename(out), "%d KB" % (len(data) // 1024))


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for stem in [a for a in sys.argv[1:] if not a.startswith("--")] or ["TTWS-7", "TTWS-5"]:
        rebuild(stem, dry)
