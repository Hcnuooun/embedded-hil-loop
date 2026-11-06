# embedded-hil-loop

A skill for AI agents (and the humans supervising them) that turns a physical MCU board into a fast,
repeatable development loop — **without asking a human to tap the screen, describe what they see, or
flash a build by hand**.

It packages three capabilities and the discipline that makes them trustworthy:

| | |
|---|---|
| **Probe** | read/write live symbols, watch counters, flash and verify — no `printf`, no rebuild |
| **Inject** | drive the touch input cache over the debug probe, so UI tests become scripts |
| **Capture** | dump the display layer's memory to PNG, so "it looks right" becomes evidence |
| plus | a scan-out budget method for single-framebuffer displays, and a catalogue of the bugs that cost the most |

The worked case is an STM32H743 + 800×480 LTDC panel + LVGL UI: single framebuffer, no DMA2D, no
double buffering. Every number in the references was measured on that board. The loop transfers to
any target with a debug probe; the capture/decode paths are STM32-LTDC specific and the method is
not.

## Why this exists

An agent that cannot see the board is reduced to reading code and guessing. The usual workaround —
"flash this, tap that, tell me what happens" — costs a human round-trip per hypothesis and produces
evidence you cannot diff, replay, or archive.

This skill is the result of debugging exactly that way being too slow. A real example from its
history: a page switch looked correct in the plot area but left the previous page's side panel in
place. Reading `s_page` said the switch had happened; the screenshot said otherwise; a counter showed
the redraw gate had deadlocked on a two-line budget error. That entire diagnosis took minutes because
the screen could be tapped and captured by script.

## What is in the box

```
embedded-hil-loop/
├── SKILL.md                       # what the agent loads (workflow, rules, symptom table)
├── README.md / README.zh.md       # this file
├── PUBLISH.md                     # pre-publish checklist
├── CHANGELOG.md
├── references/
│   ├── protocol.md                # working agreement: read-first, evidence, authorisation, handover
│   ├── probe-recipes.md           # J-Link recipes, struct offsets, command words, timing validity
│   ├── ui-harness.md              # synthetic touch, framebuffer capture, PC preview, assertions
│   ├── scanout-budget.md          # tearing math, banded wipes, worked numbers, deadlock case study
│   └── pitfalls.md                # 15 bugs: symptom → cause → fix → how to catch it next time
├── scripts/
│   ├── jprobe.py                  # read/watch/write/flash/shot over J-Link
│   ├── synth_touch.py             # tap/press/move/release through the input cache
│   └── validate_skill.py          # pre-publish checks for skill packages
└── assets/
    ├── AGENTS.template.md         # project instruction skeleton
    └── handover.template.md       # handover skeleton (current truth / stale / next)
```

## Install

A filesystem skill is a directory containing `SKILL.md` at the top level of a scanned root.

```bash
# user-wide (available to every project)
cp -r embedded-hil-loop ~/.dsh/skills/

# or per project (committed with the repo)
mkdir -p .dsh/skills && cp -r embedded-hil-loop .dsh/skills/
```

Windows (PowerShell):

```powershell
Copy-Item -Recurse embedded-hil-loop "$HOME\.dsh\skills\"
```

The catalog picks it up without a restart (the provider watches the skill roots). Confirm it appears
as `embedded-hil-loop` before relying on it.

## Requirements

* Python 3.10+ (the scripts use `X | None` type hints).
* Pillow — only for `jprobe.py shot`.
* SEGGER J-Link software (`JLink.exe` / `JLinkExe`). The scripts look at `--jlink`, then `$JLINK`,
  then the default install path, then `PATH`.
* `arm-none-eabi-nm` from the Arm GNU toolchain, or pass `--nm`.
* A board you are allowed to flash and reset.

`shot` is written for the STM32 LTDC. For another display controller, change the register map and
the pixel-format decoding in one place (`cmd_shot`); the rest of the workflow is unchanged.

## Quickstart

Set `SKILL` to this directory and run from the firmware project root:

```bash
# 1. is the board alive, and is it the build I think?
python "$SKILL/scripts/jprobe.py" --elf build/firmware.elf status s_frame_no --seconds 1

# 2. what does the screen look like right now?
python "$SKILL/scripts/jprobe.py" --elf build/firmware.elf shot out/before.png

# 3. do the thing without a human
python "$SKILL/scripts/synth_touch.py" --elf build/firmware.elf tap 200 418
sleep 0.5

# 4. prove it
python "$SKILL/scripts/jprobe.py" --elf build/firmware.elf shot out/after.png
```

Expected output shape:

```
== status over 1.0s ==
  s_frame_no                      29227   delta +64   (64.0/s)
layer1 CFBAR=0x24004000 pitch=800 800x480 fmt=l8 -> out/after.png
tap (200,418) hold 120 ms
```

If `delta` is 0, the firmware is hung or you are talking to a different build — stop and fix that
before interpreting anything else.

## What "good" looks like

* a UI change is verified by two screenshots and a counter delta, not by reading the diff twice;
* a page transition is proven by a capture taken after the transition settles, plus a tear-counter
  delta over a known interval;
* the handover records the numbers, so the next session does not re-derive them;
* the board is left flashed with the production build and physical input working.

## Design notes worth knowing before you edit it

* **Symbols from the ELF, never hard-coded addresses.** Static variables are in the symbol table;
  `arm-none-eabi-nm -n` gives you addresses in order. If the ELF and the flashed image disagree, the
  values are plausible garbage — this is called out in the pitfalls.
* **Writes need a halt.** J-Link silently skips `w4` when the core is running. `jprobe.py` halts,
  writes, and resumes.
* **Capture follows the live registers.** `CFBAR`, pitch, format and line count are read from the
  layer, so double buffering or a palette change does not produce a picture of the wrong buffer.
* **L8 decodes as RGB332 by default**, because that is LVGL's 8-bit colour and the common panel
  layout. Pass `--palette` for a custom CLUT.
* **Synthetic touch needs a disable symbol.** Writing the input cache is not enough if the real
  driver keeps overwriting it; the tool writes the driver's "device absent" flag first. After use,
  physical touch is dead until reset — reset the board before handing it back.

## Status

Used on a real STM32H743 + LVGL product build for: page transitions, slider drags, modal pages,
single-shot capture, tear-rate measurement and a display-pipeline deadlock. The scripts in this
package are the generalized versions of the project-local tools; both were run against hardware
before this package was written.

## License

MIT — see [LICENSE](LICENSE). The copyright line is `2026 16654`; replace it with the name or handle
you publish under (one line, same year).

## Provenance

Distilled from an AI-assisted embedded project (STM32H743VIT6, LTDC L8 panel, LVGL 8.3) where the
whole loop was: handover → probe → reproduce → instrument → fix → capture → record. The references
keep the measured numbers so the advice stays falsifiable.
