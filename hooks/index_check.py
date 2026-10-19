#!/usr/bin/env python3
"""PostToolUse (Write|Edit|MultiEdit): nudge generated markdown towards OPERATING-MODEL §9.

After a markdown file is written, three cheap checks, independent of where the file
lives:
  (a) a long file (> LONG_LINES lines, >= MIN_SECTIONS `## ` sections) with no
      `## Contents` table;
  (b) the file's folder now holds >= 2 markdown files and no INDEX.md;
  (c) the folder has an INDEX.md that does not mention this file.
Any hit is returned as additionalContext so the model sees it; nothing is blocked.

Read-only: never writes a file, never runs a subprocess. Fails open: any error, or
any input it does not understand, yields `{}` and exit 0.
"""
import json, os, pathlib, re, sys

LONG_LINES = 150
MIN_SECTIONS = 4
MARKER_LINES = 10
INDEX_NAME = "INDEX.md"
DOC_SUFFIX = ".md"
# Files whose structure is fixed by a convention or a tool: never asked for a Contents table.
FIXED_STRUCTURE = {"SKILL.md", INDEX_NAME, "TERMS.md", "CHANGELOG.md"}
# Conventional repository files: neither checked nor counted as a folder's documents.
REPO_CONVENTION = FIXED_STRUCTURE | {"README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md",
                                     "SECURITY.md", "CODE_OF_CONDUCT.md", "LICENSE.md"}
SKIP_DIRS = {"node_modules", ".git"}
GENERATED = re.compile(r"\bgenerated\b|never edit by hand", re.I)
CONTENTS = re.compile(r"^##\s+(table of\s+)?contents\b", re.I)
FENCE = re.compile(r"^\s*(```|~~~)")
RULE = "OPERATING-MODEL §9"


def sections(lines):
    n, contents, fenced = 0, False, False
    for l in lines:
        if FENCE.match(l):
            fenced = not fenced
        elif not fenced and l.startswith("## "):
            n += 1
            contents = contents or bool(CONTENTS.match(l))
    return n, contents


def warnings(path):
    if path.suffix.lower() != DOC_SUFFIX or not path.is_file():
        return []
    if SKIP_DIRS.intersection(path.parts):
        return []
    lines = path.read_text(errors="replace").splitlines()
    if GENERATED.search("\n".join(lines[:MARKER_LINES])):
        return []
    out = []
    if path.name not in FIXED_STRUCTURE and len(lines) > LONG_LINES:
        n, has_contents = sections(lines)
        if n >= MIN_SECTIONS and not has_contents:
            out.append(f"{path} is {len(lines)} lines with {n} `## ` sections and no "
                       "`## Contents` table: add one after the summary, one row per section "
                       "saying what it answers, linked by anchor.")
    if path.name in REPO_CONVENTION:
        return out
    folder = path.parent
    index = folder / INDEX_NAME
    if index.is_file():
        if path.name not in index.read_text(errors="replace"):
            out.append(f"{index} does not mention {path.name}: add a row for it "
                       "(one line on what it answers).")
    else:
        docs = [e for e in os.listdir(str(folder))
                if e.lower().endswith(DOC_SUFFIX) and e not in REPO_CONVENTION]
        if len(docs) >= 2:
            out.append(f"{folder} now holds {len(docs)} markdown files and no {INDEX_NAME}: "
                       "write one (a table of every file, one line on what each answers, a "
                       "'start here' pointer), or run the tool that generates it.")
    return out


def main(raw):
    payload = json.loads(raw)
    target = (payload.get("tool_input") or {}).get("file_path")
    if not isinstance(target, str) or not target:
        return {}
    path = pathlib.Path(target)
    if not path.is_absolute():
        path = pathlib.Path(payload.get("cwd") or os.getcwd()) / path
    found = warnings(path)
    if not found:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": f"Index rule ({RULE}): " + " ".join(found)}}


if __name__ == "__main__":
    try:
        result = main(sys.stdin.read())
    except Exception:  # fail-open: an error yields no context, never a broken tool call
        result = {}
    print(json.dumps(result))
    sys.exit(0)
