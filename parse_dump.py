#!/usr/bin/env python3
"""
Parse Alpha-Bus / MONO CSV dump into frames.

The script reads a CSV file where each row contains at least one column with
a single byte value (e.g. "0x7E", "7E", "126"). It concatenates all bytes from
the given column in order and splits the stream into frames where each frame
starts with 0x7E and ends with the next 0x7E (both delimiters included).

Each frame is written as one line in the output text file, bytes formatted
as "0xNN" and separated by commas.

Example:
    python parse_frames.py dump.csv frames.txt --column 1 --skip-header
"""

import argparse
import csv
from typing import List, Optional, Tuple


def parse_byte(value: str) -> Optional[int]:
    """
    Parse a string into a byte (0..255).

    Accepts:
        - "0x7E" / "0X7e"
        - "7E" / "7e"
        - "126" (decimal)

    Returns:
        Integer 0..255 or None if the value cannot be parsed.
    """
    if value is None:
        return None

    s = value.strip()
    if not s:
        return None

    # Normalize potential trailing commas etc.
    # e.g. "0x7E," -> "0x7E"
    if s.endswith(","):
        s = s[:-1].strip()

    try:
        if s.lower().startswith("0x"):
            return int(s, 16)
        # Try hex first (common in dumps)
        try:
            return int(s, 16)
        except ValueError:
            return int(s, 10)
    except ValueError:
        return None


def read_byte_stream_from_csv(
    input_path: str,
    column_index: int,
    skip_header: bool = False,
) -> List[int]:
    """
    Read a CSV file and extract a linear stream of bytes from the given column.

    Args:
        input_path: Path to the CSV file.
        column_index: Zero-based index of the column with the byte value.
        skip_header: If True, the first row is skipped.

    Returns:
        List of integers (0..255) representing the byte stream.
    """
    bytes_stream: List[int] = []

    with open(input_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=",")
        for row_idx, row in enumerate(reader):
            if skip_header and row_idx == 0:
                continue
            if not row:
                continue
            if len(row) <= column_index:
                continue

            raw_val = row[column_index]
            b = parse_byte(raw_val)
            if b is None:
                # Ignore unparsable values
                continue
            if not (0 <= b <= 0xFF):
                continue

            bytes_stream.append(b)

    return bytes_stream


def split_frames_by_0x7E(byte_stream: List[int]) -> List[List[int]]:
    """
    Split a byte stream into frames using 0x7E as start/end delimiter.

    Rules:
        - A frame starts when 0x7E is seen while we are not currently
          inside a frame.
        - A frame ends when 0x7E is seen while we are inside a frame.
        - Both the starting and ending 0x7E are included in the frame.

    Example:
        Stream: 7E 81 7D 5E 7E 7E A1 24 00 7E
        Frames:
            [7E, 81, 7D, 5E, 7E]
            [7E, A1, 24, 00, 7E]
    """
    frames: List[List[int]] = []
    current: List[int] = []
    inside_frame = False

    for b in byte_stream:
        if b == 0x7E:
            if not inside_frame:
                # Start a new frame
                inside_frame = True
                current = [b]
            else:
                # End current frame
                current.append(b)
                if current:
                    frames.append(current)
                current = []
                inside_frame = False
        else:
            if inside_frame:
                current.append(b)
            else:
                # Outside frame, ignore the byte
                continue

    # If there is an unfinished frame at the end, you can decide whether to keep it.
    # Here we discard incomplete frames (no closing 0x7E).
    return frames


def write_frames_to_file(frames: List[List[int]], output_path: str) -> None:
    """
    Write frames to a text file, one frame per line.

    Each byte is written in "0xNN" uppercase hex format, separated by commas.

    Example line:
        0x7E,0xA1,0x24,0x90,0x00,0x00,0x00,0xEA,0x7E
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for frame in frames:
            hex_bytes = ["0x{:02X}".format(b) for b in frame]
            f.write(",".join(hex_bytes) + "\n")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=("Extract MONO/Alpha-Bus frames from CSV dump using 0x7E as start/end delimiter.")
    )
    parser.add_argument(
        "input_csv",
        help="Path to input CSV dump (e.g. Alpha-Bus_Fröhliche_Weihnachten.csv)",
    )
    parser.add_argument(
        "output_txt",
        help="Path to output text file with one frame per line.",
    )
    parser.add_argument(
        "--column",
        type=int,
        default=1,
        help="Zero-based index of the CSV column that contains the byte value (default: 1, i.e. second column).",
    )
    parser.add_argument(
        "--skip-header",
        action="store_true",
        help="Skip the first line of the CSV file (useful if there is a header).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    byte_stream = read_byte_stream_from_csv(
        input_path=args.input_csv,
        column_index=args.column,
        skip_header=args.skip_header,
    )

    frames = split_frames_by_0x7E(byte_stream)

    write_frames_to_file(frames, args.output_txt)

    print(f"Read {len(byte_stream)} bytes from {args.input_csv}")
    print(f"Extracted {len(frames)} frames")
    print(f"Frames written to {args.output_txt}")


if __name__ == "__main__":
    main()
