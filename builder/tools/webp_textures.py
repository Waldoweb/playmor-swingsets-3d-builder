#!/usr/bin/env python3
"""webp_textures.py -- shrink the models without touching their shape.

Run from builder/:   python3 tools/webp_textures.py [models/X.glb ...]
With no arguments it rewrites every models/*.glb in place under a new
content-hashed name (the old file is removed), then you run
`node tools/build_models.js` to refresh the manifest.

Two things, both invisible in the yard:

1. Embedded textures become WebP. The floor's wood grain alone was a 331 KB
   PNG with no transparency, carried inside fifteen models; as WebP it is
   20 KB. Opaque images go lossy at quality 85, images with transparency go
   lossless, and any image that would not get smaller is left alone.
   Textures are marked with EXT_texture_webp, which the app's GLTFLoader
   (r127) reads.

2. The second UV set goes. Several models carry TEXCOORD_1 left over from
   lightmap baking; no material samples it and the app has no light or
   ambient-occlusion maps. Its accessors and buffer views are dropped.

Everything else -- nodes, joints, names, materials, geometry -- is copied
byte for byte, so the manifest changes only in file name and size.
Needs Pillow (pip install pillow).
"""
import glob, hashlib, io, json, os, struct, sys
from PIL import Image

JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942


def read_glb(path):
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<4sII", f.read(12))
        assert magic == b"glTF" and version == 2, path
        js = bin_ = None
        while f.tell() < length:
            n, kind = struct.unpack("<II", f.read(8))
            data = f.read(n)
            if kind == JSON_CHUNK: js = json.loads(data)
            elif kind == BIN_CHUNK: bin_ = data
    return js, bin_ or b""


def write_glb(path, js, bin_):
    j = json.dumps(js, separators=(",", ":")).encode()
    j += b" " * ((4 - len(j) % 4) % 4)
    b = bin_ + b"\0" * ((4 - len(bin_) % 4) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(j) + 8 + len(b)))
        f.write(struct.pack("<II", len(j), JSON_CHUNK) + j)
        f.write(struct.pack("<II", len(b), BIN_CHUNK) + b)


def view_bytes(js, bin_, index):
    bv = js["bufferViews"][index]
    start = bv.get("byteOffset", 0)
    return bin_[start:start + bv["byteLength"]]


def to_webp(data):
    """The image as WebP, or None when that would not be smaller."""
    im = Image.open(io.BytesIO(data))
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    out = io.BytesIO()
    if has_alpha:
        im.convert("RGBA").save(out, "WEBP", lossless=True, quality=100, method=6)
    else:
        im.convert("RGB").save(out, "WEBP", quality=85, method=6)
    return out.getvalue() if out.tell() < len(data) else None


def strip_uv1(js):
    """Remove TEXCOORD_1 from every primitive; returns the accessor indices freed."""
    freed = set()
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            if "TEXCOORD_1" in prim["attributes"]:
                freed.add(prim["attributes"].pop("TEXCOORD_1"))
    # Still referenced elsewhere? Then not free.
    used = set()
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            used.update(prim["attributes"].values())
            if "indices" in prim: used.add(prim["indices"])
            for t in prim.get("targets", []): used.update(t.values())
    for skin in js.get("skins", []):
        if "inverseBindMatrices" in skin: used.add(skin["inverseBindMatrices"])
    for anim in js.get("animations", []):
        for s in anim["samplers"]: used.update([s["input"], s["output"]])
    return freed - used


def renumber(js, key, keep):
    """Drop entries of js[key] not in `keep`; return old->new index map."""
    remap = {}
    new = []
    for i, entry in enumerate(js.get(key, [])):
        if i in keep:
            remap[i] = len(new)
            new.append(entry)
    js[key] = new
    return remap


def convert(path):
    js, bin_ = read_glb(path)
    before = os.path.getsize(path)
    report = {"images": 0, "image_bytes": 0, "uv1_dropped": 0}

    # 1. textures
    replacements = {}
    for i, image in enumerate(js.get("images", [])):
        if "bufferView" not in image: continue
        data = view_bytes(js, bin_, image["bufferView"])
        webp = to_webp(data)
        if webp is None: continue
        replacements[image["bufferView"]] = webp
        image["mimeType"] = "image/webp"
        report["images"] += 1
        report["image_bytes"] += len(data) - len(webp)
    if replacements:
        for tex in js.get("textures", []):
            src = tex.get("source")
            if src is not None and js["images"][src].get("mimeType") == "image/webp":
                tex.setdefault("extensions", {})["EXT_texture_webp"] = {"source": src}
        for key in ("extensionsUsed", "extensionsRequired"):
            lst = js.setdefault(key, [])
            if "EXT_texture_webp" not in lst: lst.append("EXT_texture_webp")

    # 2. the second UV set
    freed = strip_uv1(js)
    report["uv1_dropped"] = len(freed)

    # Nothing to do? Then leave the file exactly as it is. Rewriting it would
    # give it a new hash, and with it a new name, for no change at all -- and
    # a new name is a fresh download for every visitor.
    if not replacements and not freed:
        report.update(file=os.path.basename(path), before=before, after=before)
        return report
    keep_acc = {i for i in range(len(js.get("accessors", []))) if i not in freed}
    acc_map = renumber(js, "accessors", keep_acc)
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            prim["attributes"] = {k: acc_map[v] for k, v in prim["attributes"].items()}
            if "indices" in prim: prim["indices"] = acc_map[prim["indices"]]
            prim["targets"] = [{k: acc_map[v] for k, v in t.items()} for t in prim.get("targets", [])] or prim.get("targets")
            if prim.get("targets") is None: prim.pop("targets", None)
    for skin in js.get("skins", []):
        if "inverseBindMatrices" in skin: skin["inverseBindMatrices"] = acc_map[skin["inverseBindMatrices"]]
    for anim in js.get("animations", []):
        for s in anim["samplers"]: s["input"], s["output"] = acc_map[s["input"]], acc_map[s["output"]]

    # 3. re-lay the buffer: only views something still points at
    used_views = set()
    for a in js.get("accessors", []):
        if "bufferView" in a: used_views.add(a["bufferView"])
        if "sparse" in a:
            used_views.add(a["sparse"]["indices"]["bufferView"]); used_views.add(a["sparse"]["values"]["bufferView"])
    for im in js.get("images", []):
        if "bufferView" in im: used_views.add(im["bufferView"])
    view_map = {}
    new_views, out = [], bytearray()
    for i, bv in enumerate(js.get("bufferViews", [])):
        if i not in used_views: continue
        data = replacements.get(i, view_bytes(js, bin_, i))
        out += b"\0" * ((4 - len(out) % 4) % 4)
        nv = {k: v for k, v in bv.items() if k not in ("byteOffset", "byteLength")}
        nv["byteOffset"], nv["byteLength"], nv["buffer"] = len(out), len(data), 0
        view_map[i] = len(new_views)
        new_views.append(nv)
        out += data
    js["bufferViews"] = new_views
    for a in js.get("accessors", []):
        if "bufferView" in a: a["bufferView"] = view_map[a["bufferView"]]
        if "sparse" in a:
            a["sparse"]["indices"]["bufferView"] = view_map[a["sparse"]["indices"]["bufferView"]]
            a["sparse"]["values"]["bufferView"] = view_map[a["sparse"]["values"]["bufferView"]]
    for im in js.get("images", []):
        if "bufferView" in im: im["bufferView"] = view_map[im["bufferView"]]
    js["buffers"] = [{"byteLength": len(out)}]

    # 4. write under the content hash, drop the old name
    stem = os.path.basename(path).rsplit(".", 2)[0] if len(os.path.basename(path).split(".")) == 3 else os.path.basename(path)[:-4]
    tmp = path + ".tmp"
    write_glb(tmp, js, bytes(out))
    digest = hashlib.sha256(open(tmp, "rb").read()).hexdigest()[:8]
    new_path = os.path.join(os.path.dirname(path), f"{stem}.{digest}.glb")
    os.replace(tmp, new_path)
    if new_path != path: os.remove(path)
    report.update(file=os.path.basename(new_path), before=before, after=os.path.getsize(new_path))
    return report


if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(glob.glob("models/*.glb"))
    total_before = total_after = 0
    for p in paths:
        r = convert(p)
        total_before += r["before"]; total_after += r["after"]
        print(f"{r['file']:32} {r['before']//1024:>6} KB -> {r['after']//1024:>5} KB  webp {r['images']}  uv1 dropped {r['uv1_dropped']}")
    print(f"total {total_before//1024//1024} MB -> {total_after//1024//1024} MB ({total_after//1024} KB)")
