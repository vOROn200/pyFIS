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

# Bit shift for each type.
# Positive (> 0): Insert zeros at the beginning (Shift Right / Delay).
# Negative (< 0): Remove bits from the beginning (Shift Left / Advance).
SHIFT_BITS_TYPE_90 = 0
SHIFT_BITS_TYPE_10 = 2


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

    # Apply shifting
    for addr, t in queues:
        shift = 0
        if t == 0x90:
            shift = SHIFT_BITS_TYPE_90
        elif t == 0x10:
            shift = SHIFT_BITS_TYPE_10

        if shift < 0:
            # Negative shift: Remove bits from start (Shift Left)
            # We append zeros at the end to maintain length
            abs_shift = abs(shift)
            queues[(addr, t)] = queues[(addr, t)][abs_shift:] + [0] * abs_shift
        elif shift > 0:
            # Positive shift: Add zeros to start (Shift Right)
            # We remove bits from the end to maintain length
            queues[(addr, t)] = ([0] * shift + queues[(addr, t)])[:-shift]

    # Optional: debug info to stderr
    print("Bit counts per (addr, type):", file=sys.stderr)
    total_bits = 0
    for addr, t in sorted(queues.keys()):
        n = len(queues[(addr, t)])
        total_bits += n

        # Calculate shift for display
        shift = 0
        if t == 0x90:
            shift = SHIFT_BITS_TYPE_90
        elif t == 0x10:
            shift = SHIFT_BITS_TYPE_10

        print(
            f"  addr=0x{addr:X}, type=0x{t:X}, bits={n} (shift={shift})",
            file=sys.stderr,
        )

        if DEBUG_SHOW_BITS:
            # Use original bits to show what was there
            orig_bits = original_queues[(addr, t)]
            # Use current bits to show result
            curr_bits = queues[(addr, t)]

            RED = "\033[91m"
            GREEN = "\033[92m"
            RESET = "\033[0m"

            # --- Format first 16 bits ---
            if shift < 0:
                # Shift Left (Removed bits from start)
                removed_count = abs(shift)
                removed_part = "".join(str(b) for b in orig_bits[:removed_count])

                # Limit removed part display
                disp_removed = removed_part[:16]

                curr_part = "".join(str(b) for b in curr_bits[:16])
                first_16_str = f"{RED}{disp_removed}{RESET}{curr_part}"

            elif shift > 0:
                # Shift Right (Added zeros to start)
                added_count = shift
                added_part = "".join(str(b) for b in curr_bits[:added_count])

                # Limit added part display
                disp_added = added_part[:16]

                rest_part = "".join(str(b) for b in curr_bits[added_count : added_count + 16])
                first_16_str = f"{GREEN}{disp_added}{RESET}{rest_part}"
            else:
                first_16_str = "".join(str(b) for b in curr_bits[:16])

            # --- Format last 16 bits ---
            if shift < 0:
                # Shift Left (Added zeros to end)
                added_count = abs(shift)
                # Last 16 bits of current sequence
                last_16_curr = curr_bits[-16:]

                # The added zeros are at the very end
                # If added_count >= 16, all last 16 are green
                green_len = min(added_count, 16)
                normal_len = 16 - green_len

                normal_part = "".join(str(b) for b in last_16_curr[:normal_len])
                green_part = "".join(str(b) for b in last_16_curr[normal_len:])

                last_16_str = f"{normal_part}{GREEN}{green_part}{RESET}"

            elif shift > 0:
                # Shift Right (Lost bits from end)
                lost_count = shift
                # Last 16 bits of ORIGINAL sequence (to show what was lost)
                last_16_orig = orig_bits[-16:]

                # The lost bits are at the very end of original
                lost_len = min(lost_count, 16)
                kept_len = 16 - lost_len

                kept_part = "".join(str(b) for b in last_16_orig[:kept_len])
                lost_part = "".join(str(b) for b in last_16_orig[kept_len:])

                last_16_str = f"{kept_part}{RED}{lost_part}{RESET}"
            else:
                last_16_str = "".join(str(b) for b in curr_bits[-16:])

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
