# Handover — `<date>`

> Write this while the context is fresh. A handover that restates the old one rots twice as fast:
> say what is **true now**, what is **stale**, and what is **next**. Link deep material instead of
> copying it.

## 0. One paragraph: what state is the project in

`<what works, what is being debugged, which build is flashed>`

## 1. Current truth (measured)

| Item | Value | How it was measured |
|---|---|---|
| build flashed | `<hex path, timestamp>` | `<probe read of a version symbol / flash log>` |
| frame rate | `<n fps>` | `jprobe status <frame counter>` |
| tear rate | `<n/s idle>` | tear counter delta over `<N>` s |
| draw cost | `<ms, scenario>` | `<instrumented counter>` |
| memory | `<flash %, RAM % / free>` | link output |

## 2. What changed in this session

- `<change 1>: <why>; <evidence>`
- `<change 2>: ...`

## 3. Stale claims (do not act on these)

- `<doc §x>`: `<claim>` — replaced by `<what is true now>`.
- `<old assumption about hardware/timing>` — `<counter-evidence>`.

## 4. Next step

1. `<smallest useful action>`
2. `<...>`

## 5. Traps already mapped (so the next session does not pay again)

- `<symptom> -> <cause> -> <fix/location>`

## 6. Commands

```bash
<build>          # production
<flash>
<probe status>
<capture>
<preview>
```

## 7. Open questions for the human

- `<decision needed>` (`<options and tradeoff>`)
