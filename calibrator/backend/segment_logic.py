import sys
import os
from typing import List, Dict, Optional

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

try:
    import core
except ImportError:
    # Fallback or mock if core is not found (should not happen in this workspace)
    core = None


class SegmentLogic:
    def __init__(self, display_address: int = 0x05):
        # store lower nibble to match MONO address encoding
        self.display_address = display_address & 0x0F

    @staticmethod
    def map_display_row_to_physical(seg: Dict, seg_row: int) -> int:
        """Map UI row (0==top) directly to physical scan row inside the segment."""
        return seg_row

    def get_segment_info(self, segment_name: str) -> Optional[Dict]:
        if not core:
            return None
        for seg in core.SEGMENTS:
            if seg["name"] == segment_name:
                return seg
        return None

    def generate_single_pixel_command(
        self,
        segment_name: str,
        seg_row: int,
        seg_col: int,
        frame_format: str = "raw-payload",
    ) -> List[int]:
        """
        Generate the payload that activates the specific pixel.
        Returns the raw bytes of the payload (addr, type, data...).
        """
        if not core:
            return []

        # 1. Create empty matrix
        matrix = [[0 for _ in range(core.MATRIX_COLS)] for _ in range(core.MATRIX_ROWS)]

        # 2. Find global coordinates
        seg = self.get_segment_info(segment_name)
        if not seg:
            return []

        physical_seg_row = self.map_display_row_to_physical(seg, seg_row)
        global_row = seg["row_start"] + physical_seg_row
        global_col = seg["col_start"] + seg_col

        if 0 <= global_row < core.MATRIX_ROWS and 0 <= global_col < core.MATRIX_COLS:
            matrix[global_row][global_col] = 1
        else:
            return []

        # 3. Build queues
        queues = core.build_bit_queues_from_matrix(matrix)

        # 4. Build payloads
        # This returns a list of payloads. We need to find the one that has the bit set.
        # Since we only set one bit, only one payload will have non-zero data (excluding headers).
        # However, due to bit reversal and padding, '0' bits might look like 0x00.
        # We look for the payload corresponding to the address/type of the pixel.

        # Let's calculate the expected address and type to filter.
        # We can use core helpers to find the type/addr.
        # But core.build_column_payloads does the packing.

        payloads = core.build_column_payloads(queues)

        # Find the payload that is not all zeros (ignoring headers).
        # A payload structure: [addr, type, d0..d4, type, d0..d4...]
        # It's safer to just return the payload that corresponds to the pixel's address.
        # But build_column_payloads groups by address.

        # Let's find the address of the pixel.
        # We can re-use the logic from core to find the address/type for this pixel.
        # Or just scan the generated payloads for non-zero data bytes.

        target_payload = []

        for p in payloads:
            # Check if this payload has any non-zero data bytes.
            # Structure is dynamic, but generally bytes at specific offsets are data.
            # Simple heuristic: if any byte > 0 (and it's not just the address/type headers which are non-zero).
            # Address is p[0]. Types are 0x90/0x10.
            # If we have only 1 pixel set, the data bytes for that pixel will be non-zero.
            # The data bytes for other pixels will be 0.

            # Let's look for the payload that contains the active bit.
            # Since we started with a clean matrix, only the relevant payload will have data bits set.
            # BUT, wait. 0x90 and 0x10 are non-zero. Address is non-zero.
            # We need to check the DATA bytes.

            # A payload is a list of ints.
            # We can try to see if it matches the one we expect.
            # But simpler: just return the one that is "active".

            is_active = False
            # Skip address (index 0)
            # Then groups of 6 bytes (type + 5 data)? No.
            # core.py: group = [ptype] + data_bytes (5 bytes). Total 6 bytes.
            # Payload = [addr] + group1 + group2 ...

            # Iterate over groups
            idx = 1
            while idx < len(p):
                # p[idx] is type
                # p[idx+1 .. idx+5] are data
                data_chunk = p[idx + 1 : idx + 6]
                if any(b != 0 for b in data_chunk):
                    is_active = True
                    break
                idx += 6

            if is_active:
                target_payload = p
                break

        # If we didn't find any active payload (maybe the pixel is a hole?), return empty or the first one for that segment?
        # If it's a hole, no bit is set.

        if not target_payload and payloads:
            # Fallback: maybe return the one for the address, even if empty?
            # But which address?
            # Let's calculate it.
            seg_row_type, seg_col_type = core.map_scan_to_type_coords(seg, global_row, global_col)
            ptype = core.logical_type_for_segment_pixel(seg_row_type, seg_col_type)
            if ptype is None:
                return []  # Hole

            addr = seg["addr_90"] if ptype == core.TYPE_90 else seg["addr_10"]

            # Find payload with this address
            for p in payloads:
                if p[0] == addr:
                    target_payload = p
                    break

        if frame_format == "A5-frame":
            return self._wrap_in_a5_frame(target_payload)

        return target_payload

    def generate_blank_payloads(self, frame_format: str = "raw-payload") -> List[List[int]]:
        """Build zeroed payloads for every address/type combination."""
        if not core:
            return []

        matrix = [[0 for _ in range(core.MATRIX_COLS)] for _ in range(core.MATRIX_ROWS)]
        queues = core.build_bit_queues_from_matrix(matrix)
        payloads = core.build_column_payloads(queues)

        if frame_format == "A5-frame":
            return [self._wrap_in_a5_frame(p) for p in payloads]
        return payloads

    def get_pixel_info(self, segment_name: str, seg_row: int, seg_col: int):
        seg = self.get_segment_info(segment_name)
        if not seg:
            return {}

        global_col = seg["col_start"] + seg_col

        physical_seg_row = self.map_display_row_to_physical(seg, seg_row)
        global_row = seg["row_start"] + physical_seg_row
        seg_row_type, seg_col_type = core.map_scan_to_type_coords(seg, global_row, global_col)
        ptype = core.logical_type_for_segment_pixel(seg_row_type, seg_col_type)

        if ptype is None:
            return {"type": "hole", "address": None, "bit_index": -1}

        addr = seg["addr_90"] if ptype == core.TYPE_90 else seg["addr_10"]

        # Calculate bit index
        bit_index = self.calculate_bit_index(seg, seg_row, seg_col)

        return {"type": ptype, "address": addr, "bit_index": bit_index}

    def calculate_bit_index(self, seg: Dict, target_seg_row: int, target_seg_col: int) -> int:
        """
        Calculate the bit index (0-based) for the pixel at (target_seg_row, target_seg_col)
        within its specific (addr, type) queue.
        """
        if not core:
            return -1

        # Replicate the scanning logic from core.build_bit_queues_from_matrix
        # But only for this segment and only counting bits for the target's type.

        # 1. Determine target type
        physical_seg_row = self.map_display_row_to_physical(seg, target_seg_row)
        global_row = seg["row_start"] + physical_seg_row
        global_col = seg["col_start"] + target_seg_col
        target_seg_row_type, target_seg_col_type = core.map_scan_to_type_coords(seg, global_row, global_col)
        target_ptype = core.logical_type_for_segment_pixel(target_seg_row_type, target_seg_col_type)

        if target_ptype is None:
            return -1

        # 2. Scan and count
        col_range, row_range = core.segment_scan_ranges(seg)

        bit_counter = 0
        target_physical_row = physical_seg_row

        for col in col_range:
            for row in row_range:
                # Convert global scan coords to local segment coords for comparison
                curr_seg_row = row - seg["row_start"]
                curr_seg_col = col - seg["col_start"]

                # Check if we reached the target
                if curr_seg_row == target_physical_row and curr_seg_col == target_seg_col:
                    return bit_counter

                # Check type of current pixel
                s_row_type, s_col_type = core.map_scan_to_type_coords(seg, row, col)
                ptype = core.logical_type_for_segment_pixel(s_row_type, s_col_type)

                if ptype == target_ptype:
                    bit_counter += 1

        return -1

    def generate_command_from_bit_index(
        self, segment_name: str, addr: int, type_code: int, bit_index: int, frame_format: str = "raw-payload"
    ) -> List[int]:
        """
        Generate a payload where only the bit at `bit_index` is set for the given (addr, type).
        """
        if not core or bit_index < 0:
            return []

        # Create a queue with a single bit set
        # We need to know the total length?
        # core.build_column_payloads handles chunks of 40.
        # If bit_index is e.g. 150, we need at least 151 bits.
        # Let's make it large enough, e.g. 160 (multiple of 40).

        length = max(160, bit_index + 1)
        # Round up to next multiple of 40
        if length % 40 != 0:
            length += 40 - (length % 40)

        queue = [0] * length
        queue[bit_index] = 1

        # Construct the queues dict expected by build_column_payloads
        queues = {(addr, type_code): queue}

        # Generate payloads
        payloads = core.build_column_payloads(queues)

        # Extract the relevant payload
        target_payload = []
        for p in payloads:
            if p[0] == addr:
                target_payload = p
                break

        if not target_payload:
            return []

        if frame_format == "A5-frame":
            return self._wrap_in_a5_frame(target_payload)

        return target_payload

    def _wrap_in_a5_frame(self, payload: List[int]) -> List[int]:
        command_byte = 0xA0 | self.display_address
        frame = [0x7E, command_byte] + payload
        checksum = command_byte
        for b in payload:
            checksum ^= b
        frame.append(checksum)
        frame.append(0x7E)
        return frame
