#!/usr/bin/env python3
"""
Clear a LAWO flipdot panel over the MONO/Alpha-like protocol.

This script sends a PRE_BITMAP_FLIPDOT command followed by 36
COLUMN_DATA_FLIPDOT telegrams with all-zero pixel data, which
matches the 0x91/0xA1 pattern seen in the CU-5 serial dump.
"""

import argparse
import time
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

def print_reply(reply):
    if reply:
        print(f"Reply received: {' '.join(f'{b:02X}' for b in reply)}")
    else:
        print("No reply received")

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
    
        reply = master.send_command(args.address, master.CMD_PRE_BITMAP_FLIPDOT, [0x24, 0x12])
        print_reply(reply)

        time.sleep(0.2)

        data = [0x24 , 
                0x90, 0xFF, 0xFF,0,0,0,
                0x90, 0, 0,0,0,0,
                0x90, 0, 0,0,0,0,
                0x90, 0, 0,0,0,0,
                0x90, 0, 0,0,0,0,
                0x90, 0, 0,0,0xFF,0xFF,
                ]

        reply = master.send_command(args.address, master.CMD_COLUMN_DATA_FLIPDOT, data)
        print_reply(reply)

        time.sleep(0.2)

        input ("Press Enter to send another query...")

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
