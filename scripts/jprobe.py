#!/usr/bin/env python3
"""jprobe.py — talk to a running MCU through J-Link without stopping it any longer than necessary.

Five things an agent needs on a board:
  * read typed symbols from the ELF (integers, counters, flags)
  * watch counters over time and get the *delta*, not the absolute value
  * write a value (poke a command word, reset a counter)
  * flash a new build
  * dump the display layer to PNG (visual evidence, no camera, no human)

Design notes
------------
* Symbols are resolved from the ELF with `arm-none-eabi-nm`, so the probe always talks about the
  build that is actually flashed. If the ELF and the flashed image disagree, values are garbage —
  keep them in sync and re-run.
* J-Link Commander writes need the core halted (`h` before `w4`/`w2`/`w1`, `g` after). Reads and
  `savebin` do not.
* The LTDC layer dump reads the live registers, so it follows whatever address/format the firmware
  programmed (double buffering, palette, RGB565, ...) instead of assuming one.

Usage
-----
    python jprobe.py --elf build/firmware.elf status s_frame_no s_tear_cnt --seconds 1
    python jprobe.py --elf build/firmware.elf read s_page s_state 0xE0001004
    python jprobe.py --elf build/firmware.elf watch s_flush_cnt --seconds 5
    python jprobe.py --elf build/firmware.elf write s_cmd=3 s_arg=1
    python jprobe.py --elf build/firmware.elf flash build/firmware.hex
    python jprobe.py --elf build/firmware.elf shot out/now.png
    python jprobe.py --elf build/firmware.elf raw "mem32 0x50001044 1"

Every command takes `--jlink`, `--device` and `--nm` so it works on a machine other than the one it
was written on.
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import subprocess
import sys
import tempfile

DEFAULT_JLINK = r"C:\Program Files\SEGGER\JLink\JLink.exe"
DEFAULT_DEVICE = "STM32H743VI"

# LTDC (STM32). Layer register block: L1 = 0x50001084, L2 = 0x50001104.
LTDC_BASE = 0x50001000
LTDC_LAYER = {1: LTDC_BASE + 0x84, 2: LTDC_BASE + 0x104}
LTDC_REG = {"CR": 0x00, "WHPCR": 0x04, "WVPCR": 0x08, "PFCR": 0x10,
            "CFBAR": 0x28, "CFBLR": 0x2C, "CFBLNR": 0x30}
# PFCR[2:0] -> bytes per pixel + decoder name
PIXEL_FORMATS = {
    0: (4, "argb8888"),
    1: (3, "rgb888"),
    2: (2, "rgb565"),
    3: (2, "argb1555"),
    4: (2, "argb4444"),
    5: (1, "l8"),
    6: (1, "al44"),
    7: (1, "al88"),
}


# --------------------------------------------------------------------------- jlink
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


def run_commander(jlink: str, device: str, commands: list[str]) -> str:
    """Write a J-Link Commander script, run it, return combined output."""
    script = "\n".join(["si 1", "speed 4000"] + commands + ["q"])
    fd, path = tempfile.mkstemp(suffix=".jlink", text=True)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(script)
        proc = subprocess.run(
            [jlink, "-device", device, "-if", "SWD", "-speed", "4000",
             "-autoconnect", "1", "-NoGui", "1", "-CommandFile", path],
            capture_output=True, text=True, errors="replace", timeout=300,
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    out = (proc.stdout or "") + (proc.stderr or "")
    if "Cannot connect" in out or "Could not connect" in out:
        sys.exit("cannot connect to the target: check USB, power and SWD wiring")
    return out


def read_words(out: str) -> list[int]:
    """`mem32` lines look like `2000ABCD = 0000000F`; keep them in output order."""
    return [int(m.group(2), 16)
            for m in re.finditer(r"^\s*([0-9A-Fa-f]{8}) = ([0-9A-Fa-f]{8})\s*$", out, re.M)]


# --------------------------------------------------------------------------- symbols
def load_symbols(elf: str, nm: str) -> dict[str, int]:
    try:
        out = subprocess.run([nm, "-n", elf], capture_output=True, text=True, timeout=120).stdout
    except FileNotFoundError:
        sys.exit(f"{nm} not found: pass --nm <path to arm-none-eabi-nm>")
    syms: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            try:
                syms[parts[2]] = int(parts[0], 16)
            except ValueError:
                pass
    return syms


def resolve(items: list[str], syms: dict[str, int]) -> list[tuple[str, int]]:
    """Accept symbols, comma-separated symbols, or 0x addresses."""
    out: list[tuple[str, int]] = []
    for token in [t for item in items for t in item.split(",") if t.strip()]:
        token = token.strip()
        if token.lower().startswith("0x"):
            out.append((token, int(token, 16)))
        elif token in syms:
            out.append((token, syms[token]))
        else:
            sys.exit(f"unknown symbol {token!r} — is --elf the build that is flashed?")
    return out


def word_at(jlink: str, device: str, addr: int) -> int:
    vals = read_words(run_commander(jlink, device, ["connect", f"mem32 0x{addr:08X} 1"]))
    if not vals:
        sys.exit(f"read failed at 0x{addr:08X}")
    return vals[0]


# --------------------------------------------------------------------------- commands
def cmd_read(a, syms) -> None:
    pairs = resolve(a.items, syms)
    got = run_commander(a.jlink, a.device, ["connect"] + [f"mem32 0x{addr:08X} 1" for _, addr in pairs])
    vals = read_words(got)
    if len(vals) < len(pairs):
        print(got)
        sys.exit("incomplete read")
    print(f"{'symbol / address':<28}{'hex':>12}{'dec':>14}")
    for (name, _), val in zip(pairs, vals):
        print(f"{name:<28}0x{val:08X}{val:>14}")


def cmd_status(a, syms) -> None:
    pairs = resolve(a.items, syms) if a.items else []
    cmds = [f"mem32 0x{addr:08X} 1" for _, addr in pairs] + ["sleep %d" % (a.seconds * 1000)]
    cmds += [f"mem32 0x{addr:08X} 1" for _, addr in pairs]
    got = run_commander(a.jlink, a.device, ["connect"] + cmds)
    vals = read_words(got)
    if len(vals) < len(pairs) * 2:
        print(got)
        sys.exit("incomplete read")
    first = vals[: len(pairs)]
    second = vals[len(pairs): len(pairs) * 2]
    print(f"== status over {a.seconds}s ==")
    for (name, _), v0, v1 in zip(pairs, first, second):
        d = (v1 - v0) & 0xFFFFFFFF
        signed = d - (1 << 32) if d >= (1 << 31) else d
        print(f"  {name:<24} {v1:>12}   delta {signed:+d}"
              + (f"   ({signed / a.seconds:.1f}/s)" if a.seconds else ""))


def cmd_watch(a, syms) -> None:
    pairs = resolve(a.items, syms)
    n = max(2, a.samples)
    gap_ms = max(1, int(a.seconds * 1000 / (n - 1)))
    cmds: list[str] = []
    for _ in range(n):
        cmds += [f"mem32 0x{addr:08X} 1" for _, addr in pairs]
        cmds.append(f"sleep {gap_ms}")
    got = run_commander(a.jlink, a.device, ["connect"] + cmds)
    vals = read_words(got)
    if len(vals) < n * len(pairs):
        print(got)
        sys.exit("incomplete sampling")
    print(f"  {n} samples every {gap_ms / 1000:.2f}s")
    for j, (name, _) in enumerate(pairs):
        col = [vals[i * len(pairs) + j] for i in range(n)]
        print(f"  {name:<24} {col[0]:>12} -> {col[-1]:>12}   delta {col[-1] - col[0]:+d}"
              + ("   (not moving)" if col[-1] == col[0] and len(col) > 1 else ""))


def cmd_write(a, syms) -> None:
    pairs: list[tuple[int, int]] = []
    for item in a.assign:
        if "=" not in item:
            sys.exit("expected SYMBOL=VALUE")
        key, val = item.split("=", 1)
        key, val = key.strip(), val.strip()
        addr = int(key, 16) if key.lower().startswith("0x") else resolve([key], syms)[0][1]
        pairs.append((addr, int(val, 0)))
    cmds = [f"W4 0x{addr:08X}, 0x{val:08X}" for addr, val in pairs]
    got = run_commander(a.jlink, a.device, ["connect", "h"] + cmds + ["g"])
    for addr, val in pairs:
        print(f"  wrote 0x{addr:08X} = 0x{val:08X}")
    if "ERROR" in got.upper() or "Fail" in got:
        print(got)


def cmd_flash(a, syms) -> None:
    hexfile = os.path.abspath(a.hex)
    if not os.path.exists(hexfile):
        sys.exit(f"not found: {hexfile}")
    got = run_commander(a.jlink, a.device, [f'loadfile "{hexfile}"', "r", "g"])
    if "O.K." not in got:
        print(got[-2000:])
        sys.exit("flash failed")
    print(f"flashed {hexfile}")


def cmd_raw(a, syms) -> None:
    cmds = ["connect"]
    if a.halt:
        cmds.append("h")
    cmds += a.commands
    if a.halt:
        cmds.append("g")
    print(run_commander(a.jlink, a.device, cmds))


def cmd_shot(a, syms) -> None:
    """Read the live LTDC layer registers, dump that memory, decode to PNG."""
    from PIL import Image

    base = LTDC_LAYER[a.layer]
    regs = [LTDC_REG["WHPCR"], LTDC_REG["WVPCR"], LTDC_REG["PFCR"],
            LTDC_REG["CFBAR"], LTDC_REG["CFBLR"], LTDC_REG["CFBLNR"]]
    got = run_commander(a.jlink, a.device,
                        ["connect"] + [f"mem32 0x{base + off:08X} 1" for off in regs])
    vals = read_words(got)
    if len(vals) < len(regs):
        print(got)
        sys.exit("cannot read LTDC layer registers")
    whpcr, wvpcr, pfcr, cfbar, cfblr, cfblnr = vals
    x0 = whpcr & 0x0FFF
    x1 = (whpcr >> 16) & 0x0FFF
    y0 = wvpcr & 0x07FF
    y1 = (wvpcr >> 16) & 0x07FF
    win_w = max(1, x1 - x0 + 1)
    win_h = max(1, y1 - y0 + 1)
    bpp, fmt = PIXEL_FORMATS.get(pfcr & 0x7, (1, "l8"))
    pitch = (cfblr >> 16) & 0x1FFF or win_w * bpp
    # The buffer (pitch x CFBLNR) is what the CPU draws; the window can be a few pixels smaller
    # because of an off-by-one in the LTDC config -- capture the buffer unless told otherwise.
    stride_w = pitch // bpp if bpp and pitch % bpp == 0 else win_w
    width = stride_w if 1 <= stride_w <= 4096 else win_w
    height = cfblnr if 1 <= cfblnr <= 4096 else win_h
    if a.window:
        width, height, pitch = win_w, win_h, win_w * bpp
    if a.format != "auto":
        fmt = a.format
        bpp = {"l8": 1, "rgb565": 2, "rgb888": 3, "argb8888": 4,
               "argb1555": 2, "argb4444": 2, "al44": 1, "al88": 1}[fmt]
        pitch = width * bpp
    if a.width:
        width = a.width
    if a.height:
        height = a.height
    need = pitch * height

    binpath = os.path.abspath(a.raw)
    os.makedirs(os.path.dirname(binpath) or ".", exist_ok=True)
    run_commander(a.jlink, a.device, [f'savebin "{binpath}", 0x{cfbar:08X}, {need}'])
    raw = open(binpath, "rb").read()

    img = Image.new("RGB", (width, height), (0, 0, 0))
    px = img.load()
    lut = _load_palette(a.palette) if fmt in ("l8", "al44", "al88") else None
    for y in range(height):
        row = y * pitch
        for x in range(width):
            off = row + x * bpp
            if off + bpp > len(raw):
                break
            if fmt == "l8":
                idx = raw[off]
                px[x, y] = lut[idx] if lut else _rgb332(idx)
            elif fmt == "rgb565":
                v = raw[off] | (raw[off + 1] << 8)
                px[x, y] = (((v >> 11) & 0x1F) * 255 // 31,
                            ((v >> 5) & 0x3F) * 255 // 63,
                            (v & 0x1F) * 255 // 31)
            elif fmt == "rgb888":
                b, g, r = raw[off], raw[off + 1], raw[off + 2]
                px[x, y] = (r, g, b)
            elif fmt == "argb8888":
                b, g, r = raw[off], raw[off + 1], raw[off + 2]
                px[x, y] = (r, g, b)
            else:
                px[x, y] = (0, 0, 0)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    img.save(a.out)
    print(f"layer{a.layer} CFBAR=0x{cfbar:08X} pitch={pitch} {width}x{height} fmt={fmt} -> {a.out}")


def _rgb332(i: int) -> tuple[int, int, int]:
    """LVGL's 8-bit colour is RGB332 (RRRGGGBB); most L8 panels use the same split.
    If a board uses a different 256-entry CLUT, pass --palette."""
    return (((i >> 5) & 7) * 255 // 7, ((i >> 2) & 7) * 255 // 7, (i & 3) * 255 // 3)


def _load_palette(path: str | None) -> list[tuple[int, int, int]] | None:
    """Optional palette file: one `RRGGBB` per line (usually 256 lines). None = RGB332."""
    if not path:
        return None
    cols: list[tuple[int, int, int]] = []
    for line in open(path, encoding="utf-8"):
        line = line.strip().lstrip("#")
        if len(line) >= 6 and all(c in "0123456789abcdefABCDEF" for c in line[:6]):
            cols.append((int(line[0:2], 16), int(line[2:4], 16), int(line[4:6], 16)))
    if not cols:
        sys.exit(f"palette {path}: expected RRGGBB per line")
    return cols


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="J-Link probe for MCU firmware")
    ap.add_argument("--elf", default="build/firmware.elf", help="ELF matching the flashed build")
    ap.add_argument("--device", default=DEFAULT_DEVICE)
    ap.add_argument("--jlink", default=None)
    ap.add_argument("--nm", default="arm-none-eabi-nm")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("read", help="read symbols or addresses")
    p.add_argument("items", nargs="*", default=[])

    p = sub.add_parser("status", help="read twice and print the delta (counters, fps)")
    p.add_argument("items", nargs="*", default=[])
    p.add_argument("--seconds", type=float, default=1.0)

    p = sub.add_parser("watch", help="sample several times")
    p.add_argument("items", nargs="+")
    p.add_argument("--seconds", type=float, default=5.0)
    p.add_argument("--samples", type=int, default=6)

    p = sub.add_parser("write", help="write 32-bit values (SYMBOL=VALUE)")
    p.add_argument("assign", nargs="+")

    p = sub.add_parser("flash", help="flash a .hex/.bin and reset")
    p.add_argument("hex")

    p = sub.add_parser("shot", help="dump the LTDC layer to PNG")
    p.add_argument("out")
    p.add_argument("--raw", default="out/_fb_raw.bin")
    p.add_argument("--layer", type=int, choices=(1, 2), default=1)
    p.add_argument("--window", action="store_true",
                   help="capture only the LTDC window instead of the whole layer buffer")
    p.add_argument("--format", default="auto",
                   choices=("auto", "l8", "rgb565", "rgb888", "argb8888",
                            "argb1555", "argb4444", "al44", "al88"))
    p.add_argument("--width", type=int, default=0)
    p.add_argument("--height", type=int, default=0)
    p.add_argument("--palette", default=None, help="256-line RRGGBB palette for L8/AL44/AL88")

    p = sub.add_parser("raw", help="run raw J-Link Commander commands")
    p.add_argument("commands", nargs="+")
    p.add_argument("--halt", action="store_true")

    a = ap.parse_args()
    a.jlink = find_jlink(a.jlink)
    syms = load_symbols(a.elf, a.nm) if a.cmd != "flash" else {}
    {"read": cmd_read, "status": cmd_status, "watch": cmd_watch, "write": cmd_write,
     "flash": cmd_flash, "shot": cmd_shot, "raw": cmd_raw}[a.cmd](a, syms)


if __name__ == "__main__":
    main()
