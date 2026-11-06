# Publishing checklist

A filesystem skill is discovered as `<root>/<name>/SKILL.md`, one level deep. There is no manifest,
no build step, and no registry — publishing means "make this directory easy to drop into a root".

## 1. Before anything leaves the machine

```bash
python scripts/validate_skill.py
```

It checks the things a loader silently rejects or a reader only notices too late: frontmatter,
kebab-case `name`, a usable `description`, referenced files that do not exist, Python that does not
parse, and user-specific absolute paths.

Then check by eye:

- [ ] no project ELF, firmware image, build directory, or customer screenshot is inside the folder
- [ ] no absolute path from your machine (`C:\Users\...`, `/home/...`)
- [ ] every command in `README*.md` works when the folder is installed somewhere else
- [ ] `SKILL.md` says *when to use it*, not just what it is
- [ ] the body is short enough to load often; deep material sits in `references/`

## 2. License

`LICENSE` is MIT, copyright `2026 16654`. Replace the holder with the name or handle you publish
under (one line, same year) before the first push. If you later include code under another license,
keep both notices and say which files they cover.

## 3. Version and changelog

* `CHANGELOG.md` gets an entry per release: added / changed / fixed.
* Bump the version in the changelog heading; the skill format has no version field, so the file is
  the version.
* Skill bodies are re-read on every load, so a body fix ships as soon as the file lands — say so in
  the changelog instead of pretending there is a release pipeline.

## 4. Package shape

```
embedded-hil-loop/          <- directory name should match `name:` in SKILL.md
├── SKILL.md                <- required, frontmatter + body
├── README.md, README.zh.md optional, for humans browsing the repo
├── PUBLISH.md, CHANGELOG.md
├── references/             <- loaded on demand by path from the body
├── scripts/                <- executed by the agent; keep them dependency-light
└── assets/                 <- templates copied into projects
```

Distribution options, in increasing effort:

| Form | How | When |
|---|---|---|
| Directory copy | `cp -r embedded-hil-loop ~/.dsh/skills/` | simplest, works today |
| Zip | compress the directory; users unzip into a skills root | sharing in chat/email |
| Git repo | repo root = the bundle directory | normal open-source publishing |
| Plugin bundle | ship the folder under a package's `assets/` and mount a provider | when you want it installed as part of a product |

Do not nest the bundle one level deeper (e.g. `repo/skills/embedded-hil-loop/SKILL.md`): that is
inside the watched root only if the root is `repo/skills`, which is easy to get wrong. Keep
`SKILL.md` at the top of the distributable directory.

## 5. Publish and smoke-test

1. Push / zip / copy.
2. Install into a **fresh** location (`~/.dsh/skills` on another account, or a project's `.dsh/skills`).
3. Open a new session in a firmware project and ask for the skill by name.
4. Run the quickstart on a board: `status` must show a rate, `shot` must produce a PNG, `synth_touch`
   must change the UI.
5. Uninstall by deleting the directory; confirm the catalog no longer offers it.

## 6. Compatibility honesty

Write down what is portable and what is not, so users do not blame the method for a platform detail:

* probe recipes: J-Link and OpenOCD (both documented)
* capture/decode: STM32 LTDC today; other display controllers need the register map in `cmd_shot`
* synthetic input: the *pattern* is generic, the symbol names are project-specific (`--map`)
* tear budget: generic for single-framebuffer scan-out, constants must be re-measured per panel

Keep that table in `README.md` (it is there now) and update it when someone ports the skill.
