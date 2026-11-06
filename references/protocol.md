# Working agreement for AI-driven embedded work

This is the human-facing half of the skill. The tools make the loop fast; this makes it trustworthy.

## 1. Read before you speak

The first action on any task is to read the current state, not to answer from memory:

1. newest handover, then the project `AGENTS.md` (the file may be stale — treat it as a claim);
2. `git status` / recent log, to see what is uncommitted (in these projects a dirty tree is the
   normal state, not a broken workspace);
3. the live board: counters advancing, a fresh framebuffer capture;
4. the specific subsystem the task touches (page/state variables, config, last measurements).

Only then form a hypothesis. If the handover and the board disagree, **the board wins**, and the
disagreement goes into the report.

## 2. Evidence, not adjectives

A statement about behaviour needs one of:

| Claim | Evidence |
|---|---|
| "it runs" | `status` shows the frame counter advancing at the expected rate |
| "the page switched" | a capture after the switch, plus the page variable |
| "it doesn't tear" | tear counter delta over N seconds |
| "it is faster" | before/after draw time in µs or lines, same scenario |
| "the value is correct" | the symbol read, printed with its address/ELF |

If you cannot measure it, say what you observed and what you could not verify. Uncertainty stated
up front is cheap; a confident wrong answer costs a reflash and the user's trust.

## 3. One authorisation per change, one change per iteration

* Schematic/PCB edits and destructive hardware actions: propose, get an explicit yes, then act.
* Firmware edits: batch related edits, but keep the *reason* for each one separate in the report.
* Never slip a "while I was there" change into a fix. It hides regressions and makes the evidence
  ambiguous.
* When a change is risky (flash/bootloader/memory map), state the recovery path first.

## 4. No hidden special cases

Temporary hacks are allowed; hidden hacks are not. If a value, pin, address or object needs special
handling, it must appear in three places:

1. a comment marking it as a temporary exception and why;
2. the delivery summary (say it out loud, unprompted);
3. the project instruction file / handover.

A whitelist that silently makes a checker pass is the worst version of this bug: it converts a
detectable defect into a false clean report.

## 5. Handover discipline

Write the handover while the context is fresh, not at the end. Keep three sections separate:

* **Current truth** — measured facts, with the numbers.
* **Stale claims** — which older documents/sections are now wrong, and what replaced them.
* **Next step** — the smallest useful next action, and the traps already mapped.

Link the deep material (reports, plans) instead of copying it. A handover that restates everything
rots twice as fast as one that points.

## 6. Reporting back to the human

Lead with the conclusion, then the evidence, then what is not done. Specifically:

* what changed, in one sentence per change;
* what it was measured against (before/after numbers or captures);
* what you did **not** do, and which assumptions you made;
* any temporary exception, hard-coded value or workaround — proactively, not when asked.

If a request conflicts with what the board shows, say so before implementing it: "the code says X,
the capture shows Y, which do you want?" is a valid and cheap answer.

## 7. When to stop

Stop and ask when: the action is destructive and unauthorised; the evidence contradicts the request;
the fix would need a hardware change; or two iterations in a row failed for reasons you cannot
explain. Do not keep reflashing a board on a theory that has stopped producing new information.
