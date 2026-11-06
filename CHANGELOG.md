# Changelog

## 0.1.2 — 2026-11-06

### Fixed

- The scan-out window rule now covers **both** sides of the dirty box (beam already passed / beam has
  not arrived yet). Budgeting only the "after" side starves a box pinned to the bottom edge.
- The starvation failsafe must count whenever the area is dirty, not only after the beam passed —
  otherwise it shares the failing condition and never fires.
- Added pitfall #16 with the real failure signature (plot animating, text frozen, one bottom-edge
  dirty rect) and the probe reads that identify it.

## 0.1.1 — 2026-11-06

### Added

- `LICENSE` (MIT, copyright `2026 Hcnuooun`) and License sections in both READMEs.
- Ready-to-push git repository layout (`.gitignore` for caches and captures).

## 0.1.0 — 2026-11-06

First public shape, distilled from a working STM32H743 + LVGL + LTDC project.

### Added

- `SKILL.md`: operating rules, the six-step hardware loop, a symptom → first-probe table, the
  display scan-out budget in one page, the expensive pitfalls, a definition of done.
- `references/protocol.md`: read-first working agreement, evidence rules, one-change-per-iteration,
  no hidden special cases, handover discipline, when to stop and ask.
- `references/probe-recipes.md`: J-Link Commander recipes, symbol/struct reads, command words,
  cycle-counter validity, flashing and verifying the image, OpenOCD equivalents.
- `references/ui-harness.md`: three-layer test harness (PC preview, synthetic touch, framebuffer
  capture), assertions that make screenshots evidence, state-settling discipline.
- `references/scanout-budget.md`: the window formula, budget calibration from measured draws, the
  starvation deadlock case study, banded page wipes, dirty-rectangle merging, honest tear counting.
- `references/pitfalls.md`: 15 entries, each with symptom, cause, fix and how to catch it next time.
- `scripts/jprobe.py`: read/watch/write/flash/layer-capture over J-Link; symbols from the ELF.
- `scripts/synth_touch.py`: tap/press/move/release through the input cache, with a symbol map and a
  dry-run mode.
- `scripts/validate_skill.py`: pre-publish checks for skill packages.
- `assets/AGENTS.template.md`, `assets/handover.template.md`.

### Verified on hardware

- `jprobe.py status/shot` and `synth_touch.py tap` were run against a live board before this release;
  the capture follows the live LTDC registers and decodes L8/RGB332 by default.
