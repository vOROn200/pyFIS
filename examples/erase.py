#!/usr/bin/env python3
"""
Clear a LAWO flipdot panel over the MONO/Alpha-like protocol.

This script sends a PRE_BITMAP_FLIPDOT command followed by 36
COLUMN_DATA_FLIPDOT telegrams with all-zero pixel data, which
matches the 0x91/0xA1 pattern seen in the CU-5 serial dump.
"""

import argparse
import time
from main import print_reply
from lawo import SerialMONOMaster


def parse_args():
    parser = argparse.ArgumentParser(
        description="Clear a LAWO flipdot panel via MONO bus"
    )
    parser.add_argument(
        "--port",
        default="COM3",
        help="Serial port name (e.g. COM3, /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=19200,
        help="Serial baudrate (default: 19200)",
    )
    parser.add_argument(
        "--address",
        type=lambda v: int(v, 0),
        default=0x5,
        help="MONO bus address (0x0 - 0xF), use 0x prefix for hex",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=True,
        help="Enable debug output in SerialMONOMaster",
    )
    return parser.parse_args()


# According to the CU-5 dump:
#   0xA1, <addr>, 32 data bytes, checksum
# so the payload *data* for CMD_COLUMN_DATA_FLIPDOT is:
#   [addr] + 32 bytes.
ZERO_DATA_SEGMENT = [0x00] * 32

# Addresses used by CU-5 for column data:
#   odd rows:  0x24 .. 0x13
#   even rows: 0x12 .. 0x01
FIRST_ODD_ADDR = 0x24
LAST_ODD_ADDR = 0x13
FIRST_EVEN_ADDR = 0x12
LAST_EVEN_ADDR = 0x01

# PRE_BITMAP parameters from the dump:
#   0x91, 0x24, 0x12, checksum
# We keep them as-is because they describe the panel's internal
# segmentation (36 column segments total, 18 per half), not just
# your logical 26x48 area.
PRE_BITMAP_PARAM_1 = 0x24  # total number of column segments
PRE_BITMAP_PARAM_2 = 0x12  # segments per half (odd/even)


def erase_display(master: SerialMONOMaster, address: int) -> None:
    """
    Send a bitmap preamble and then 36 all-zero column-data frames
    to clear the entire physical panel.
    """

    # 1) Tell the controller that a bitmap transfer is about to follow.
    #    These parameters are taken directly from the CU-5 dump:
    #      0x91, 0x24, 0x12, CS
    setup_data = [PRE_BITMAP_PARAM_1, PRE_BITMAP_PARAM_2]
    master.send_command(address, master.CMD_PRE_BITMAP_FLIPDOT, setup_data)
    # Small pause so the slave can prepare for the stream
    time.sleep(0.1)

    # 2) Odd rows: addresses 0x24 down to 0x13
    for addr_byte in range(FIRST_ODD_ADDR, LAST_ODD_ADDR - 1, -1):
        payload = [addr_byte] + ZERO_DATA_SEGMENT
        master.send_command(address, master.CMD_COLUMN_DATA_FLIPDOT, payload)
        # Short delay to mimic CU-5 pacing and be gentle to the hardware
        time.sleep(0.01)

    # 3) Even rows: addresses 0x12 down to 0x01
    for addr_byte in range(FIRST_EVEN_ADDR, LAST_EVEN_ADDR - 1, -1):
        payload = [addr_byte] + ZERO_DATA_SEGMENT
        master.send_command(address, master.CMD_COLUMN_DATA_FLIPDOT, payload)
        time.sleep(0.01)

    print("All 36 column segments have been written with zeros.")
    print("Display should now be fully cleared (all dots black/off).")


def main():
    args = parse_args()

    master = SerialMONOMaster(
        args.port,
        baudrate=args.baudrate,
        debug=args.debug,
    )

    try:
        reply = master.send_command(args.address, master.CMD_QUERY, [])
        print_reply(reply)

        time.sleep(0.2)
    
        erase_display(master, args.address)

        time.sleep(0.2)

        reply = master.send_command(args.address, master.CMD_QUERY, [0x7E])
        print_reply(reply)

        
    finally:
        # If SerialMONOMaster exposes a close() method, call it.
        # If not, this is harmless.
        close = getattr(master, "close", None)
        if callable(close):
            close()
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
