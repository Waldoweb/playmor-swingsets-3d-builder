#!/usr/bin/env python3
"""
GLB base64 replacement and extraction script.
- Replace: Only replaces the base64 data portion of the GLB field, preserving everything else exactly.
- Extract: Create .glb files from base64 data in categories.js
"""

import re
import base64
import os
import sys
from pathlib import Path

def glb_to_base64_data_only(glb_file_path):
    """Convert GLB file to base64 string (data portion only, without prefix)"""
    try:
        with open(glb_file_path, 'rb') as f:
            glb_data = f.read()
        
        # Convert to base64 - return only the data part
        base64_data = base64.b64encode(glb_data).decode('utf-8')
        return base64_data
        
    except Exception as e:
        print(f"Error reading GLB file: {e}")
        return None

def replace_glb_base64_only(categories_file, category_name, glb_file):
    """Replace only the base64 data part of the GLB field"""
    try:
        # Check if GLB file exists
        if not os.path.exists(glb_file):
            print(f"GLB file not found: {glb_file}")
            return False
        
        # Convert GLB to base64
        print(f"Converting {glb_file} to base64...")
        new_base64_data = glb_to_base64_data_only(glb_file)
        if not new_base64_data:
            return False
        
        # Read the original file
        with open(categories_file, 'rb') as f:
            original_content = f.read()
        
        # Convert to string for processing
        content = original_content.decode('utf-8')
        
        # Find the exact pattern for this category's GLB field
        # Pattern: glb : "data:application/octet-stream;base64,XXXXX"
        pattern = rf'(glb\s*:\s*"data:application/octet-stream;base64,)([^"]*?)(")'
        
        # Find the category block first
        category_pattern = rf'(\{{\s*name\s*:\s*"{re.escape(category_name)}"\s*,.*?)(glb\s*:\s*"data:application/octet-stream;base64,)([^"]*?)(".*?\}})'
        
        def replace_category_glb(match):
            before_category = match.group(1)
            glb_prefix = match.group(2)
            old_base64 = match.group(3)
            after_glb = match.group(4)
            
            print(f"Found category '{category_name}'")
            print(f"Old base64 length: {len(old_base64)} characters")
            print(f"New base64 length: {len(new_base64_data)} characters")
            
            return before_category + glb_prefix + new_base64_data + after_glb
        
        # Replace only in the specific category
        new_content, count = re.subn(category_pattern, replace_category_glb, content, flags=re.DOTALL)
        
        if count == 0:
            print(f"Category '{category_name}' with GLB data not found")
            return False
        
        # Write back as bytes to preserve exact formatting
        with open(categories_file, 'wb') as f:
            f.write(new_content.encode('utf-8'))
        
        print(f"Successfully updated GLB base64 data for '{category_name}'")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

def extract_glb_from_category(categories_file, category_name, output_dir="./extracted_glb"):
    """Extract GLB file from base64 data in categories.js"""
    try:
        # Read the categories file
        with open(categories_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the category and extract its GLB base64 data
        pattern = rf'\{{\s*name\s*:\s*"{re.escape(category_name)}"\s*,.*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)".*?\}}'
        
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            print(f"Category '{category_name}' with GLB data not found")
            return False
        
        base64_data = match.group(1)
        print(f"Found category '{category_name}' with {len(base64_data)} characters of base64 data")
        
        # Decode base64 to binary data
        try:
            # Add padding if necessary
            missing_padding = len(base64_data) % 4
            if missing_padding:
                base64_data += '=' * (4 - missing_padding)
            glb_data = base64.b64decode(base64_data)
        except Exception as e:
            print(f"Error decoding base64 data: {e}")
            return False
        
        # Create output directory if it doesn't exist
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Create safe filename
        safe_filename = re.sub(r'[<>:"/\\|?*]', '_', category_name)
        output_file = output_path / f"{safe_filename}.glb"
        
        # Write GLB file
        with open(output_file, 'wb') as f:
            f.write(glb_data)
        
        print(f"Successfully extracted GLB file: {output_file}")
        print(f"File size: {len(glb_data):,} bytes")
        return True
        
    except Exception as e:
        print(f"Error extracting GLB: {e}")
        return False

def extract_all_glb_files(categories_file, output_dir="./extracted_glb"):
    """Extract all GLB files from categories.js"""
    try:
        # Read the categories file
        with open(categories_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find all categories with GLB data
        pattern = r'name\s*:\s*"([^"]+)".*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)"'
        matches = re.findall(pattern, content, re.DOTALL)
        
        if not matches:
            print("No categories with GLB data found")
            return False
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        print(f"Found {len(matches)} categories with GLB data")
        print(f"Extracting to: {output_path}")
        print("-" * 60)
        
        success_count = 0
        for category_name, base64_data in matches:
            try:
                # Add padding if necessary
                missing_padding = len(base64_data) % 4
                if missing_padding:
                    base64_data += '=' * (4 - missing_padding)
                # Decode base64
                glb_data = base64.b64decode(base64_data)
                
                # Create safe filename
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', category_name)
                output_file = output_path / f"{safe_filename}.glb"
                
                # Write GLB file
                with open(output_file, 'wb') as f:
                    f.write(glb_data)
                
                print(f"✓ {category_name:<30} -> {output_file.name} ({len(glb_data):,} bytes)")
                success_count += 1
                
            except Exception as e:
                print(f"✗ {category_name:<30} -> Error: {e}")
        
        print("-" * 60)
        print(f"Successfully extracted {success_count}/{len(matches)} GLB files")
        return success_count > 0
        
    except Exception as e:
        print(f"Error extracting GLB files: {e}")
        return False

def list_categories_with_glb_info(categories_file):
    """List all categories with GLB information"""
    try:
        with open(categories_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find all categories with GLB data
        pattern = r'name\s*:\s*"([^"]+)".*?glb\s*:\s*"([^"]*?)"'
        matches = re.findall(pattern, content, re.DOTALL)
        
        print(f"\nFound {len(matches)} categories:")
        print("-" * 80)
        
        for i, (name, glb_data) in enumerate(matches, 1):
            if glb_data.startswith('data:application/octet-stream;base64,'):
                data_type = "GLB base64"
                data_length = len(glb_data) - len('data:application/octet-stream;base64,')
                # Estimate file size (base64 is ~33% larger than binary)
                estimated_size = int(data_length * 0.75)
                size_info = f"~{estimated_size:,} bytes"
            elif glb_data.startswith('data:'):
                data_type = "Other base64"
                data_length = len(glb_data)
                size_info = f"{data_length} chars"
            else:
                data_type = "Text/Path"
                data_length = len(glb_data)
                size_info = f"{data_length} chars"
            
            print(f"{i:2d}. {name:<35} {data_type:<12} {size_info}")
        
        return len(matches)
        
    except Exception as e:
        print(f"Error listing categories: {e}")
        return 0

def extract_swing_layers(categories_file, layer_type, output_dir="./swing_layers"):
    """Extract specific swing layers (b8 or b10) from categories.js"""
    if layer_type not in ['b8', 'b10']:
        print("Error: Layer type must be 'b8' or 'b10'")
        return False

    try:
        # Read the categories file
        with open(categories_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find swing-related categories (exclude "Swing Beams" category)
        # Pattern 1: Individual swing items with GLB data
        swing_pattern = rf'(\{{\s*name\s*:\s*"(?!.*Swing Beam)([^"]*swing[^"]*)".*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)".*?\}})'
        matches = re.findall(swing_pattern, content, re.DOTALL | re.IGNORECASE)

        # Pattern 2: Child swing items within the "Swings" category (ALL children, not just ones with "swing" in name)
        child_swing_pattern = rf'(\{{\s*name\s*:\s*"([^"]+)"\s*,\s*thumbnail\s*:.*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)".*?\}})'

        # Find the Swings category block and extract child items
        # Look for the pattern: { name : "Swings" , ... items : [ ... ] }
        swings_category_pattern = r'\{\s*name\s*:\s*"Swings".*?items\s*:\s*\[(.*?)\]\s*\}'
        swings_match = re.search(swings_category_pattern, content, re.DOTALL | re.IGNORECASE)

        if swings_match:
            swings_content = swings_match.group(1)
            child_matches = re.findall(child_swing_pattern, swings_content, re.DOTALL | re.IGNORECASE)
            # Add child matches to main matches list
            for child_match in child_matches:
                matches.append(child_match)

        # Pattern 3: Standalone swing items like "Horse Glider" - items that are swing-related but don't have "swing" in name
        # These are typically glider, trapeze, or similar playground equipment
        standalone_swing_keywords = ['glider', 'trapeze']
        for keyword in standalone_swing_keywords:
            standalone_pattern = rf'(\{{\s*name\s*:\s*"([^"]*{keyword}[^"]*)".*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)".*?\}})'
            standalone_matches = re.findall(standalone_pattern, content, re.DOTALL | re.IGNORECASE)
            for standalone_match in standalone_matches:
                matches.append(standalone_match)

        # Pattern 4: Items with glbs arrays - extract specific GLB data for the target layer
        # Need to extract the exact GLB data that matches the layer, not just the first one found
        # Structure: glbs : [ { glb : "data:...", layer : "b8" }, { glb : "data:...", layer : "b10" } ]
        glbs_items_pattern = rf'\{{\s*name\s*:\s*"([^"]+)".*?glbs\s*:\s*\[([^\]]*?)\].*?\}}'
        glbs_items = re.findall(glbs_items_pattern, content, re.DOTALL | re.IGNORECASE)

        for item_name, glbs_content in glbs_items:
            # Look for the specific GLB object with the target layer within this glbs array
            # Pattern: { glb : "data:...", layer : "b8" } (glb comes first based on actual structure)
            glb_with_layer_pattern = rf'\{{\s*glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)"\s*,\s*layer\s*:\s*"{layer_type}"\s*\}}'
            layer_matches = re.findall(glb_with_layer_pattern, glbs_content, re.DOTALL | re.IGNORECASE)

            for base64_data in layer_matches:
                if base64_data:
                    # Create a match tuple similar to other patterns: (full_text, name, base64_data)
                    # Mark this as a pre-filtered match so extraction function knows not to re-filter
                    full_text = f'{{ name : "{item_name}", layer : "{layer_type}", pre_filtered : true }}'
                    matches.append((full_text, item_name, base64_data))

        if not matches:
            print(f"No swing categories found")
            return False

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Create layer-specific subdirectory
        layer_output_path = output_path / layer_type
        layer_output_path.mkdir(exist_ok=True)

        print(f"Extracting {layer_type} layers from swing categories")
        print(f"Output directory: {layer_output_path}")
        print("-" * 60)

        success_count = 0
        for match_text, category_name, base64_data in matches:
            # Category name is already captured in the regex

            # Check if this is a pre-filtered match from glbs arrays
            is_pre_filtered = 'pre_filtered : true' in match_text

            if not is_pre_filtered:
                # For non-pre-filtered matches, check if this item contains the specific layer
                # Look for the simple layer property: layer : "b8" or layer : "b10"
                # Handle both single glb property and glbs array structures
                layer_pattern = rf'layer\s*:\s*"{layer_type}"'
                has_layer = bool(re.search(layer_pattern, match_text, re.IGNORECASE))

                # If not found in single glb, check if this item has glbs array with the layer
                if not has_layer:
                    # Look for glbs array structure: glbs : [ ... { layer : "b8" } ... ]
                    glbs_pattern = rf'glbs\s*:\s*\[([^\]]*layer\s*:\s*"{layer_type}"[^\]]*)\]'
                    has_layer = bool(re.search(glbs_pattern, match_text, re.IGNORECASE | re.DOTALL))

                if not has_layer:
                    print(f"  - {category_name:<35} -> No {layer_type} layer found")
                    continue
            # Pre-filtered matches are guaranteed to have the correct layer, so skip validation

            try:
                # Add padding if necessary
                missing_padding = len(base64_data) % 4
                if missing_padding:
                    base64_data += '=' * (4 - missing_padding)
                # Decode base64 to get GLB file
                glb_data = base64.b64decode(base64_data)

                # Create safe filename
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', category_name)
                output_file = layer_output_path / f"{safe_filename}_{layer_type}.glb"

                # Write GLB file
                with open(output_file, 'wb') as f:
                    f.write(glb_data)

                print(f"  OK {category_name:<35} -> {output_file.name} ({len(glb_data):,} bytes)")
                success_count += 1

            except Exception as e:
                print(f"  ERR {category_name:<35} -> Error: {e}")

        print("-" * 60)
        print(f"Successfully extracted {success_count} {layer_type} layer files from swing categories")
        return success_count > 0

    except Exception as e:
        print(f"Error extracting swing layers: {e}")
        return False

def import_swing_layer(categories_file, layer_type, swing_category_name, glb_file):
    """Import GLB file as b8 or b10 layer for specific swing category"""
    if layer_type not in ['b8', 'b10']:
        print("Error: Layer type must be 'b8' or 'b10'")
        return False

    try:
        # Check if GLB file exists
        if not os.path.exists(glb_file):
            print(f"GLB file not found: {glb_file}")
            return False

        # Convert GLB to base64
        print(f"Converting {glb_file} to base64 for {layer_type} layer...")
        new_base64_data = glb_to_base64_data_only(glb_file)
        if not new_base64_data:
            return False

        # Read the original file
        with open(categories_file, 'rb') as f:
            original_content = f.read()

        # Convert to string for processing
        content = original_content.decode('utf-8')

        # Simple logic: Find same name AND same layer, then replace GLB base64 data
        # We need to handle two different GLB structures:
        # 1. Complex structure: glbs array with layer field: { name: "CategoryName", glbs: [{ glb: "data:...", layer: "b10" }] }
        # 2. Simple structure: single glb field: { name: "CategoryName", glb: "data:..." }

        # First try the complex structure with glbs array and layer field
        pattern_with_layer = rf'(glb\s*:\s*"data:application/octet-stream;base64,)([^"]*?)("\s*,\s*layer\s*:\s*"{re.escape(layer_type)}")'

        # Find all category blocks with the target name
        category_pattern = rf'(\{{\s*name\s*:\s*"{re.escape(swing_category_name)}".*?\}})'
        category_matches = re.finditer(category_pattern, content, re.DOTALL)

        replacement_made = False
        for category_match in category_matches:
            category_content = category_match.group(1)
            category_start = category_match.start(1)
            category_end = category_match.end(1)

            # Within this category, look for the GLB with matching layer (complex structure)
            def replace_glb_data_with_layer(match):
                nonlocal replacement_made
                glb_prefix = match.group(1)
                old_base64 = match.group(2)
                glb_suffix = match.group(3)

                print(f"Found category '{swing_category_name}' with {layer_type} layer (complex structure)")
                print(f"Old base64 length: {len(old_base64)} characters")
                print(f"New base64 length: {len(new_base64_data)} characters")

                replacement_made = True
                return glb_prefix + new_base64_data + glb_suffix

            # Try to replace within this category block using the complex pattern
            new_category_content = re.sub(pattern_with_layer, replace_glb_data_with_layer, category_content, flags=re.DOTALL)

            # If no replacement was made with complex pattern, try simple pattern
            if not replacement_made:
                # For simple structure: just glb field without layer specification
                # We'll replace it only if the layer_type is b10 (since simple structures are typically b10)
                # or if it's explicitly for a simple swing that doesn't have layer variants
                pattern_simple = rf'(glb\s*:\s*"data:application/octet-stream;base64,)([^"]*?)(")'

                def replace_glb_data_simple(match):
                    nonlocal replacement_made
                    glb_prefix = match.group(1)
                    old_base64 = match.group(2)
                    glb_suffix = match.group(3)

                    print(f"Found category '{swing_category_name}' with simple glb structure")
                    print(f"Assuming this is for {layer_type} layer")
                    print(f"Old base64 length: {len(old_base64)} characters")
                    print(f"New base64 length: {len(new_base64_data)} characters")

                    replacement_made = True
                    return glb_prefix + new_base64_data + glb_suffix

                new_category_content = re.sub(pattern_simple, replace_glb_data_simple, category_content, flags=re.DOTALL)

            if replacement_made:
                # Replace the category block in the main content
                content = content[:category_start] + new_category_content + content[category_end:]
                break

        if not replacement_made:
            print(f"Category '{swing_category_name}' with {layer_type} layer not found")
            return False

        # Write back as bytes to preserve exact formatting
        with open(categories_file, 'wb') as f:
            f.write(content.encode('utf-8'))

        print(f"Successfully imported {layer_type} layer GLB data for category '{swing_category_name}'")
        return True

    except Exception as e:
        print(f"Error importing swing layer: {e}")
        return False

def extract_tire_swing(categories_file, category_name, output_dir="./tire_swing"):
    """Extract tire swing GLB file from categories.js"""
    try:
        # Read the categories file
        with open(categories_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find the tire swing category with joint: "joint,1,tire"
        pattern = rf'\{{\s*name\s*:\s*"{re.escape(category_name)}".*?joint\s*:\s*"joint,1,tire".*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)".*?\}}'

        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if not match:
            print(f"Tire swing category '{category_name}' with joint,1,tire not found")
            return False

        base64_data = match.group(1)
        print(f"Found tire swing '{category_name}' with {len(base64_data)} characters of base64 data")

        # Decode base64 to binary data
        try:
            # Add padding if necessary
            missing_padding = len(base64_data) % 4
            if missing_padding:
                base64_data += '=' * (4 - missing_padding)
            glb_data = base64.b64decode(base64_data)
        except Exception as e:
            print(f"Error decoding base64 data: {e}")
            return False

        # Create output directory if it doesn't exist
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Create safe filename
        safe_filename = re.sub(r'[<>:"/\\|?*]', '_', category_name)
        output_file = output_path / f"{safe_filename}_tire.glb"

        # Write GLB file
        with open(output_file, 'wb') as f:
            f.write(glb_data)

        print(f"Successfully extracted tire swing GLB file: {output_file}")
        print(f"File size: {len(glb_data):,} bytes")
        return True

    except Exception as e:
        print(f"Error extracting tire swing GLB: {e}")
        return False

def import_tire_swing(categories_file, category_name, glb_file):
    """Import GLB file for tire swing category (joint,1,tire)"""
    try:
        # Check if GLB file exists
        if not os.path.exists(glb_file):
            print(f"GLB file not found: {glb_file}")
            return False

        # Convert GLB to base64
        print(f"Converting {glb_file} to base64 for tire swing...")
        new_base64_data = glb_to_base64_data_only(glb_file)
        if not new_base64_data:
            return False

        # Read the original file
        with open(categories_file, 'rb') as f:
            original_content = f.read()

        # Convert to string for processing
        content = original_content.decode('utf-8')

        # Find the tire swing category and replace its GLB data
        # Pattern: find category with name and joint: "joint,1,tire", then replace the glb field
        pattern = rf'(\{{\s*name\s*:\s*"{re.escape(category_name)}".*?joint\s*:\s*"joint,1,tire".*?glb\s*:\s*"data:application/octet-stream;base64,)([^"]*?)(".*?\}})'

        def replace_tire_glb(match):
            before_glb = match.group(1)
            old_base64 = match.group(2)
            after_glb = match.group(3)

            print(f"Found tire swing category '{category_name}'")
            print(f"Old base64 length: {len(old_base64)} characters")
            print(f"New base64 length: {len(new_base64_data)} characters")

            return before_glb + new_base64_data + after_glb

        # Replace in the specific tire swing category
        new_content, count = re.subn(pattern, replace_tire_glb, content, flags=re.DOTALL | re.IGNORECASE)

        if count == 0:
            print(f"Tire swing category '{category_name}' with joint,1,tire not found")
            return False

        # Write back as bytes to preserve exact formatting
        with open(categories_file, 'wb') as f:
            f.write(new_content.encode('utf-8'))

        print(f"Successfully imported tire swing GLB data for '{category_name}'")
        return True

    except Exception as e:
        print(f"Error importing tire swing: {e}")
        return False

def extract_tire_swing_layer(categories_file, layer_type, output_dir="./tire_swing_layers"):
    """Extract specific tire swing layer (b4, etc.) from categories.js"""
    try:
        # Read the categories file
        with open(categories_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find tire swing items with joint: "joint,1,tire" and glbs arrays
        tire_pattern = rf'(\{{\s*name\s*:\s*"([^"]+)".*?joint\s*:\s*"joint,1,tire".*?glbs\s*:\s*\[([^\]]*?)\].*?\}})'
        matches = re.findall(tire_pattern, content, re.DOTALL | re.IGNORECASE)

        if not matches:
            print(f"No tire swing categories with glbs arrays found")
            return False

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # Create layer-specific subdirectory
        layer_output_path = output_path / layer_type
        layer_output_path.mkdir(exist_ok=True)

        print(f"Extracting {layer_type} layers from tire swing categories")
        print(f"Output directory: {layer_output_path}")
        print("-" * 60)

        success_count = 0
        for match_text, category_name, glbs_content in matches:
            # Look for the specific GLB object with the target layer
            glb_with_layer_pattern = rf'\{{\s*glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)"\s*,\s*layer\s*:\s*"{layer_type}"\s*\}}'
            layer_matches = re.findall(glb_with_layer_pattern, glbs_content, re.DOTALL | re.IGNORECASE)

            for base64_data in layer_matches:
                if not base64_data:
                    continue

                try:
                    # Add padding if necessary
                    missing_padding = len(base64_data) % 4
                    if missing_padding:
                        base64_data += '=' * (4 - missing_padding)
                    # Decode base64 to get GLB file
                    glb_data = base64.b64decode(base64_data)

                    # Create safe filename
                    safe_filename = re.sub(r'[<>:"/\\|?*]', '_', category_name)
                    output_file = layer_output_path / f"{safe_filename}_{layer_type}.glb"

                    # Write GLB file
                    with open(output_file, 'wb') as f:
                        f.write(glb_data)

                    print(f"  OK {category_name:<35} -> {output_file.name} ({len(glb_data):,} bytes)")
                    success_count += 1

                except Exception as e:
                    print(f"  ERR {category_name:<35} -> Error: {e}")

        print("-" * 60)
        print(f"Successfully extracted {success_count} {layer_type} layer files from tire swing categories")
        return success_count > 0

    except Exception as e:
        print(f"Error extracting tire swing layers: {e}")
        return False

def import_tire_swing_layer(categories_file, layer_type, category_name, glb_file):
    """Import GLB file as specific layer for tire swing category"""
    try:
        # Check if GLB file exists
        if not os.path.exists(glb_file):
            print(f"GLB file not found: {glb_file}")
            return False

        # Convert GLB to base64
        print(f"Converting {glb_file} to base64 for {layer_type} layer...")
        new_base64_data = glb_to_base64_data_only(glb_file)
        if not new_base64_data:
            return False

        # Read the original file
        with open(categories_file, 'rb') as f:
            original_content = f.read()

        # Convert to string for processing
        content = original_content.decode('utf-8')

        # Find tire swing with matching name, joint, and layer
        pattern_with_layer = rf'(glb\s*:\s*"data:application/octet-stream;base64,)([^"]*?)("\s*,\s*layer\s*:\s*"{re.escape(layer_type)}")'

        # Find the tire swing category block
        # First try with joint property (preferred)
        category_pattern = rf'(\{{\s*name\s*:\s*"{re.escape(category_name)}".*?joint\s*:\s*"joint,1,tire".*?\}})'
        category_matches = list(re.finditer(category_pattern, content, re.DOTALL))

        # If not found, try fallback pattern without joint property (for entries with glbs array already)
        if not category_matches:
            # Match entries with name and glbs array containing the specified layer
            category_pattern = rf'(\{{\s*name\s*:\s*"{re.escape(category_name)}".*?glbs\s*:\s*\[.*?\].*?\}})'
            all_matches = list(re.finditer(category_pattern, content, re.DOTALL))
            # Filter to only those containing the specified layer
            layer_pattern = rf'layer\s*:\s*"{re.escape(layer_type)}"'
            category_matches = [m for m in all_matches if re.search(layer_pattern, m.group(1))]

        replacement_made = False
        for category_match in category_matches:
            category_content = category_match.group(1)
            category_start = category_match.start(1)
            category_end = category_match.end(1)

            # Within this category, look for the GLB with matching layer
            def replace_glb_data_with_layer(match):
                nonlocal replacement_made
                glb_prefix = match.group(1)
                old_base64 = match.group(2)
                glb_suffix = match.group(3)

                print(f"Found tire swing '{category_name}' with {layer_type} layer")
                print(f"Old base64 length: {len(old_base64)} characters")
                print(f"New base64 length: {len(new_base64_data)} characters")

                replacement_made = True
                return glb_prefix + new_base64_data + glb_suffix

            # Try to replace within this category block
            new_category_content = re.sub(pattern_with_layer, replace_glb_data_with_layer, category_content, flags=re.DOTALL)

            if replacement_made:
                # Replace the category block in the main content
                content = content[:category_start] + new_category_content + content[category_end:]
                break

        if not replacement_made:
            print(f"Tire swing '{category_name}' with {layer_type} layer not found")
            return False

        # Write back as bytes to preserve exact formatting
        with open(categories_file, 'wb') as f:
            f.write(content.encode('utf-8'))

        print(f"Successfully imported {layer_type} layer GLB data for tire swing '{category_name}'")
        return True

    except Exception as e:
        print(f"Error importing tire swing layer: {e}")
        return False

def list_tire_swings(categories_file):
    """List all tire swing categories with layer information"""
    try:
        with open(categories_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find items with joint: "joint,1,tire" (capture full match text)
        tire_pattern = rf'(\{{\s*name\s*:\s*"([^"]+)".*?joint\s*:\s*"joint,1,tire".*?\}})'
        matches = re.findall(tire_pattern, content, re.DOTALL | re.IGNORECASE)

        # Also look for items with glbs arrays that have layer information
        glbs_pattern = rf'(\{{\s*name\s*:\s*"([^"]+)".*?joint\s*:\s*"joint,1,tire".*?glbs\s*:\s*\[([^\]]*?)\].*?\}})'
        glbs_matches = re.findall(glbs_pattern, content, re.DOTALL | re.IGNORECASE)

        print(f"\nFound {len(matches)} tire swing categories:")
        print("-" * 100)
        print(f"{'Category Name':<35} {'Data Type':<12} {'Size':<15} {'b4':<5} {'Layers'}")
        print("-" * 100)

        for i, (match_text, name) in enumerate(matches, 1):
            # Check if this has glbs array with layers
            has_glbs = False
            layers_found = []

            for glbs_match_text, glbs_name, glbs_content in glbs_matches:
                if glbs_name == name:
                    has_glbs = True
                    # Find all layers in this glbs array
                    layer_pattern = r'layer\s*:\s*"([^"]+)"'
                    layers_found = re.findall(layer_pattern, glbs_content, re.IGNORECASE)
                    break

            if has_glbs:
                data_type = "GLB layers"
                has_b4 = 'Yes' if 'b4' in layers_found else 'No'
                layers_str = ', '.join(sorted(set(layers_found)))
                size_info = f"{len(layers_found)} layers"
            else:
                # Single GLB
                glb_pattern = rf'glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)"'
                glb_match = re.search(glb_pattern, match_text, re.DOTALL)
                if glb_match:
                    base64_data = glb_match.group(1)
                    data_type = "GLB single"
                    estimated_size = int(len(base64_data) * 0.75)
                    size_info = f"~{estimated_size:,} bytes"
                    has_b4 = 'N/A'
                    layers_str = 'none'
                else:
                    data_type = "Unknown"
                    size_info = "N/A"
                    has_b4 = 'N/A'
                    layers_str = 'none'

            print(f"{name:<35} {data_type:<12} {size_info:<15} {has_b4:<5} {layers_str}")

        return len(matches)

    except Exception as e:
        print(f"Error listing tire swings: {e}")
        return 0

def list_swing_layers(categories_file):
    """List all swing categories with their layer information"""
    try:
        with open(categories_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find swing-related categories (exclude "Swing Beams" category)
        # Pattern 1: Individual swing items with GLB data (capture full match text)
        swing_pattern = rf'(\{{\s*name\s*:\s*"(?!.*Swing Beam)([^"]*swing[^"]*)".*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)".*?\}})'
        matches = re.findall(swing_pattern, content, re.DOTALL | re.IGNORECASE)

        # Pattern 2: Child swing items within the "Swings" category (ALL children, not just ones with "swing" in name)
        child_swing_pattern = rf'(\{{\s*name\s*:\s*"([^"]+)"\s*,\s*thumbnail\s*:.*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)".*?\}})'

        # Find the Swings category block and extract child items
        # Look for the pattern: { name : "Swings" , ... items : [ ... ] }
        swings_category_pattern = r'\{\s*name\s*:\s*"Swings".*?items\s*:\s*\[(.*?)\]\s*\}'
        swings_match = re.search(swings_category_pattern, content, re.DOTALL | re.IGNORECASE)

        if swings_match:
            swings_content = swings_match.group(1)
            child_matches = re.findall(child_swing_pattern, swings_content, re.DOTALL | re.IGNORECASE)
            # Add child matches to main matches list
            for child_match in child_matches:
                matches.append(child_match)

        # Pattern 3: Standalone swing items like "Horse Glider" - items that are swing-related but don't have "swing" in name
        # These are typically glider, trapeze, or similar playground equipment
        standalone_swing_keywords = ['glider', 'trapeze']
        for keyword in standalone_swing_keywords:
            standalone_pattern = rf'(\{{\s*name\s*:\s*"([^"]*{keyword}[^"]*)".*?glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)".*?\}})'
            standalone_matches = re.findall(standalone_pattern, content, re.DOTALL | re.IGNORECASE)
            for standalone_match in standalone_matches:
                matches.append(standalone_match)

        # Pattern 4: Items with glbs arrays - extract all GLB objects from glbs arrays
        # We need to get both b8 and b10 layers for the listing function
        # Structure: glbs : [ { glb : "data:...", layer : "b8" }, { glb : "data:...", layer : "b10" } ]
        glbs_items_pattern = rf'\{{\s*name\s*:\s*"([^"]+)".*?glbs\s*:\s*\[([^\]]*?)\].*?\}}'
        glbs_items = re.findall(glbs_items_pattern, content, re.DOTALL | re.IGNORECASE)

        for item_name, glbs_content in glbs_items:
            # Look for all GLB objects in this glbs array and extract them separately
            # Use the corrected pattern that matches glb followed by layer
            all_glb_pattern = rf'\{{\s*glb\s*:\s*"data:application/octet-stream;base64,([^"]*?)"\s*,\s*layer\s*:\s*"([^"]*?)"\s*\}}'
            all_glb_matches = re.findall(all_glb_pattern, glbs_content, re.DOTALL | re.IGNORECASE)

            for base64_data, layer_type in all_glb_matches:

                if base64_data:
                    # Create a match tuple with the layer info embedded
                    full_text = f'{{ name : "{item_name}", layer : "{layer_type}" }}'
                    matches.append((full_text, item_name, base64_data))

        print(f"\nFound {len(matches)} swing categories:")
        print("-" * 100)
        print(f"{'Category Name':<35} {'Data Type':<12} {'Size':<15} {'b8':<5} {'b10':<5}")
        print("-" * 100)

        for i, (match_text, name, base64_data) in enumerate(matches, 1):
            data_type = "GLB base64"
            data_length = len(base64_data)
            # Estimate file size (base64 is ~33% larger than binary)
            estimated_size = int(data_length * 0.75)
            size_info = f"~{estimated_size:,} bytes"

            # Check for layer types using simple property search
            try:
                # Look for layer : "b8" or layer : "b10" in the original match text
                has_b8 = bool(re.search(r'layer\s*:\s*"b8"', match_text, re.IGNORECASE))
                has_b10 = bool(re.search(r'layer\s*:\s*"b10"', match_text, re.IGNORECASE))

                # If not found in single glb, check glbs array structures
                if not has_b8:
                    glbs_b8_pattern = r'glbs\s*:\s*\[([^\]]*layer\s*:\s*"b8"[^\]]*)\]'
                    has_b8 = bool(re.search(glbs_b8_pattern, match_text, re.IGNORECASE | re.DOTALL))

                if not has_b10:
                    glbs_b10_pattern = r'glbs\s*:\s*\[([^\]]*layer\s*:\s*"b10"[^\]]*)\]'
                    has_b10 = bool(re.search(glbs_b10_pattern, match_text, re.IGNORECASE | re.DOTALL))

                has_b8 = 'Yes' if has_b8 else 'No'
                has_b10 = 'Yes' if has_b10 else 'No'

            except:
                has_b8 = 'Err'
                has_b10 = 'Err'

            print(f"{name:<35} {data_type:<12} {size_info:<15} {has_b8:<5} {has_b10:<5}")

        return len(matches)

    except Exception as e:
        print(f"Error listing swing categories: {e}")
        return 0

def main():
    categories_file = "playmor/public_html/yard/js/categories.js"

    if not os.path.exists(categories_file):
        print(f"Categories file not found: {categories_file}")
        sys.exit(1)

    if len(sys.argv) == 1:
        # No arguments - show help
        print("GLB Base64 Tool for categories.js")
        print("=" * 50)
        print("\nCommands:")
        print("  Replace GLB data:")
        print('    python replace_glb_only.py "Category Name" "path/to/file.glb"')
        print("\n  Extract single GLB file:")
        print('    python replace_glb_only.py extract "Category Name" [output_dir]')
        print("\n  Extract all GLB files:")
        print("    python replace_glb_only.py extract-all [output_dir]")
        print("\n  List categories:")
        print("    python replace_glb_only.py list")
        print("\n  === TIRE SWING COMMANDS (joint,1,tire) ===")
        print("  List tire swing categories with layer info:")
        print("    python replace_glb_only.py tire-list")
        print("\n  Extract tire swing layers (b4, etc.):")
        print('    python replace_glb_only.py tire-layer-extract b4 [output_dir]')
        print("\n  Import tire swing layer GLB:")
        print('    python replace_glb_only.py tire-layer-import b4 "Tire Swing" "path/to/file.glb"')
        print("\n  Extract single tire swing GLB (old format):")
        print('    python replace_glb_only.py tire-extract "Tire Swing" [output_dir]')
        print("\n  Import single tire swing GLB (old format):")
        print('    python replace_glb_only.py tire-import "Tire Swing" "path/to/tire_swing.glb"')
        print("\n  === SWING LAYER COMMANDS ===")
        print("  List swing categories with layer info:")
        print("    python replace_glb_only.py swing-list")
        print("\n  Extract swing layers (b8 or b10):")
        print('    python replace_glb_only.py swing-extract b8 [output_dir]')
        print('    python replace_glb_only.py swing-extract b10 [output_dir]')
        print("\n  Import swing layer GLB file:")
        print('    python replace_glb_only.py swing-import b8 "Swing Category" "path/to/file.glb"')
        print('    python replace_glb_only.py swing-import b10 "Swing Category" "path/to/file.glb"')
        print("\nExamples:")
        print('  python replace_glb_only.py "Deluxe sky" "./deluxe sky.glb"')
        print('  python replace_glb_only.py extract "Tower" "./my_glb_files"')
        print("  python replace_glb_only.py extract-all")
        print("  python replace_glb_only.py list")
        print('  python replace_glb_only.py swing-extract b8 "./swing_b8_layers"')
        print('  python replace_glb_only.py swing-import b10 "Baby Swing" "./baby_swing_b10.glb"')
    
    elif len(sys.argv) == 2:
        command = sys.argv[1].lower()
        
        if command == "list":
            count = list_categories_with_glb_info(categories_file)
            print(f"\nTotal categories: {count}")
        
        elif command == "extract-all":
            if extract_all_glb_files(categories_file):
                print("Extraction completed!")
            else:
                print("Extraction failed!")

        elif command == "swing-list":
            count = list_swing_layers(categories_file)
            print(f"\nTotal swing categories: {count}")

        elif command == "tire-list":
            count = list_tire_swings(categories_file)
            print(f"\nTotal tire swing categories: {count}")

        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("Use 'python replace_glb_only.py' to see available commands")
    
    elif len(sys.argv) == 3:
        if sys.argv[1].lower() == "extract":
            # Extract single category
            category_name = sys.argv[2]
            if extract_glb_from_category(categories_file, category_name):
                print("Extraction completed!")
            else:
                print("Extraction failed!")

        elif sys.argv[1].lower() == "tire-extract":
            # Extract tire swing GLB
            category_name = sys.argv[2]
            if extract_tire_swing(categories_file, category_name):
                print("Tire swing extraction completed!")
            else:
                print("Tire swing extraction failed!")

        elif sys.argv[1].lower() == "tire-import":
            print("Error: tire-import requires 3 arguments")
            print('Usage: python replace_glb_only.py tire-import "Category Name" "path/to/file.glb"')

        elif sys.argv[1].lower() == "extract-all":
            # Extract all with custom output directory
            output_dir = sys.argv[2]
            if extract_all_glb_files(categories_file, output_dir):
                print("Extraction completed!")
            else:
                print("Extraction failed!")

        elif sys.argv[1].lower() == "swing-extract":
            # Extract swing layers (b8 or b10)
            layer_type = sys.argv[2]
            if extract_swing_layers(categories_file, layer_type):
                print("Swing layer extraction completed!")
            else:
                print("Swing layer extraction failed!")

        elif sys.argv[1].lower() == "tire-layer-extract":
            # Extract tire swing layers (b4, etc.)
            layer_type = sys.argv[2]
            if extract_tire_swing_layer(categories_file, layer_type):
                print("Tire swing layer extraction completed!")
            else:
                print("Tire swing layer extraction failed!")

        else:
            # Replace GLB data (original functionality)
            category_name = sys.argv[1]
            glb_file = sys.argv[2]

            if replace_glb_base64_only(categories_file, category_name, glb_file):
                print("GLB replacement completed!")
            else:
                print("GLB replacement failed!")
    
    elif len(sys.argv) == 4:
        if sys.argv[1].lower() == "extract":
            # Extract single category with custom output directory
            category_name = sys.argv[2]
            output_dir = sys.argv[3]
            if extract_glb_from_category(categories_file, category_name, output_dir):
                print("Extraction completed!")
            else:
                print("Extraction failed!")

        elif sys.argv[1].lower() == "tire-extract":
            # Extract tire swing GLB with custom output directory
            category_name = sys.argv[2]
            output_dir = sys.argv[3]
            if extract_tire_swing(categories_file, category_name, output_dir):
                print("Tire swing extraction completed!")
            else:
                print("Tire swing extraction failed!")

        elif sys.argv[1].lower() == "tire-import":
            # Import tire swing GLB
            category_name = sys.argv[2]
            glb_file = sys.argv[3]
            if import_tire_swing(categories_file, category_name, glb_file):
                print("Tire swing import completed!")
            else:
                print("Tire swing import failed!")

        elif sys.argv[1].lower() == "swing-extract":
            # Extract swing layers with custom output directory
            layer_type = sys.argv[2]
            output_dir = sys.argv[3]
            if extract_swing_layers(categories_file, layer_type, output_dir):
                print("Swing layer extraction completed!")
            else:
                print("Swing layer extraction failed!")

        elif sys.argv[1].lower() == "tire-layer-extract":
            # Extract tire swing layers with custom output directory
            layer_type = sys.argv[2]
            output_dir = sys.argv[3]
            if extract_tire_swing_layer(categories_file, layer_type, output_dir):
                print("Tire swing layer extraction completed!")
            else:
                print("Tire swing layer extraction failed!")

        else:
            print("Invalid arguments. Use 'python replace_glb_only.py' to see available commands")
    
    elif len(sys.argv) == 5:
        if sys.argv[1].lower() == "swing-import":
            # Import swing layer GLB file
            layer_type = sys.argv[2]
            category_name = sys.argv[3]
            glb_file = sys.argv[4]
            if import_swing_layer(categories_file, layer_type, category_name, glb_file):
                print("Swing layer import completed!")
            else:
                print("Swing layer import failed!")

        elif sys.argv[1].lower() == "tire-layer-import":
            # Import tire swing layer GLB file
            layer_type = sys.argv[2]
            category_name = sys.argv[3]
            glb_file = sys.argv[4]
            if import_tire_swing_layer(categories_file, layer_type, category_name, glb_file):
                print("Tire swing layer import completed!")
            else:
                print("Tire swing layer import failed!")

        else:
            print("Invalid arguments. Use 'python replace_glb_only.py' to see available commands")

    else:
        print("Too many arguments. Use 'python replace_glb_only.py' to see available commands")

if __name__ == "__main__":
    main()