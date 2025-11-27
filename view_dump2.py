#!/usr/bin/env python3
"""
Reconstruct a flipdot bitmap (approximation) from an Alpha-Bus dump.

The script expects a text file where each line contains one HDLC frame,
e.g.:

    0x7E,0xA1,0x24,0x90,...,0xEA,0x7E
or:
    CU-5;0x7E,0xA1,...,0x7E
"""

import argparse
from typing import Iterable, List, Optional

from PIL import Image

PANEL_WIDTH = 216
PANEL_HEIGHT = 32


def parse_hex_line(line: str) -> Optional[List[int]]:
    """Parse one line of the dump into a list of integer bytes.

    The line may optionally start with a label like 'CU-5;' or 'LCD;'.
    """
    line = line.strip()
    if not line:
        return None

    if ";" in line:
        _, data = line.split(";", 1)
    else:
        data = line

    parts = [p.strip() for p in data.split(",") if p.strip()]
    try:
        return [int(p, 16) for p in parts]
    except ValueError:
        # Ignore malformed lines
        return None


def iter_frames(path: str) -> Iterable[List[int]]:
    """Yield all valid HDLC frames from the dump file."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            frame = parse_hex_line(line)
            if not frame:
                continue
            if frame[0] != 0x7E or frame[-1] != 0x7E:
                # Not a proper HDLC-delimited frame
                continue
            yield frame


def map_col_addr_to_group_index(col_addr: int, first_selector: int) -> int:
    """Map Alpha-Bus column address to a 0-based 12-column group index.

    According to the observed dump:
      - Odd-line frames use selectors 0x90 and column addresses 0x24..0x13.
      - Even-line frames use selectors 0x10 and column addresses 0x12..0x01.

    Both sets cover 18 column groups -> 18 * 12 = 216 columns.
    """
    if first_selector == 0x90:
        # Odd-line A1 frames (addresses 0x24..0x13)
        group_index = 0x24 - col_addr
    elif first_selector == 0x10:
        # Even-line A1 frames (addresses 0x12..0x01)
        group_index = 0x12 - col_addr
    else:
        raise ValueError(f"Unexpected selector byte 0x{first_selector:02X}")

    if not (0 <= group_index < 18):
        raise ValueError(
            f"Column address 0x{col_addr:02X} mapped to group_index={group_index}, "
            f"which is outside expected range [0..17]"
        )
    return group_index


def decode_pairs(byte: int) -> List[int]:
    """Decode one data byte into four 2-bit pixel codes (MSB first).

    Bits layout: (b7,b6), (b5,b4), (b3,b2), (b1,b0)
    Each 2-bit code:
      00 = ignore (no change)
      01 = ignore (no change)
      10 = dark (OFF)
      11 = bright (ON)
    """
    return [
        (byte >> 6) & 0b11,
        (byte >> 4) & 0b11,
        (byte >> 2) & 0b11,
        byte & 0b11,
    ]


def apply_a1_frame(frame: List[int], panel: List[List[int]]) -> None:
    """Apply one A1 (column data) frame to the panel state.

    Frame layout (as observed from dump):
      [0]   = 0x7E  (HDLC start)
      [1]   = 0xA1  (command)
      [2]   = col_addr
      [3..] = 30 payload bytes (5 blocks x 6 bytes: selector + 5 data bytes)
      [-2]  = checksum (ignored here)
      [-1]  = 0x7E  (HDLC end)
    """
    width = len(panel[0])
    height = len(panel)

    col_addr = frame[2]
    payload = frame[3:-2]  # drop checksum and trailing 0x7E

    # Expect exactly 30 bytes = 5 blocks * 6 bytes
    if len(payload) != 30:
        # Unknown / different format, skip for safety
        return

    first_selector = payload[0]
    group_index = map_col_addr_to_group_index(col_addr, first_selector)
    x_start = group_index * 12  # 12 columns per group

    # There are 5 blocks, each 6 bytes: [selector, d0, d1, d2, d3, d4]
    # Total usable data bytes per frame: 5 blocks * 5 bytes = 25 bytes.
    # Each data byte carries 4 2-bit pixel codes -> 25 * 4 = 100 codes.
    #
    # We distribute these 100 “logical” positions over the 12xHEIGHT area
    # of this group in a simple regular pattern. This mapping is heuristic
    # and may require adjustment for a real XY5 wiring map.
    pos_index = 0
    for block in range(5):
        selector = payload[block * 6]  # 0x90 (odd) or 0x10 (even) in this dump
        # In this reconstruction we do not distinguish further by selector,
        # because we want a consistent 2D bitmap. If needed, selector can be
        # used to map to different physical row sets.
        for byte_index in range(5):
            b = payload[block * 6 + 1 + byte_index]
            for code in decode_pairs(b):
                # Map logical position to (x,y) inside this 12-column group.
                # We iterate over x first (0..11), then y.
                x_offset = pos_index % 12
                y = (pos_index // 12) % height
                x = x_start + x_offset

                if 0 <= x < width:
                    if code == 0b11:
                        # Set pixel ON
                        panel[y][x] = 1
                    elif code == 0b10:
                        # Set pixel OFF
                        panel[y][x] = 0
                    # 00 / 01 -> no change

                pos_index += 1


def build_image_from_dump(
    dump_path: str,
    width: int = PANEL_WIDTH,
    height: int = PANEL_HEIGHT,
) -> Image.Image:
    """Reconstruct panel image from Alpha-Bus A1 frames in the dump."""
    # Initialize panel with all pixels OFF
    panel = [[0 for _ in range(width)] for _ in range(height)]

    for frame in iter_frames(dump_path):
        if len(frame) < 4:
            continue
        cmd = frame[1]
        if cmd == 0xA1:
            apply_a1_frame(frame, panel)

    # Convert to grayscale PIL image: 0 = black, 255 = white
    img = Image.new("L", (width, height), 0)
    pixels = []
    for y in range(height):
        for x in range(width):
            pixels.append(255 if panel[y][x] else 0)
    img.putdata(pixels)
    return img


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct flipdot bitmap from Alpha-Bus dump (A1 frames).")
    parser.add_argument(
        "dump",
        help="Path to dump text file (one HDLC frame per line).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="reconstructed.png",
        help="Output PNG filename (default: reconstructed.png).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=PANEL_WIDTH,
        help=f"Panel width in pixels (default: {PANEL_WIDTH}).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=PANEL_HEIGHT,
        help=f"Panel height in pixels (default: {PANEL_HEIGHT}).",
    )
    args = parser.parse_args()

    img = build_image_from_dump(
        args.dump,
        width=args.width,
        height=args.height,
    )
    img.save(args.output)
    print(f"Saved reconstructed image to: {args.output}")


if __name__ == "__main__":
    main()
