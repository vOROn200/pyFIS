import sys
import os
import logging
import time
from typing import List, Sequence

# Add project root to sys.path to import lawo package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

try:
    from lawo import SerialMONOMaster
    from lawo.mono_protocol import CMD_COLUMN_DATA_FLIPDOT, CMD_PRE_BITMAP_FLIPDOT, CMD_QUERY
except ImportError:
    SerialMONOMaster = None
    CMD_COLUMN_DATA_FLIPDOT = 0x10
    CMD_PRE_BITMAP_FLIPDOT = 0x20
    CMD_QUERY = 0x02

logger = logging.getLogger(__name__)


class Transport:
    def __init__(
        self,
        port: str,
        baudrate: int,
        simulation: bool = False,
        display_address: int = 0x05,
        pre_width: int = 0x08,
        pre_height: int = 0x04,
        command_delay: float = 0.2,
    ):
        self.port = port
        self.baudrate = baudrate
        self.simulation = simulation
        self.master = None
        self.display_address = display_address & 0x0F
        self.pre_bitmap_payload = [pre_width & 0xFF, pre_height & 0xFF]
        self.command_delay = max(0.0, command_delay)

    def connect(self):
        if self.simulation:
            logger.info(f"Transport: Simulation mode. Virtual connection to {self.port}")
            return

        if SerialMONOMaster is None:
            logger.error("Transport: lawo package not found. Forcing simulation.")
            self.simulation = True
            return

        try:
            self.master = SerialMONOMaster(self.port, self.baudrate, stopbits=2)
            logger.info(f"Transport: Connected to {self.port} at {self.baudrate}")
        except Exception as e:
            logger.error(f"Transport: Connection failed: {e}")
            raise

    def send_command(self, command_bytes: Sequence[int]):
        """Compatibility wrapper for sending a single payload."""
        return self.send_payload_batch([command_bytes])

    def send_payload_batch(self, payload_batches: Sequence[Sequence[int]]):
        """Send a batch of payloads with a single QUERY/PRE/QUERY sequence."""
        sanitized_batches: List[List[int]] = []
        for batch in payload_batches:
            sanitized_batches.append([int(b) & 0xFF for b in batch])

        if not sanitized_batches:
            logger.warning("Transport: No payloads to send")
            return False

        if self.simulation:
            self._log_simulated_batch(sanitized_batches)
            return True

        if not self.master:
            logger.error("Transport: Not connected")
            return False

        if not self._send_bus_command(CMD_QUERY, [], "initial QUERY"):
            return False
        if not self._send_bus_command(CMD_PRE_BITMAP_FLIPDOT, self.pre_bitmap_payload, "PRE_BITMAP"):
            return False
        for idx, payload in enumerate(sanitized_batches):
            if not self._send_bus_command(CMD_COLUMN_DATA_FLIPDOT, payload, f"COLUMN_DATA[{idx}]"):
                return False
        return self._send_bus_command(CMD_QUERY, [], "final QUERY")

    def _send_bus_command(self, command: int, payload: List[int], label: str) -> bool:
        try:
            self.master.send_command(self.display_address, command, payload)
            self._sleep_after_command()
            logger.debug(f"Transport: Sent {label} (cmd=0x{command:02X}, len={len(payload)})")
            return True
        except Exception as e:
            logger.error(f"Transport: {label} failed: {e}")
            return False

    def _sleep_after_command(self):
        if self.command_delay > 0:
            time.sleep(self.command_delay)

    def _log_simulated_batch(self, payloads: List[List[int]]):
        hex_query = self._format_bytes([])
        hex_pre = self._format_bytes(self.pre_bitmap_payload)
        payload_logs = "; ".join(self._format_bytes(p) for p in payloads)
        logger.info(
            "Transport [SIM]: QUERY(%s) -> PRE_BITMAP(%s) -> COLUMN_DATA_BATCH[%s] -> QUERY(%s)",
            hex_query,
            hex_pre,
            payload_logs,
            hex_query,
        )

    @staticmethod
    def _format_bytes(data: Sequence[int]) -> str:
        if not data:
            return "-"
        return ",".join(f"0x{b:02X}" for b in data)

    def close(self):
        if self.master:
            # self.master.close() # If available
            pass
