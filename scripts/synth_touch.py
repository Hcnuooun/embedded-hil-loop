#!/usr/bin/env python3
"""synth_touch.py — make the firmware think a finger touched the screen, through the debug probe.

Why this exists
---------------
On a board with a touch panel, every UI test normally costs a human tap plus a human look.
That is slow, unrepeatable and blocks the agent from iterating. Almost every touch driver feeds
LVGL from a small cache (`pressed`, `x`, `y`) that the input-device read callback returns.
If you can write those variables, you can "tap" from a script — and pair it with a framebuffer
dump to see the result.

Three steps are needed, in this order:

1. **Stop the physical driver from overwriting the cache.** Find the condition that short-circuits
   the polling function (this project: `if (s_addr8 == 0) return;` in `Touch_Poll`) and write the
   variable so polling returns immediately. Any equivalent "driver disabled / no device" flag works.
2. **Write the cache.** pressed=1, x/y in screen pixels.
3. **Release** by writing pressed=0. Hold long enough for at least one LVGL read period (5–20 ms;
   120 ms is safe and still feels like a tap).

Pitfalls
--------
* The pressed variable is usually `uint8_t` and coordinates `uint16_t` — writing 4 bytes clobbers
  the neighbours. This tool defaults to those widths; use `--size` when the cache differs.
* LVGL only emits CLICKED on release, and only if the pointer stayed on the object. A "tap" needs
  press → (>= 1 read period) → release, not a single write.
* Modal pages: if the callback calls `lv_indev_wait_release()`, keep the press until after the new
  page is up, otherwise the release can hit the widget underneath.
* After using this on a real board, physical touch stays dead until reset (that is the point of
  step 1). Say so when you hand the board back.

Usage
-----
    python synth_touch.py --elf build/firmware.elf tap 200 418
    python synth_touch.py --elf build/firmware.elf tap 600 418 --hold 200
    python synth_touch.py --elf build/firmware.elf press 600 228
    python synth_touch.py --elf build/firmware.elf move  450 228
    python synth_touch.py --elf build/firmware.elf release
    python synth_touch.py --elf build/firmware.elf --map "pressed=g_tp_pressed,x=g_tp_x,y=g_tp_y,disable=" --dry-run tap 10 10
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time

DEFAULT_JLINK = r"C:\Program Files\SEGGER\JLink\JLink.exe"
DEFAULT_DEVICE = "STM32H743VI"
DEFAULT_MAP = "pressed=s_cpressed,x=s_cx,y=s_cy,disable=s_addr8"
DEFAULT_SIZE = {"pressed": 1, "disable": 1, "x": 2, "y": 2}


def find_jlink(path: str | None) -> str:
    if path:
        return path
    env = os.environ.get("JLINK") or os.environ.get("JLINK_PATH")
    if env:
        return env
    if os.path.exists(DEFAULT_JLINK):
        return DEFAULT_JLINK
    from shutil import which
    got = which("JLink.exe") or which("JLink") or which("JLinkExe")
    if not got:
        sys.exit("JLink not found: pass --jlink <path> or set JLINK")
    return got


def load_symbols(elf: str, nm: str) -> dict[str, int]:
    try:
        out = subprocess.run([nm, "-n", elf], capture_output=True, text=True, timeout=120).stdout
    except FileNotFoundError:
        sys.exit(f"{nm} not found: pass --nm <path>")
    syms: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            try:
                syms[parts[2]] = int(parts[0], 16)
            except ValueError:
                pass
    return syms


def run_commander(jlink: str, device: str, commands: list[str]) -> str:
    script = "\n".join(["si 1", "speed 4000", "connect", "h"] + commands + ["g", "q"])
    fd, path = tempfile.mkstemp(suffix=".jlink", text=True)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(script)
        proc = subprocess.run(
            [jlink, "-device", device, "-if", "SWD", "-speed", "4000",
             "-autoconnect", "1", "-NoGui", "1", "-CommandFile", path],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    out = (proc.stdout or "") + (proc.stderr or "")
    if "Cannot connect" in out or "Could not connect" in out:
        sys.exit("cannot connect to the target")
    if "ERROR" in out.upper() or "Fail" in out:
        print(out)
    return out


class Touch:
    def __init__(self, elf: str, jlink: str, device: str, mapping: str,
                 sizes: dict[str, int], nm: str, dry_run: bool):
        self.syms = load_symbols(elf, nm)
        self.jlink, self.device, self.dry_run = jlink, device, dry_run
        self.map: dict[str, int] = {}
        self.size: dict[str, int] = {}
        for item in mapping.split(","):
            item = item.strip()
            if not item:
                continue
            key, _, sym = item.partition("=")
            key, sym = key.strip(), sym.strip()
            if not sym:
                continue
            if sym not in self.syms:
                sys.exit(f"{key}: symbol {sym!r} not in the ELF — did you pass the flashed build?")
            self.map[key] = self.syms[sym]
            self.size[key] = sizes.get(key, DEFAULT_SIZE.get(key, 1))
        for need in ("pressed", "x", "y"):
            if need not in self.map:
                sys.exit(f"--map must define {need}=SYMBOL")

    def _w(self, key: str, value: int) -> str:
        width = self.size[key]
        cmd = {1: "w1", 2: "w2", 4: "w4"}[width]
        return f"{cmd} 0x{self.map[key]:08X}, 0x{value & ((1 << (8 * width)) - 1):0{2 * width}X}"

    def _exec(self, cmds: list[str], what: str) -> None:
        if self.dry_run:
            print(f"[dry-run] {what}: " + " | ".join(cmds))
            return
        run_commander(self.jlink, self.device, cmds)

    def press(self, x: int, y: int) -> None:
        cmds = []
        if "disable" in self.map:
            cmds.append(self._w("disable", 0))
        cmds += [self._w("x", x), self._w("y", y), self._w("pressed", 1)]
        self._exec(cmds, f"press ({x},{y})")

    def move(self, x: int, y: int) -> None:
        self._exec([self._w("x", x), self._w("y", y)], f"move ({x},{y})")

    def release(self) -> None:
        self._exec([self._w("pressed", 0)], "release")

    def tap(self, x: int, y: int, hold_ms: int) -> None:
        self.press(x, y)
        time.sleep(hold_ms / 1000.0)
        self.release()


def main() -> None:
    ap = argparse.ArgumentParser(description="synthetic touch input over J-Link")
    ap.add_argument("--elf", default="build/firmware.elf")
    ap.add_argument("--device", default=DEFAULT_DEVICE)
    ap.add_argument("--jlink", default=None)
    ap.add_argument("--nm", default="arm-none-eabi-nm")
    ap.add_argument("--map", default=DEFAULT_MAP,
                    help="cache symbols: pressed=,x=,y=,disable= (empty disables the step)")
    ap.add_argument("--size", action="append", default=[],
                    help="override width, e.g. --size x=4 (defaults: pressed/disable 1, x/y 2)")
    ap.add_argument("--dry-run", action="store_true", help="print the writes, touch nothing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tap"); p.add_argument("x", type=int); p.add_argument("y", type=int)
    p.add_argument("--hold", type=int, default=120)
    p = sub.add_parser("press"); p.add_argument("x", type=int); p.add_argument("y", type=int)
    p = sub.add_parser("move"); p.add_argument("x", type=int); p.add_argument("y", type=int)
    sub.add_parser("release")
    a = ap.parse_args()

    sizes = dict(DEFAULT_SIZE)
    for item in a.size:
        k, _, v = item.partition("=")
        sizes[k.strip()] = int(v)

    t = Touch(os.path.abspath(a.elf), find_jlink(a.jlink), a.device, a.map, sizes, a.nm, a.dry_run)
    if a.cmd == "tap":
        t.tap(a.x, a.y, a.hold)
        print(f"tap ({a.x},{a.y}) hold {a.hold} ms")
    elif a.cmd == "press":
        t.press(a.x, a.y)
        print(f"press ({a.x},{a.y})")
    elif a.cmd == "move":
        t.move(a.x, a.y)
        print(f"move ({a.x},{a.y})")
    else:
        t.release()
        print("release")


if __name__ == "__main__":
    main()
