#!/usr/bin/env python3
"""Test raw flipdot commands for 26x48 panel."""

import serial
import time

def checksum_flipdot(data):
    """Calculate flipdot checksum: 0xFF - XOR of all bytes."""
    xorval = 0
    for b in data:
        xorval ^= b
    return 0xFF - xorval

def send_row(ser, address, row_num, pixels_26):
    """
    Send a row to flipdot display.
    
    pixels_26: list of 26 pixel values (0 or 1)
    """
    # Convert 26 pixels to flipdot format (4 pixels per byte)
    # Flipdot format: bit 7=enable, bit 6=color, bits 5-4=next pixel, etc.
    row_data = []
    
    for i in range(0, 26, 4):
        byte = 0
        for j in range(4):
            if i + j < 26:
                if pixels_26[i + j]:
                    # Enable (1) + Yellow (1) = 0b11 = 0x3
                    byte |= 0x03 << (6 - j*2)
                else:
                    # Enable (1) + Black (0) = 0b10 = 0x2
                    byte |= 0x02 << (6 - j*2)
            else:
                # Skip pixel: 0b00
                byte |= 0x00 << (6 - j*2)
        row_data.append(byte)
    
    # Build command
    cmd_byte = 0xA0 | (address & 0x0F)
    payload = [cmd_byte, row_num] + row_data + [0x00]
    chk = checksum_flipdot(payload)
    payload.append(chk)
    
    frame = bytes([0x7E] + payload + [0x7E])
    
    print(f"Row {row_num}: {' '.join(f'{b:02X}' for b in frame)}")
    ser.write(frame)
    time.sleep(0.02)

def main():
    port = "COM3"
    address = 0x5
    
    ser = serial.Serial(port, 19200, timeout=1)
    
    print("Sending test pattern to flipdot 26x48 display...")
    
    # Test: Draw horizontal lines at rows 0, 10, 20, 30, 40
    test_rows = [0, 10, 20, 30, 40]
    
    for row in range(48):
        if row in test_rows:
            # All pixels ON
            pixels = [1] * 26
        else:
            # All pixels OFF
            pixels = [0] * 26
        
        send_row(ser, address, row, pixels)
    
    print("Done!")
    ser.close()

if __name__ == "__main__":
    main()
