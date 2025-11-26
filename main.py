#!/usr/bin/env python3

import time
from lawo import SerialMONOMaster

DISPLAY_ADDRESS = int(0x05)
COMMAND_DELAY = 0.2


def main():

    bus = SerialMONOMaster(
        port="COM3",
        baudrate=19200,
        stopbits=1,
        debug=True,
    )

    bus.send_command(DISPLAY_ADDRESS, bus.CMD_QUERY, [])

    time.sleep(COMMAND_DELAY)

    bus.send_command(DISPLAY_ADDRESS, bus.CMD_PRE_BITMAP_FLIPDOT, [0x05, 0x01])

    time.sleep(COMMAND_DELAY)

    payload = [0x05]

    # fmt: off
    payload.extend([
        0x90, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0x90, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x90, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x90, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x90, 0x00, 0x00, 0x00, 0x00, 0x00,
    ])
    # fmt: on

    bus.send_command(DISPLAY_ADDRESS, bus.CMD_COLUMN_DATA_FLIPDOT, payload)

    time.sleep(COMMAND_DELAY)

    bus.send_command(DISPLAY_ADDRESS, bus.CMD_QUERY, [])


if __name__ == "__main__":
    main()
