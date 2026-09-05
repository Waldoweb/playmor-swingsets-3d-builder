#!/usr/bin/env node
/**
 * strip_embedded_models.js — remove the base64 GLBs from categories.js.
 *
 * Run from builder/:   node tools/strip_embedded_models.js
 *
 * This is the step that actually delivers the download saving: the geometry is
 * about 96% of categories.js, and every visitor was fetching all of it before
 * the app could start. Models now load individually from models/, so the copy
 * embedded here is dead weight.
 *
 * What it keeps: everything else. Names, thumbnails (needed immediately, and
 * only ~1.2 MB), tubular, slope, and the shape of the glbs arrays including
 * their layer names. Only the data URIs are replaced, with null.
 *
 * Keeping the structure matters — build_models.js reads it to know which
 * products have layers, and it is how a stripped categories.js still describes
 * the catalog. After this runs, models/ is the source of truth for geometry
 * and build_models.js switches to rebuilding the manifest from those files.
 *
 * Refuses to run if models/manifest.json is missing or does not cover every
 * product, because that is the only remaining way to find the geometry.
 */

const fs = require("fs");

const CATEGORIES_JS = "js/categories.js";
const MANIFEST = "models/manifest.json";

function main() {
  if (!fs.existsSync(CATEGORIES_JS)) {
    console.error(`Missing ${CATEGORIES_JS}. Run this from the builder/ directory.`);
    process.exit(1);
  }
  if (!fs.existsSync(MANIFEST)) {
    console.error(`Missing ${MANIFEST}. Run tools/build_models.js first.`);
    process.exit(1);
  }

  const source = fs.readFileSync(CATEGORIES_JS, "utf8");
  const manifest = JSON.parse(fs.readFileSync(MANIFEST, "utf8"));
  const categories = new Function(source + "; return Categories;")();

  // Every product must be reachable through the manifest before we drop the
  // only other copy of its geometry.
  const objectMapping = JSON.parse(fs.readFileSync("object-mapping.json", "utf8"));
  const byPosition = new Map();
  for (const [objectId, info] of Object.entries(objectMapping.objects)) {
    const category = objectMapping.categories[info.category];
    if (category) byPosition.set(`${category.display_order}:${info.index}`, objectId);
  }

  const missing = [];
  categories.forEach((category, categoryIndex) => {
    (category.children || []).forEach((child, childIndex) => {
      const objectId = byPosition.get(`${categoryIndex}:${childIndex}`);
      const entry = objectId && manifest.products[objectId];
      const wanted = "glbs" in child ? child.glbs.length : 1;
      if (!entry) missing.push(`${child.name}: no manifest entry`);
      else if (entry.files.length !== wanted)
        missing.push(`${child.name}: manifest has ${entry.files.length} files, expected ${wanted}`);
      else
        for (const file of entry.files)
          if (!fs.existsSync("models/" + file.file))
            missing.push(`${child.name}: missing models/${file.file}`);
    });
  });

  if (missing.length) {
    console.error("Refusing to strip — the manifest does not cover every product:");
    for (const problem of missing) console.error(`  ${problem}`);
    process.exit(1);
  }

  // Replace only the data URIs. Everything else in the file is untouched.
  let removed = 0;
  let removedBytes = 0;
  const stripped = source.replace(
    /"data:(?:application|model)\/[^;"]*;base64,[A-Za-z0-9+/=]+"/g,
    (match) => {
      removed++;
      removedBytes += match.length;
      return "null";
    }
  );

  const before = Buffer.byteLength(source);
  const after = Buffer.byteLength(stripped);

  // The thumbnails are also data URIs and live in the same file. They are
  // needed immediately to draw the catalog, so losing them to an over-eager
  // regex would be an obvious disaster and a subtle one to spot in a 35 MB
  // diff. Count them before and after.
  const countPngs = (text) => (text.match(/data:image\/png;base64,/g) || []).length;
  if (countPngs(stripped) !== countPngs(source)) {
    console.error(
      `Refusing to write — thumbnails changed from ${countPngs(source)} to ${countPngs(stripped)}.`
    );
    process.exit(1);
  }

  // Sanity: the file must still parse, and still describe the same catalog.
  const reparsed = new Function(stripped + "; return Categories;")();
  const countChildren = (c) => c.reduce((n, x) => n + (x.children || []).length, 0);
  if (countChildren(reparsed) !== countChildren(categories)) {
    console.error("Refusing to write — stripped file describes a different catalog.");
    process.exit(1);
  }

  fs.writeFileSync(CATEGORIES_JS, stripped);
  console.log(`removed   : ${removed} embedded models (${(removedBytes / 1048576).toFixed(1)} MB of base64)`);
  console.log(`categories: ${(before / 1048576).toFixed(1)} MB -> ${(after / 1048576).toFixed(1)} MB`);
  console.log(`thumbnails and structure kept; models/ is now the source of truth`);
}

main();
