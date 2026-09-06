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
    const offset = offsets[parsed.layer] || [0, 0, 0];
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

module.exports = { readJointPositions, deriveSockets };
