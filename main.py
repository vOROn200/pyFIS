#!/usr/bin/env python3
"""
Clear a LAWO flipdot panel over the MONO/Alpha-like protocol.

This script sends a PRE_BITMAP_FLIPDOT command followed by 36
COLUMN_DATA_FLIPDOT telegrams with all-zero pixel data, which
matches the 0x91/0xA1 pattern seen in the CU-5 serial dump.
"""

import time
from lawo import SerialMONOMaster

def main():

    ADDRESS = int(0x05)

    bus = SerialMONOMaster(
        "COM3",
        baudrate=19200,
        stopbits=1,
        debug=True,
    )

    bus.send_command(ADDRESS, bus.CMD_QUERY, [])

    time.sleep(0.2)

    bus.send_command(ADDRESS, bus.CMD_PRE_BITMAP_FLIPDOT, [0x05, 0x01])

    time.sleep(0.2) 

    data = [0x05 , 
            0x90, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
            0x90, 0, 0, 0 , 0, 0,
            0x90, 0, 0, 0,  0, 0,
            0x90, 0, 0 ,0 , 0, 0, 
            0x90, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
            ]

    bus.send_command(ADDRESS, bus.CMD_COLUMN_DATA_FLIPDOT, data)

    time.sleep(0.2) 

    bus.send_command(ADDRESS, bus.CMD_QUERY, [])

if __name__ == "__main__":
    main()
