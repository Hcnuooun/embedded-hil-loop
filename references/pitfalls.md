# Pitfall catalogue

Each entry is a bug that actually cost time on a real board. Format: **symptom → cause → fix → how
to catch it next time**.

## 1. A hidden widget is not an erased widget

**Symptom.** After switching pages, most of the screen updates but a few labels from the old page stay
on top of the new one (a title, "TIME/VOLT" rows, axis text). The page variable says the switch
happened.

**Cause.** Toggling `LV_OBJ_FLAG_HIDDEN` stops *drawing* the object; it does not clear the pixels it
already drew. If nothing repaints that area, the old pixels remain — and the symptom looks like "the
page didn't switch".

**Fix.** Correctness is an *area* property: invalidate (and repaint) the whole region that changed,
not just the objects you showed. On a single-buffer scan-out display this is also where the scan-line
budget applies — see `scanout-budget.md`.

**Catch it next time.** After any visibility change, capture the screen and assert that no colour
belonging to the old page survives in the affected region.

## 2. Dirty rectangles merge into an unfittable box

**Symptom.** A table stops updating (or tears) only when some unrelated label happens to update at the
same time. Capture shows a horizontal seam across the table.

**Cause.** The scheduler budgets for the union bounding box. A 94-row table plus a 26-row status
label above it becomes a 236-row box; add a wipe band and it becomes 400 rows, larger than any window.

**Fix.** Defer small text updates to after the refresh (`disp->inv_p == 0`), split large objects into
halves, and keep periodic updates from coinciding with transitions.

**Catch it next time.** Log the dirty bbox height per draw; an unexpected large value is this bug.

## 3. Cost estimate > achievable window ⇒ permanent starvation

**Symptom.** One subsystem freezes forever (a waveform stops, a plot goes black) while everything else
runs. A "paint frame" counter stops advancing.

**Cause.** The window upper bound was computed at a start position that is not legal (`box_bottom+1`
instead of `box_bottom+margin+1`), so the estimate could exceed it by a few lines and no frame ever
qualified. The estimator never decayed because it only updates after a successful draw.

**Fix.** Compute the achievable maximum at the earliest legal start; clamp the estimate; force a draw
after N *frames* of starvation.

**Catch it next time.** Read the "last painted frame" counter; if it is frozen while the loop runs,
the gate is the suspect, not the drawing code.

## 4. Failsafe counted per loop iteration

**Symptom.** Tearing at a steady rate under load; the tear counter climbs even when the redraw is fast.

**Cause.** `s_wait++` ran on every main-loop pass. The loop is a few microseconds, so "8" elapsed
inside one scan line and the forced draw always landed on the beam.

**Fix.** Increment at most once per frame.

**Catch it next time.** The tear counter's rate changes with the loop's speed rather than with the
draw's cost — that is the signature.

## 5. Debug output that feeds itself

**Symptom.** A tear appears, then a label showing the tear count updates, which causes more tearing,
which updates the label…

**Cause.** The debug label lives inside the measured area and its update is a dirty rectangle.

**Fix.** Update diagnostics at low rate, outside the measured region, and never let their invalidation
join the area being measured. Or keep them behind a probe-read variable instead of on screen.

**Catch it next time.** Tear rate that correlates with the counter's own value.

## 6. Fake tears from halting the core

**Symptom.** The tear counter jumps every time you attach the debugger.

**Cause.** A halt advances the panel's beam but not the CPU; when the CPU resumes it is "late"
relative to the beam.

**Fix.** Measure tearing in a window with no halts; read counters before/after that window only.

## 7. Cycle counters that do not count

**Symptom.** Every measured duration is 0 or absurdly small; the sums look impossible.

**Cause.** The cycle counter was not running (or the read path/session was not counting) while the
firmware ran. Numbers were plausible-looking zeros, which is worse than a crash.

**Fix.** Verify the timebase first: arm, sleep a known interval in the probe script, read; the delta
must be ≈ f_cpu. Only then interpret timings.

## 8. Stale ELF, plausible garbage

**Symptom.** A symbol reads a value that "could be" right but behaves inconsistently after a rebuild.

**Cause.** Probe addressed from an older ELF while the board ran a newer build (or vice versa).

**Fix.** Keep one ELF per build directory and pass it explicitly; re-flash and re-read together. Add a
version constant that changes every build and read it after flashing.

## 9. Touch driver conflates "no new data" with "released"

**Symptom.** Pressing and holding acts like repeated taps; modal pages open and close by themselves.

**Cause.** A capacitive controller reports "new data" at 100 Hz, but the poll runs at 200 Hz. Most
polls see the "no new data" status; treating that as release makes `pressed` flicker, generating
PRESSED/CLICKED pairs.

**Fix.** Distinguish three states: has-points, no-points-reported (real release), no-new-data (keep
current state). Add a watchdog for a dead controller.

## 10. Modal page eats the release

**Symptom.** Hold a button that opens a modal page, release, and the widget underneath the finger is
triggered instead.

**Cause.** LVGL re-runs hit testing on the next read; the release is delivered to the newly visible
widget.

**Fix.** In the callback that opens/close a modal, call `lv_indev_wait_release()`.

## 11. Screenshot taken mid-transition

**Symptom.** A capture shows half the old page and half the new one; you conclude the switch is broken.

**Cause.** The transition (banded wipe or a slow full repaint) takes 100–300 ms; the capture happened
in the middle.

**Fix.** Wait for a settle condition (a "wipe pending" flag, or the frame counter advancing by N
frames) before capturing.

## 12. The overlay's own style invalidates the page

**Symptom.** Dragging a slider repaints more than the slider; frame rate collapses.

**Cause.** Rounded corners / shadows / an icon glyph inside the moved object force a mask rebuild or a
larger invalidation every frame.

**Fix.** Square the track/fill, drop the shadow, use a small font for the icon (or a bitmap). Measure
the draw before and after; the difference is usually 2×.

## 13. A linker section silently overlaps a scanned buffer

**Symptom.** Random display corruption or a black band that appears/disappears with unrelated code
changes.

**Cause.** `.bss` grew into a framebuffer placed at a hard-coded address; nothing warns at link time.

**Fix.** Give the overlay/buffer its own region and cap the RAM section so growth fails the link
instead of corrupting pixels.

**Catch it next time.** Print section end vs buffer start in the build output; treat "grew by 3 KB" as
a display bug until proven otherwise.

## 14. Two builds, one board

**Symptom.** A feature works with the debug build and not with the production build (or the reverse).

**Cause.** Different compile paths (`#if DEBUG`), different optimisation, or an experimental build
that was flashed last and forgotten.

**Fix.** Keep production and experiment build directories separate, flash the production image before
delivery, and verify a symbol that differs. Say which build you tested.

## 15. Timing numbers measured on the wrong axis

**Symptom.** A "draw cost" that does not change when the dirty area doubles; a rate that is off by
the timer's prescaler.

**Cause.** The counter counts something else (pixels, calls, loop passes) or the tick base is not
1 kHz.

**Fix.** Record the units next to every number, and validate one known interval end-to-end (e.g. a
1 s sleep must produce 1 s of ticks).
