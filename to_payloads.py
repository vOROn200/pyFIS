#!/usr/bin/env python3
"""
Generate payload lines for LAWO CMD_COLUMN_DATA_FLIPDOT from an ANSI
text file describing a 26x48 logical matrix.

This script:
  - Reads a 26x48 logical matrix from a text file (ANSI-art style).
  - Splits the panel into four 13x24 segments with per-type addressing
    defined in lawo_panel.SEGMENTS.
  - Applies the type layout INSIDE each segment (0x90/0x10 + "hole" pixel).
  - Fills each segment vertically (column-major).
  - Packs bits into groups of 40 bits -> 5 data bytes, with per-byte bit
    reversal (so that decoding with the visualization script yields
    the same bits).
  - Emits payload lines for CMD_COLUMN_DATA_FLIPDOT in text format:

        addr, type0, d0, d1, d2, d3, d4, type1, d0, ...

    where each line corresponds to one bus.send_command(
        DISPLAY_ADDRESS, CMD_COLUMN_DATA_FLIPDOT, payload
    ).

IMPORTANT:
  Payloads are generated in DESCENDING address order: 0x08, 0x07, ..., 0x01.

  The ANSI input format is expected to be 26 lines of up to 48 characters each.
  Any character in {'X', 'x', '█'} is treated as ON (1), everything else as OFF (0).
"""

import sys
import os
from typing import Dict, List, Tuple

from core import (
    MATRIX_ROWS,
    MATRIX_COLS,
    read_ansi_matrix_from_file,
    build_bit_queues_from_matrix,
    build_column_payloads,
)

DEBUG_SHOW_BITS = True

# Number of bits to trim from the END of the sequence for each type
TRIM_END_BITS_TYPE_90 = 0
TRIM_END_BITS_TYPE_10 = 2


def format_payload(payload: List[int]) -> str:
    """Format a payload as a CSV line with 0xXX tokens."""
    return ",".join(f"0x{b:02X}" for b in payload)


def main() -> None:
    ansi_path = None
    if len(sys.argv) > 1:
        ansi_path = sys.argv[1]
    elif os.path.exists("ansi.txt"):
        print("Reading from default file: ansi.txt", file=sys.stderr)
        ansi_path = "ansi.txt"

    if not ansi_path:
        print(
            f"Usage: {sys.argv[0]} <ansi_matrix.txt>  # 26x48 ANSI-art file",
            file=sys.stderr,
        )
        print("   or: (reads ansi.txt if present)", file=sys.stderr)
        sys.exit(1)

    # 1. Build logical image from ANSI file
    matrix = read_ansi_matrix_from_file(ansi_path)

    # 2. Convert logical pixels to per-(addr, type) bit queues
    queues = build_bit_queues_from_matrix(matrix)

    # Keep a copy of original queues for debug display
    original_queues = {k: list(v) for k, v in queues.items()}

    # Apply trimming
    for addr, t in queues:
        trim_count = 0
        if t == 0x90:
            trim_count = TRIM_END_BITS_TYPE_90
        elif t == 0x10:
            trim_count = TRIM_END_BITS_TYPE_10

        if trim_count > 0:
            queues[(addr, t)] = queues[(addr, t)][:-trim_count]

    # Optional: debug info to stderr
    print("Bit counts per (addr, type):", file=sys.stderr)
    total_bits = 0
    for addr, t in sorted(queues.keys()):
        n = len(queues[(addr, t)])
        total_bits += n

        # Calculate trimmed bits for display
        trim_count = 0
        if t == 0x90:
            trim_count = TRIM_END_BITS_TYPE_90
        elif t == 0x10:
            trim_count = TRIM_END_BITS_TYPE_10

        print(f"  addr=0x{addr:X}, type=0x{t:X}, bits={n} (trimmed {trim_count} from end)", file=sys.stderr)

        if DEBUG_SHOW_BITS:
            # Use original bits to show what was there, and highlight trimmed part
            bits = original_queues[(addr, t)]

            # Format first 16 bits
            first_16_str = "".join(str(b) for b in bits[:16])

            # Format last 16 bits (handling trimming visualization)
            # We take the last 16 bits of the ORIGINAL sequence
            last_16_bits = bits[-16:]

            # If trimming happened within the last 16 bits
            if trim_count > 0:
                # Split last 16 into kept and trimmed parts
                # kept part length within the last 16 window
                kept_len = max(0, 16 - trim_count)

                kept_part = "".join(str(b) for b in last_16_bits[:kept_len])
                trimmed_part = "".join(str(b) for b in last_16_bits[kept_len:])

                # ANSI color for red (trimmed part)
                RED = "\033[91m"
                RESET = "\033[0m"
                last_16_str = f"{kept_part}{RED}{trimmed_part}{RESET}"
            else:
                last_16_str = "".join(str(b) for b in last_16_bits)

            print(f"    [{first_16_str}] ... [{last_16_str}]", file=sys.stderr)

    print(f"Total bits across all queues: {total_bits}", file=sys.stderr)

    # 3. Build payloads (0x08 .. 0x01 descending)
    payloads = build_column_payloads(queues, groups_per_payload=4)

    # 4. Print payloads to stdout AND write to payloads.txt
    output_lines = []
    for payload in payloads:
        line = format_payload(payload)
        print(line)
        output_lines.append(line)

    with open("payloads.txt", "w", encoding="utf-8") as f:
        for line in output_lines:
            f.write(line + "\n")

    print("Payloads written to payloads.txt", file=sys.stderr)


if __name__ == "__main__":
    main()
