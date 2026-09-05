#!/usr/bin/env node
/**
 * ground_catalog_sets.js — drop each saved catalog set onto the ground.
 *
 * Run from builder/:   node tools/ground_catalog_sets.js [--dry-run]
 *
 * Several of the pre-designed sets were saved with everything sitting slightly
 * above y=0 — five of them by exactly 0.05 and one by 0.1, which is a nudge
 * from however they were authored rather than drift. Restoring a design uses
 * the absolute positions in the file, so the whole set loads hovering over the
 * mulch, while the same parts placed by hand land exactly on it.
 *
 * The fix is to subtract each set's lowest Y from every model in it. That
 * grounds the set and preserves the structure exactly, because every model
 * moves by the same amount.
 *
 * Only `position.y` is touched. The `joints` and `connections` arrays refer to
 * other models by index rather than by position, so they are unaffected — this
 * is what makes a blanket shift safe.
 *
 * Idempotent: a set already sitting at 0 is left alone, so this can be re-run
 * after new sets are added.
 */

const fs = require("fs");
const path = require("path");

const CATALOG_DIR = "assets/catalog";
const EPSILON = 1e-9;

function main() {
  const dryRun = process.argv.includes("--dry-run");

  if (!fs.existsSync(CATALOG_DIR)) {
    console.error(`Missing ${CATALOG_DIR}. Run this from the builder/ directory.`);
    process.exit(1);
  }

  let changed = 0;
  for (const name of fs.readdirSync(CATALOG_DIR).sort()) {
    if (!name.endsWith(".json")) continue;
    const file = path.join(CATALOG_DIR, name);
    const raw = fs.readFileSync(file, "utf8");
    const design = JSON.parse(raw);
    const models = design.models_data || [];
    if (!models.length) continue;

    const lowest = Math.min(...models.map((m) => m.position.y));
    if (Math.abs(lowest) < EPSILON) {
      console.log(`  ${name.padEnd(34)} already grounded`);
      continue;
    }

    for (const model of models) model.position.y -= lowest;

    // Re-check rather than trust the arithmetic.
    const after = Math.min(...models.map((m) => m.position.y));
    if (Math.abs(after) > EPSILON) {
      console.error(`  ${name}: still ${after} after shifting — not written`);
      process.exit(1);
    }

    // Written compact, matching how these files are already stored. Indenting
    // them rewrites every line, which buries a handful of changed numbers in a
    // 4,000-line diff and adds ~8 KB per file to what gets deployed.
    if (!dryRun) fs.writeFileSync(file, JSON.stringify(design));
    changed++;
    console.log(
      `  ${name.padEnd(34)} lowered by ${lowest.toFixed(4)}` +
        (dryRun ? "  (dry run)" : "")
    );
  }

  console.log(`\n${changed} set(s) ${dryRun ? "would be" : ""} grounded.`);
}

main();
