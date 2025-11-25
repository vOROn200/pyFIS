#!/usr/bin/env python3
"""Simple demo that renders text and sends it to a LAWO MONO LED display."""

import argparse
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore[import]
except ImportError as exc:
    raise SystemExit("The Pillow package is required: pip install pillow") from exc

from lawo import LawoFont, SerialMONOMaster
from lawo.mono_protocol import MONOProtocol


class PrintingMONOMaster(MONOProtocol):
    """Debug helper that logs frames instead of talking to real hardware."""

    def _send(self, frame):
        print(f"[dry-run] sending {len(frame)} bytes: "
              f"{' '.join(f'{byte:02X}' for byte in frame)}")

    def _receive(self):
        print(f"[dry-run] checking for reply")
        return bytes([0x7E, 0x00, 0x7E])


def parse_args():
    parser = argparse.ArgumentParser(
        description=("Render text with a LAWO font (or the default Pillow font) "
                     "and push it to a MONO LED sign."),
    )
    parser.add_argument("text", type=str, nargs='?', help="Text to display")
    parser.add_argument("--port", default="/dev/ttyUSB0",
                        help="Serial port connected to the MONO bus")
    parser.add_argument("--baudrate", type=int, default=19200,
                        help="Serial baudrate")
    parser.add_argument("--address", type=lambda v: int(v, 0), default=0x0,
                        help="MONO bus address (0x0 - 0xF)")
    parser.add_argument("--width", type=int,
                        help="Display width in pixels")
    parser.add_argument("--height", type=int,
                        help="Display height in pixels")
    parser.add_argument("--font-file", type=Path,
                        help="Optional LAWO *.F?? font file")
    parser.add_argument("--save-image", type=Path,
                        help="Store the rendered bitmap for inspection")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not open the serial port, only print frames")
    parser.add_argument("--debug", action="store_true",
                        help="Dump raw MONO frames")
    parser.add_argument("--test-query", action="store_true",
                        help="Only send query command and show response")
    return parser.parse_args()


def render_text_image(text, width, height, font_path):
    """Render text into a grayscale Pillow image that matches the LED size."""

    if font_path:
        font = LawoFont()
        font.read_file(str(font_path))
        glyph_img = font.render_text(text)
    else:
        font = ImageFont.load_default()
        tmp = Image.new("L", (width * 2 or 1, height or font.size), 0)
        draw = ImageDraw.Draw(tmp)
        draw.text((0, 0), text, fill=255, font=font)
        bbox = tmp.getbbox()
        glyph_img = tmp.crop(bbox) if bbox else tmp

    canvas = Image.new("L", (width, height), 0)
    crop = glyph_img.crop((0, 0, min(width, glyph_img.width),
                           min(height, glyph_img.height)))
    x_off = max(0, (width - crop.width) // 2)
    y_off = max(0, (height - crop.height) // 2)
    canvas.paste(crop, (x_off, y_off))
    return canvas


def main():
    args = parse_args()
    
    master = (PrintingMONOMaster(debug=args.debug)
              if args.dry_run else
              SerialMONOMaster(args.port, baudrate=args.baudrate, debug=args.debug))
    
    # Test query mode
    if args.test_query:
        print(f"Sending query command to address 0x{args.address:X}...")
        reply = master.send_command(args.address, master.CMD_QUERY, [], 
                                    checksum_method='flipdot')
        if reply:
            print(f"✓ Reply received: {' '.join(f'{b:02X}' for b in reply)}")
        else:
            print("✗ No reply received")
        return
    
    # Normal display mode
    if not args.text:
        print("Error: text argument is required (unless using --test-query)")
        return
    
    if not args.width or not args.height:
        print("Error: --width and --height are required (unless using --test-query)")
        return
    
    image = render_text_image(args.text, args.width, args.height, args.font_file)

    if args.save_image:
        image.save(args.save_image)
        print(f"Saved preview bitmap to {args.save_image}")

    master.set_display_attributes(args.address, {"width": args.width, "height": args.height})
    master.display_image_led(args.address, image)
    print("Bitmap queued for display")


if __name__ == "__main__":
    main()
