"""Put a re-exported GLB's nodes back in the order the original had them.

Blender's exporter sorts sibling nodes by name. The app and the manifest
honour node order -- a design saved before joints were named refers to a
joint by its index -- so a re-export must not reshuffle them. Nodes are
matched by name; anything unmatched keeps its relative order at the end.
"""
import struct, json, sys

def read(p):
    with open(p, "rb") as f:
        magic, version, length = struct.unpack("<4sII", f.read(12))
        chunks = []
        while f.tell() < length:
            n, kind = struct.unpack("<II", f.read(8))
            chunks.append((kind, f.read(n)))
    return chunks

def write(p, chunks):
    body = b""
    for kind, data in chunks:
        pad = (4 - len(data) % 4) % 4
        data = data + (b" " if kind == 0x4E4F534A else b"\0") * pad
        body += struct.pack("<II", len(data), kind) + data
    with open(p, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)

orig, new, out = sys.argv[1:4]
oc, nc = read(orig), read(new)
og = json.loads(oc[0][1]); ng = json.loads(nc[0][1])
order = [n.get("name") for n in og["nodes"]]
by_name = {}
for i, n in enumerate(ng["nodes"]):
    by_name.setdefault(n.get("name"), []).append(i)
new_order = []
for name in order:
    lst = by_name.get(name)
    if lst: new_order.append(lst.pop(0))
rest = [i for i in range(len(ng["nodes"])) if i not in new_order]
new_order += rest
remap = {old: pos for pos, old in enumerate(new_order)}
nodes = [ng["nodes"][i] for i in new_order]
for n in nodes:
    if "children" in n:
        n["children"] = sorted((remap[c] for c in n["children"]), key=lambda c: c)
        # children in the original's order, not numeric: order siblings by their new index, which follows the original order
for s in ng.get("scenes", []):
    s["nodes"] = sorted(remap[c] for c in s["nodes"])
for skin in ng.get("skins", []):
    skin["joints"] = [remap[c] for c in skin["joints"]]
    if "skeleton" in skin: skin["skeleton"] = remap[skin["skeleton"]]
ng["nodes"] = nodes
nc[0] = (nc[0][0], json.dumps(ng, separators=(",", ":")).encode())
write(out, nc)
names_after = [n.get("name") for n in ng["nodes"]]
print("node order matches original:", names_after == order, "| unmatched:", len(rest))
