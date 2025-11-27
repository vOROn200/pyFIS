import sys
import csv
from PIL import Image


def parse_frames_to_image(input_filename, output_filename):
    # Configuration based on analysis
    # The protocol addresses 36 logical rows (18 odd + 18 even).
    # The dump contains 5 groups of 5 bytes = 25 bytes * 8 bits = 200 pixels width.
    # The user mentioned 216 width, but the data only supports 200.
    # We will create a canvas of 216 width to be safe, leaving the right side empty.

    IMG_WIDTH = 216
    IMG_HEIGHT = 36  # Protocol supports 36 lines (0x24 down to 0x01)
    DATA_WIDTH = 200  # Actual data found in frames

    # Initialize a blank image (black background)
    img = Image.new("1", (IMG_WIDTH, IMG_HEIGHT), 0)
    pixels = img.load()

    # Mapping logic for protocol commands
    # Odd Rows: 0x24 (36) -> Row 0, 0x23 -> Row 2, ..., 0x13 -> Row 34
    # Even Rows: 0x12 (18) -> Row 1, 0x11 -> Row 3, ..., 0x01 -> Row 35

    try:
        with open(input_filename, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: Could not find {input_filename}")
        return

    print(f"Processing {len(lines)} lines...")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Parse hex strings into integers
        try:
            parts = [int(x, 16) for x in line.split(",")]
        except ValueError:
            continue

        # Valid drawing frames start with 0x7E (Start), 0xA1 (Header)
        # Check basic length and header
        if len(parts) < 3 or parts[0] != 0x7E or parts[1] != 0xA1:
            continue

        # Structure based on analysis:
        # [0]=7E, [1]=A1, [2]=CMD, [3]=SEP, [4..8]=DATA, [9]=SEP, ...
        # Total groups of 5 bytes separated by 0x90 or 0x10.

        cmd = parts[2]

        # Determine Y coordinate (Physical Row)
        y = -1
        if 0x13 <= cmd <= 0x24:
            # Odd rows (0, 2, 4...)
            # 0x24 -> 0, 0x23 -> 2
            index = 0x24 - cmd
            y = index * 2
        elif 0x01 <= cmd <= 0x12:
            # Even rows (1, 3, 5...)
            # 0x12 -> 1, 0x11 -> 3
            index = 0x12 - cmd
            y = index * 2 + 1

        if y == -1:
            continue  # Unknown command

        # Extract Data Bytes
        # Data is in blocks of 5 bytes, separated by a control byte (0x90 or 0x10)
        # Indices in 'parts':
        # Header: 0, 1, 2
        # Block 1: Sep at 3, Data at 4,5,6,7,8
        # Block 2: Sep at 9, Data at 10..14
        # Block 3: Sep at 15, Data at 16..20
        # Block 4: Sep at 21, Data at 22..26
        # Block 5: Sep at 27, Data at 28..32

        data_bytes = []
        # Define start indices for data blocks (skipping the separator)
        block_starts = [4, 10, 16, 22, 28]

        for start in block_starts:
            if start + 5 <= len(parts):
                data_bytes.extend(parts[start : start + 5])

        # Draw pixels
        # Analysis of User's "Testpattern":
        # 0x01 (Binary ...001) in the first byte is the Leftmost pixel.
        # This implies LSB (Least Significant Bit) is the Leftmost pixel in the byte.
        # Data stream goes Left -> Right.

        current_x = 0
        for byte in data_bytes:
            for bit in range(8):
                if current_x >= IMG_WIDTH:
                    break

                # Check bit at position 'bit' (0 is LSB)
                is_on = (byte >> bit) & 1

                if is_on:
                    pixels[current_x, y] = 1

                current_x += 1

    # Save the result
    # We crop the height to 32 as requested (ignoring the bottom 4 logical rows if unused)
    # or keep 36 if the pattern dictates. Based on "32x216", we crop.
    final_img = img.crop((0, 0, IMG_WIDTH, 32))
    final_img.save(output_filename)
    print(f"Successfully generated {output_filename}")


if __name__ == "__main__":
    parse_frames_to_image("frames.txt", "result.png")
