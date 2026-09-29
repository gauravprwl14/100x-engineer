#!/usr/bin/env python3
"""Project-level learning: lessons that outlive the conversation that produced them.

The gap this closes: a mistake costs an hour, gets fixed, and the fix lives only in
the transcript that produced it -- gone the moment the session ends, invisible to the
next agent (or the next session of the same agent) that hits the same wall. This
plugin already has a project-level store for decisions (`decisions/`), specs
(`specs/`) and root causes (`rca/`); nothing accumulated lessons into it, and Claude
Code's own memory is a separate mechanism this plugin does not write to.

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
    learn.py lint                     # rejects an unattached or unfalsifiable lesson

Python stdlib only.
"""
import argparse, datetime, fnmatch, json, pathlib, re, sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent

def project_root():
    """Where the USER's lessons/ live: the git root of the current directory, not
    the plugin's own directory. Copied from decide.py -- see its docstring for why
    resolving against the plugin root is the wrong default.
    """
    import subprocess
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return pathlib.Path(r.stdout.strip())
    return pathlib.Path.cwd()



def rel(p):
    """Display path, resilient to a target outside ROOT.

    `Path.relative_to` raises rather than degrading, and symlinked temp dirs
    (/tmp vs /private/tmp on macOS) make that a real crash, not a corner case.
    """
    try:
        return pathlib.Path(p).resolve().relative_to(ROOT.resolve())
    except Exception:
        return pathlib.Path(p)


ROOT = project_root()
DIR = ROOT / "lessons"
META_RX = re.compile(r"```json meta\s*\n(.*?)\n```", re.S)
KINDS = ("gotcha", "convention", "failure", "preference")
TRIGGER_RX = re.compile(r"\b(when|if|before|after|during|until)\b", re.I)
MIN_LESSON_CHARS = 15


def load_all():
    out = []
    if not DIR.exists():
        return out
    for p in sorted(DIR.glob("LESSON-*.md")):
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
    ids = [int(m.group(1)) for p in DIR.glob("LESSON-*.md")
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
                     r.get("source") or "—", r.get("date", "?"), r["_path"].name))
    rows.sort(key=lambda x: x[0])
    out = ["# Lesson index", "",
           f"{len(rows)} lesson(s). Regenerate with `python3 scripts/learn.py index`.",
           "", "| id | kind | lesson | affects | source | date |",
           "|---|---|---|---|---|---|"]
    for i, k, t, af, src, d, fn in rows:
        out.append(f"| [{i}]({fn}) | {k} | {t} | `{af}` | {src} | {d} |")
    if bad:
        out += ["", "## Malformed records", ""]
        out += [f"- `{r['_path'].name}` — {r['_error']}" for r in bad]
    out += ["", "## How to use this", "",
            "- `learn.py relevant <path>` — lessons that apply before editing a file.",
            "- `learn.py list --kind gotcha` — browse by kind.",
            "- `learn.py lint` — every lesson is attached (affects or source) and, "
            "if a preference, states an observable trigger.", ""]
    (DIR / "INDEX.md").write_text("\n".join(out))
    print(f"wrote lessons/INDEX.md ({len(rows)} lesson(s)"
          + (f", {len(bad)} malformed)" if bad else ")"))
    return 1 if bad else 0


def cmd_list(a):
    recs = [r for r in load_all() if not r.get("_error")]
    if a.kind:
        recs = [r for r in recs if r.get("kind") == a.kind]
    if a.affects:
        recs = [r for r in recs
                if any(fnmatch.fnmatch(a.affects, pat) or a.affects.startswith(pat.rstrip("*/"))
                       for pat in (r.get("affects") or []))]
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
    hits = []
    for r in recs:
        for pat in r.get("affects") or []:
            if fnmatch.fnmatch(a.path, pat) or a.path.startswith(pat.rstrip("*/")):
                hits.append(r)
                break
    if not hits:
        print(f"no recorded lesson affects {a.path}")
        return 0
    print(f"{len(hits)} lesson(s) apply to {a.path}:\n")
    for r in hits:
        print(f"  {r['id']}  [{r.get('kind')}]  {r.get('lesson','')[:140]}")
        if r.get("source"):
            print(f"       source: {r['source']}")
    return 0


def cmd_lint(a):
    """Reject a lesson that will never be recalled or never be falsified.

    Two failure modes: a lesson with no `affects` and no `source` is unattached --
    `relevant` will never surface it and nothing points at where it came from, so it
    is functionally a lesson nobody will ever read again. A `preference` with no
    observable trigger (no when/if/before/after) is an opinion, not a lesson -- it
    gives an agent nothing to notice at the moment it would matter.
    """
    recs = load_all()
    errs = 0
    for r in recs:
        p_ = r.get("_path")
        name = p_.name if p_ else "?"
        if r.get("_error"):
            print(f"  ERROR {name}: {r['_error']}"); errs += 1; continue
        if r.get("kind") not in KINDS:
            print(f"  ERROR {name}: kind {r.get('kind')!r} not in {KINDS}"); errs += 1
        lesson = (r.get("lesson") or "").strip()
        if len(lesson) < MIN_LESSON_CHARS or lesson.startswith("<"):
            print(f"  ERROR {name}: lesson text is empty or a placeholder"); errs += 1
        if not (r.get("affects") or []) and not (r.get("source") or "").strip():
            print(f"  ERROR {name}: no `affects` glob and no `source` — this lesson "
                  f"is unattached, `learn.py relevant` will never surface it"); errs += 1
        if r.get("kind") == "preference" and not TRIGGER_RX.search(lesson):
            print(f"  ERROR {name}: preference has no observable trigger "
                  f"(when/if/before/after/...) — this reads as an opinion, not a "
                  f"lesson an agent can act on at the moment it matters"); errs += 1
    print(f"\nlearn lint: {len(recs)} record(s), {errs} error(s)")
    return 1 if errs else 0


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
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
