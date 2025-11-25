#!/usr/bin/env python3
"""Test MONO flipdot display."""

import argparse
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit("The Pillow package is required: pip install pillow") from exc

from lawo import SerialMONOMaster

def parse_args():
    parser = argparse.ArgumentParser(description="Test MONO flipdot display")
    parser.add_argument("text", type=str, help="Text to display")
    parser.add_argument("--port", default="COM3", help="Serial port")
    parser.add_argument("--baudrate", type=int, default=19200, help="Serial baudrate")
    parser.add_argument("--address", type=lambda v: int(v, 0), default=0x5,
                        help="MONO bus address (0x0 - 0xF)")
    parser.add_argument("--width", type=int, default=28, help="Display width")
    parser.add_argument("--height", type=int, default=16, help="Display height")
    parser.add_argument("--col-offset", type=int, default=0, help="Column offset")
    parser.add_argument("--debug", action="store_true", help="Debug output")
    return parser.parse_args()

def render_text(text, width, height):
    """Render text to image."""
    font = ImageFont.load_default()
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    draw.text((2, 2), text, fill=255, font=font)
    return img

def main():
    args = parse_args()
    
    master = SerialMONOMaster(args.port, baudrate=args.baudrate, debug=args.debug)
    
    image = render_text(args.text, args.width, args.height)
    
    print(f"Sending image to flipdot display at address 0x{args.address:X}...")
    master.send_image_flipdot(args.address, image, args.col_offset)
    print("Done!")

if __name__ == "__main__":
    main()
