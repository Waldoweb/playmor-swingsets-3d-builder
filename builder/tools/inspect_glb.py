#!/usr/bin/env python3
"""
GLB Model Inspector
===================
Inspects GLB/GLTF files to list all mesh/object names.
Useful for understanding the structure and naming conventions.

Usage:
    python inspect_glb.py <path_to_glb_file>
    python inspect_glb.py --all  # Inspect all GLB files in models folder
"""

import sys
import json
import struct
from pathlib import Path


def read_glb(filepath: Path) -> dict:
    """Read a GLB file and return the JSON content."""
    with open(filepath, 'rb') as f:
        # GLB Header (12 bytes)
        magic = f.read(4)
        if magic != b'glTF':
            raise ValueError(f"Not a valid GLB file: {filepath}")

        version = struct.unpack('<I', f.read(4))[0]
        length = struct.unpack('<I', f.read(4))[0]

        # First chunk should be JSON
        chunk_length = struct.unpack('<I', f.read(4))[0]
        chunk_type = f.read(4)

        if chunk_type != b'JSON':
            raise ValueError(f"First chunk is not JSON: {filepath}")

        json_data = f.read(chunk_length)
        return json.loads(json_data.decode('utf-8'))


def get_mesh_names(gltf_json: dict) -> list:
    """Extract all mesh names from glTF JSON."""
    names = []

    # Get mesh names
    if 'meshes' in gltf_json:
        for i, mesh in enumerate(gltf_json['meshes']):
            name = mesh.get('name', f'Mesh_{i}')
            names.append(('mesh', name))

    # Get node names (which may reference meshes)
    if 'nodes' in gltf_json:
        for i, node in enumerate(gltf_json['nodes']):
            name = node.get('name', f'Node_{i}')
            has_mesh = 'mesh' in node
            names.append(('node', name, has_mesh))

    return names


def inspect_glb(filepath: Path, filter_term: str = None):
    """Inspect a GLB file and print mesh/node names."""
    print(f"\n{'='*60}")
    print(f"File: {filepath.name}")
    print('='*60)

    try:
        gltf = read_glb(filepath)
        names = get_mesh_names(gltf)

        # Separate nodes and meshes
        meshes = []
        nodes = []
        for item in names:
            if item[0] == 'mesh':
                meshes.append((item[0], item[1]))
            elif item[0] == 'node':
                nodes.append((item[1], item[2] if len(item) > 2 else False))

        # Filter for fence-related if requested
        fence_nodes = [n for n, _ in nodes if 'fence' in n.lower()]
        joint_nodes = [n for n, _ in nodes if n.lower().startswith('joint')]

        print(f"\nTotal nodes: {len(nodes)}")
        print(f"Total meshes: {len(meshes)}")

        if fence_nodes:
            print(f"\n[FENCE] FENCE nodes ({len(fence_nodes)}):")
            for name in sorted(fence_nodes):
                print(f"   - {name}")
        else:
            print(f"\n[WARNING]  NO FENCE nodes found!")
            print("    (Fence hiding won't work - names must contain 'fence')")

        if joint_nodes:
            print(f"\n[JOINT] JOINT nodes ({len(joint_nodes)}):")
            for name in sorted(joint_nodes):
                print(f"   - {name}")

        if filter_term:
            filtered = [n for n, _ in nodes if filter_term.lower() in n.lower()]
            if filtered:
                print(f"\n[SEARCH] Nodes containing '{filter_term}':")
                for name in sorted(filtered):
                    print(f"   - {name}")

        # Print all node names
        print(f"\n[LIST] ALL node names:")
        for name, has_mesh in sorted(nodes, key=lambda x: x[0].lower()):
            mesh_indicator = " [mesh]" if has_mesh else ""
            print(f"   - {name}{mesh_indicator}")

    except Exception as e:
        print(f"Error reading {filepath}: {e}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg = sys.argv[1]
    filter_term = sys.argv[2] if len(sys.argv) > 2 else None

    if arg == '--all':
        # Inspect all GLB files in models folder
        models_dir = Path(__file__).parent.parent / 'models'
        if not models_dir.exists():
            print(f"Models directory not found: {models_dir}")
            sys.exit(1)

        for glb_file in sorted(models_dir.glob('*.glb')):
            inspect_glb(glb_file, filter_term)
    else:
        filepath = Path(arg)
        if not filepath.exists():
            # Try relative to models folder
            models_dir = Path(__file__).parent.parent / 'models'
            filepath = models_dir / arg
            if not filepath.exists():
                filepath = models_dir / f"{arg}.glb"

        if not filepath.exists():
            print(f"File not found: {arg}")
            sys.exit(1)

        inspect_glb(filepath, filter_term)


if __name__ == '__main__':
    main()
