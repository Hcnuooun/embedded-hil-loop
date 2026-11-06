---
name: embedded-hil-loop
description: Use when developing or debugging MCU firmware and hardware UIs on a real board — flashing and verifying builds, probing live variables, injecting synthetic touch input, capturing the framebuffer, or diagnosing a display that tears, freezes, or shows a stale page. Turns a physical board into a fast, evidence-first loop that does not need a human to tap or watch the screen.
---

# Embedded hardware-in-the-loop development

Firmware is only true on the board. The expensive failure mode is an agent that reads code, writes
plausible code, and asks the human to flash it and describe what happened. This skill replaces that
with three capabilities — **probe, inject, capture** — and a discipline of measuring one thing at a
time.

Worked case: STM32H7 + LTDC panel + LVGL single-framebuffer UI. The loop transfers to any target
with a debug probe (J-Link, OpenOCD) and any display whose memory you can read.

## Operating rules

1. **Read the live state before you explain anything.** A handover, a README, and last session's
   screenshot are hypotheses. `status`/`read` and a fresh capture are facts.
2. **Every claim gets evidence.** "It works now" means a symbol value, a counter delta, or a
   screenshot — not "the code looks right".
3. **Change one thing per iteration.** If two edits land together and the symptom changes, you have
   learned nothing. Keep an A/B build when the cause is unclear.
4. **Never make the human be the input device or the camera.** Inject the tap, dump the frame.
   Save the human for power, wiring, probes, and decisions.
5. **Hardware actions are the human's call** unless they asked you to run them: flashing, reset,
   power, re-wiring, erasing. Say exactly what you will do before doing it.
6. **Write down what became true.** Context dies; a handover with "current truth / stale claims /
   next step" is what makes the next session fast. Templates in `assets/`.

## The loop

Commands below run **from the firmware project root**; resolve `scripts/...` against this skill's
directory (the loader reports it as the resource base) and `<elf>` against the project.

### 0. Recover context
Read the newest handover and the project `AGENTS.md`; check `git status` (an uncommitted tree is
normal in these projects and is not a broken workspace). Note which build directory is production
(`build/`) and which is experimental (`build-exp/`).

### 1. Prove the board runs the build you think it does
```bash
python scripts/jprobe.py --elf build/firmware.elf status s_frame_no s_tear_cnt --seconds 1
python scripts/jprobe.py --elf build/firmware.elf shot out/now.png
```
If `s_frame_no` is not advancing, the firmware is hung or not the one you think. If the image is
black, the panel/backlight/CLUT is the first suspect, not your UI code. If symbols are "unknown",
the ELF and the flashed image disagree — fix that before any measurement.

### 2. Reproduce deterministically
Turn the human action into a script: synthetic touch for UI, a command word written over the probe
for state changes, a scripted sequence of taps. Capture before/after.
```bash
python scripts/synth_touch.py --elf build/firmware.elf tap 200 418
python scripts/jprobe.py --elf build/firmware.elf shot out/after.png
```
A bug you cannot trigger twice is not yet a bug you can fix.

### 3. Localize with counters, not with reading code harder
Add a counter/flag for each hypothesis, read it, and remove the ones that did not pay. Reading a
counter delta over one second is usually faster than adding a printf and reflashing. See
`references/probe-recipes.md` for symbol reads, struct field offsets, and timing validity.

### 4. Fix the smallest thing that explains the evidence
Then re-run the *same* reproduction. A fix that changes the reproduction is a new bug.

### 5. Measure the delta and sweep the neighbours
Numbers worth recording: frame rate, tear counter delta, worst-case draw time, and the states you
touched (other page, settings page, boot, idle). Regressions hide in the path you did not exercise.

### 6. Record it
Update the handover: what is true now, what in the old document is stale, what is left. Put the raw
numbers in a short report next to it. The next agent should not have to rediscover the loop.

## The three tools

| Tool | What it does | Why it pays |
|---|---|---|
| `scripts/jprobe.py` | read/watch/write symbols, flash, dump the display layer to PNG | no printf, no rebuild, no camera |
| `scripts/synth_touch.py` | drive the touch cache over the probe | UI tests without a human |
| `scripts/validate_skill.py` | pre-publish checks for this kind of skill package | avoids silent catalog rejection |

Both hardware tools take `--elf` (must match the flashed build), `--device`, `--jlink`, `--nm`.
They never hard-code a project path; symbol names come from the ELF.

## Symptom → first probe

| Symptom | Probe first | Usual cause |
|---|---|---|
| UI frozen, frame counter advancing | `read` the page/state variables; `shot` | scheduler gated a draw and never let it through |
| Only part of the screen changed | `shot`; read a "full redraw requested" flag | hidden widgets are skipped, but their old pixels are not erased |
| Page switch shows the old page's panel | check the invalidation *area*, not the page variable | dirty boxes joined into one box that no longer fits the safe window |
| A waveform/label stopped updating | read the paint frame counter and the cost estimate | estimate > achievable window ⇒ starvation loop; needs a per-frame failsafe |
| Tearing only under load | read the tear counter before/after, one change at a time | drawing outside the scan-out window, or a debug label feeding back into the dirty area |
| Touch does nothing | read the input cache; check the driver's "device present" flag | driver never produced a pressed state, or a modal page ate the release |
| Display black but code runs | check layer enable, framebuffer address, pitch, CLUT | LTDC reads an address the CPU wrote to a different memory |
| Numbers look absurd | verify the timebase first | cycle counter not running, wrapped, or measured across a halt |

## Display scan-out budget (the one piece of math to internalise)

On a continuously scanned panel, a write is safe only while the beam is *not* inside the area you
are writing. For a panel with `H_total` lines and line time `t_line`:

```
safe_window(y) = (H_total - y) + (box_top - margin)     # only valid once y > box_bottom + margin
window_ms      = safe_window * t_line
budget_needed  = dirty_rows * k + c                     # k, c measured, not guessed
```

Rules that came out of real bugs:

* Consider **both** windows: the beam already passed the box (`(H_total - y) + (box_top - margin)`)
  and the beam has not reached it yet (`(box_top - margin) - y`). Take the larger one. Budgeting only
  the "already passed" side starves a box pinned to the bottom edge: its after-window is ten lines
  per frame while its before-window is hundreds.
* Compute the maximum achievable window at a *legal* start, never at `y = box_bottom + 1`; the
  few-line difference is enough to deadlock a draw forever.
* Overestimating the budget is not "safe": it shrinks the legal start window until nothing qualifies.
  Calibrate `k`/`c` from measured draws, then keep ~25 % headroom.
* Failsafes must count **frames**, not loop iterations, and must count whenever the area is dirty —
  never behind the same condition that is currently failing. A tight `App_Loop` runs every few
  microseconds, so "8 iterations" is a fraction of a millisecond and forces a draw on the beam.
* Full-page changes: split into bands (60–120 rows), invalidate one band at a time, and advance only
  after the previous band was actually drawn. Suppress other invalidation sources during the wipe,
  or they merge with a band into a box that no longer fits.

Full worked numbers, banding code shape, and the failure signatures:
`references/scanout-budget.md`.

## Pitfalls that cost the most

* **A hidden widget is not a repainted widget.** Toggling `HIDDEN` leaves old pixels until something
  draws over them. Correctness comes from repainting the area, not from the flag.
* **Invalidation areas merge.** Two unrelated dirty rectangles become one bounding box. Budget for
  the union, and keep periodic text updates from colliding with a big repaint.
* **Self-referential debug output.** A label that shows fps/tear count updates itself, grows the
  dirty area, causes a tear, which changes the label again. Show those numbers without letting them
  drive the layout.
* **A screenshot taken too early is a lie.** Wait for the state to settle (a page wipe can take
  100–300 ms), and check the state variable as well as the pixels.
* **Timing across a halt is not timing.** Verify the cycle counter advances before trusting any
  microsecond number; read counters twice and divide by the real elapsed time.
* **Never leave the board in a state the user cannot use.** Synthetic input disables physical touch
  until reset; the experimental build may lack production behaviour. Restore and say so.

More, with the exact symptom each one produced: `references/pitfalls.md`.

## Schematic and PCB work

If the task is schematic/layout rather than firmware, use the EDA tool's own skill (e.g. the
EasyEDA API skill) for the API and file format, and apply the same working agreement: read the
current design first, propose, get one authorisation per change, then verify with the design's own
checkers (net tracing, DRC, overlap) and save a snapshot. The protocol is shared; the EDA API is not
part of this skill.

## Definition of done

- [ ] the reproduction passes, captured with `jprobe.py shot` (before and after)
- [ ] the counter that proved the bug is back to its healthy delta (fps, tear, latency)
- [ ] boot, idle, the other page/mode, and the settings path were exercised
- [ ] production build flashed (not the experimental one), and physical input works
- [ ] handover updated: current truth, stale claims, next step; numbers in a report
- [ ] any special case or hard-coded assumption is called out explicitly

## References

| File | Contents |
|---|---|
| `references/protocol.md` | working agreement with the human: read-first, evidence, authorisation, handover |
| `references/probe-recipes.md` | J-Link recipes, symbol/struct offsets, command words, timing validity |
| `references/ui-harness.md` | synthetic touch, framebuffer capture, PC preview harness, UI regression checks |
| `references/scanout-budget.md` | tearing math, banded wipes, worked numbers and failure signatures |
| `references/pitfalls.md` | the full catalogue: symptom, cause, fix |
| `assets/AGENTS.template.md` | project instruction file skeleton |
| `assets/handover.template.md` | handover skeleton (current truth / stale / next) |
