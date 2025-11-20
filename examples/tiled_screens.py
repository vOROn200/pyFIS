#!/usr/bin/env python3
"""
Example of controlling multiple LAWO MONO screens as a single tiled display.
Scenario: Three 26x48 vertical screens arranged side-by-side.
"""

import argparse
import time
from PIL import Image, ImageDraw, ImageFont

try:
    from lawo import SerialMONOMaster
    from lawo.mono_protocol import MONOProtocol
except ImportError:
    import sys
    import os
    # Allow running from examples/ folder without installing package
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from lawo import SerialMONOMaster
    from lawo.mono_protocol import MONOProtocol

class PrintingMONOMaster(MONOProtocol):
    """Dry-run master that prints frames instead of sending them."""
    def _send(self, frame):
        print(f"[dry-run] Address {frame[0] & 0x0F} <- {len(frame)} bytes: "
              f"{' '.join(f'{byte:02X}' for byte in frame)}")

    def _receive(self, length):
        return bytes([0x7E] + [0x00] * (length - 2) + [0x7E])

def main():
    parser = argparse.ArgumentParser(description="Tiled LAWO MONO Display Demo")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--text", default="ABC", help="Text to display across screens")
    parser.add_argument("--dry-run", action="store_true", help="Simulate only")
    args = parser.parse_args()

    # 1. Define your screen layout
    # Example: 3 screens of 26x48 pixels, addresses 1, 2, 3
    screens = [
        {"address": 1, "width": 26, "height": 48, "x_offset": 0},
        {"address": 2, "width": 26, "height": 48, "x_offset": 26},
        {"address": 3, "width": 26, "height": 48, "x_offset": 52},
    ]

    # 2. Calculate total canvas size
    total_width = sum(s["width"] for s in screens)
    max_height = max(s["height"] for s in screens)
    
    print(f"Configured {len(screens)} screens. Total canvas: {total_width}x{max_height}")

    # 3. Initialize Master
    if args.dry_run:
        master = PrintingMONOMaster(debug=False)
    else:
        master = SerialMONOMaster(args.port, baudrate=19200)

    # 4. Register displays
    for s in screens:
        master.set_display_attributes(s["address"], 
                                      {"width": s["width"], "height": s["height"]})

    # 5. Render Content
    # Create a canvas for the whole setup
    canvas = Image.new("L", (total_width, max_height), 0)
    draw = ImageDraw.Draw(canvas)
    
    # Draw text centered across all screens
    try:
        # Try to load a larger font
        font = ImageFont.truetype("Arial.ttf", 40)
    except IOError:
        font = ImageFont.load_default()
    
    # Draw text
    draw.text((5, 0), args.text, fill=255, font=font)
    
    # Optional: Draw a line across all screens to verify alignment
    draw.line((0, max_height-1, total_width, 0), fill=255, width=2)

    if args.dry_run:
        canvas.save("tiled_preview.png")
        print("Saved preview to tiled_preview.png")

    # 6. Slice and Send
    print("Sending data to screens...")
    for s in screens:
        # Crop the part of the image for this screen
        box = (s["x_offset"], 0, s["x_offset"] + s["width"], s["height"])
        screen_image = canvas.crop(box)
        
        print(f"Updating Screen {s['address']} (Region {box})...")
        master.display_image_led(s["address"], screen_image)
        
        # Small pause between screens to prevent bus congestion
        time.sleep(0.1)

    print("Done.")

if __name__ == "__main__":
    main()
