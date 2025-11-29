import sys
import os
import logging
from typing import List

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
    def __init__(self, port: str, baudrate: int, simulation: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.simulation = simulation
        self.master = None
        self.display_address = 0x05  # Default, can be configurable

    def connect(self):
        if self.simulation:
            logger.info(f"Transport: Simulation mode. Virtual connection to {self.port}")
            return

        if SerialMONOMaster is None:
            logger.error("Transport: lawo package not found. Forcing simulation.")
            self.simulation = True
            return

        try:
            self.master = SerialMONOMaster(self.port, self.baudrate)
            logger.info(f"Transport: Connected to {self.port} at {self.baudrate}")
        except Exception as e:
            logger.error(f"Transport: Connection failed: {e}")
            raise

    def send_command(self, command_bytes: List[int]):
        """
        Send a raw command.
        If command_bytes is a full frame (starts with 0x7E), send as is (if supported by library).
        The lawo library usually constructs frames.

        If we are sending CMD_COLUMN_DATA_FLIPDOT, the library expects the payload.
        """
        if self.simulation:
            hex_str = ",".join(f"0x{b:02X}" for b in command_bytes)
            logger.info(f"Transport [SIM]: Sending {hex_str}")
            return True

        if not self.master:
            logger.error("Transport: Not connected")
            return False

        try:
            # Heuristic: check if it looks like a full frame or just payload
            # The user wants to send specific commands.
            # SerialMONOMaster.send_command(address, command, data)

            # If the user provides a full frame (0x7E ... 0x7E), we might need to bypass the library's framing
            # or use a raw send method if available.
            # Looking at SerialMONOMaster, it likely has a method to send constructed commands.

            # For this calibrator, we are generating payloads for CMD_COLUMN_DATA_FLIPDOT.
            # The generated command in the model is likely the payload part or the full frame.
            # Let's assume we are working with payloads for CMD_COLUMN_DATA_FLIPDOT for now,
            # as that's what core.py generates.

            # However, the user might want to send raw bytes.
            # If the library doesn't support raw send, we might need to access the serial object directly.

            if hasattr(self.master, "ser") and self.master.ser:
                self.master.ser.write(bytearray(command_bytes))
                logger.info(f"Transport: Sent {len(command_bytes)} bytes raw")
            else:
                # Fallback if we can't access serial directly (shouldn't happen with pyserial)
                logger.warning("Transport: Could not access raw serial port")
                return False

            return True
        except Exception as e:
            logger.error(f"Transport: Send failed: {e}")
            return False

    def close(self):
        if self.master:
            # self.master.close() # If available
            pass
