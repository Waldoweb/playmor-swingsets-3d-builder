import re
import base64
from pathlib import Path

# Path to your assets.js file
input_file = "assets.js"
output_dir = Path("extracted_images")
output_dir.mkdir(exist_ok=True)

# Read file
with open(input_file, "r", encoding="utf-8") as f:
    content = f.read()

# Find all Base64 data URIs
matches = re.findall(r"data:image/(png|jpg|jpeg|gif);base64,([A-Za-z0-9+/=]+)", content)

# Save images
for i, (img_type, b64data) in enumerate(matches):
    # Fix padding
    missing_padding = len(b64data) % 4
    if missing_padding:
        b64data += "=" * (4 - missing_padding)

    try:
        img_data = base64.b64decode(b64data)
        filename = output_dir / f"image_{i}.{img_type}"
        with open(filename, "wb") as img_file:
            img_file.write(img_data)
        print(f"Saved: {filename}")
    except Exception as e:
        print(f"Skipping image {i}: {e}")