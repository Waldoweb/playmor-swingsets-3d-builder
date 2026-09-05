#!/usr/bin/env python3
"""build_textures.py — move the mulch and ground textures out of assets.js.

Run from builder/:   python3 tools/build_textures.py

Writes:
  textures/<name>.<hash>.<ext>   one per texture, content-hashed
  textures/manifest.json         name -> filename

Why: these were base64 data URIs inside assets.js, so every visitor downloaded
all of them as part of a 2.9 MB script before anything rendered. As files they
lose the ~33% base64 overhead, download in parallel, and cache.

Two things worth knowing about the conversions:

* WebP is not a blanket win. The PNGs shrink by roughly 90%, but re-encoding
  an already-lossy JPEG at the same pixel size makes it *larger* — the two
  JPEGs here grew by 10-20% in testing. They are resized instead.

* WebGL needs power-of-two dimensions for RepeatWrapping, and three.js quietly
  upscales anything else at load. `pink` was 1000x750 and `grass` 1920x1920,
  so both were being stretched to the next power of two in memory every run.
  Targeting POT sizes removes that.

joint_ring is left exactly as it is: a 1152px-wide sprite strip that costs 2 KB
as a PNG, gets bigger as WebP, and would break if resized.

Like the model build, this has two modes. While assets.js still holds the
base64 it is the source. Once stripped, textures/ is the source and only the
manifest is rebuilt.
"""

import base64
import hashlib
import io
import json
import os
import re
import sys

ASSETS_JS = "js/assets.js"
OUT_DIR = "textures"

# asset index -> (name, target longest edge or None to keep, output format)
PLAN = {
    0: ("mulch_border_h", None, "webp"),
    1: ("mulch_border_v", None, "webp"),
    2: ("mulch_border_pink", 512, "webp"),   # was 1000x750, non-POT
    3: ("mulch_tar", None, "webp"),
    4: ("mulch_blue", None, "webp"),
    5: ("joint_ring", None, "keep"),         # sprite strip; do not touch
    8: ("ground_grass", 1024, "webp"),       # was 1920x1920, non-POT
}
QUALITY = 75


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


def extract(source: str):
    """Pull each planned texture out of assets.js. Returns {} once stripped."""
    found = {}
    for index, (name, _, _) in PLAN.items():
        match = re.search(
            r"/\*\s*%d\s*=[^*]*\*/\s*'data:image/(\w+);base64,([A-Za-z0-9+/=]+)'" % index,
            source,
        )
        if not match:
            continue
        raw = match.group(2)
        found[name] = (match.group(1), base64.b64decode(raw + "=" * (-len(raw) % 4)))
    return found


def convert(name: str, ext: str, data: bytes):
    """Return (filename_extension, bytes) after any resize and re-encode."""
    _, target, fmt = next(v for v in PLAN.values() if v[0] == name), None, None
    target, fmt = _[1], _[2]
    if fmt == "keep":
        return ext, data

    from PIL import Image

    image = Image.open(io.BytesIO(data))
    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    if target is not None:
        image = image.resize((target, target), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=QUALITY, method=6)
    return "webp", buffer.getvalue()


def main():
    if not os.path.exists(ASSETS_JS):
        sys.exit(f"Missing {ASSETS_JS}. Run this from the builder/ directory.")
    os.makedirs(OUT_DIR, exist_ok=True)

    source = open(ASSETS_JS, encoding="utf-8", errors="replace").read()
    embedded = extract(source)

    existing = {}
    for filename in os.listdir(OUT_DIR):
        match = re.match(r"^(.+)\.[0-9a-f]{8}\.(\w+)$", filename)
        if match:
            existing[match.group(1)] = filename

    manifest, before, after = {}, 0, 0

    if embedded:
        for filename in os.listdir(OUT_DIR):
            if filename != "manifest.json":
                os.unlink(os.path.join(OUT_DIR, filename))
        for name, (ext, data) in embedded.items():
            out_ext, out_data = convert(name, ext, data)
            filename = f"{name}.{content_hash(out_data)}.{out_ext}"
            open(os.path.join(OUT_DIR, filename), "wb").write(out_data)
            manifest[name] = filename
            before += len(data)
            after += len(out_data)
            pct = 100 - len(out_data) * 100 // len(data)
            print(f"  {name:<20}{len(data)//1024:>6}K -> {len(out_data)//1024:>5}K  {pct:>4}%")
        print(f"\n  {'total':<20}{before//1024:>6}K -> {after//1024:>5}K"
              f"  {100 - after * 100 // before:>4}%")
    else:
        for name, _, _ in PLAN.values():
            if name not in existing:
                sys.exit(f"No file for texture '{name}' in {OUT_DIR}/")
            manifest[name] = existing[name]
            after += os.path.getsize(os.path.join(OUT_DIR, existing[name]))
        print(f"  rebuilt manifest from {len(manifest)} existing files "
              f"({after//1024}K)")

    with open(os.path.join(OUT_DIR, "manifest.json"), "w") as handle:
        json.dump({"textures": manifest}, handle, indent=2)
    print(f"  manifest: {OUT_DIR}/manifest.json")


if __name__ == "__main__":
    main()
