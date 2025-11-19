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
python examples/lawo_mono.py "HELLO" \
  --width 128 --height 16 \
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
