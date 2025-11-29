#!/usr/bin/env python3
"""Export confirmed pixels from mapping.json in a compact table."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

DEFAULT_MAPPING = Path("mapping.json")


def load_mapping(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Mapping file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def format_command(data: List[int]) -> str:
    if not data:
        return ""
    return "".join(f"{byte:02X}" for byte in data)


def resolve_command(pixel: dict) -> str:
    remaps = pixel.get("remap_commands") or []
    remap_active = pixel.get("remap_active", False)
    if remap_active and remaps:
        # remap entries may be dicts with metadata
        alt = remaps[0]
        data = alt.get("data") if isinstance(alt, dict) else alt
        return format_command(data or pixel.get("assigned_command", []))
    return format_command(pixel.get("assigned_command", []))


def export_confirmed(mapping: dict):
    pixels = mapping.get("pixels", [])
    confirmed = [p for p in pixels if p.get("status") == "tested_ok"]
    if not confirmed:
        print("No confirmed pixels found.")
        return

    header = f"{'Coord':>10} | {'Addr':>4} | {'Type':>4} | Command"
    print(header)
    print("-" * len(header))
    for pixel in confirmed:
        coord = f"({pixel.get('col', '?')},{pixel.get('row', '?')})"
        addr = pixel.get("address")
        ptype = pixel.get("type_code")
        command = resolve_command(pixel)
        print(f"{coord:>10} | {addr:04X} | {ptype:04X} | {command}")


def main():
    mapping_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAPPING
    mapping = load_mapping(mapping_path)
    export_confirmed(mapping)


if __name__ == "__main__":
    main()
