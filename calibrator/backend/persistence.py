import json
import os
from typing import Optional, List, Any, Dict
from .model import SegmentMapping
from .command_codec import extract_data_bytes, full_to_compact_record


class PersistenceManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self) -> dict:
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_config(self, config: dict):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        self.config = config

    def load_mapping(self, file_path: str) -> Optional[SegmentMapping]:
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._normalize_mapping_payloads(data)
                return SegmentMapping(**data)
            except Exception as e:
                print(f"Error loading mapping: {e}")
                return None
        return None

    def save_mapping(self, file_path: str, mapping: SegmentMapping):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(mapping.model_dump_json(indent=2))

    def _normalize_mapping_payloads(self, data: Dict[str, Any]):
        pixels = data.get("pixels", [])
        for pixel in pixels:
            address = pixel.get("address")
            type_code = pixel.get("type_code")
            for key in ("generated_command", "assigned_command"):
                payload = pixel.get(key)
                if isinstance(payload, list) and payload:
                    if self._looks_like_full(payload, address):
                        pixel[key] = extract_data_bytes(payload)
                elif payload is None:
                    pixel[key] = []

            remap_list = pixel.get("remap_commands", [])
            normalized_remaps = []
            for item in remap_list:
                if isinstance(item, dict) and "data" in item:
                    normalized_remaps.append(item)
                elif isinstance(item, list) and item:
                    record = full_to_compact_record(item)
                    if record["address"] is not None:
                        normalized_remaps.append(record)
            pixel["remap_commands"] = normalized_remaps
            pixel.setdefault("remap_active", False)

            # Ensure commands stored as compact even for freshly generated payloads
            for key in ("generated_command", "assigned_command"):
                payload = pixel.get(key)
                if isinstance(payload, list):
                    pixel[key] = payload

    def _looks_like_full(self, payload: List[Any], address: Optional[int]) -> bool:
        if not payload:
            return False
        if address is not None and payload[0] != address:
            return False
        return (len(payload) - 1) % 6 == 0
