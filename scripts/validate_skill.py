#!/usr/bin/env python3
"""validate_skill.py — pre-flight checks before publishing a filesystem skill.

Checks the things a skill loader silently rejects or a reader only notices later:
  * `SKILL.md` exists at the bundle root and starts with YAML frontmatter
  * frontmatter has a kebab-case `name` (matching the directory, by convention) and a `description`
  * optional keys are valid (`whenToUse`, `metadata`, `disable-model-invocation`, `user-invocable`)
  * every relative path mentioned in the body (`references/...`, `scripts/...`, `assets/...`) exists
  * every Python script compiles
  * no absolute local paths leaked into the package (a very common pre-publish mistake)

Usage:
    python validate_skill.py [--root .]
Exit code 0 = publishable, 1 = problems printed.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESOURCE = re.compile(r"(?:references|scripts|assets)/[A-Za-z0-9_.\-/]+")
BOOL_KEYS = ("disable-model-invocation", "user-invocable")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        raise ValueError("SKILL.md must start with '---' frontmatter")
    end = text.find("\n---", 3)
    if end < 0:
        raise ValueError("frontmatter is not closed with '---'")
    raw = text[3:end].strip("\r\n")
    body = text[end + 4:]
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"frontmatter line is not 'key: value': {line!r}")
        fields[key.strip()] = value.strip().strip("'\"")
    return fields, body


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    problems: list[str] = []
    notes: list[str] = []

    skill_md = os.path.join(root, "SKILL.md")
    if not os.path.isfile(skill_md):
        sys.exit(f"missing {skill_md}")
    text = open(skill_md, encoding="utf-8").read()
    try:
        fields, body = parse_frontmatter(text)
    except ValueError as exc:
        sys.exit(f"frontmatter: {exc}")

    name = fields.get("name", "")
    if not KEBAB.match(name):
        problems.append(f"name {name!r} is not kebab-case")
    if name != os.path.basename(root):
        notes.append(f"name {name!r} differs from directory {os.path.basename(root)!r} "
                     "(allowed, but confusing when installed)")
    if not fields.get("description"):
        problems.append("description is required and must say when to use the skill")
    length = len(fields.get("description", ""))
    if length > 1024:
        problems.append(f"description is {length} chars; most catalogs truncate far earlier")
    for key in BOOL_KEYS:
        if key in fields and fields[key].lower() not in ("true", "false", "yes", "no", "on", "off", "1", "0"):
            problems.append(f"{key} is not a boolean: {fields[key]!r}")

    for ref in sorted(set(RESOURCE.findall(body))):
        if not os.path.exists(os.path.join(root, ref)):
            problems.append(f"body references missing file: {ref}")

    for dirpath, _, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            if f.endswith(".py"):
                try:
                    compile(open(p, encoding="utf-8").read(), p, "exec")
                except SyntaxError as exc:
                    problems.append(f"python does not parse: {os.path.relpath(p, root)}: {exc}")
            if f.endswith((".md", ".py", ".json", ".yml", ".yaml")):
                try:
                    content = open(p, encoding="utf-8").read()
                except UnicodeDecodeError:
                    problems.append(f"not UTF-8: {os.path.relpath(p, root)}")
                    continue
                rel = os.path.relpath(p, root)
                # A user's home directory is always a leak; in docs, any absolute local path is.
                # Placeholders ("C:\Users\...", "<name>") are not leaks.
                def _real(path: str) -> bool:
                    return "..." not in path and "<" not in path

                for m in re.finditer(r"[A-Za-z]:\\Users\\[^\\\s\"'`]+", content):
                    if _real(m.group(0)):
                        problems.append(f"user-specific path in {rel}: {m.group(0)}")
                for m in re.finditer(r"/(?:Users|home)/[A-Za-z0-9_.\-]+/", content):
                    if _real(m.group(0)):
                        problems.append(f"user-specific path in {rel}: {m.group(0)}")
                if f.endswith(".md"):
                    for m in re.finditer(r"[A-Za-z]:\\[^\s\"'`]+", content):
                        if _real(m.group(0)):
                            problems.append(f"absolute path in docs {rel}: {m.group(0)}")

    print(f"skill: {name}  ({len(body.splitlines())} body lines, description {length} chars)")
    for n in notes:
        print(f"  note: {n}")
    if problems:
        for p in problems:
            print(f"  FAIL: {p}")
        sys.exit(1)
    print("  ok: publishable")


if __name__ == "__main__":
    main()
