# TrueTone Freeze

Keep the last ambient-light color adjustment on an external monitor when closing your MacBook lid.

While the lid is **open**, the script reads the MacBook's ambient-light sensor and leaves macOS True Tone untouched. When the lid is **closed**, it applies an approximate color correction to connected external displays using CoreGraphics gamma tables. Opening the lid again removes the script's correction.

> It's not 100% accurate, but close enough to be nearly unnoticable.

## Requirements

- macOS on a supported MacBook with an accessible ambient-light sensor (see [macbook-als-spectral](https://github.com/8rulerstar/macbook-als-spectral) for a list of supported devices, your device not being on the list does not necessarily mean it wont work
- Python 3.8+ (no pip packages required) 


## Setup

1. Download or clone this repository RECURSIVELY!
```bash
git clone --recurse-submodules https://github.com/Aurardian/FreezeTrueTone.git
```
2. Open a Terminal
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

Adjust the effect's strength (default: `0.85`, range: `0`–`2`):

```bash
python3 truetone_freeze.py --strength 1.5
```

Adjust how long the interval between each refresh is (default: `5.00`, range: `0.2`–`10`, in seconds):

```bash
python3 truetone_freeze.py --interval 4
```

Press **Ctrl+C** to stop. (The script will stop at the beginning of the next cycle, can take up to your selected interval) The script attempts to restore the gamma tables it changed. If necessary, you can reset the system's gamma settings for **all displays** with:

```bash
python3 truetone_freeze.py --reset
```

The last calculated adjustment is saved locally and reused on the next launch. Keep the script running while using your MacBook in clamshell mode.
