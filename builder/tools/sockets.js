/**
 * sockets.js — group a model's joints into the openings a person actually sees.
 *
 * A joint carries one layer and one facing. That is less than the real product
 * needs, so anything richer has been faked by putting several joints in the
 * same place: a tower post that takes either a scope or a steering wheel is two
 * joints 6 cm apart, a swing hanger that also takes a horse glider is two joints
 * at one point, and a baby swing that can face either way is two more.
 *
 * Nothing in the catalog accepts two parts at one spot, so the grouping rule is
 * purely geometric: joints at the same point are one opening, and filling it
 * consumes all of them. That is why there is no exclusion table in here, and no
 * per-model markup — the two conventions that grew up to patch this (`_x_0` on
 * the swing beams, and the five-field `g4/g5` form on the towers) both become
 * unnecessary for same-spot joints.
 *
 * The `g4/g5` groups are left alone. Those describe distinct positions about
 * half a unit apart that conflict *spatially* — a climber mounted centrally
 * covers the left and right mounts either side of it — which is a real rule
 * about different openings, not a workaround for this one.
 *
 * Positions come from the GLB's node hierarchy rather than from three.js, so
 * this runs at build time with no browser and no renderer.
 */

const JSON_CHUNK = 0x4e4f534a;
const GLB_MAGIC = 0x46546c67;

// ---------------------------------------------------------------- matrix math
// Column-major 4x4, matching glTF's own layout so a node's `matrix` can be
// used as-is. Only compose and transform-point are needed.

function identity() {
  return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
}

function multiply(a, b) {
  const out = new Array(16);
  for (let col = 0; col < 4; col++) {
    for (let row = 0; row < 4; row++) {
      out[col * 4 + row] =
        a[row] * b[col * 4] +
        a[4 + row] * b[col * 4 + 1] +
        a[8 + row] * b[col * 4 + 2] +
        a[12 + row] * b[col * 4 + 3];
    }
  }
  return out;
}

/** Build a node's local matrix from either its `matrix` or its TRS fields. */
function localMatrix(node) {
  if (Array.isArray(node.matrix) && node.matrix.length === 16) {
    return node.matrix.slice();
  }
  const [tx, ty, tz] = node.translation || [0, 0, 0];
  const [qx, qy, qz, qw] = node.rotation || [0, 0, 0, 1];
  const [sx, sy, sz] = node.scale || [1, 1, 1];

  const x2 = qx + qx, y2 = qy + qy, z2 = qz + qz;
  const xx = qx * x2, xy = qx * y2, xz = qx * z2;
  const yy = qy * y2, yz = qy * z2, zz = qz * z2;
  const wx = qw * x2, wy = qw * y2, wz = qw * z2;

  return [
    (1 - (yy + zz)) * sx, (xy + wz) * sx, (xz - wy) * sx, 0,
    (xy - wz) * sy, (1 - (xx + zz)) * sy, (yz + wx) * sy, 0,
    (xz + wy) * sz, (yz - wx) * sz, (1 - (xx + yy)) * sz, 0,
    tx, ty, tz, 1,
  ];
}

/** The translation component of a matrix — where the node ends up. */
function originOf(matrix) {
  return [matrix[12], matrix[13], matrix[14]];
}

/** A point carried through a matrix. */
function transformPoint(m, p) {
  return [
    m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12],
    m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
    m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14],
  ];
}

// ------------------------------------------------------------------ glb nodes

/** Read a GLB's JSON chunk. */
function readGltfJson(buffer) {
  if (buffer.readUInt32LE(0) !== GLB_MAGIC) throw new Error("not a GLB");
  let offset = 12;
  while (offset < buffer.length) {
    const length = buffer.readUInt32LE(offset);
    const type = buffer.readUInt32LE(offset + 4);
    offset += 8;
    if (type === JSON_CHUNK) {
      return JSON.parse(buffer.slice(offset, offset + length).toString("utf8"));
    }
    offset += length;
  }
  throw new Error("no JSON chunk in GLB");
}

/**
 * Every joint node with its position in model space.
 *
 * `sanitize` is passed in rather than duplicated: GLTFLoader rewrites node
 * names as it loads, so the manifest has to carry the names the app will
 * actually see, and both callers must agree on that exactly.
 */
function readJointPositions(buffer, sanitize) {
  const gltf = readGltfJson(buffer);
  const nodes = gltf.nodes || [];
  const roots = (gltf.scenes && gltf.scenes[gltf.scene || 0])
    ? gltf.scenes[gltf.scene || 0].nodes || []
    : nodes.map((_, index) => index);

  const found = [];
  const walk = (index, parentMatrix) => {
    const node = nodes[index];
    if (!node) return;
    const worldMatrix = multiply(parentMatrix, localMatrix(node));
    const name = typeof node.name === "string" ? sanitize(node.name) : "";
    if (name.toLowerCase().startsWith("joint")) {
      found.push({ name, position: originOf(worldMatrix) });
    }
    for (const child of node.children || []) walk(child, worldMatrix);
  };
  for (const root of roots) walk(root, identity());
  return found;
}

/**
 * The box round everything in the file, in model space.
 *
 * Every mesh's accessor extents, carried through its node's world matrix and
 * merged -- the same box THREE.Box3.setFromObject measures on the loaded
 * model, hidden joint geometry included, which is what the fit test used to
 * clone the mesh to get. Read here so the app can ask whether a part would
 * fit somewhere before its model has been downloaded.
 */
function readBounds(buffer) {
  const gltf = readGltfJson(buffer);
  const nodes = gltf.nodes || [];
  const roots = (gltf.scenes && gltf.scenes[gltf.scene || 0])
    ? gltf.scenes[gltf.scene || 0].nodes || []
    : nodes.map((_, index) => index);

  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  const walk = (index, parentMatrix) => {
    const node = nodes[index];
    if (!node) return;
    const worldMatrix = multiply(parentMatrix, localMatrix(node));
    if (node.mesh !== undefined && gltf.meshes && gltf.meshes[node.mesh]) {
      for (const primitive of gltf.meshes[node.mesh].primitives || []) {
        const accessor = gltf.accessors[(primitive.attributes || {}).POSITION];
        if (!accessor || !accessor.min || !accessor.max) continue;
        for (let corner = 0; corner < 8; corner++) {
          const local = [
            corner & 1 ? accessor.max[0] : accessor.min[0],
            corner & 2 ? accessor.max[1] : accessor.min[1],
            corner & 4 ? accessor.max[2] : accessor.min[2],
          ];
          const world = transformPoint(worldMatrix, local);
          for (let axis = 0; axis < 3; axis++) {
            if (world[axis] < min[axis]) min[axis] = world[axis];
            if (world[axis] > max[axis]) max[axis] = world[axis];
          }
        }
      }
    }
    for (const child of node.children || []) walk(child, worldMatrix);
  };
  for (const root of roots) walk(root, identity());
  if (!Number.isFinite(min[0])) return null;
  return [min.map(round), max.map(round)];
}

/**
 * A part's box in quarters about each joint: the plane through the joint
 * square to x and the one square to z cut the part into four, and each
 * quarter gets the box round its own share of the geometry.
 *
 * A part's one box runs the whole height of the part on every side of its
 * joint. A wave slide's hood reaches 0.5 m back over the deck from where the
 * slide hangs, 1.5 m up -- and as a box that reach went down to the ground,
 * inside the tower, where it met the picnic table. In quarters, the slide is
 * its own boxes out in the yard and two small ones for the hood, up on the
 * deck.
 *
 * Triangles are clipped at the planes, not sorted by their corners, so a
 * board crossing a plane is in both quarters up to the plane: the four boxes
 * together hold all of the part, and the fit test can only lose room that
 * was never there. Null for a joint where the quarters come to more than
 * nine tenths of the whole box -- nothing worth the extra tests.
 *
 * Measured from the geometry, not the accessor extents readBounds uses:
 * those are per mesh, and a slide whose bed and hood are one mesh would
 * come back as the whole slide again.
 */
function readQuarterBounds(buffer, joints, bounds) {
  const gltf = readGltfJson(buffer);
  const bin = readBinChunk(buffer);
  const nodes = gltf.nodes || [];
  const roots = (gltf.scenes && gltf.scenes[gltf.scene || 0])
    ? gltf.scenes[gltf.scene || 0].nodes || []
    : nodes.map((_, index) => index);
  if (!bin) return {};

  // quarter q: bit 0 is the +x side, bit 1 the +z side.
  const boxes = joints.map(() => [null, null, null, null]);
  const grow = (j, q, p) => {
    const box = boxes[j][q] || (boxes[j][q] = [[Infinity, Infinity, Infinity], [-Infinity, -Infinity, -Infinity]]);
    for (let k = 0; k < 3; k++) {
      if (p[k] < box[0][k]) box[0][k] = p[k];
      if (p[k] > box[1][k]) box[1][k] = p[k];
    }
  };
  // Sutherland-Hodgman against one half-space: axis value * sign >= cut * sign.
  const clip = (polygon, axis, cut, sign) => {
    const out = [];
    for (let i = 0; i < polygon.length; i++) {
      const a = polygon[i];
      const b = polygon[(i + 1) % polygon.length];
      const a_in = (a[axis] - cut) * sign >= 0;
      const b_in = (b[axis] - cut) * sign >= 0;
      if (a_in) out.push(a);
      if (a_in !== b_in) {
        const t = (cut - a[axis]) / (b[axis] - a[axis]);
        out.push([0, 1, 2].map((k) => a[k] + (b[k] - a[k]) * t));
      }
    }
    return out;
  };

  const walk = (index, parentMatrix) => {
    const node = nodes[index];
    if (!node) return;
    const worldMatrix = multiply(parentMatrix, localMatrix(node));
    if (node.mesh !== undefined && gltf.meshes && gltf.meshes[node.mesh]) {
      for (const primitive of gltf.meshes[node.mesh].primitives || []) {
        if (primitive.mode !== undefined && primitive.mode !== 4) continue;
        const accessor = gltf.accessors[(primitive.attributes || {}).POSITION];
        if (!accessor || accessor.componentType !== 5126 || accessor.bufferView === undefined) continue;
        const view = gltf.bufferViews[accessor.bufferView];
        const stride = view.byteStride || 12;
        const start = (view.byteOffset || 0) + (accessor.byteOffset || 0);
        const points = [];
        for (let i = 0; i < accessor.count; i++) {
          const at = start + i * stride;
          points.push(transformPoint(worldMatrix, [bin.readFloatLE(at), bin.readFloatLE(at + 4), bin.readFloatLE(at + 8)]));
        }
        let indices = null;
        if (primitive.indices !== undefined) {
          const ia = gltf.accessors[primitive.indices];
          const iv = gltf.bufferViews[ia.bufferView];
          const size = { 5121: 1, 5123: 2, 5125: 4 }[ia.componentType];
          const read = { 1: "readUInt8", 2: "readUInt16LE", 4: "readUInt32LE" }[size];
          const base = (iv.byteOffset || 0) + (ia.byteOffset || 0);
          indices = [];
          for (let i = 0; i < ia.count; i++) indices.push(bin[read](base + i * (iv.byteStride || size)));
        }
        const count = indices ? indices.length : points.length;
        for (let t = 0; t + 2 < count; t += 3) {
          const triangle = [0, 1, 2].map((k) => points[indices ? indices[t + k] : t + k]);
          joints.forEach((joint, j) => {
            const [jx, , jz] = joint.position;
            for (let q = 0; q < 4; q++) {
              const piece = clip(clip(triangle, 0, jx, q & 1 ? 1 : -1), 2, jz, q & 2 ? 1 : -1);
              for (const p of piece) grow(j, q, p);
            }
          });
        }
      }
    }
    for (const child of node.children || []) walk(child, worldMatrix);
  };
  for (const root of roots) walk(root, identity());

  const volume = (box) =>
    Math.max(0, box[1][0] - box[0][0]) * Math.max(0, box[1][1] - box[0][1]) * Math.max(0, box[1][2] - box[0][2]);
  const out = {};
  joints.forEach((joint, j) => {
    const quarters = boxes[j].filter(Boolean);
    const total = quarters.reduce((sum, box) => sum + volume(box), 0);
    if (quarters.length && total < volume(bounds) * 0.9)
      out[joint.name] = quarters.map((box) => [box[0].map(round), box[1].map(round)]);
  });
  return out;
}

/** A GLB's binary chunk, or null if it has none. */
function readBinChunk(buffer) {
  let offset = 12;
  while (offset < buffer.length) {
    const length = buffer.readUInt32LE(offset);
    const type = buffer.readUInt32LE(offset + 4);
    offset += 8;
    if (type === 0x004e4942) return buffer.slice(offset, offset + length);
    offset += length;
  }
  return null;
}

// -------------------------------------------------------------------- sockets

function distance(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

function round(value) {
  // Three decimals is finer than any real joint separation and keeps the
  // manifest diffable.
  return Math.round(value * 1000) / 1000;
}

/**
 * Group joints into sockets.
 *
 * Each joint is first moved to where its marker belongs, which for almost
 * everything is where it already is. Clustering then runs on those marker
 * positions, so a socket whose dot has been nudged clear of a neighbour is
 * correctly treated as the separate opening it is.
 *
 * Greedy single-pass clustering is deliberate: the real clusters are either
 * coincident or ~6 cm apart, with the nearest non-cluster at 30 cm, so there is
 * no chain long enough for the order of iteration to matter.
 */
function deriveSockets(joints, parseJoint, config) {
  const offsets = (config && config.marker_offsets) || {};
  const epsilon = (config && config.cluster_epsilon) || 0.1;

  const sockets = [];
  for (const joint of joints) {
    const parsed = parseJoint(joint.name);
    // Keyed by joint name first, then by layer. A layer key moves every dot of
    // that kind, which is right for the picnic mount and wrong for the tire
    // hanger: that one is layer `s`, so keying it by layer would drag every
    // swing hanger on every beam down with it. Its name is `joint,0,s,tire`,
    // which is unique in a file and the same on both Summit towers -- the two
    // that have the hanger -- so the name says exactly what is meant.
    const offset = offsets[joint.name] || offsets[parsed.layer] || [0, 0, 0];
    const marker = [
      joint.position[0] + offset[0],
      joint.position[1] + offset[1],
      joint.position[2] + offset[2],
    ];

    let socket = sockets.find((s) => distance(s.marker, marker) <= epsilon);
    if (!socket) {
      socket = { marker, offset, accepts: [], facings: [], joints: [] };
      sockets.push(socket);
    }
    if (!socket.accepts.includes(parsed.layer)) socket.accepts.push(parsed.layer);
    if (!socket.facings.includes(parsed.direction)) socket.facings.push(parsed.direction);
    socket.joints.push(joint.name);
  }

  return sockets.map((socket) => {
    const out = {
      marker: socket.marker.map(round),
      accepts: socket.accepts.slice().sort(),
      facings: socket.facings.slice().sort((a, b) => a - b),
      joints: socket.joints,
    };
    // Emitted only where it is not zero, so the common socket stays compact
    // and a reader can see at a glance which markers have been moved.
    if (socket.offset.some((v) => v !== 0)) out.marker_offset = socket.offset;
    return out;
  });
}

module.exports = { readJointPositions, readBounds, readQuarterBounds, deriveSockets };
