#!/usr/bin/env python3
"""Keep native macOS True Tone while the MacBook lid is open, and apply
an approximate frozen correction to external displays only while it is closed.

The built-in display is not modified. The sensor is sampled while the lid
is open; on lid close, the last RGB correction is applied to external displays.
On lid reopen, only this program's gamma adjustment is removed, letting
macOS handle native True Tone normally again.

Requires als_hid.py and als_decode.py from:
    https://github.com/8rulerstar/macbook-als-spectral

Requires no other dependencies, requires Python 3.8 or above

    python3 truetone_freeze.py --dry-run
    python3 truetone_freeze.py
    python3 truetone_freeze.py --strength 1.4
    python3 truetone_freeze.py --reset  # reset ColorSync for ALL displays

Keep macOS True Tone enabled if you use it normally: this program
does not change gamma tables while the lid is open. The closed-lid correction
is an approximation and cannot reproduce the exact True Tone color, it does 
get close enough to where differences are nearly imperceptible
"""

from __future__ import annotations

import argparse
import ctypes as C
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

CG_ID = C.c_uint32
CG_FLOAT = C.c_float
STATE_FILE = Path.home() / ".local" / "state" / "truetone-freeze" / "last.json"

ALS_DIR = (
    Path(__file__).resolve().parent
    / "macbook-als-spectral"
)


def clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def cct_xy(kelvin: float) -> tuple[float, float]:
    """Approximate Planckian white-point chromaticity (CIE 1931 xy)."""
    t = clamp(kelvin, 2500.0, 12000.0)
    if t <= 4000:
        x = -0.2661239e9 / t**3 - 0.2343580e6 / t**2 + 0.8776956e3 / t + 0.179910
    else:
        x = -3.0258469e9 / t**3 + 2.1070379e6 / t**2 + 0.2226347e3 / t + 0.240390
    if t <= 4000:
        if t <= 2222:
            y = -1.1063814 * x**3 - 1.34811020 * x**2 + 2.18555832 * x - 0.20219683
        else:
            y = -0.9549476 * x**3 - 1.37418593 * x**2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x**3 - 5.8733867 * x**2 + 3.75112997 * x - 0.37001483
    return x, y


def white_rgb(kelvin: float) -> tuple[float, float, float]:
    """D65-relative linear sRGB values for a chromaticity at luminance Y=1.

    This is a generic approximation, not an EDID-calibrated monitor transform.
    """
    x, y = cct_xy(kelvin)
    X, Y, Z = x / y, 1.0, (1.0 - x - y) / y
    return (
        3.2406 * X - 1.5372 * Y - 0.4986 * Z,
        -0.9689 * X + 1.8758 * Y + 0.0415 * Z,
        0.0557 * X - 0.2040 * Y + 1.0570 * Z,
    )


def calculate_gains(lux: float, ambient_k: float, strength: float) -> tuple[tuple[float, float, float], float]:
    """Partial white-point adaptation in mired space; RGB <=1, no clipping."""
    # Sensor chromaticity estimates are unreliable in near-darkness.
    if not (math.isfinite(lux) and math.isfinite(ambient_k)):
        raise ValueError("non-finite sensor reading")
    if lux < 4.0 or not (2500 <= ambient_k <= 12000):
        raise ValueError("unusable ambient reading")

    # Maximum adaptation increases with light level. This is intentionally gentle.
    fraction = clamp((0.10 + 0.35 * clamp(lux / 800.0, 0.0, 1.0)) * strength, 0.0, 0.90)
    native_k = 6500.0
    target_mired = (1.0 - fraction) * (1e6 / native_k) + fraction * (1e6 / ambient_k)
    target_k = 1e6 / target_mired
    neutral = white_rgb(native_k)
    target = white_rgb(target_k)
    relative = tuple(max(0.05, n / d) for n, d in zip(target, neutral))
    peak = max(relative)
    return tuple(clamp(v / peak, 0.0, 1.0) for v in relative), target_k


def load_gains() -> tuple[float, float, float]:
    try:
        obj = json.loads(STATE_FILE.read_text())
        gains = tuple(float(v) for v in obj["gains"])
        if len(gains) == 3 and all(math.isfinite(v) and 0.05 <= v <= 1.0 for v in gains):
            return gains  # type: ignore[return-value]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return (1.0, 1.0, 1.0)


def save_gains(gains: tuple[float, float, float]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps({"gains": gains, "saved_at": time.time()}, indent=2) + "\n")
    os.replace(temp, STATE_FILE)


def lid_closed() -> bool | None:
    """IOPMrootDomain AppleClamshellState: True=lid closed; None=unknown."""
    try:
        out = subprocess.run(
            ["/usr/sbin/ioreg", "-r", "-n", "IOPMrootDomain", "-d", "1"],
            check=False, capture_output=True, text=True, timeout=3,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r'"AppleClamshellState"\s*=\s*(Yes|No|True|False|0|1)\b', out, re.I)
    if not match:
        return None
    return match.group(1).lower() in ("yes", "true", "1")


class CoreGraphics:
    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("Only macOS is supported")
        cg = C.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGGetActiveDisplayList.argtypes = [C.c_uint32, C.POINTER(CG_ID), C.POINTER(C.c_uint32)]
        cg.CGGetActiveDisplayList.restype = C.c_int32
        cg.CGDisplayIsBuiltin.argtypes = [CG_ID]
        cg.CGDisplayIsBuiltin.restype = C.c_uint32
        cg.CGDisplayGammaTableCapacity.argtypes = [CG_ID]
        cg.CGDisplayGammaTableCapacity.restype = C.c_uint32
        cg.CGGetDisplayTransferByTable.argtypes = [
            CG_ID, C.c_uint32, C.POINTER(CG_FLOAT), C.POINTER(CG_FLOAT),
            C.POINTER(CG_FLOAT), C.POINTER(C.c_uint32),
        ]
        cg.CGGetDisplayTransferByTable.restype = C.c_int32
        cg.CGSetDisplayTransferByTable.argtypes = [
            CG_ID, C.c_uint32, C.POINTER(CG_FLOAT), C.POINTER(CG_FLOAT), C.POINTER(CG_FLOAT),
        ]
        cg.CGSetDisplayTransferByTable.restype = C.c_int32
        cg.CGDisplayRestoreColorSyncSettings.argtypes = []
        cg.CGDisplayRestoreColorSyncSettings.restype = None
        self.cg = cg

    def external_ids(self) -> list[int]:
        count = C.c_uint32()
        if self.cg.CGGetActiveDisplayList(0, None, C.byref(count)):
            raise RuntimeError("Could not enumerate displays")
        if not count.value:
            return []
        ids = (CG_ID * count.value)()
        if self.cg.CGGetActiveDisplayList(count.value, ids, C.byref(count)):
            raise RuntimeError("Could not enumerate displays")
        return [int(i) for i in ids[:count.value] if not self.cg.CGDisplayIsBuiltin(i)]

    def read(self, display_id: int) -> tuple[list[float], list[float], list[float]]:
        capacity = self.cg.CGDisplayGammaTableCapacity(display_id)
        if not 2 <= capacity <= 65536:
            raise RuntimeError(f"Display {display_id}: invalid LUT capacity {capacity}")
        arrs = [(CG_FLOAT * capacity)() for _ in range(3)]
        count = C.c_uint32()
        err = self.cg.CGGetDisplayTransferByTable(display_id, capacity, *arrs, C.byref(count))
        if err or not 2 <= count.value <= capacity:
            raise RuntimeError(f"Display {display_id}: gamma read failed (error={err}, samples={count.value})")
        return tuple([float(v) for v in arr[: count.value]] for arr in arrs)  # type: ignore[return-value]

    def write(self, display_id: int, table: tuple[list[float], list[float], list[float]]) -> None:
        n = len(table[0])
        if not (n >= 2 and all(len(c) == n for c in table)):
            raise RuntimeError("Malformed gamma table")
        arrs = [(CG_FLOAT * n)(*channel) for channel in table]
        err = self.cg.CGSetDisplayTransferByTable(display_id, n, *arrs)
        if err:
            raise RuntimeError(f"Display {display_id}: gamma write failed (CGError {err})")

    def reset(self) -> None:
        self.cg.CGDisplayRestoreColorSyncSettings()


GammaTable = tuple[list[float], list[float], list[float]]


def tables_match(a: GammaTable, b: GammaTable, tol: float = 1e-4) -> bool:
    return all(
        len(ca) == len(cb) and all(abs(x - y) <= tol for x, y in zip(ca, cb))
        for ca, cb in zip(a, b)
    )


def tinted_table(base: GammaTable, gains: tuple[float, float, float]) -> GammaTable:
    return tuple([clamp(v * gain, 0.0, 1.0) for v in channel] for channel, gain in zip(base, gains))  # type: ignore[return-value]


@dataclass
class DisplayState:
    baseline: GammaTable
    last_written: GammaTable | None = None


class DisplayController:
    def __init__(self, cg: CoreGraphics, display_filter: int | None) -> None:
        self.cg = cg
        self.filter = display_filter
        self.states: dict[int, DisplayState] = {}
        self.absent_logged = False

    def update(self, gains: tuple[float, float, float]) -> None:
        ids = self.cg.external_ids()
        if self.filter is not None:
            ids = [d for d in ids if d == self.filter]
        if not ids and not self.absent_logged:
            print("No selected external display active; retaining frozen gains.", flush=True)
            self.absent_logged = True
        if ids:
            self.absent_logged = False
        for did in ids:
            try:
                current = self.cg.read(did)
                state = self.states.get(did)
                if state is None:
                    # After a display ID changes, macOS might retain the gamma table.
                    # Re-use the old baseline only if the *entire* current table
                    # matches a ramp written by this process (prevents compounding).
                    baseline = current
                    inherited_ramp = None
                    for prior in self.states.values():
                        if prior.last_written is not None and tables_match(current, prior.last_written):
                            baseline = prior.baseline
                            inherited_ramp = prior.last_written
                            break
                    state = DisplayState(baseline, inherited_ramp)
                    self.states[did] = state
                    print(f"External display {did}: {len(baseline[0])} gamma samples", flush=True)
                elif state.last_written is not None and not tables_match(current, state.last_written):
                    # macOS restored/replaced our ramp (common after clamshell
                    # transitions). Use the new ramp as the baseline unless it's
                    # exactly our original baseline.
                    if not tables_match(current, state.baseline):
                        state.baseline = current
                        print(f"Display {did}: system changed gamma baseline", flush=True)
                    state.last_written = None
                target = tinted_table(state.baseline, gains)
                if not tables_match(current, target):
                    self.cg.write(did, target)
                    state.last_written = target
            except RuntimeError as exc:
                print(f"Warning: {exc}; will retry", file=sys.stderr, flush=True)

    def restore(self) -> None:
        """Remove only ramps written by us (never force-reset other displays).

        A clamshell transition can change a monitor's CoreGraphics display ID.
        In that case, recognize our previously-written ramp by its contents.
        If macOS/another app has replaced the ramp, leave it alone.
        """
        if not any(s.last_written is not None for s in self.states.values()):
            return
        try:
            ids = self.cg.external_ids()
        except RuntimeError as exc:
            print(f"Warning: cannot enumerate displays for restore: {exc}", file=sys.stderr)
            return
        if self.filter is not None:
            ids = [d for d in ids if d == self.filter]

        for did in ids:
            try:
                current = self.cg.read(did)
                state = self.states.get(did)
                owner = state if state is not None and state.last_written is not None and tables_match(current, state.last_written) else None
                if owner is None:
                    for prior in self.states.values():
                        if prior.last_written is not None and tables_match(current, prior.last_written):
                            owner = prior
                            break
                if owner is not None:
                    self.cg.write(did, owner.baseline)
                    print(f"External display {did}: restored native gamma (lid open)", flush=True)
                    # Associate this display ID with the original baseline so
                    # a later lid-close won't capture our tint as its baseline.
                    self.states[did] = DisplayState(owner.baseline)
                    owner.last_written = None
                elif state is not None and state.last_written is not None:
                    # macOS has already reset/replaced our ramp; don't overwrite it.
                    state.baseline = current
                    state.last_written = None
            except RuntimeError as exc:
                print(f"Warning: couldn't restore {did}: {exc}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strength", type=float, default=0.80, help="adaptation strength, 0..2 (default 0.80)")
    ap.add_argument("--interval", type=float, default=5.0, help="update interval seconds (default 5.0)")
    ap.add_argument("--display-id", type=int, help="restrict adjustments to a particular external display ID")
    ap.add_argument("--dry-run", action="store_true", help="calculate and print gains without changing displays")
    ap.add_argument("--reset", action="store_true", help="restore system ColorSync gamma settings for ALL displays and quit")
    args = ap.parse_args()
    if not 0 <= args.strength <= 2:
        ap.error("--strength must be between 0 and 2")
    if not 0.2 <= args.interval <= 10:
        ap.error("--interval must be between 0.2 and 10")

    if args.reset:
        print("Resetting ColorSync gamma tables for all displays...")
        CoreGraphics().reset()
        return
    if not ALS_DIR.is_dir():
        raise RuntimeError(f"ALS dependency directory not found: {ALS_DIR}")
    sys.path.insert(0, str(ALS_DIR))
    # The user has already tested this ALS reader with color_live.py.
    try:
        from als_decode import decode_fields
        from als_hid import open_als, pump, warn_if_unverified_model
    except ImportError as exc:
        raise RuntimeError(
            f"Could not import ALS modules from {ALS_DIR}"
        ) from exc

    warn_if_unverified_model()
    print("TrueTone Freeze (approximation, not Apple's exact white-point correction)")
    print("Leave native macOS True Tone ON; no gamma changes while lid is open.")
    print("Only external displays are tinted, and only with the lid CLOSED.")
    print("Ctrl-C stops the script and restores any gamma ramps we changed.")

    recent: list[tuple[float, float, float]] = []  # monotonic time, lux, CCT

    def handle_report(raw: bytes) -> None:
        fields = decode_fields(raw)
        if not fields:
            return
        lux, kelvin = float(fields["lux"]), float(fields["cct"])
        when = time.monotonic()
        if math.isfinite(lux) and math.isfinite(kelvin) and 4 <= lux < 50000 and 2500 <= kelvin <= 12000:
            recent.append((when, lux, kelvin))
            del recent[:-7]

    open_als(handle_report)
    cg = None if args.dry_run else CoreGraphics()
    controller = DisplayController(cg, args.display_id) if cg else None
    gains = load_gains()
    print(f"Starting gains: R={gains[0]:.3f} G={gains[1]:.3f} B={gains[2]:.3f}")
    last_lid: bool | None = None
    last_save = 0.0
    last_tick = time.monotonic()
    stop_requested = False

    def handle_sigint(signum, frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, handle_sigint)
    signal.signal(signal.SIGINT, handle_sigint)
    # SIGINT is left as KeyboardInterrupt so the CFRunLoop can be interrupted.

    try:
        while not stop_requested:
            # CFRunLoopRunInMode may return early when the ALS stops reporting
            # (particularly in clamshell mode). Keep the polling interval fixed.
            poll_start = time.monotonic()
            pump(args.interval)
            remaining = args.interval - (time.monotonic() - poll_start)
            if remaining > 0:
                time.sleep(remaining)
            now = time.monotonic()
            elapsed = max(0.0, now - last_tick)
            last_tick = now
            lid = lid_closed()
            if lid != last_lid:
                print("Lid: " + (
                    "CLOSED — applying last sensor correction to external display(s)"
                    if lid is True else
                    "OPEN — native True Tone only, removing our correction"
                    if lid is False else
                    "UNKNOWN — no tint applied; attempting restore"
                ), flush=True)
                if lid is True:
                    save_gains(gains)
                last_lid = lid

            # No updates if the lid is closed/unknown, or if sensor reports are
            # missing/stale. Keep the last valid correction instead.
            recent[:] = [s for s in recent if now - s[0] < 3.0]
            new_sensor = recent and (now - recent[-1][0] < 1.5)
            if lid is False and new_sensor:
                sorted_lux = sorted(s[1] for s in recent)
                sorted_k = sorted(s[2] for s in recent)
                mid = len(recent) // 2
                lux = sorted_lux[mid]
                kelvin = sorted_k[mid]
                try:
                    target, screen_k = calculate_gains(lux, kelvin, args.strength)
                except ValueError:
                    pass
                else:
                    # 4-second time constant for smooth transitions.
                    alpha = 1.0 - math.exp(-elapsed / 4.0)
                    gains = tuple(x + alpha * (y - x) for x, y in zip(gains, target))  # type: ignore[assignment]
                    if now - last_save > 3.0:
                        save_gains(gains)
                        last_save = now
                    print(f"{lux:6.1f} lx, room {kelvin:6.0f} K, target {screen_k:6.0f} K → "
                          f"R={gains[0]:.3f} G={gains[1]:.3f} B={gains[2]:.3f}", flush=True)
            if controller is not None:
                if lid is True:
                    # Keep reapplying while closed: macOS may reset the LUT
                    # or assign a new display ID during clamshell transitions.
                    controller.update(gains)
                else:
                    # Crucially, never write a tint while the lid is open.
                    # Restore only a tint previously written by this process.
                    controller.restore()
    finally:
        print("\nExiting...", flush=True)
        if controller is not None:
            controller.restore()
        print("Done. Saved gains retained for next launch.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
