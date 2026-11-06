# Scan-out budget: writing to a display the panel is continuously reading

Applies to any MCU with a parallel/RGB or MIPI panel and a single framebuffer (no double buffering).
If the CPU writes the pixels the panel is currently scanning, the visible result is a horizontal
seam. The fix is not "draw faster"; it is "draw only while the beam is elsewhere, and know how long
the beam takes to come back".

## 1. The model

Panel timing is defined by total lines `H_total` (active + blanking) and pixel clock `f_pclk`:

```
line_time   = H_total / f_pclk          # e.g. 976 / 33.333 MHz = 29.28 us
frame_time  = V_total * line_time       # e.g. 528 * 29.28 us  = 15.455 ms  (64.7 Hz)
```

The active area starts at line `V_offset` (`VSW + VBP`), so **screen row y is panel line y + V_offset**.

A draw is safe when the scan line is outside the dirty rectangle. Once the line has passed the
rectangle, the beam must wrap around the frame and come back to the rectangle's top:

```
safe_window_lines(y) = (H_total - y_ltcd) + (box_top_ltcd - margin)    # only if y_ltcd > box_bottom + margin
safe_window_time     = safe_window_lines * line_time
```

`margin` covers the loop's own latency between deciding and starting to write (2–4 lines is typical).

## 2. Budget calibration (measure, do not guess)

Model the cost of an LVGL refresh as `need_lines = k * dirty_rows + c`, with `k`/`c` derived from
real draws on the board (divide the measured µs by `line_time`):

| Dirty area | Measured | In lines | Implied |
|---|---|---|---|
| 47-row slider knob | 4.8 ms | ≈164 | small draws are overhead-dominated |
| 196-row table | 5–8 ms | ≈170–273 | |
| 360-row full page | 10–13 ms | ≈341–444 | |

A usable fit was `k = 1.25`, `c = 100` lines (≈2.9 ms + 0.037 ms/row), about 25 % above the worst
observed draw. Re-measure on your panel; the constants are hardware- and widget-dependent.

## 3. The deadlock (a real one)

The first version computed the maximum window as `H_total - dirty_rows` — as if a draw could start
at `y = box_bottom + 1`. The earliest legal start is `box_bottom + margin + 1`, which is `2*margin+1`
lines later, so the *achievable* maximum is smaller by that amount:

```
achievable_max = H_total - box_bottom - margin - 1 + box_top - margin
```

With a full-screen plot area (box 0..359, `V_offset=35`, margin 3) the achievable maximum is 162
lines. The paint-cost estimator had risen to 162 → `need = 164`. Result: `need > window` forever.
The waveform never repainted again (the panel kept drawing it with LVGL, so the plot looked "frozen"
while everything else worked), and every later attempt was rejected by the same comparison.

Two fixes, both needed:

* compute `hopeless = need > achievable_max` (not `> H_total - rows`);
* keep a starvation failsafe that forces the draw after **N frames**.

A third, smaller one: clamp the estimator. It should never exceed the achievable maximum, or it
locks itself out.

## 4. Failsafe: count frames, not loop iterations

```c
if (past_boundary) s_wait++;
if (s_wait >= 8) { force_draw = true; s_wait = 0; }
```

On a fast main loop this is wrong: the loop runs every few microseconds, so 8 iterations is well
under a millisecond. The force then fires while the beam is inside the rectangle — every single
draw becomes a tear. Count once per frame instead:

```c
uint32_t fr = frame_counter();
if (past && s_wait_frame != fr) { s_wait_frame = fr; s_wait++; }
```

With a per-frame counter, a healthy draw passes the window check long before 8 frames and the
failsafe only fires on a genuine stall.

## 5. Full-page changes: banded wipe

A full-page repaint (360 rows ≈ 450 lines of drawing) cannot fit a 168-line window. Waiting does not
help. Options:

1. **Flash one frame.** Draw immediately after the beam passes; accept one seam. Simple, and fine for
   a deliberate page change.
2. **Banded wipe (recommended).** Invalidate one band, draw it, then invalidate the next:

```c
/* on the page change: do NOT let the hide/show flags invalidate the whole page */
lv_disp_enable_invalidation(disp, false);
/* ... toggle page/axis visibility, change tab colours ... */
lv_disp_enable_invalidation(disp, true);

wipe_begin();                       /* invalidate band 0 only */

/* after every successful refresh (flush counter changed): */
void UI_WipeStep(void) {
  if (++band < BANDS) invalidate_band(band);
}
```

Practical numbers from a 800×480 / 64.7 Hz panel:

* 80-row bands: 3–4 ms each, window ≥ 7 ms at the earliest legal start → no seam;
* 120-row bands measured much worse on the bottom bar (13 ms), so **band size is not uniform in
  cost** — the band containing big opaque widgets (tab buttons) must be smaller or separate;
* total transition 6 frames ≈ 100 ms, which reads as a deliberate wipe;
* during the wipe, **suppress other invalidation sources** (a 5 Hz table update that lands on a band
  merges with it into a 400-row box and destroys the budget). Pause periodic updates while
  `wipe_active`, and resume them afterwards.

If a band's window is uncertain, force it (`hopeless = true` while wiping): a band that waits many
frames makes the transition look stuck, and landing a 3–4 ms band in a ≥7 ms window is safe anyway.

## 6. Dirty rectangles merge

The scheduler sees the *union* of pending invalidations. Two unrelated updates in one frame can
produce a box far taller than either:

* a 94-row table + a 26-row status label above it → 236-row box (45..250), past the budget;
* a 196-row table + a 120-row wipe band → 400-row box.

Mitigations, in order of preference:

1. **Defer small text updates** to after the refresh (`if (disp->inv_p == 0)`), so they become their
   own small draw. A 1 Hz fps label must not ride along with a 5 Hz table.
2. **Split the big object** into halves and invalidate one half per tick; each half fits, and the
   eye still reads it as live (2.5 Hz per half at 5 Hz ticks).
3. **Widen the budget only for the union you expect**, and measure the tear counter afterwards.

## 7. Measuring tearing honestly

Keep a counter incremented only when a draw's scan position crossed its own dirty box:

```c
if (scan_crossed(top, bot, y_before, y_after)) s_tear_cnt++;
```

Rules:

* It is a cumulative counter; compare deltas over a known interval.
* Read it twice with the probe and divide by the measured time.
* Do not halt the core in the same second (a halt advances the beam but not the CPU and manufactures
  a tear).
* A tearing count without a scenario is meaningless: record idle, during drag, during page change.

Expected orders of magnitude for a tuned single-buffer UI: idle ≈ 0.1–0.5 tears/s (periodic tables),
drag ≈ 0–2 per 80 steps, page transition ≈ 0–2 per change.

## 8. When double buffering is the right answer

Double buffering removes the whole problem but costs bandwidth and memory:

```
bytes/s = width * height * bytes_per_pixel * fps
```

800×480×1 B×65 ≈ 25 MB/s of continuous panel read, plus the same amount again for memcpy/flip if you
copy. If the bus can absorb two framebuffers and the LTDC can be pointed at the back buffer at
VSYNC, prefer it. If not (small AXI SRAM, no spare bandwidth), the scan-out budget above is the
cheaper engineering answer — and it is what the worked case uses.

## 9. Checklist for a new page or overlay

- [ ] dirty areas are as small as the design allows; text that changes often is separate from art
- [ ] the budget model is calibrated on this board (k, c), not inherited from a doc
- [ ] `hopeless` compares against the achievable maximum, computed at the earliest legal start
- [ ] the failsafe counts frames
- [ ] full-page transitions are banded, with other invalidations suppressed
- [ ] a tear counter exists and is read before/after every layout change
- [ ] idle redraw rate is intentional (what updates at 1/5/10 Hz, and why)
