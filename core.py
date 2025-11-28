#!/usr/bin/env python3
"""
Shared logic for a 26x48 LAWO flip-dot/LED panel:

- Geometry and segment configuration.
- Type layout inside segments (0x90 / 0x10 + "hole" pixel).
- Helpers to:
    * parse hex CSV lines and split them into A5 frames vs raw payloads,
    * convert A5 frames / column payloads into (addr, type) bit queues,
    * fill a 26x48 logical matrix from (addr, type) bit queues,
    * convert a logical 26x48 matrix into (addr, type) bit queues,
    * build CMD_COLUMN_DATA_FLIPDOT payloads from these queues,
    * read a 26x48 ANSI-art file into a logical matrix (with warnings).

Scan order inside segments:

- Top segments (row_start == 0):
    rows:    top -> bottom
    columns: left -> right
    start:   top-left corner

- Bottom segments (row_start > 0):
    rows:    bottom -> top
    columns: right -> left
    start:   bottom-right corner
"""

import sys
from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Tuple

# Panel geometry (logical)
MATRIX_ROWS = 26
MATRIX_COLS = 48

# Pixel types
TYPE_90 = 0x90
TYPE_10 = 0x10

# Feature flags
ENABLE_HOLE_PIXEL = False

# Segment configuration.
# row_end / col_end are EXCLUSIVE.
SEGMENTS = [
    {
        "name": "top-left",
        "row_start": 0,
        "row_end": 13,  # 13 rows: 0..12
        "col_start": 0,
        "col_end": 24,  # 24 columns: 0..23
        "addr_90": 0x7,
        "addr_10": 0x3,
    },
    {
        "name": "top-right",
        "row_start": 0,
        "row_end": 13,
        "col_start": 24,
        "col_end": 48,
        "addr_90": 0x8,
        "addr_10": 0x4,
    },
    {
        "name": "bottom-left",
        "row_start": 13,
        "row_end": 26,  # 13 rows: 13..25
        "col_start": 0,
        "col_end": 24,
        "addr_90": 0x6,
        "addr_10": 0x2,
    },
    {
        "name": "bottom-right",
        "row_start": 13,
        "row_end": 26,
        "col_start": 24,
        "col_end": 48,
        "addr_90": 0x5,
        "addr_10": 0x1,
    },
]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def reverse_byte(b: int) -> int:
    """
    Reverse bit order in a single byte.

    Example:
        0b01111111 -> 0b11111110
    """
    rb = 0
    for i in range(8):
        rb = (rb << 1) | ((b >> i) & 0x01)
    return rb & 0xFF


# ---------------------------------------------------------------------------
# Geometry: mapping segment-local coordinates -> type
# ---------------------------------------------------------------------------


def logical_type_for_segment_pixel(seg_row: int, seg_col: int) -> Optional[int]:
    """
    Determine logical pixel type (0x90 or 0x10) for a given pixel inside a
    segment, based on segment-local coordinates (seg_row, seg_col).

    seg_row: 0..12 (13 local rows)
    seg_col: 0..23 (24 local columns)

    Rules per segment:

      - Special case:
          bottom-right pixel (seg_row == 12, seg_col == 23) has no type and
          must not be filled or consume any bits. Return None.

      - For first 12 rows (seg_row 0..11):
          seg_row 0 (1st row)  -> type 0x90
          seg_row 1 (2nd row)  -> type 0x10
          seg_row 2 -> type 0x90
          ...

      - For last row (seg_row == 12, seg_col != 23):
          types alternate by column starting from 0x90 at col 0:
              seg_col 0 -> 0x90
              seg_col 1 -> 0x10
              seg_col 2 -> 0x90
              seg_col 3 -> 0x10
              ...
    """
    # Bottom-right pixel in the segment is a "hole" (no type, no bit)
    if ENABLE_HOLE_PIXEL and seg_row == 12 and seg_col == 23:
        return None

    if seg_row < 12:
        # Alternate per row (1-based parity)
        return TYPE_90 if (seg_row % 2 == 0) else TYPE_10

    # Last row (seg_row == 12), except bottom-right already handled
    return TYPE_90 if (seg_col % 2 == 0) else TYPE_10


# ---------------------------------------------------------------------------
# Decoding: parse hex lines, split frames vs payloads, and build bit queues
# ---------------------------------------------------------------------------


def parse_hex_line(line: str) -> List[int]:
    """
    Parse a single CSV-like line of hex bytes into a list of integers.

    Examples of accepted tokens:
      "0x7E", "7E", "0x7e", "7e"

    If the line cannot be parsed, an empty list is returned.
    """
    tokens = [t.strip() for t in line.split(",") if t.strip()]
    result: List[int] = []
    for tok in tokens:
        # Normalize "0x" prefix if present
        if tok.lower().startswith("0x"):
            tok = tok[2:]
        try:
            value = int(tok, 16)
        except ValueError:
            # If something is malformed (e.g. "70x7E"), skip the whole line
            return []
        result.append(value & 0xFF)
    return result


def extract_frames_and_payloads(
    lines: Iterable[str],
) -> Tuple[List[List[int]], List[List[int]]]:
    """
    Split input into two collections:

      - frames: full 0xA5 frames of the form
            [0x7E, 0xA5, addr, payload..., checksum, 0x7E]

      - payloads: "raw" payload lines of the form
            [addr, type0, d0, d1, d2, d3, d4, type1, ...]

    Detection logic per non-empty, successfully-parsed line:
      - if bytes[0] == 0x7E and bytes[1] == 0xA5 and bytes[-1] == 0x7E:
            -> frame
      - else:
            -> payload
    """
    frames: List[List[int]] = []
    payloads: List[List[int]] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        bytes_line = parse_hex_line(line)
        if not bytes_line:
            continue
        if len(bytes_line) < 2:
            continue

        if bytes_line[0] == 0x7E and bytes_line[-1] == 0x7E and len(bytes_line) >= 5 and bytes_line[1] == 0xA5:
            frames.append(bytes_line)
        else:
            payloads.append(bytes_line)

    return frames, payloads


def _append_bits_from_data_bytes(q: Deque[int], data_bytes: Iterable[int]) -> None:
    """
    Helper: for each data byte, reverse it and append its bits (MSB-first)
    to the given deque.
    """
    for b in data_bytes:
        b_rev = reverse_byte(b)
        for bit_pos in range(7, -1, -1):  # MSB -> LSB of reversed byte
            bit = (b_rev >> bit_pos) & 0x1
            q.append(bit)


def build_addr_type_bit_queues_from_frames(
    frames: List[List[int]],
) -> Dict[Tuple[int, int], Deque[int]]:
    """
    Given all 0xA5 frames, build bit queues keyed by (addr, type).

    For each frame:
      frame = [0x7E, 0xA5, addr, payload..., checksum, 0x7E]

      payload is split into groups of 6 bytes:
        [type_byte, b0, b1, b2, b3, b4]

      type_byte: 0x90 or 0x10
      b0..b4: pixel bytes (5 bytes * 8 bits = 40 bits)

    Each data byte is bit-reversed BEFORE extracting bits.
    Bits are then taken MSB-first from the reversed bytes.
    """
    queues: Dict[Tuple[int, int], Deque[int]] = {}

    for frame in frames:
        addr = frame[2]
        payload = frame[3:-2]  # exclude: 0x7E, 0xA5, addr, checksum, 0x7E
        i = 0

        while i + 6 <= len(payload):
            type_byte = payload[i]
            data_bytes = payload[i + 1 : i + 6]

            if type_byte not in (TYPE_90, TYPE_10):
                # Unknown type marker: stop parsing this frame's payload
                break

            key = (addr, type_byte)
            q = queues.setdefault(key, deque())
            _append_bits_from_data_bytes(q, data_bytes)

            i += 6

    return queues


def build_addr_type_bit_queues_from_payloads(
    payloads: List[List[int]],
) -> Dict[Tuple[int, int], Deque[int]]:
    """
    Given all "raw" payload lines, build bit queues keyed by (addr, type).

    Each payload line is assumed to be:

        [addr, type0, b0, b1, b2, b3, b4, type1, b0, ..., ...]

    We interpret it exactly as the payload part of the 0xA5 frame, but with
    an explicit leading addr byte instead of coming from the 0xA5 header.

    For each payload line:
      addr = payload[0]
      body = payload[1:]

      body is split into groups of 6 bytes:
        [type_byte, b0, b1, b2, b3, b4]

      type_byte: 0x90 or 0x10
      b0..b4: pixel bytes

    Each data byte is bit-reversed BEFORE extracting bits.
    Bits are then taken MSB-first from the reversed bytes.
    """
    queues: Dict[Tuple[int, int], Deque[int]] = {}

    for line_bytes in payloads:
        if len(line_bytes) < 7:
            # At least addr + one group(6 bytes)
            continue

        addr = line_bytes[0]
        body = line_bytes[1:]
        i = 0

        while i + 6 <= len(body):
            type_byte = body[i]
            data_bytes = body[i + 1 : i + 6]

            if type_byte not in (TYPE_90, TYPE_10):
                # Unknown type marker: stop parsing this payload line
                break

            key = (addr, type_byte)
            q = queues.setdefault(key, deque())
            _append_bits_from_data_bytes(q, data_bytes)

            i += 6

    return queues


# ---------------------------------------------------------------------------
# Decoding: from (addr, type) bit queues -> logical matrix
# ---------------------------------------------------------------------------


def fill_matrix_from_segments(
    bit_queues: Dict[Tuple[int, int], Deque[int]],
) -> Tuple[List[List[int]], List[List[Optional[int]]]]:
    """
    Build the logical MATRIX_ROWS x MATRIX_COLS matrix using separate queues
    per segment and per type.

    Scan order:

      - Top segments (row_start == 0):
            for row from top to bottom:
                for col from left to right:
                    consume next bit for matching (addr, type)

      - Bottom segments (row_start > 0):
            for row from bottom to top:
                for col from right to left:
                    consume next bit for matching (addr, type)

    Returns:
      - matrix_bits[row][col]  -> 0 or 1
      - matrix_types[row][col] -> TYPE_90 / TYPE_10 / None
    """
    matrix_bits: List[List[int]] = [[0 for _ in range(MATRIX_COLS)] for _ in range(MATRIX_ROWS)]
    matrix_types: List[List[Optional[int]]] = [[None for _ in range(MATRIX_COLS)] for _ in range(MATRIX_ROWS)]

    for seg in SEGMENTS:
        rs = seg["row_start"]
        re = seg["row_end"]
        cs = seg["col_start"]
        ce = seg["col_end"]
        addr_90 = seg["addr_90"]
        addr_10 = seg["addr_10"]

        # Ensure queues exist for this segment and type
        q90 = bit_queues.setdefault((addr_90, TYPE_90), deque())
        q10 = bit_queues.setdefault((addr_10, TYPE_10), deque())

        # Define scan ranges depending on segment position (top vs bottom)
        if rs == 0:
            # Top segments: top -> bottom, left -> right
            row_range = range(rs, re)
            col_range = range(cs, ce)
        else:
            # Bottom segments: bottom -> top, right -> left
            row_range = range(re - 1, rs - 1, -1)
            col_range = range(ce - 1, cs - 1, -1)

        for row in row_range:
            for col in col_range:
                seg_row = row - rs
                seg_col = col - cs
                ptype = logical_type_for_segment_pixel(seg_row, seg_col)

                if ptype is None:
                    # Hole pixel: keep OFF, do not consume bits
                    matrix_bits[row][col] = 0
                    matrix_types[row][col] = None
                    continue

                if ptype == TYPE_90:
                    bit = q90.popleft() if q90 else 0
                else:
                    bit = q10.popleft() if q10 else 0

                matrix_bits[row][col] = bit
                matrix_types[row][col] = ptype

    return matrix_bits, matrix_types


# ---------------------------------------------------------------------------
# Encoding: from logical matrix -> (addr, type) bit queues -> payloads
# ---------------------------------------------------------------------------


def build_bit_queues_from_matrix(
    matrix: List[List[int]],
) -> Dict[Tuple[int, int], List[int]]:
    """
    Convert the logical matrix into bit queues for each (addr, type) pair.

    Scan order matches fill_matrix_from_segments:

      - Top segments (row_start == 0):
            rows    top -> bottom
            columns left -> right

      - Bottom segments (row_start > 0):
            rows    bottom -> top
            columns right -> left

    For each real pixel (type != None), append its bit (0/1) to the
    corresponding queue keyed by (addr, type), where addr is chosen
    from segment.addr_90 or segment.addr_10.
    """
    queues: Dict[Tuple[int, int], List[int]] = {}

    for seg in SEGMENTS:
        rs = seg["row_start"]
        re = seg["row_end"]
        cs = seg["col_start"]
        ce = seg["col_end"]
        addr_90 = seg["addr_90"]
        addr_10 = seg["addr_10"]

        if rs == 0:
            # Top segments: top -> bottom, left -> right
            row_range = range(rs, re)
            col_range = range(cs, ce)
        else:
            # Bottom segments: bottom -> top, right -> left
            row_range = range(re - 1, rs - 1, -1)
            col_range = range(ce - 1, cs - 1, -1)

        for row in row_range:
            for col in col_range:
                seg_row = row - rs
                seg_col = col - cs
                ptype = logical_type_for_segment_pixel(seg_row, seg_col)
                if ptype is None:
                    # Hole pixel: no type, does not consume bits
                    continue

                bit = matrix[row][col]  # 0 or 1
                addr = addr_90 if ptype == TYPE_90 else addr_10
                key = (addr, ptype)
                q = queues.setdefault(key, [])
                q.append(bit)

    return queues


def bits_to_data_bytes(bits: List[int]) -> List[int]:
    """
    Convert a flat list of bits (MSB-first per byte) into a list of bytes.

    For each group of 8 bits:
      - build a byte 'b_rev' where the first bit in the list becomes the MSB,
        the last becomes LSB.
      - then reverse the bit order (b = reverse_byte(b_rev)) to match the
        protocol's expectation (the decoder will reverse again and read MSB-first).

    The input length does not have to be a multiple of 8; this function zero-pads
    the last byte if necessary.
    """
    result: List[int] = []
    for i in range(0, len(bits), 8):
        chunk = bits[i : i + 8]
        if len(chunk) < 8:
            chunk = chunk + [0] * (8 - len(chunk))

        b_rev = 0
        for bit in chunk:
            b_rev = (b_rev << 1) | (bit & 0x01)

        result.append(reverse_byte(b_rev))
    return result


def build_column_payloads(
    queues: Dict[Tuple[int, int], List[int]],
    groups_per_payload: int = 4,
) -> List[List[int]]:
    """
    Build payloads for CMD_COLUMN_DATA_FLIPDOT from per-(addr, type) bit queues.

    For each (addr, type):
      - Bits are grouped into chunks of 40:
            40 bits -> 5 data bytes
      - Each 40-bit chunk becomes one "group":
            [type_byte, data_byte0, ..., data_byte4]
      - Up to 'groups_per_payload' such groups are packed into one payload:
            [addr, group1..., group2..., ...]

    Payloads are generated in DESCENDING addr order: 0x08,0x07,...,0x01.

    Returns:
      List of payloads, each payload is a list of bytes:

        [addr, type0, d0, d1, d2, d3, d4, type1, d0, ...]
    """
    payloads: List[List[int]] = []
    GROUP_BITS = 40

    # Collect all used addresses and iterate over them in descending order.
    used_addrs = sorted({addr for (addr, _) in queues.keys()}, reverse=True)

    for addr in used_addrs:
        # We process types in a fixed order: 0x90 first, then 0x10
        for ptype in (TYPE_90, TYPE_10):
            key = (addr, ptype)
            if key not in queues:
                continue

            bits = queues[key]

            # Build all groups (40 bits -> type + 5 bytes)
            groups: List[List[int]] = []
            idx = 0
            while idx < len(bits):
                chunk = bits[idx : idx + GROUP_BITS]
                if len(chunk) < GROUP_BITS:
                    chunk = chunk + [0] * (GROUP_BITS - len(chunk))

                data_bytes = bits_to_data_bytes(chunk)
                if len(data_bytes) != 5:
                    raise RuntimeError(f"Expected 5 data bytes per group, got {len(data_bytes)}")

                group = [ptype] + data_bytes
                groups.append(group)
                idx += GROUP_BITS

            # Pack groups into payloads with up to 'groups_per_payload' groups each
            gi = 0
            while gi < len(groups):
                payload: List[int] = [addr]
                for g in groups[gi : gi + groups_per_payload]:
                    payload.extend(g)
                payloads.append(payload)
                gi += groups_per_payload

    return payloads


# ---------------------------------------------------------------------------
# ANSI matrix reader (for ansi_to_payload)
# ---------------------------------------------------------------------------


def read_ansi_matrix_from_file(path: str) -> List[List[int]]:
    """
    Read a MATRIX_ROWS x MATRIX_COLS logical matrix from an ANSI-art file.

    Rules:
      - All lines in the file are read; only the first MATRIX_ROWS are used.
      - Each line is converted to bits:
            'X', 'x', '█' -> 1 (ON)
            everything else -> 0 (OFF)
      - If a line has length < MATRIX_COLS, it is padded with OFF (0) pixels,
        and a warning is printed to stderr.
      - If a line has length > MATRIX_COLS, it is truncated, and a warning
        is printed to stderr.
      - If fewer than MATRIX_ROWS lines are present, additional OFF rows
        are appended at the bottom (with warning).
      - If more than MATRIX_ROWS lines are present, extra lines are ignored
        for the matrix (with warning about total line count).
    """
    rows: List[List[int]] = []
    total_lines = 0

    with open(path, "r", encoding="utf-8") as f:
        for line_idx, raw_line in enumerate(f):
            total_lines += 1
            line_no = line_idx + 1

            if len(rows) >= MATRIX_ROWS:
                # Still count lines for warnings, but do not build more rows
                continue

            # Strip only newline characters, keep all visible characters
            line = raw_line.rstrip("\n\r")
            char_count = len(line)

            if char_count < MATRIX_COLS:
                print(
                    f"Warning: line {line_no} has length {char_count}, "
                    f"expected {MATRIX_COLS} (will be padded with OFF pixels).",
                    file=sys.stderr,
                )
            elif char_count > MATRIX_COLS:
                print(
                    f"Warning: line {line_no} has length {char_count}, " f"expected {MATRIX_COLS} (will be truncated).",
                    file=sys.stderr,
                )

            # Convert characters to bits
            row_bits: List[int] = []
            for ch in line:
                if ch in ("X", "x", "█"):
                    row_bits.append(1)
                else:
                    row_bits.append(0)

            # Normalize row length
            if len(row_bits) < MATRIX_COLS:
                row_bits.extend([0] * (MATRIX_COLS - len(row_bits)))
            else:
                row_bits = row_bits[:MATRIX_COLS]

            rows.append(row_bits)

    if total_lines < MATRIX_ROWS:
        print(
            f"Warning: file has only {total_lines} lines, "
            f"expected {MATRIX_ROWS} (missing rows will be filled with OFF pixels).",
            file=sys.stderr,
        )
    elif total_lines > MATRIX_ROWS:
        print(
            f"Warning: file has {total_lines} lines, "
            f"expected {MATRIX_ROWS} (extra lines are ignored for the matrix).",
            file=sys.stderr,
        )

    # Pad missing rows with OFF pixels if necessary
    while len(rows) < MATRIX_ROWS:
        rows.append([0] * MATRIX_COLS)

    return rows
