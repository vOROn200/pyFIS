#!/usr/bin/env python3
"""
Reconstruct a 26x48 logical flip-dot/LED matrix from MONO data and
print it as ANSI-art, highlighting different pixel types in different colors.

Supported input formats (one frame/payload per line):

1) Old 0xA5 frame format:
   0x7E,0xA5,<addr>,<payload...>,<checksum>,0x7E

   where payload is interpreted as groups of 6 bytes:
       [type_byte, b0, b1, b2, b3, b4]
   type_byte is 0x90 or 0x10, b0..b4 are 5 data bytes (40 bits).

2) New payload format (for CMD_COLUMN_DATA_FLIPDOT):
   <addr>, type0, d0, d1, d2, d3, d4, type1, d0, ...

   where:
     - the first byte is the address for this payload (0x08..0x01),
     - the rest is a sequence of groups:
           [type_byte, b0, b1, b2, b3, b4] ...

In both cases:
  - Each data byte is bit-reversed before extracting bits.
  - Bits from each group are pushed into queues keyed by (addr, type).

Geometry and addressing are defined in lawo_panel.py.
"""

import sys
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from lawo_panel import (
    MATRIX_ROWS,
    MATRIX_COLS,
    TYPE_90,
    TYPE_10,
    extract_frames_and_payloads,
    build_addr_type_bit_queues_from_frames,
    build_addr_type_bit_queues_from_payloads,
    fill_matrix_from_segments,
)

# ANSI characters for output
ANSI_CHAR_ON = "X"
ANSI_CHAR_OFF = "·"

# ANSI color codes
ANSI_RESET = "\x1b[0m"
ANSI_COLOR_90 = "\x1b[33m"  # yellow for type 0x90
ANSI_COLOR_10 = "\x1b[36m"  # cyan for type 0x10


def render_matrix_as_ansi(
    matrix_bits: List[List[int]],
    matrix_types: List[List[Optional[int]]],
) -> str:
    """
    Convert the logical matrix to an ANSI-art string using two characters:
      - ANSI_CHAR_ON for pixels == 1, colored by type:
            type 0x90 -> ANSI_COLOR_90
            type 0x10 -> ANSI_COLOR_10
      - ANSI_CHAR_OFF for pixels == 0 (no color).
    """
    lines: List[str] = []

    for row_bits, row_types in zip(matrix_bits, matrix_types):
        line_chars: List[str] = []
        for bit, ptype in zip(row_bits, row_types):
            if bit:
                # ON pixel: color by type
                if ptype == TYPE_90:
                    color = ANSI_COLOR_90
                elif ptype == TYPE_10:
                    color = ANSI_COLOR_10
                else:
                    # Should not normally happen, fallback to no color
                    color = ""
                line_chars.append(f"{color}{ANSI_CHAR_ON}{ANSI_RESET}")
            else:
                # OFF pixel: plain
                line_chars.append(ANSI_CHAR_OFF)
        lines.append("".join(line_chars))

    return "\n".join(lines)


def main() -> None:
    """
    Entry point.

    Usage examples:
        # From file with 0xA5 frames:
        python3 dump_to_ansi.py dump_frames.txt

        # From file with raw payloads (addr, type, d0..d4, ...):
        python3 dump_to_ansi.py payloads.txt

        # From stdin:
        cat dump.txt | python3 dump_to_ansi.py
    """
    if len(sys.argv) > 1 and sys.argv[1] not in ("-", ""):
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    frames, payloads = extract_frames_and_payloads(lines)

    if not frames and not payloads:
        print(
            "No 0xA5 frames or payload lines found in input.",
            file=sys.stderr,
        )
        return

    # Build queues from both sources and merge them
    bit_queues: Dict[Tuple[int, int], Deque[int]] = {}

    if frames:
        queues_frames = build_addr_type_bit_queues_from_frames(frames)
        for key, q in queues_frames.items():
            bit_queues.setdefault(key, deque()).extend(q)

    if payloads:
        queues_payloads = build_addr_type_bit_queues_from_payloads(payloads)
        for key, q in queues_payloads.items():
            bit_queues.setdefault(key, deque()).extend(q)

    # Debug: show how many bits we collected per (addr, type)
    print("Collected bits per (addr, type):", file=sys.stderr)
    for (addr, t), q in sorted(bit_queues.items()):
        print(
            f"  addr=0x{addr:X}, type=0x{t:X}, bits={len(q)}",
            file=sys.stderr,
        )

    matrix_bits, matrix_types = fill_matrix_from_segments(bit_queues)
    ansi_art = render_matrix_as_ansi(matrix_bits, matrix_types)
    print(ansi_art)


if __name__ == "__main__":
    main()
