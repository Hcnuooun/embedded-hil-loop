# UI test harness: see and touch the screen without a human

The goal is a UI change you can verify in under a minute, repeatedly, with no hands on the board.
Three layers, cheapest first.

| Layer | Runs on | Catches | Misses |
|---|---|---|---|
| 1. PC preview | host | layout, text, colour, stale-pixel logic, page transitions | real timing, tearing, panel/CLUT, touch driver |
| 2. Synthetic touch | board | input handling, event order, modal pages | what the screen actually looks like |
| 3. Framebuffer capture | board | the real pixels, including tearing and stale regions | what a human perceives over time |

Use 1 while designing, 2 + 3 to prove it.

## Layer 1 — PC preview of the *same* UI sources

Compile `app_ui.c` / `app_plot.c` / the graphics layer for the host, link LVGL with a stub display
driver and a stub board layer, feed synthetic data, render the framebuffer to BMP/PNG.

Rules that keep it honest:

* **Same sources, no forks.** If the preview needs an `#ifdef` in the UI file, the preview has
  stopped testing the product.
* **Same pixel format.** Use the panel's real format (e.g. L8 + 256-colour CLUT), not RGB888, or
  colour/dithering bugs disappear in the preview.
* **Deterministic signals.** Generate noise/sine/spectrum in the stub, seeded, so two runs differ
  only by the code change.
* It cannot show tearing; do not claim it does.

Minimal shape:

```c
/* preview main: register a display whose flush is a no-op (direct mode writes the buffer) */
lv_disp_draw_buf_init(&buf, fb, NULL, W * H);
drv.direct_mode = 1; drv.flush_cb = flush_noop; lv_disp_drv_register(&drv);
UI_Init(); UI_SetPage(PAGE); pump(30);   /* run timers, then */ UI_Paint();
write_bmp("preview.bmp");                /* decode L8 through the CLUT */
```

`pump(n)` should tick time and run `lv_timer_handler()` (plus any "step the deferred-redraw state
machine" hook), otherwise deferred text/animations never appear in the capture.

## Layer 2 — synthetic touch over the probe

A touch driver almost always funnels into a small cache that the LVGL read callback returns:

```c
static uint8_t  s_pressed; static uint16_t s_x, s_y;   /* filled by the polling function */
static void read_cb(...) { data->state = s_pressed ? PRESSED : RELEASED;
                           data->point.x = s_x; data->point.y = s_y; }
```

To drive it:

1. Find the poll function's early-out (`if (!device_ok) return;`, `if (addr == 0) return;`).
2. Write that flag so polling stops overwriting the cache.
3. Write `pressed=1` and the coordinates; wait ≥ one read period; write `pressed=0`.

```bash
python scripts/synth_touch.py --elf build/firmware.elf tap 200 418
python scripts/synth_touch.py --elf build/firmware.elf press 600 228
python scripts/synth_touch.py --elf build/firmware.elf move  450 228
python scripts/synth_touch.py --elf build/firmware.elf release
```

Event semantics to respect:

* LVGL emits `CLICKED` on release, and only if the pointer stayed on the object; a single write is
  not a tap.
* Drag handlers want `PRESSED` → several `PRESSING` → `RELEASED`; move in more than one step.
* A modal page that appears under the finger needs `lv_indev_wait_release()` in its callback, or the
  release lands on the widget that was underneath.
* Some drivers report "new data, zero contacts" separately from "no new data". Conflating them makes
  the pressed state flicker at the report rate and produces repeated CLICKED events.

## Layer 3 — framebuffer capture

Read the layer's live registers, then the memory, then decode:

1. `WHPCR`/`WVPCR` → window size; `PFCR[2:0]` → format; `CFBLR[31:16]` → pitch; `CFBAR` → address.
2. `savebin` that many bytes.
3. Decode per format (L8 through the CLUT, RGB565, ARGB8888) and save a PNG.

```bash
python scripts/jprobe.py --elf build/firmware.elf shot out/after.png
python scripts/jprobe.py --elf build/firmware.elf shot out/after.png --palette panel.clut
```

Why live registers: the firmware may be double-buffering, showing a different layer, or using a
palette. Hard-coding one address gives you a picture of the wrong buffer — which looks like a UI bug.

## Making captures assertable

A screenshot is evidence only if you can say what it proves. Cheap assertions:

* **Colour census.** Count pixels of a known palette index in a region: "after the page switch the
  plot area contains 0 pixels of the old trace colour". Catches stale pixels that a human eye
  forgives.
* **Region hash.** Crop the panel/table area, hash it before/after, and require a change for a
  state change (and no change for a no-op tap).
* **Anchor pixels.** Sample a few coordinates that must be a specific colour in each state
  (tab highlight, title, trigger line).
* **Before/after diff.** Save both captures; a diff image localises what the change actually touched.

Keep the expected numbers next to the test, not in your head.

## Test sequences worth keeping as a script

| Scenario | Sequence | Assert |
|---|---|---|
| page switch | tap tab A, wait 300 ms, tap tab B, wait | panel region changed; tab highlight colour; no old-page colour left |
| settings open/close | tap gear, tap BACK | card region appears then disappears; underlying page repainted |
| value drag | press, 5×move, release | value text changed; no other region changed |
| single-shot | tap SINGLE | state label changes; frame content freezes |
| no-op tap | tap the current tab | nothing changes (and nothing flickers) |
| idle | 10 s, no input | redraw count and tear counter stay at their expected rates |

## Timing discipline

* Wait for the state to settle, not a fixed sleep: poll the firmware's "redraw pending"/"wipe active"
  flag, or read the frame counter twice.
* A full-page transition can take 100–300 ms on a scan-out-gated system. A capture 50 ms after the
  tap shows a half-drawn page and looks like a bug.
* Do not halt the core in the same second you compare tear counters; a halt creates a fake tear.
