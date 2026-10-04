#!/usr/bin/env python3
"""Project-level learning: lessons that outlive the conversation that produced them.

The gap this closes: a mistake costs an hour, gets fixed, and the fix lives only in
the transcript that produced it -- gone the moment the session ends, invisible to the
next agent (or the next session of the same agent) that hits the same wall. This
plugin already has a project-level store for decisions (`decisions/`), specs
(`specs/`) and root causes (`rca/`); nothing accumulated lessons into it, and Claude
Code's own memory is a separate mechanism this plugin does not write to.

Where a lesson belongs -- three stores, split by who needs it:

  personal preference    ("I like terse commit messages")  -> the agent's own
                         auto-memory. Per user, never committed; this tool does
                         not write there.
  project fact / gotcha  ("the integration suite needs `docker compose up db`")
                         -> a lesson here, under lessons/, git-tracked and reviewed,
                         so every teammate and every agent session gets it.
  stable team rule       a lesson that has held long enough to be a standing
                         instruction -> promoted into AGENTS.md with
                         `learn.py promote <id>`, which prints the exact snippet and
                         target section and writes only with --yes.

A lesson is a short, falsifiable fact -- a gotcha, a convention, a failure mode, or a
scoped preference -- filed the same way a decision is: a markdown file with a
```json meta``` block, so `ledger.py` discovers it alongside ADRs and RCAs. The part
that makes a lesson worth writing down is `relevant <path>`: at the moment an agent
is about to touch a file, it asks what was already learned about that path, rather
than the lesson sitting unread in `lessons/` until someone remembers to grep it.

    learn.py add "<lesson>" --kind gotcha --affects "src/auth/**" --source ADR-0003
    learn.py list [--kind K] [--affects PATH]
    learn.py index                    # regenerate lessons/INDEX.md
    learn.py relevant src/auth/x.ts   # lessons that apply before editing this file
    learn.py promote LESSON-0003      # show the AGENTS.md snippet; --yes to write it
    learn.py lint                     # rejects an unattached, unsourced or stale lesson

Python stdlib only.
"""
import argparse, datetime, json, pathlib, re, subprocess, sys
import _paths

PLUGIN = pathlib.Path(__file__).resolve().parent.parent

def rel(p):
    """Display path relative to the git root, resilient to a target outside it."""
    return _paths.show(p, ROOT)


# ROOT is the user's git root, not the plugin's directory (records written into the
# installed plugin are invisible to the project and lost on upgrade); lessons live under
# the records root (_paths.py). Outside a repo ROOT falls back to cwd for reads only.
ROOT, _ = _paths.git_root()
DIR = _paths.resolve(ROOT)[0] / "lessons"
META_RX = re.compile(r"```json meta\s*\n(.*?)\n```", re.S)
KINDS = ("gotcha", "convention", "failure", "preference")
TRIGGER_RX = re.compile(r"\b(when|if|before|after|during|until)\b", re.I)
MIN_LESSON_CHARS = 15
SECTION_BY_KIND = {"gotcha": "## Gotchas", "failure": "## Gotchas",
                   "convention": "## Conventions", "preference": "## Conventions"}
PATH_SOURCE_RX = re.compile(r"^([\w./-]+\.\w+|[\w.-]+/[\w./-]+)(:\d+(-\d+)?)?$")


def glob_rx(pattern):
    """Glob where `**` spans directories, `*` stays inside one segment, and a bare
    directory (`src/auth`, `src/auth/`) means everything under it."""
    p = pattern.strip()
    p = p[2:] if p.startswith("./") else p
    if not any(c in p for c in "*?["):
        p = p.rstrip("/") + "/**" if not re.search(r"\.\w+$", p) else p
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out += r"(?:.*/)?"; i += 3
        elif p.startswith("**", i):
            out += r".*"; i += 2
        elif p[i] == "*":
            out += r"[^/]*"; i += 1
        elif p[i] == "?":
            out += r"[^/]"; i += 1
        else:
            out += re.escape(p[i]); i += 1
    return re.compile(rf"^{out}$")


def norm_path(path):
    p = pathlib.Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(ROOT.resolve())
        except ValueError:
            pass
    s = str(p).replace("\\", "/")
    return s[2:] if s.startswith("./") else s


def matches(path, patterns):
    path = norm_path(path)
    return any(glob_rx(pat).match(path) for pat in patterns or [])


def load_all():
    out = []
    if not DIR.exists():
        return out
    for p in sorted(DIR.rglob("LESSON-*.md")):
        text = p.read_text(errors="replace")
        m = META_RX.search(text)
        if not m:
            out.append({"_path": p, "_error": "no ```json meta block"})
            continue
        try:
            meta = json.loads(m.group(1))
        except Exception as e:
            out.append({"_path": p, "_error": f"meta block is not valid JSON: {e}"})
            continue
        meta["_path"] = p
        meta["_body"] = text
        out.append(meta)
    return out


def next_id():
    # rglob, not glob: `ledger.py shard` moves lessons into YYYY/QN/, and a top-level
    # scan would hand out an id that already exists in a shard.
    ids = [int(m.group(1)) for p in DIR.rglob("LESSON-*.md")
           if (m := re.match(r"LESSON-(\d+)", p.name))]
    return f"LESSON-{max(ids, default=0) + 1:04d}"


TEMPLATE = '''# {id}: {title}

```json meta
{meta}
```

## Lesson

{lesson}

## Why it matters

<!-- What it costs when this is not known -- the hour lost, the outage, the review
     comment repeated for the third time. A lesson with no cost is trivia, not a
     lesson. -->
'''


def cmd_add(a):
    DIR.mkdir(parents=True, exist_ok=True)
    lid = next_id()
    title = a.lesson.strip()
    if len(title) > 72:
        title = title[:69].rstrip() + "..."
    meta = {
        "id": lid,
        "title": title,
        "kind": a.kind,
        "lesson": a.lesson.strip(),
        "affects": [p for p in (a.affects or [])],
        "source": a.source,
        "date": datetime.date.today().isoformat(),
        "added_by": a.by,
    }
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or "lesson"
    path = DIR / f"{lid}-{slug}.md"
    path.write_text(TEMPLATE.format(id=lid, title=title, lesson=a.lesson.strip(),
                                    meta=json.dumps(meta, indent=2)))
    print(f"created {rel(path)}")
    if not meta["affects"] and not meta["source"]:
        print("  WARN no --affects and no --source -- this lesson will not surface "
              "via `learn.py relevant` and has no cited origin. `learn.py lint` will "
              "reject it as-is.")
    cmd_index(a)
    return 0


def cmd_index(a):
    recs = load_all()
    DIR.mkdir(parents=True, exist_ok=True)
    rows, bad = [], []
    for r in recs:
        if r.get("_error"):
            bad.append(r)
            continue
        rows.append((r.get("id", "?"), r.get("kind", "?"), r.get("title", "?"),
                     ", ".join(r.get("affects") or []) or "—",
                     r.get("source") or "—", r.get("date", "?"),
                     r["_path"].relative_to(DIR).as_posix()))
    rows.sort(key=lambda x: x[0])
    out = ["# Lesson index", "",
           f"{len(rows)} lesson(s). Regenerate with `python3 scripts/learn.py index`.",
           "", "| id | kind | lesson | affects | source | date |",
           "|---|---|---|---|---|---|"]
    for i, k, t, af, src, d, fn in rows:
        out.append(f"| [{i}]({fn}) | {k} | {t} | `{af}` | {src} | {d} |")
    if bad:
        out += ["", "## Malformed records", ""]
        out += [f"- `{r['_path'].relative_to(DIR).as_posix()}` — {r['_error']}" for r in bad]
    out += ["", "## How to use this", "",
            "- `learn.py relevant <path>` — lessons that apply before editing a file.",
            "- `learn.py list --kind gotcha` — browse by kind.",
            "- `learn.py lint` — every lesson is attached (affects or source) and, "
            "if a preference, states an observable trigger.", ""]
    (DIR / "INDEX.md").write_text("\n".join(out))
    print(f"wrote {rel(DIR / 'INDEX.md')} ({len(rows)} lesson(s)"
          + (f", {len(bad)} malformed)" if bad else ")"))
    return 1 if bad else 0


def cmd_list(a):
    recs = [r for r in load_all() if not r.get("_error")]
    if a.kind:
        recs = [r for r in recs if r.get("kind") == a.kind]
    if a.affects:
        recs = [r for r in recs if matches(a.affects, r.get("affects"))]
    if not recs:
        print("no lessons match")
        return 0
    for r in sorted(recs, key=lambda x: x.get("id", "")):
        print(f"  {r['id']:12s} [{r.get('kind','?'):10s}] {r.get('title','')[:70]}")
        print(f"               affects: {', '.join(r.get('affects') or []) or '—'}"
              f"   source: {r.get('source') or '—'}")
    return 0


def cmd_relevant(a):
    """The one command that turns a filed lesson back into a recall: what should an
    agent know before it edits THIS file."""
    recs = [r for r in load_all() if not r.get("_error")]
    hits = [r for r in recs if matches(a.path, r.get("affects"))]
    if not hits:
        print(f"no recorded lesson affects {a.path}")
        return 0
    print(f"{len(hits)} lesson(s) apply to {a.path}:\n")
    for r in hits:
        print(f"  {r['id']}  [{r.get('kind')}]  {r.get('lesson','')[:140]}")
        if r.get("source"):
            print(f"       source: {r['source']}")
    return 0


def tracked_files():
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--cached", "--others",
                        "--exclude-standard"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else None


def record_problems(r, files):
    """(errors, warnings) for one lesson record."""
    errs, warns = [], []
    if r.get("kind") not in KINDS:
        errs.append(f"kind {r.get('kind')!r} not in {KINDS}")
    lesson = (r.get("lesson") or "").strip()
    if len(lesson) < MIN_LESSON_CHARS or lesson.startswith("<"):
        errs.append("lesson text is empty or a placeholder")
    affects = r.get("affects") or []
    source = (r.get("source") or "").strip()
    if not affects:
        errs.append("no `affects` glob — `learn.py relevant` will never surface this lesson "
                    "from the file it concerns")
    if not source:
        errs.append("no `source` (ADR id, RCA id, or file:line) — it cannot be re-checked "
                    "when the code moves")
    elif PATH_SOURCE_RX.match(source) and not re.match(r"^(ADR|RCA|LESSON|SPEC|PRD)-", source):
        path = source.split(":")[0]
        if not (ROOT / path).exists():
            errs.append(f"source path {path!r} no longer exists — the lesson is probably "
                        f"stale; re-verify it or delete it")
    if r.get("kind") == "preference" and not TRIGGER_RX.search(lesson):
        errs.append("preference has no observable trigger (when/if/before/after/...) — "
                    "this reads as an opinion, not a lesson an agent can act on")
    if files is not None:
        for pat in affects:
            if not any(glob_rx(pat).match(f) for f in files):
                warns.append(f"affects glob {pat!r} matches no tracked file")
    return errs, warns


def cmd_lint(a):
    """Reject a lesson that will never be recalled, cannot be re-checked, or is stale.

    No `affects`: `relevant` never surfaces it. No `source`: nothing to re-verify it
    against. A `source` path that no longer exists: the lesson outlived its code and is
    now trusted and wrong. A `preference` with no observable trigger is an opinion.
    """
    recs = load_all()
    files = tracked_files()
    errs = 0
    for r in recs:
        p_ = r.get("_path")
        name = p_.name if p_ else "?"
        if r.get("_error"):
            print(f"  ERROR {name}: {r['_error']}"); errs += 1; continue
        e, w = record_problems(r, files)
        for m in e:
            print(f"  ERROR {name}: {m}")
        for m in w:
            print(f"  WARN  {name}: {m}")
        errs += len(e)
    print(f"\nlearn lint: {len(recs)} record(s), {errs} error(s)")
    return 1 if errs else 0


def insertion_point(lines, heading):
    """Index to insert at the end of `heading`'s section, or None if absent."""
    fence, start = False, None
    for i, l in enumerate(lines):
        if l.lstrip().startswith("```"):
            fence = not fence
        if fence:
            continue
        if start is None and l.strip().lower() == heading.lower():
            start = i
        elif start is not None and re.match(r"^#{1,2}\s", l):
            end = i
            while end > start + 1 and not lines[end - 1].strip():
                end -= 1
            return end
    if start is None:
        return None
    end = len(lines)
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def cmd_promote(a):
    """Print the AGENTS.md snippet for a stable lesson; write it only with --yes."""
    recs = {r.get("id"): r for r in load_all() if not r.get("_error")}
    r = recs.get(a.id)
    if not r:
        print(f"no such lesson: {a.id}")
        return 2
    e, _ = record_problems(r, None)
    if e:
        print(f"{a.id} is not stable enough to promote — fix `learn.py lint` first:")
        for m in e:
            print(f"  - {m}")
        return 1
    if a.file:
        target = ROOT / a.file
    else:
        target = next((ROOT / n for n in ("AGENTS.md", "CLAUDE.md") if (ROOT / n).exists()),
                      ROOT / "AGENTS.md")
    heading = a.section or SECTION_BY_KIND.get(r.get("kind"), "## Gotchas")
    if not heading.startswith("#"):
        heading = "## " + heading
    snippet = (f"- {r['lesson'].strip()} Applies to "
               f"{', '.join('`' + x + '`' for x in r.get('affects') or [])}. "
               f"Source: {r.get('source')}. ({r['id']})")
    text = target.read_text() if target.exists() else ""
    if f"({r['id']})" in text:
        print(f"{a.id} is already promoted into {rel(target)}; nothing to do")
        return 0
    lines = text.splitlines()
    at = insertion_point(lines, heading)
    if at is None:
        new_lines = lines + ([""] if lines and lines[-1].strip() else []) + [heading, "", snippet]
        where = f"new section {heading!r} appended at the end"
    else:
        new_lines = lines[:at] + [snippet] + lines[at:]
        where = f"end of section {heading!r}, line {at + 1}"
    print(f"target : {rel(target)}{'' if target.exists() else ' (will be created)'}")
    print(f"section: {where}")
    print(f"snippet:\n{snippet}")
    if not a.yes:
        print("\nNothing has changed. Re-run with --yes to write the snippet and mark the "
              "lesson as promoted.")
        return 0
    target.write_text("\n".join(new_lines) + "\n")
    path = r["_path"]
    body = path.read_text()
    m = META_RX.search(body)
    meta = json.loads(m.group(1))
    meta["promoted_to"] = f"{rel(target)}#{re.sub(r'[^a-z0-9 -]', '', heading.lstrip('#').strip().lower()).replace(' ', '-')}"
    meta["promoted_on"] = datetime.date.today().isoformat()
    path.write_text(body[:m.start(1)] + json.dumps(meta, indent=2) + body[m.end(1):])
    print(f"\nwrote {rel(target)} and marked {a.id} promoted")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("add"); n.add_argument("lesson")
    n.add_argument("--kind", required=True, choices=KINDS)
    n.add_argument("--affects", action="append", help="glob this lesson applies to (repeatable)")
    n.add_argument("--source", default=None, help="ADR-id, RCA-id, or file:line this came from")
    n.add_argument("--by", default="claude")
    n.set_defaults(fn=cmd_add)
    ix = sub.add_parser("index"); ix.set_defaults(fn=cmd_index)
    li = sub.add_parser("list")
    li.add_argument("--kind", default=None, choices=KINDS)
    li.add_argument("--affects", default=None)
    li.set_defaults(fn=cmd_list)
    rl = sub.add_parser("relevant"); rl.add_argument("path"); rl.set_defaults(fn=cmd_relevant)
    lt = sub.add_parser("lint"); lt.set_defaults(fn=cmd_lint)
    pr = sub.add_parser("promote", help="promote a stable lesson into AGENTS.md")
    pr.add_argument("id")
    pr.add_argument("--file", default=None,
                    help="target instructions file (default AGENTS.md, else CLAUDE.md)")
    pr.add_argument("--section", default=None,
                    help="target heading (default: '## Gotchas' for gotcha/failure, "
                         "'## Conventions' for convention/preference)")
    pr.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    pr.set_defaults(fn=cmd_promote)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
