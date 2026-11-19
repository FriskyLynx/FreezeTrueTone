# TrueTone Freeze

Keep the last ambient-light color adjustment on an external monitor when closing your MacBook lid.

While the lid is **open**, the script reads the MacBook's ambient-light sensor and leaves macOS True Tone untouched. When the lid is **closed**, it applies an approximate color correction to connected external displays using CoreGraphics gamma tables. Opening the lid again removes the script's correction.

> This approximates True Tone; it does not capture Apple's exact True Tone adjustment.

## Requirements

- macOS on a supported MacBook with an accessible ambient-light sensor
- Python 3.8+ (no pip packages required)
- [`als_hid.py` and `als_decode.py`](https://github.com/8rulerstar/macbook-als-spectral)

## Setup

1. Download or clone [macbook-als-spectral](https://github.com/8rulerstar/macbook-als-spectral).
2. Place `truetone_freeze.py` in that folder, alongside `als_hid.py` and `als_decode.py`.
3. Leave macOS True Tone enabled if you normally use it.

## Usage

Run from the folder containing the script:

```bash
python3 truetone_freeze.py
```

Preview sensor readings and calculated color adjustments without changing any display:

```bash
python3 truetone_freeze.py --dry-run
```

Adjust the effect's strength (default: `1.0`, range: `0`–`2`):

```bash
python3 truetone_freeze.py --strength 1.5
```

Press **Ctrl+C** to stop. The script attempts to restore the gamma tables it changed. If necessary, you can reset the system's ColorSync gamma settings for **all displays** with:

```bash
python3 truetone_freeze.py --reset
```

The last calculated adjustment is saved locally and reused on the next launch. Keep the script running while using your MacBook in clamshell mode.
