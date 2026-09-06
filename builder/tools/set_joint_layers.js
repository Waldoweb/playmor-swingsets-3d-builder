#!/usr/bin/env node
/**
 * set_joint_layers.js — rewrite a joint's layer in the model file itself.
 *
 * Run from builder/:   node tools/set_joint_layers.js [--dry-run]
 *                      node tools/build_models.js      (afterwards, to re-hash)
 *
 * A joint's layer lives in its node name (`joint,<direction>,<layer>`), and the
 * app parses it out of the loaded GLB at run time. So unlike the marker offsets
 * and cut-outs, this cannot be corrected in the manifest — the model is the
 * source of truth and has to be the thing that changes.
 *
 * What this is for: four parts carry the layer `*`, which matches *every*
 * socket in the catalog. A Bridge can currently be hung off a swing hanger or
 * a picnic mount. Weldon confirmed where each actually belongs:
 *
 *   Bridge, Tunnel      span between two decks
 *   Bubble Panel Kit    wherever a climb goes  — a deck
 *   Tic-Tac-Toe         wherever a slide goes  — a deck
 *
 * All four are deck parts, so all four become `deck`, a layer that matches any
 * deck height (5 = 4ft, 6 = 5ft, 8 = 7ft) but nothing else. That replaces a
 * total wildcard with a narrow rule, which is the point.
 *
 * Editing a GLB this way is safe: node names live in the JSON chunk, joints are
 * empties, and the binary chunk carrying all the mesh data is copied through
 * untouched. The tool verifies that.
 *
 * Idempotent — a joint already on the target layer is left alone, so this can
 * be re-run after new models are added.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const OUT_DIR = "models";
const CONFIG = "tools/sockets.config.json";
const GLB_MAGIC = 0x46546c67;
const JSON_CHUNK = 0x4e4f534a;

function readChunks(buffer) {
  if (buffer.readUInt32LE(0) !== GLB_MAGIC) throw new Error("not a GLB");
  const chunks = [];
  let offset = 12;
  while (offset < buffer.length) {
    const length = buffer.readUInt32LE(offset);
    const type = buffer.readUInt32LE(offset + 4);
    offset += 8;
    chunks.push({ type, data: buffer.slice(offset, offset + length) });
    offset += length;
  }
  return chunks;
}

function writeChunks(chunks) {
  const parts = [];
  for (const chunk of chunks) {
    // glTF requires each chunk to be four-byte aligned, JSON padded with
    // spaces and binary with zeroes.
    const pad = (4 - (chunk.data.length % 4)) % 4;
    const filler = Buffer.alloc(pad, chunk.type === JSON_CHUNK ? 0x20 : 0x00);
    const data = Buffer.concat([chunk.data, filler]);
    const header = Buffer.alloc(8);
    header.writeUInt32LE(data.length, 0);
    header.writeUInt32LE(chunk.type, 4);
    parts.push(header, data);
  }
  const body = Buffer.concat(parts);
  const header = Buffer.alloc(12);
  header.writeUInt32LE(GLB_MAGIC, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(12 + body.length, 8);
  return Buffer.concat([header, body]);
}

/** Replace the layer field of a joint node name, keeping every other field. */
function relayer(name, to) {
  const parts = name.split(",");
  if (parts.length < 3) return name;
  parts[2] = to;
  return parts.join(",");
}

function main() {
  const dryRun = process.argv.includes("--dry-run");
  if (!fs.existsSync(OUT_DIR) || !fs.existsSync(CONFIG)) {
    console.error("Run this from the builder/ directory.");
    process.exit(1);
  }

  const config = JSON.parse(fs.readFileSync(CONFIG, "utf8"));
  const overrides = config.layer_overrides || {};
  if (!Object.keys(overrides).length) {
    console.log("No layer_overrides configured — nothing to do.");
    return;
  }

  // stem -> filename, so "Bridge" finds "Bridge.<hash>.glb"
  const files = new Map();
  for (const name of fs.readdirSync(OUT_DIR)) {
    const match = name.match(/^(.+)\.[0-9a-f]{8}\.glb$/);
    if (match) files.set(match[1], name);
  }

  let changedFiles = 0;
  let changedJoints = 0;

  for (const [objectId, rule] of Object.entries(overrides)) {
    const from = rule.from;
    const to = rule.to;

    // A product may be one file or several, one per layer.
    const stems = [...files.keys()].filter(
      (stem) => stem === objectId || stem.startsWith(`${objectId}__`)
    );
    if (!stems.length) {
      console.error(`  ${objectId}: no model file found`);
      process.exit(1);
    }

    for (const stem of stems) {
      const filename = files.get(stem);
      const full = path.join(OUT_DIR, filename);
      const original = fs.readFileSync(full);
      const chunks = readChunks(original);
      const jsonChunk = chunks.find((c) => c.type === JSON_CHUNK);
      const gltf = JSON.parse(jsonChunk.data.toString("utf8"));

      const renamed = [];
      for (const node of gltf.nodes || []) {
        if (typeof node.name !== "string") continue;
        if (!node.name.toLowerCase().startsWith("joint")) continue;
        const fields = node.name.split(",");
        if (fields.length < 3 || fields[2] !== from) continue;
        const next = relayer(node.name, to);
        if (next === node.name) continue;
        renamed.push(`${node.name} -> ${next}`);
        node.name = next;
      }

      if (!renamed.length) {
        console.log(`  ${stem.padEnd(14)} already on '${to}'`);
        continue;
      }

      jsonChunk.data = Buffer.from(JSON.stringify(gltf), "utf8");
      const rebuilt = writeChunks(chunks);

      // The mesh data must survive untouched — that is what makes editing a
      // model in place safe rather than a re-export.
      const before = readChunks(original).filter((c) => c.type !== JSON_CHUNK);
      const after = readChunks(rebuilt).filter((c) => c.type !== JSON_CHUNK);
      const identical =
        before.length === after.length &&
        before.every((chunk, i) => chunk.data.equals(after[i].data));
      if (!identical) {
        console.error(`  ${stem}: binary chunk changed — refusing to write`);
        process.exit(1);
      }

      // The filename's hash is a promise about the bytes, and that promise is
      // what lets models/ ship with immutable caching. Changing the content
      // without renaming would leave every browser and edge cache serving the
      // old geometry forever, with no way to bust it — so the rename is part
      // of the edit, not a follow-up step.
      const hash = crypto.createHash("sha256").update(rebuilt).digest("hex").slice(0, 8);
      const renamedFile = `${stem}.${hash}.glb`;
      if (!dryRun) {
        fs.writeFileSync(path.join(OUT_DIR, renamedFile), rebuilt);
        if (renamedFile !== filename) fs.unlinkSync(full);
        files.set(stem, renamedFile);
      }
      changedFiles++;
      changedJoints += renamed.length;
      console.log(
        `  ${stem.padEnd(14)} ${renamed.join(", ")}\n  ${"".padEnd(14)} ${filename} -> ${renamedFile}` +
          (dryRun ? "  (dry run)" : "")
      );
    }
  }

  console.log(
    `\n${changedJoints} joint(s) in ${changedFiles} file(s) ${dryRun ? "would be" : ""} relayered.`
  );
  if (changedFiles && !dryRun) {
    console.log("Run tools/build_models.js next to refresh the manifest.");
  }
}

main();
