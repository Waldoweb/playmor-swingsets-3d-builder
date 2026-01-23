#!/usr/bin/env python3
"""
Thumbnail Manager for categories.js
====================================
Import and export thumbnail images from/to categories.js file.

Usage:
    python thumbnail_manager.py export [--output-dir OUTPUT_DIR]
    python thumbnail_manager.py import [--input-dir INPUT_DIR]

Structure:
    Categories have thumbnails at two levels:
    1. Category level (e.g., "Towers")
    2. Item level (e.g., "Play Tower")

Export creates folder structure:
    thumbnails/
        Towers/
            _category.png          (category thumbnail)
            Play Tower.png         (item thumbnail)
            DX Play Tower.png
            ...
        Swing Beams/
            _category.png
            3 Swing Beam - 8 ft.png
            ...
"""

import os
import re
import sys
import base64
import argparse
from pathlib import Path


# Default paths
SCRIPT_DIR = Path(__file__).parent
DEFAULT_CATEGORIES_JS = SCRIPT_DIR.parent / "js" / "categories.js"
DEFAULT_THUMBNAILS_DIR = SCRIPT_DIR / "thumbnails"


def sanitize_filename(name: str) -> str:
    """Sanitize name for use as filename."""
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip()


def extract_base64_data(data_uri: str) -> tuple[str, bytes]:
    """Extract image format and binary data from data URI."""
    # Pattern: data:image/png;base64,<data>
    match = re.match(r'data:image/(\w+);base64,(.+)', data_uri, re.DOTALL)
    if match:
        img_format = match.group(1)
        b64_data = match.group(2).strip()
        # Fix padding if needed
        padding = 4 - (len(b64_data) % 4)
        if padding != 4:
            b64_data += '=' * padding
        try:
            return img_format, base64.b64decode(b64_data)
        except Exception as e:
            print(f"  Warning: Failed to decode base64: {e}")
            return None, None
    return None, None


def create_data_uri(img_path: Path) -> str:
    """Create data URI from image file."""
    ext = img_path.suffix.lower()
    mime_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    mime = mime_types.get(ext, 'image/png')

    with open(img_path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('ascii')

    return f'data:{mime};base64,{data}'


def find_string_value(content: str, start_pos: int) -> tuple[str, int]:
    """
    Find a quoted string value starting at position.
    Returns the string content and end position.
    Handles the case where the string contains special characters.
    """
    # Skip whitespace and find opening quote
    pos = start_pos
    while pos < len(content) and content[pos] in ' \t\n\r:':
        pos += 1

    if pos >= len(content) or content[pos] != '"':
        return None, pos

    pos += 1  # Skip opening quote
    start = pos

    # Find closing quote (not escaped)
    while pos < len(content):
        if content[pos] == '"' and content[pos-1] != '\\':
            break
        pos += 1

    return content[start:pos], pos + 1


def parse_categories_js(content: str) -> list:
    """
    Parse categories.js content to extract structure.
    Returns list of categories with their thumbnails and children.
    """
    categories = []

    # Find category blocks by searching for pattern: { name: "...", thumbnail: "...", children: [
    # We need to handle that thumbnails are very long base64 strings

    pos = 0
    while True:
        # Find next category start (has 'children' which distinguishes from items)
        # Look for pattern: { name : "CategoryName" ,  thumbnail : "data:...
        cat_start = content.find('children', pos)
        if cat_start == -1:
            break

        # Go back to find the { that starts this category
        brace_pos = content.rfind('{', pos, cat_start)
        if brace_pos == -1:
            pos = cat_start + 1
            continue

        # Extract category name
        name_match = re.search(r'name\s*:\s*"([^"]+)"', content[brace_pos:cat_start])
        if not name_match:
            pos = cat_start + 1
            continue
        cat_name = name_match.group(1)

        # Extract category thumbnail - find thumbnail : " and then read until closing "
        thumb_match = re.search(r'thumbnail\s*:', content[brace_pos:cat_start])
        if thumb_match:
            thumb_start = brace_pos + thumb_match.end()
            cat_thumbnail, thumb_end = find_string_value(content, thumb_start)
        else:
            cat_thumbnail = None

        # Find children array start
        children_start = content.find('[', cat_start)
        if children_start == -1:
            pos = cat_start + 1
            continue

        # Find matching ] for children array
        bracket_count = 1
        children_pos = children_start + 1
        while bracket_count > 0 and children_pos < len(content):
            if content[children_pos] == '[':
                bracket_count += 1
            elif content[children_pos] == ']':
                bracket_count -= 1
            children_pos += 1

        children_content = content[children_start + 1:children_pos - 1]

        # Parse items in children
        items = []
        item_pos = 0
        while True:
            # Find next item (has 'glb' or is a simple { name: ..., thumbnail: ... } without children)
            item_brace = children_content.find('{', item_pos)
            if item_brace == -1:
                break

            # Find the closing brace for this item
            # Need to handle nested braces
            brace_count = 1
            item_end = item_brace + 1
            while brace_count > 0 and item_end < len(children_content):
                if children_content[item_end] == '{':
                    brace_count += 1
                elif children_content[item_end] == '}':
                    brace_count -= 1
                item_end += 1

            item_content = children_content[item_brace:item_end]

            # Extract item name
            item_name_match = re.search(r'name\s*:\s*"([^"]+)"', item_content)
            if item_name_match:
                item_name = item_name_match.group(1)

                # Extract item thumbnail
                item_thumb_match = re.search(r'thumbnail\s*:', item_content)
                if item_thumb_match:
                    item_thumb_start = item_thumb_match.end()
                    item_thumbnail, _ = find_string_value(item_content, item_thumb_start)

                    if item_thumbnail and item_thumbnail.startswith('data:image'):
                        items.append({
                            'name': item_name,
                            'thumbnail': item_thumbnail
                        })

            item_pos = item_brace + item_end - item_brace

        if cat_thumbnail:
            categories.append({
                'name': cat_name,
                'thumbnail': cat_thumbnail,
                'items': items
            })

        pos = children_pos

    return categories


def export_thumbnails(categories_path: Path, output_dir: Path):
    """Export all thumbnails from categories.js to folder structure."""
    print(f"Reading {categories_path}...")

    with open(categories_path, 'r', encoding='utf-8') as f:
        content = f.read()

    categories = parse_categories_js(content)

    if not categories:
        print("No categories found!")
        return

    print(f"Found {len(categories)} categories")

    output_dir.mkdir(parents=True, exist_ok=True)

    total_exported = 0

    for cat in categories:
        cat_name = sanitize_filename(cat['name'])
        cat_dir = output_dir / cat_name
        cat_dir.mkdir(exist_ok=True)

        # Export category thumbnail
        img_format, img_data = extract_base64_data(cat['thumbnail'])
        if img_data:
            cat_thumb_path = cat_dir / f"_category.{img_format}"
            with open(cat_thumb_path, 'wb') as f:
                f.write(img_data)
            print(f"  Exported: {cat_name}/_category.{img_format}")
            total_exported += 1

        # Export item thumbnails
        for item in cat['items']:
            item_name = sanitize_filename(item['name'])
            img_format, img_data = extract_base64_data(item['thumbnail'])
            if img_data:
                item_thumb_path = cat_dir / f"{item_name}.{img_format}"
                with open(item_thumb_path, 'wb') as f:
                    f.write(img_data)
                print(f"  Exported: {cat_name}/{item_name}.{img_format}")
                total_exported += 1

    print(f"\nTotal exported: {total_exported} thumbnails to {output_dir}")


def import_thumbnails(categories_path: Path, input_dir: Path):
    """Import thumbnails from folder structure back into categories.js."""
    print(f"Reading {categories_path}...")

    with open(categories_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if not input_dir.exists():
        print(f"Error: Input directory {input_dir} does not exist!")
        return

    updated_count = 0

    # Process each category folder
    for cat_dir in sorted(input_dir.iterdir()):
        if not cat_dir.is_dir():
            continue

        cat_name = cat_dir.name
        print(f"\nProcessing category: {cat_name}")

        # Process category thumbnail (_category.png/jpg/etc)
        for cat_thumb in cat_dir.glob("_category.*"):
            if cat_thumb.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                data_uri = create_data_uri(cat_thumb)
                # Find and replace category thumbnail in content
                # Pattern: { name: "cat_name", thumbnail: "..."
                pattern = re.compile(
                    r'(\{\s*name\s*:\s*"' + re.escape(cat_name) + r'"\s*,\s*'
                    r'thumbnail\s*:\s*")data:image[^"]+(")',
                    re.DOTALL
                )
                new_content, count = pattern.subn(r'\1' + data_uri + r'\2', content)
                if count > 0:
                    content = new_content
                    print(f"  Updated: {cat_name}/_category thumbnail")
                    updated_count += count
                break

        # Process item thumbnails
        for item_thumb in sorted(cat_dir.iterdir()):
            if item_thumb.name.startswith('_category'):
                continue
            if item_thumb.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                continue

            item_name = item_thumb.stem  # filename without extension
            data_uri = create_data_uri(item_thumb)

            # Find and replace item thumbnail
            # Need to match within the correct category context
            # Pattern: { name: "item_name", thumbnail: "..."
            pattern = re.compile(
                r'(\{\s*name\s*:\s*"' + re.escape(item_name) + r'"\s*,\s*'
                r'thumbnail\s*:\s*")data:image[^"]+(")',
                re.DOTALL
            )
            new_content, count = pattern.subn(r'\1' + data_uri + r'\2', content)
            if count > 0:
                content = new_content
                print(f"  Updated: {cat_name}/{item_name} thumbnail")
                updated_count += count

    if updated_count > 0:
        # Create backup
        backup_path = categories_path.with_suffix('.js.backup')
        print(f"\nCreating backup: {backup_path}")
        with open(backup_path, 'w', encoding='utf-8') as f:
            with open(categories_path, 'r', encoding='utf-8') as src:
                f.write(src.read())

        # Write updated content
        print(f"Writing updated {categories_path}...")
        with open(categories_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"\nTotal updated: {updated_count} thumbnails")
    else:
        print("\nNo thumbnails were updated.")


def main():
    parser = argparse.ArgumentParser(
        description='Import/Export thumbnails from categories.js',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Export command
    export_parser = subparsers.add_parser('export', help='Export thumbnails to folder')
    export_parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        default=DEFAULT_THUMBNAILS_DIR,
        help=f'Output directory (default: {DEFAULT_THUMBNAILS_DIR})'
    )
    export_parser.add_argument(
        '--categories-js', '-c',
        type=Path,
        default=DEFAULT_CATEGORIES_JS,
        help=f'Path to categories.js (default: {DEFAULT_CATEGORIES_JS})'
    )

    # Import command
    import_parser = subparsers.add_parser('import', help='Import thumbnails from folder')
    import_parser.add_argument(
        '--input-dir', '-i',
        type=Path,
        default=DEFAULT_THUMBNAILS_DIR,
        help=f'Input directory (default: {DEFAULT_THUMBNAILS_DIR})'
    )
    import_parser.add_argument(
        '--categories-js', '-c',
        type=Path,
        default=DEFAULT_CATEGORIES_JS,
        help=f'Path to categories.js (default: {DEFAULT_CATEGORIES_JS})'
    )

    args = parser.parse_args()

    if args.command == 'export':
        export_thumbnails(args.categories_js, args.output_dir)
    elif args.command == 'import':
        import_thumbnails(args.categories_js, args.input_dir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
