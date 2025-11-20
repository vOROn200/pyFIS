# LAWO MONO Example

This repository ships a self-contained demonstration ( `examples/lawo_mono.py` ) that renders text and transmits it to a LAWO MONO LED sign. The script can either talk to real hardware over a serial MONO bus or stay in "dry-run" mode and simply print the frames it would send.

## Dependencies

| Type | Package | Purpose |
| --- | --- | --- |
| Standard library | `argparse` , `pathlib` | CLI parsing and filesystem handling |
| Third-party | `Pillow` ( `PIL` ) | Rendering fallback glyphs, compositing bitmaps |
| Third-party | `pyserial` ( `serial` ) | Serial transport for `SerialMONOMaster` |
| Third-party | `crccheck` | Required by `LawoFont` when parsing LAWO font files |
| Project modules | `pyfis.lawo.LawoFont` | Decodes LAWO `.F??` font binaries |
| Project modules | `pyfis.lawo.SerialMONOMaster` | Serial MONO master implementation |
| Project modules | `pyfis.lawo.mono_protocol.MONOProtocol` | Core MONO frame logic |

Install the Python dependencies (once per virtual environment):

```bash
python -m pip install pillow pyserial crccheck
```

## Running the demo

The script needs to know the physical pixel size of your LED panel because the bitmap is clipped/padded to that rectangle. All arguments are documented via `-h` , but the most common flows are shown below.

### 1. Dry-run / development

Renders text, saves the bitmap so you can inspect the output, and only prints MONO frames (no hardware access).

```bash
PYTHONPATH=. python examples/lawo_mono.py "HELLO" \
  --width 26 --height 48 \
  --dry-run --debug \
  --save-image hello.png
```

### 2. Actual hardware

Replace the serial port, address, and dimensions with values that match your LED sign. When you supply a LAWO font file ( `--font-file path/to/F16` ), the glyphs will come directly from that binary instead of Pillow's default font.

```bash
python examples/lawo_mono.py "NEXT STOP" \
  --width 160 --height 16 \
  --font-file /path/to/F16 \
  --port /dev/ttyUSB0 --baudrate 19200 --address 0x1
```

Add `--save-image` if you want a PNG snapshot of the rendered bitmap that was transmitted. Use `--debug` to dump every prepared MONO frame when troubleshooting the protocol.

## Protocol Implementation Analysis

The implementation in `lawo/mono_protocol.py` has been compared with the protocol description found in [this article](https://mx-srv-001.de/bus/index.htm).

### Matches

*   **Serial Configuration:** Both use 19200 baud, 8 data bits, no parity, 1 stop bit (8N1).
*   **Frame Structure:** The frame format `Start(7E) - Cmd|Addr - Data - Checksum - Stop(7E)` is identical.
*   **Command Byte:** The construction of the command byte (High Nibble: Command, Low Nibble: Address) is implemented exactly as described.
*   **Escaping:** The byte stuffing mechanism (`7E` -> `7D 5E`,  `7D` -> `7D 5D`) is implemented correctly in `escape_frame`.
*   **Checksum (Flip-Dot):** The checksum algorithm (XOR all bytes, initialized with `0xFF`) matches the article's "FlipDot" checksum description.
*   **Pixel Encoding (Flip-Dot):** The 2-bit per pixel encoding (`10` = OFF,  `11` = ON) matches the article's description. The code initializes bytes with `0xAA` (all `10`) and ORs with `0x01` shifted (making it `11`) for active pixels.

### Differences

*   **Initialization Sequence (Command 9):**
    -   **Article:** Uses `00 07 00 00 00 02` as payload.
    -   **Code:** Uses `00 10 00 50 00 02 2E` in `display_image_flipdot`.
    -   **Analysis:** The article's payload `00 07` (Start 0, End 7) corresponds to an 8-pixel height (or an 8-pixel chunk). The code's payload `00 10` (Start 0, End 16) suggests it is configured for a 16-pixel height (assuming 0-based inclusive indexing where 0x10 is the 17th row, or 1-based where it is the 16th). The code also sends the entire column data in one go, whereas the article splits it into 8-pixel chunks. This implies the code is designed for a **newer or more capable controller** that supports larger single-command updates (e.g., full 16-pixel columns) and uses a slightly extended configuration command (7 bytes vs 6 bytes).
*   **Flip-Dot Data Payload (Command A):**
    -   **Article:** Payload consists of `[Column Address] + [Pixel Data]`.
    -   **Code:** Appends an extra `0x00` byte after the pixel data: `[Column Address] + [Pixel Data] + [0x00]`. This might be a padding byte required by specific controllers supported by this library.
*   **LED Support:**
    -   The code includes commands for LED displays (`CMD_PRE_BITMAP_LED_1` 0xB0, `CMD_PRE_BITMAP_LED_2` 0xC0, etc.) which are not covered in the article (which focuses on Flip-Dot displays).
