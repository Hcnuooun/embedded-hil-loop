# Probe recipes (J-Link, and the OpenOCD equivalents)

Everything here is deliberately tool-level: a text script for J-Link Commander, symbol names from
the flashed ELF, and no assumption about the project. `scripts/jprobe.py` wraps the common cases.

## 1. The basics

J-Link Commander runs a command file (`-CommandFile x.jlink`), one command per line:

```
si 1                 # SWD
speed 4000           # kHz
connect              # attach (may halt depending on device/settings)
h                    # halt the core
mem32 0x24000058 1   # read one 32-bit word at an address
w4 0x24000000, 0x1   # write 32-bit (needs the core halted)
savebin "out.bin", 0x24004000, 384000
loadfile "build/firmware.hex"
r                    # reset
g                    # go
q                    # quit (closes the probe session)
```

Failure modes worth recognising:

| Output | Meaning |
|---|---|
| `CPU is not halted` on a write | `h` was missing; the write is skipped *silently* |
| `Could not connect` / `Cannot connect` | power, SWD wiring, or another probe session holding the device |
| reads return `00000000` for everything | device not running / wrong device / wrong address |
| symbols "unknown" in your wrapper | the ELF does not match the flashed image |

## 2. Symbols and the ELF

Resolve symbol addresses with the toolchain's `nm`, from the **same ELF that was flashed**:

```bash
arm-none-eabi-nm -n build/firmware.elf | grep -E ' (s_page|s_frame_no|g_state)$'
```

`-n` sorts by address, which makes dumps of adjacent variables readable. Static variables are in
the table (`d`/`b`), so `static uint32_t s_frame_no;` is readable without exporting it.

Reading useful shapes:

```bash
# a counter: value now vs 1 s later -> frame rate
python scripts/jprobe.py --elf build/firmware.elf status s_frame_no --seconds 1

# a flag/state variable (read the 32-bit window that contains it, take the low byte)
python scripts/jprobe.py --elf build/firmware.elf read s_page
```

For a `uint8_t` the 32-bit read also shows the following bytes. Read the low byte for the value and
remember the neighbours when you interpret the rest.

## 3. Struct fields without exporting them

To read one field of a struct (for example `g_exp.cmd`), get its byte offset from DWARF instead of
guessing:

```bash
arm-none-eabi-gdb -batch build/firmware.elf -ex 'ptype /o exp_t'
```

Then `address = symbol address + offset`. The same trick gives `sizeof` for memory-budget questions.
Keep the offset in the script or config, and re-derive it when the struct changes — a stale offset
reads plausible garbage, which is worse than a crash.

## 4. Command words (scripting the firmware)

The most useful debug feature you can add to firmware: a small struct the PC writes and the firmware
polls.

```c
typedef struct {
  volatile uint32_t cmd, arg0, arg1, arg2, arg3;  /* PC -> firmware */
  volatile uint32_t ack;                          /* firmware -> PC: incremented per command */
} host_cmd_t;
host_cmd_t g_cmd;
```

* firmware, once per main-loop iteration: `if (g_cmd.cmd) { dispatch(g_cmd.cmd); g_cmd.ack++; g_cmd.cmd = 0; }`
* PC: write `arg*`, then `cmd` last; wait for `ack` to change; read results.
* keep the struct outside the normal `.bss` if RAM is tight (a dedicated linker section is fine).

This turns "please press the button" into a one-line script call, and it survives a reflash.

## 5. Timing that you can trust

Cortex-M cycle counter: `DEMCR.TRCENA` (0xE000EDFC bit 24) → `DWT_CTRL.CYCCNTENA`
(0xE0001000 bit 0) → `DWT_CYCCNT` (0xE0001004).

* It is 32 bits and wraps every `2^32 / f_cpu` seconds (8.94 s at 480 MHz). Deltas are fine; absolute
  values are meaningless.
* **Verify it advances before trusting any measurement.** Arm it, sleep a known interval in the
  probe script, read it: a 1 s delta must be ≈ f_cpu. If every delta is 0 or absurd, the measurement
  path is broken — fix that first, do not interpret the numbers.
* A halted core does not count. Never compare readings taken across different halt/resume patterns,
  and do not measure scan-out/tearing while stopping the core in the same second.
* For long intervals prefer a timer/SysTick counter over cycle counting.

## 6. Sampling counters

`status` (two reads, one delta) answers "is it moving and how fast". `watch` (N samples) answers
"does it move in steps or freeze". For a rate, always divide by the *measured* wall time, not the
requested sleep — probe scripts run slower than the sleep they ask for.

## 7. Flashing and proving what is flashed

```bash
python scripts/jprobe.py --elf build/firmware.elf flash build/firmware.hex
```

After flashing, prove the image: read a symbol that only exists in the new build, or a version
constant you increment per build. "It should be the new firmware" is how two hours disappear.

## 8. Memory and peripheral dumps

* `savebin` reads a contiguous region to a file — good for framebuffers, ring buffers, trace arrays.
* `mem32 <addr> <count>` prints `count` words — good for register blocks; parse the `ADDR = VALUE`
  lines in order (the same address can appear twice).
* LTDC layer registers (STM32): layer base `0x50001084` (L1) / `0x50001104` (L2); `CFBAR` +0x28,
  `CFBLR` +0x2C (pitch in bits 31:16), `PFCR` +0x10 (format in bits 2:0), `WHPCR`/`WVPCR` +0x04/+0x08.
  Reading these means the capture follows whatever the firmware programmed.

## 9. OpenOCD equivalents

| J-Link Commander | OpenOCD |
|---|---|
| `mem32 0xADDR 1` | `mdw 0xADDR 1` |
| `w4 0xADDR, 0xVAL` | `mww 0xADDR 0xVAL` |
| `savebin "f", 0xADDR, N` | `dump_image f 0xADDR N` |
| `loadfile x.hex` | `program x.elf verify reset exit` |
| `h` / `g` | `halt` / `resume` |

Symbols come from the same ELF either way; the recipes in this file are transport-independent.
