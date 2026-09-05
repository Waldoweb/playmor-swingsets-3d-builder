#!/usr/bin/env node
/**
 * build_models.js — extract the embedded GLBs out of categories.js into real
 * files, and emit a manifest of each product's joints.
 *
 * Run from builder/:   node tools/build_models.js
 *
 * Writes:
 *   models/<object_id>.glb              one per single-geometry product
 *   models/<object_id>__<layer>.glb     one per layer, for multi-layer products
 *   models/manifest.json                joints and flags, keyed by object_id
 *
 * Why a manifest: Model.capable() decides which products can be placed by
 * reading this.joints, and joints only exist once a GLB has been parsed. Once
 * models load on demand that is no longer true at catalog-render time, so the
 * joint data has to be available separately. Generating it here, from the same
 * bytes we write out, means it cannot drift from the models.
 *
 * categories.js is evaluated rather than pattern-matched so the structure is
 * read exactly as the browser reads it.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const CATEGORIES_JS = "js/categories.js";
const OBJECT_MAPPING = "object-mapping.json";
const OUT_DIR = "models";

/** Pull the Categories array out of categories.js using real JS semantics. */
function loadCategories() {
  const src = fs.readFileSync(CATEGORIES_JS, "utf8");
  return new Function(src + "; return Categories;")();
}

/**
 * Resolve a product's object_id the same way the app does in
 * getObjectIdFromCategoryIndex: match the category's display_order against the
 * product's position in the Categories array, and the child's index.
 */
function buildObjectIdLookup(objectMapping) {
  const lookup = new Map();
  for (const [objectId, info] of Object.entries(objectMapping.objects)) {
    const category = objectMapping.categories[info.category];
    if (!category) continue;
    lookup.set(`${category.display_order}:${info.index}`, objectId);
  }
  return lookup;
}

/**
 * Short content hash, folded into the filename so a model can be cached
 * forever and still update the moment its bytes change. Changing a model
 * changes its name, so there is no stale-cache window and no cache-busting
 * query string to remember.
 */
function contentHash(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex").slice(0, 8);
}

/** Decode a `data:...;base64,` URI to a Buffer. */
function decodeDataUri(dataUri) {
  const comma = dataUri.indexOf(",");
  if (comma === -1) throw new Error("not a data URI");
  return Buffer.from(dataUri.slice(comma + 1), "base64");
}

/**
 * GLTFLoader runs every node name through PropertyBinding.sanitizeNodeName, so
 * the names the app sees are not the names in the file: whitespace becomes an
 * underscore and [ ] . : / are stripped. King's Tower is the one product where
 * this bites — its joints are named `joint,0,8,1,2.001` in the GLB and arrive
 * as `joint,0,8,1,2001`. That trailing field is the excluder layer, so a
 * manifest holding the raw name would compare unequal against the running app.
 * Mirrored from the bundled three.js, which uses /[\[\]\.:\/]/g.
 */
function sanitizeNodeName(name) {
  return name.replace(/\s/g, "_").replace(/[\[\]\.:\/]/g, "");
}

/**
 * Read the node names out of a GLB's JSON chunk and keep the ones the app
 * treats as joints — the same test adopt() applies while traversing the
 * loaded scene: name.toLowerCase().startsWith("joint").
 */
function readJoints(buffer) {
  if (buffer.readUInt32LE(0) !== 0x46546c67) throw new Error("not a GLB");
  let offset = 12;
  while (offset < buffer.length) {
    const length = buffer.readUInt32LE(offset);
    const type = buffer.readUInt32LE(offset + 4);
    offset += 8;
    if (type === 0x4e4f534a) {
      const json = JSON.parse(buffer.slice(offset, offset + length).toString("utf8"));
      return (json.nodes || [])
        .filter((n) => typeof n.name === "string")
        .map((n) => sanitizeNodeName(n.name))
        .filter((n) => n.toLowerCase().startsWith("joint"));
    }
    offset += length;
  }
  throw new Error("no JSON chunk in GLB");
}

/** Parse a joint name the way adopt() does, so the manifest carries the same fields. */
function parseJoint(name) {
  const parts = name.split(",");
  const fourth = parts.length > 3 ? parts[3].toLowerCase() : null;
  return {
    name,
    direction: parseInt(parts[1], 10),
    layer: parts.length > 2 ? parts[2].toLowerCase() : null,
    tire_only: fourth === "tire",
    exclusion_layer: fourth && fourth !== "tire" ? parts[3] : null,
    excluder_layer: parts.length > 4 ? parts[4] : null,
  };
}

function main() {
  for (const required of [CATEGORIES_JS, OBJECT_MAPPING]) {
    if (!fs.existsSync(required)) {
      console.error(`Missing ${required}. Run this from the builder/ directory.`);
      process.exit(1);
    }
  }

  const categories = loadCategories();
  const objectMapping = JSON.parse(fs.readFileSync(OBJECT_MAPPING, "utf8"));
  const lookup = buildObjectIdLookup(objectMapping);

  fs.mkdirSync(OUT_DIR, { recursive: true });

  // Does categories.js still carry the geometry? If so it is the source and we
  // rewrite models/ from it. If not, models/ is the source and we only rebuild
  // the manifest from the files already there.
  const embedded = categories.some((category) =>
    (category.children || []).some((child) => {
      const first = "glbs" in child ? (child.glbs[0] || {}).glb : child.glb;
      return typeof first === "string" && first.startsWith("data:");
    })
  );

  // stem -> current filename, e.g. "P-PT" -> "P-PT.7d028968.glb"
  const existingFiles = new Map();
  for (const name of fs.readdirSync(OUT_DIR)) {
    const match = name.match(/^(.+)\.[0-9a-f]{8}\.glb$/);
    if (match) existingFiles.set(match[1], name);
  }

  if (embedded) {
    // Filenames carry a content hash, so a rebuild would otherwise leave the
    // previous generation behind for rsync to ship.
    for (const name of fs.readdirSync(OUT_DIR)) {
      if (name.endsWith(".glb")) fs.unlinkSync(path.join(OUT_DIR, name));
    }
  }
  let preservedCount = 0;

  const products = {};
  const problems = [];
  let fileCount = 0;
  let byteCount = 0;

  categories.forEach((category, categoryIndex) => {
    (category.children || []).forEach((child, childIndex) => {
      const objectId = lookup.get(`${categoryIndex}:${childIndex}`);
      if (!objectId) {
        problems.push(`No object_id for ${category.name} / ${child.name} (${categoryIndex}:${childIndex})`);
        return;
      }
      if (products[objectId]) {
        problems.push(`Duplicate object_id ${objectId} at ${category.name} / ${child.name}`);
        return;
      }

      // A product is either one GLB, or several — one per layer, which morph()
      // switches between. adopt() runs for each in turn and appends every
      // layer's joints, so the manifest lists them in the same order.
      const sources =
        "glbs" in child
          ? child.glbs.map((entry) => ({ layer: entry.layer, dataUri: entry.glb }))
          : [{ layer: null, dataUri: child.glb }];

      const files = [];
      const joints = [];

      for (const source of sources) {
        const stem =
          source.layer === null ? objectId : `${objectId}__${source.layer}`;

        // Two modes. While categories.js still carries the base64, that is the
        // source and the files are written from it. Once it has been stripped,
        // models/ *is* the source and we only re-read what is already there.
        let buffer, filename;
        if (typeof source.dataUri === "string" && source.dataUri.startsWith("data:")) {
          buffer = decodeDataUri(source.dataUri);
          filename = `${stem}.${contentHash(buffer)}.glb`;
          fs.writeFileSync(path.join(OUT_DIR, filename), buffer);
          fileCount++;
        } else {
          filename = existingFiles.get(stem);
          if (!filename) {
            problems.push(`No model file for ${stem} — expected models/${stem}.<hash>.glb`);
            continue;
          }
          buffer = fs.readFileSync(path.join(OUT_DIR, filename));
          preservedCount++;
        }
        byteCount += buffer.length;

        const names = readJoints(buffer);
        files.push({ layer: source.layer, file: filename, bytes: buffer.length, joints: names });
        joints.push(...names);
      }

      const info = objectMapping.objects[objectId];
      products[objectId] = {
        name: child.name,
        category: info.category,
        category_index: categoryIndex,
        children_index: childIndex,
        multi_layer: sources.length > 1,
        files,
        joints: joints.map(parseJoint),
      };
      if ("tubular" in child) products[objectId].tubular = child.tubular;
      if ("slope" in child) products[objectId].slope = child.slope;
    });
  });

  const manifest = {
    generated_by: "tools/build_models.js",
    generated_at: new Date().toISOString(),
    product_count: Object.keys(products).length,
    products,
  };
  fs.writeFileSync(path.join(OUT_DIR, "manifest.json"), JSON.stringify(manifest, null, 2));

  const jointTotal = Object.values(products).reduce((n, p) => n + p.joints.length, 0);
  console.log(`source   : ${embedded ? "categories.js (embedded base64)" : OUT_DIR + " (files)"}`);
  console.log(`products : ${Object.keys(products).length}`);
  console.log(
    `glb files: ${fileCount + preservedCount}` +
      (embedded ? ` written` : ` read`) +
      `  (${(byteCount / 1048576).toFixed(1)} MB)`
  );
  console.log(`joints   : ${jointTotal}`);
  console.log(`manifest : ${OUT_DIR}/manifest.json`);

  if (problems.length) {
    console.error(`\n${problems.length} problem(s):`);
    for (const problem of problems) console.error(`  ${problem}`);
    process.exit(1);
  }
}

main();
