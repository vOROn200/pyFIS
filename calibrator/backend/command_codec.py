from typing import List

CHUNK_SIZE = 5


def extract_data_bytes(payload: List[int]) -> List[int]:
    """Strip service bytes (addr/type) from a full payload, leaving only data bytes."""
    if not payload:
        return []
    data_bytes: List[int] = []
    # Skip address at index 0
    idx = 1
    while idx < len(payload):
        # Skip type byte and copy the following data chunk
        if idx >= len(payload):
            break
        chunk_start = idx + 1
        chunk_end = chunk_start + CHUNK_SIZE
        data_bytes.extend(payload[chunk_start:chunk_end])
        idx += 1 + CHUNK_SIZE
    return data_bytes


def build_full_payload(address: int, type_code: int, data_bytes: List[int]) -> List[int]:
    """Rebuild a full payload from compact data bytes."""
    if address is None or type_code is None:
        return []
    payload: List[int] = [address]
    if not data_bytes:
        payload.append(type_code)
        payload.extend([0] * CHUNK_SIZE)
        return payload
    for i in range(0, len(data_bytes), CHUNK_SIZE):
        chunk = data_bytes[i : i + CHUNK_SIZE]
        if len(chunk) < CHUNK_SIZE:
            chunk = chunk + [0] * (CHUNK_SIZE - len(chunk))
        payload.append(type_code)
        payload.extend(chunk)
    return payload


def full_to_compact_record(payload: List[int]) -> dict:
    """Convert a legacy payload into a record with address, type, and compact data."""
    if not payload:
        return {"address": None, "type_code": None, "data": []}
    address = payload[0]
    type_code = payload[1] if len(payload) > 1 else None
    return {"address": address, "type_code": type_code, "data": extract_data_bytes(payload)}
