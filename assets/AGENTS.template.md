# Project instructions (template)

> Copy to the project root as `AGENTS.md`. Keep it factual and short: it is loaded into the agent's
> context on every task. Anything that changes weekly belongs in the handover, not here.
> Replace every `<...>`; delete sections that do not apply.

## 1. What this project is

- Board / product: `<name>`, `<PCB rev / module>`
- MCU: `<part>`, `<core>`, `<clock tree summary>`
- Display / input: `<panel, resolution, interface, touch controller>`
- Toolchain: `<arm-none-eabi-gcc / Keil / IAR>`, build system `<CMake+Ninja / Make>`
- Production build: `<build/>`; experiment build: `<build-exp/>` (never deliver the experiment one)

## 2. Commands

```bash
<build command>
<flash command>                 # probe type, port, device string
<probe status command>          # counters that prove the board is alive
<framebuffer capture command>
<PC preview command>
```

## 3. Debug probe

- Probe: `<J-Link / ST-Link / OpenOCD>`, target `<device string>`
- ELF that matches the flashed image: `<path>`
- Symbols worth watching: `<counter>, <state>, <page>, <error flags>`
- Read/write conventions: `<e.g. writes need halt; tool wrapper in tools/jprobe.py>`
- Never halt while `<measuring tearing / a watchdog is armed / the motor is spinning>`.

## 4. Architecture map

| Area | File(s) | Facts |
|---|---|---|
| init + main loop | `<...>` | `<what runs when, frame cadence>` |
| display / scan-out | `<...>` | `<single/double buffer, format, panel timing>` |
| UI | `<...>` | `<LVGL version, page model, direct-draw modules>` |
| hardware drivers | `<...>` | `<IRQ priorities, DMA, buffers>` |
| measurement / DSP | `<...>` | `<block sizes, rates, where they run>` |

## 5. Rules for changes

- One change per iteration; re-run the same reproduction.
- Do not bypass the scan-out window logic to "make it draw": fix the budget.
- Do not add a whitelist/special case to make a checker pass. If a temporary exception is
  unavoidable, mark it in code, in the delivery note, and here.
- Hardware actions (`flash`, `reset`, `erase`, power, wiring) need the user's go-ahead.
- After a change: capture before/after, read the counters, and update the handover.

## 6. Known traps (project-specific)

- `<trap 1: symptom -> cause -> where>`
- `<trap 2: ...>`

## 7. Current state

- Handover: `<docs/handover_YYYY-MM-DD.md>`
- Baseline numbers: `<fps, tear rate, flash/RAM usage>`
- Known limitations: `<...>`
