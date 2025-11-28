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
SHIFT_BITS_TYPE_10 = -2

# Number of bits to cut from the START of the sequence for each type (applied BEFORE shift)
CUT_START_BITS_TYPE_90 = 0
CUT_START_BITS_TYPE_10 = 0


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

    # Apply shifting and cutting
    for addr, t in queues:
        cut = 0
        shift = 0
        if t == 0x90:
            cut = CUT_START_BITS_TYPE_90
            shift = SHIFT_BITS_TYPE_90
        elif t == 0x10:
            cut = CUT_START_BITS_TYPE_10
            shift = SHIFT_BITS_TYPE_10

        # 1. Apply Shift
        if shift < 0:
            # Negative shift: Remove bits from start (Shift Left)
            # We append zeros at the end to maintain length
            abs_shift = abs(shift)
            queues[(addr, t)] = queues[(addr, t)][abs_shift:] + [0] * abs_shift
        elif shift > 0:
            # Positive shift: Add zeros to start (Shift Right)
            # We remove bits from the end to maintain length
            queues[(addr, t)] = ([0] * shift + queues[(addr, t)])[:-shift]

        # 2. Apply Cut (Start)
        if cut > 0:
            queues[(addr, t)] = queues[(addr, t)][cut:]

    # Optional: debug info to stderr
    print("Bit counts per (addr, type):", file=sys.stderr)
    total_bits = 0
    for addr, t in sorted(queues.keys()):
        n = len(queues[(addr, t)])
        total_bits += n

        # Calculate params for display
        cut = 0
        shift = 0
        if t == 0x90:
            cut = CUT_START_BITS_TYPE_90
            shift = SHIFT_BITS_TYPE_90
        elif t == 0x10:
            cut = CUT_START_BITS_TYPE_10
            shift = SHIFT_BITS_TYPE_10

        # Calculate padding to next multiple of 40 (group size)
        padding = (40 - (n % 40)) % 40
        total_padded = n + padding

        print(
            f"  addr=0x{addr:X}, type=0x{t:X}, bits={n} -> {total_padded} (shift={shift}, cut={cut})",
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
            disp_str = ""

            if shift > 0:
                # Shift Right: Added 'shift' zeros to start.
                # Then Cut: Removed 'cut' bits from the new start.

                # 1. Zeros that were added but then cut -> RED
                del_zeros_count = min(cut, shift)
                if del_zeros_count > 0:
                    disp_str += f"{RED}{'0' * del_zeros_count}{RESET}"

                # 2. Zeros that were added and kept -> GREEN
                kept_zeros_count = max(0, shift - cut)
                if kept_zeros_count > 0:
                    disp_str += f"{GREEN}{'0' * kept_zeros_count}{RESET}"

                # 3. Original bits that were cut -> RED
                # This happens if cut > shift
                del_orig_count = max(0, cut - shift)
                if del_orig_count > 0:
                    part = "".join(str(b) for b in orig_bits[:del_orig_count])
                    # Limit display
                    if len(part) > 16:
                        part = part[:13] + "..."
                    disp_str += f"{RED}{part}{RESET}"

                # 4. Current bits (rest)
                # curr_bits starts with kept_zeros_count zeros (already shown as GREEN)
                # so we skip them in curr_bits to avoid duplication in display
                rest_part = "".join(str(b) for b in curr_bits[kept_zeros_count : kept_zeros_count + 16])
                disp_str += rest_part

            elif shift < 0:
                # Shift Left: Removed abs(shift) bits from start.
                # Then Cut: Removed 'cut' bits from the new start.
                abs_shift = abs(shift)

                # 1. Shift-removed bits -> RED
                shift_removed_part = "".join(str(b) for b in orig_bits[:abs_shift])
                if len(shift_removed_part) > 16:
                    shift_removed_part = shift_removed_part[:13] + "..."
                disp_str += f"{RED}{shift_removed_part}{RESET}"

                # 2. Cut-removed bits -> RED
                # These are from orig_bits[abs_shift : abs_shift + cut]
                cut_removed_part = "".join(str(b) for b in orig_bits[abs_shift : abs_shift + cut])
                if len(cut_removed_part) > 16:
                    cut_removed_part = cut_removed_part[:13] + "..."
                if cut_removed_part:
                    disp_str += f"{RED}{cut_removed_part}{RESET}"

                # 3. Current bits
                curr_part = "".join(str(b) for b in curr_bits[:16])
                disp_str += curr_part

            else:
                # No shift, just Cut
                if cut > 0:
                    cut_part = "".join(str(b) for b in orig_bits[:cut])
                    if len(cut_part) > 16:
                        cut_part = cut_part[:13] + "..."
                    disp_str += f"{RED}{cut_part}{RESET}"

                curr_part = "".join(str(b) for b in curr_bits[:16])
                disp_str += curr_part

            first_16_str = disp_str

            # --- Format last 16 bits ---
            if shift < 0:
                # Shift Left (Added zeros to end)
                added_count = abs(shift)
                last_16_curr = curr_bits[-16:]

                green_len = min(added_count, 16)
                normal_len = 16 - green_len

                normal_part = "".join(str(b) for b in last_16_curr[:normal_len])
                green_part = "".join(str(b) for b in last_16_curr[normal_len:])

                last_16_str = f"{normal_part}{GREEN}{green_part}{RESET}"

            elif shift > 0:
                # Shift Right (Lost bits from end)
                lost_count = shift
                # We lost bits from the END of the sequence *after cut*.
                # Sequence after cut was: ([0]*shift + orig)[cut:]
                # But wait, shift happens first, then cut.
                # Shift: [0]*shift + orig (truncated)
                # Cut: remove 'cut' from start.
                # The end of the sequence is determined by the Shift truncation.
                # The Cut just shortens the sequence from the start.

                # So the bits lost at the end are purely due to Shift.
                # They are the last 'shift' bits of the original sequence.
                # (Assuming cut doesn't eat into them, which is usually true unless sequence is tiny)

                last_16_orig = orig_bits[-16:]
                lost_len = min(lost_count, 16)
                kept_len = 16 - lost_len

                kept_part = "".join(str(b) for b in last_16_orig[:kept_len])
                lost_part = "".join(str(b) for b in last_16_orig[kept_len:])

                last_16_str = f"{kept_part}{RED}{lost_part}{RESET}"
            else:
                last_16_str = "".join(str(b) for b in curr_bits[-16:])

            padding_str = ""
            if padding > 0:
                padding_str = f" + [{'0' * padding}]"

            print(f"    [{first_16_str}] ... [{last_16_str}]{padding_str}", file=sys.stderr)

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
