#!/usr/bin/env python3
"""Decision log: record what the agent decided, what it assumed, and re-verify later.

The gap this closes: an agent makes dozens of silent choices per feature — schema
shape, transaction boundary, retry policy, what it decided NOT to handle. Those
choices are invisible in the diff and unrecoverable a month later, so nobody can ask
"was that right?" or "does that still hold?".

Every decision is a file in decisions/ with a machine-readable meta block, a
human-readable rationale, and assumptions that each carry a verification command and
a revisit trigger. The index is a table, regenerated from the files.

    decide.py new  "Session storage" --affects "src/auth/**" --tag backend
    decide.py index                  # regenerate decisions/INDEX.md
    decide.py verify                 # run every assumption's verify command
    decide.py drift                  # decisions whose code changed underneath them
    decide.py trace src/auth/token.ts
    decide.py check                  # index + drift + stale, for CI (exit 1 on problems)

Python stdlib only.
"""
import argparse, datetime, fnmatch, json, pathlib, re, subprocess, sys
import _mutation_guard as mg
import _paths

PLUGIN = pathlib.Path(__file__).resolve().parent.parent

def rel(p):
    """Display path relative to the git root, resilient to a target outside it."""
    return _paths.show(p, ROOT)


# ROOT is the user's git root, not the plugin's directory (records written into the
# installed plugin are invisible to the project and lost on upgrade); decisions live under
# the records root (_paths.py). Outside a repo ROOT falls back to cwd for reads only.
ROOT, IN_GIT_REPO = _paths.git_root()
DIR = _paths.resolve(ROOT)[0] / "decisions"
META_RX = re.compile(r"```json meta\s*\n(.*?)\n```", re.S)
STATUSES = ("proposed", "accepted", "superseded", "rejected", "revisit")


def sh(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def load_all():
    out = []
    if not DIR.exists():
        return out
    for p in sorted(DIR.glob("ADR-*.md")):
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
    ids = [int(m.group(1)) for p in DIR.glob("ADR-*.md")
           if (m := re.match(r"ADR-(\d+)", p.name))]
    return f"ADR-{max(ids, default=0) + 1:04d}"


TEMPLATE = '''# {id}: {title}

```json meta
{meta}
```

## Context

<!-- What forced a decision. One paragraph. What was true at the time that made this
     a choice rather than an obvious default. -->

## Options considered

<!-- One subsection per option. For each: what it is, and the concrete reason it
     was or was not chosen. An option with no stated downside was not really
     considered. `fit` in the meta block is a pass/fail filter applied FIRST: an
     option that does not solve the problem is out, whatever it would score. Only
     fit-passing options are compared; to compare them by number, give each a
     "scores" object (1-5 on reversibility, blast radius, moving parts,
     already-in-use, exit cost -- the approach-selection weights) and the chosen
     one must be the top weighted score or carry an "override_reason". -->

### Option A — <name>
### Option B — <name>

## Decision

<!-- What was chosen, and the single deciding factor. -->

## Consequences

<!-- What this makes easy, and what it makes hard or expensive later. The second
     half is the one people skip and the one that matters. -->

## Gaps accepted

<!-- What this decision deliberately does NOT handle. An agent that records nothing
     here is claiming it thought of everything, which is never true. Each gap needs
     either a follow-up reference or an explicit "accepted, not planned". -->

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
'''


def cmd_new(a):
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "decide.py new", ROOT):
        return 2
    if not dry:
        DIR.mkdir(parents=True, exist_ok=True)
    did = next_id()
    meta = {
        "id": did,
        "title": a.title,
        "status": "proposed",
        "date": datetime.date.today().isoformat(),
        "decided_by": a.by,
        "tags": [t for t in (a.tag or [])],
        "affects": [p for p in (a.affects or [])],
        "commit": sh(["git", "rev-parse", "--short", "HEAD"])[1] or None,
        "assumptions": [
            {"id": "A1", "claim": "<what must be true for this to be the right call>",
             "verify": "<shell command that exits non-zero if it stops being true>",
             "revisit_when": "<the observable event that invalidates this>",
             "confidence": "medium"}
        ],
        "options": [
            {"name": "<option A>", "fit": "<pass|fail>", "chosen": False,
             "why_not": "<concrete reason>"},
            {"name": "<option B>", "fit": "<pass|fail>", "chosen": True,
             "why": "<deciding factor>"}
        ],
        "supersedes": None,
        "revisit_by": None,
    }
    path = DIR / f"{did}-{re.sub(r'[^a-z0-9]+', '-', a.title.lower()).strip('-')}.md"
    new_text = TEMPLATE.format(id=did, title=a.title, meta=json.dumps(meta, indent=2))
    if dry:
        old_text = path.read_text() if path.exists() else ""
        mg.print_diff_or_noop(old_text, new_text, str(rel(path)))
        print(f"[dry-run] would also regenerate {rel(DIR / 'INDEX.md')}; nothing written")
        return 0
    path.write_text(new_text)
    print(f"created {rel(path)}")
    print("Fill in: assumptions (each needs a real verify command), options with "
          "concrete why_not, and the Gaps accepted table.")
    cmd_index(a)
    return 0


def cmd_index(a):
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "decide.py index", ROOT):
        return 2
    recs = load_all()
    if not dry:
        DIR.mkdir(parents=True, exist_ok=True)
    rows, bad = [], []
    for r in recs:
        if r.get("_error"):
            bad.append(r)
            continue
        chosen = next((o.get("name") for o in r.get("options", []) if o.get("chosen")), "—")
        nass = len(r.get("assumptions") or [])
        rows.append((r.get("id", "?"), r.get("title", "?"), r.get("status", "?"),
                     r.get("date", "?"), chosen, nass,
                     ", ".join(r.get("tags") or []) or "—",
                     ", ".join(r.get("affects") or []) or "—",
                     r["_path"].name))
    rows.sort(key=lambda x: x[0])
    out = ["# Decision index", "",
           f"{len(rows)} decision(s). Regenerate with `python3 scripts/decide.py index`.",
           "", "| id | title | status | date | chosen | assumptions | tags | affects |",
           "|---|---|---|---|---|--:|---|---|"]
    for i, t, s, d, c, n, tg, af, fn in rows:
        out.append(f"| [{i}]({fn}) | {t} | {s} | {d} | {c} | {n} | {tg} | `{af}` |")
    if bad:
        out += ["", "## Malformed records", ""]
        out += [f"- `{r['_path'].name}` — {r['_error']}" for r in bad]
    out += ["", "## How to use this", "",
            "- `decide.py verify` runs every assumption's verification command.",
            "- `decide.py drift` lists decisions whose `affects` paths changed since "
            "the decision was recorded — those need re-reading, not just re-running.",
            "- `decide.py trace <path>` says which decisions govern a file.",
            "- A decision is never edited in place once `accepted`; supersede it with a "
            "new record and set `supersedes`.", ""]
    new_text = "\n".join(out)
    if dry:
        old_text = (DIR / "INDEX.md").read_text() if (DIR / "INDEX.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, str(rel(DIR / "INDEX.md")))
        return 1 if bad else 0
    (DIR / "INDEX.md").write_text(new_text)
    print(f"wrote {rel(DIR / 'INDEX.md')} ({len(rows)} decisions"
          + (f", {len(bad)} malformed)" if bad else ")"))
    return 1 if bad else 0


def cmd_verify(a):
    recs = [r for r in load_all() if not r.get("_error")]
    total = failed = skipped = 0
    for r in recs:
        if r.get("status") in ("superseded", "rejected"):
            continue
        for asm in r.get("assumptions") or []:
            cmd = (asm.get("verify") or "").strip()
            total += 1
            if not cmd or cmd.startswith("<"):
                skipped += 1
                print(f"  SKIP  {r['id']}/{asm.get('id')}  no verify command — "
                      f"unverifiable assumption: {asm.get('claim','')[:60]}")
                continue
            # `bash -c`, never `-lc`: a login shell sources the user's profile and
            # its noise ends up reported as the assumption's failure reason.
            rc, out, err = sh(["bash", "-c", cmd])
            if rc == 0:
                print(f"  ok    {r['id']}/{asm.get('id')}  {asm.get('claim','')[:60]}")
            else:
                failed += 1
                print(f"  FAIL  {r['id']}/{asm.get('id')}  {asm.get('claim','')[:60]}")
                print(f"        $ {cmd}")
                print(f"        exit {rc}: {(err or out)[:160]}")
                print(f"        revisit_when: {asm.get('revisit_when','(unstated)')}")
    print(f"\nassumptions: {total} total, {failed} failed, {skipped} unverifiable")
    return 1 if failed else 0


def cmd_drift(a):
    """A decision is stale when the code it governs moved after it was recorded."""
    recs = [r for r in load_all() if not r.get("_error")]
    stale = 0
    today = datetime.date.today()
    for r in recs:
        if r.get("status") in ("superseded", "rejected"):
            continue
        base = r.get("commit")
        affects = r.get("affects") or []
        if base and affects:
            rc, out, _ = sh(["git", "diff", "--name-only", f"{base}..HEAD", "--"] + affects)
            changed = [l for l in out.splitlines() if l]
            if changed:
                stale += 1
                print(f"  DRIFT {r['id']}  {len(changed)} file(s) changed since "
                      f"{base} under {affects}")
                for c in changed[:6]:
                    print(f"        {c}")
                if len(changed) > 6:
                    print(f"        ... {len(changed)-6} more")
                print(f"        -> re-read {r['_path'].name}; supersede it if the "
                      f"decision no longer matches the code")
        rb = r.get("revisit_by")
        if rb:
            try:
                if datetime.date.fromisoformat(rb) < today:
                    stale += 1
                    print(f"  OVERDUE {r['id']}  revisit_by {rb} has passed")
            except Exception:
                pass
    print(f"\n{stale} decision(s) need attention")
    return 1 if stale else 0


def cmd_trace(a):
    recs = [r for r in load_all() if not r.get("_error")]
    hits = []
    for r in recs:
        for pat in r.get("affects") or []:
            if fnmatch.fnmatch(a.path, pat) or a.path.startswith(pat.rstrip("*/")):
                hits.append(r)
                break
    if not hits:
        print(f"no recorded decision governs {a.path}")
        print("If a non-obvious choice was made in this file, it is undocumented.")
        return 0
    print(f"decisions governing {a.path}:\n")
    for r in hits:
        print(f"  {r['id']}  [{r.get('status')}]  {r.get('title')}")
        print(f"       {r['_path'].relative_to(ROOT)}")
        for asm in r.get("assumptions") or []:
            print(f"       assumes {asm.get('id')}: {asm.get('claim','')[:70]}")
    return 0


# approach-selection weights, fit excluded (fit is the pass/fail filter applied first).
# prd.py imports these, so a PRD's options table and the ADR recording the same choice
# cannot score it differently.
WEIGHTS = [("reversibility", 3), ("blast radius", 3), ("moving parts", 2),
           ("already-in-use", 2), ("exit cost", 1)]


def lint_fit(name, opts, override):
    """Apply fit as a pass/fail filter before any weighted comparison. Returns the
    number of errors printed."""
    errs = 0
    fits = {}
    for o in opts:
        f = str(o.get("fit", "")).strip().lower()
        if f not in ("pass", "fail"):
            print(f"  ERROR {name}: option {o.get('name')!r} has fit {o.get('fit')!r} — "
                  f"set \"fit\": \"pass\" or \"fail\" (does it solve the problem at all?)")
            errs += 1
        fits[id(o)] = f
    if opts and fits and not any(f == "pass" for f in fits.values()):
        print(f"  ERROR {name}: no option passes the fit filter — none solves the problem")
        errs += 1
    for o in opts:
        if o.get("chosen") and fits.get(id(o)) == "fail":
            print(f"  ERROR {name}: chosen option {o.get('name')!r} fails the fit filter — "
                  f"it does not solve the problem, whatever it scores")
            errs += 1
    scored = {}
    for o in opts:
        sc = o.get("scores")
        if sc is None:
            continue
        vals = [sc.get(k) if isinstance(sc, dict) else None for k, _ in WEIGHTS]
        if not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 5
                   for v in vals):
            print(f"  ERROR {name}: option {o.get('name')!r} scores must give an integer "
                  f"1-5 for each of {', '.join(k for k, _ in WEIGHTS)}")
            errs += 1
            continue
        total = sum(v * w for v, (_, w) in zip(vals, WEIGHTS))
        if "score" in o and o["score"] != total:
            print(f"  ERROR {name}: option {o.get('name')!r} score {o['score']!r} does not "
                  f"match the recomputed {total}")
            errs += 1
        if fits.get(id(o)) == "pass":
            scored[o.get("name")] = (total, bool(o.get("chosen")))
    if len(scored) >= 2:
        top = max(v[0] for v in scored.values())
        chosen = [(n, v[0]) for n, v in scored.items() if v[1]]
        has_override = isinstance(override, str) and override.strip() \
            and not override.startswith("<")
        if chosen and chosen[0][1] < top and not has_override:
            best = max(scored, key=lambda n: scored[n][0])
            print(f"  ERROR {name}: chosen option {chosen[0][0]!r} ({chosen[0][1]}) is not "
                  f"the top fit-passing score ({best!r}, {top}) and no override_reason is "
                  f"recorded")
            errs += 1
    return errs


def cmd_lint(a):
    """Reject a decision record that documents a choice without documenting the choosing.

    The common failure is a record that names the winner and nothing else: no rejected
    options, no reason they lost, no assumption that could later be falsified. That is
    a conclusion, not a decision — it cannot be re-evaluated, which is the only reason
    to write it down.
    """
    recs = load_all()
    errs = 0
    for r in recs:
        p_ = r.get("_path")
        name = p_.name if p_ else "?"
        if r.get("_error"):
            print(f"  ERROR {name}: {r['_error']}"); errs += 1; continue
        if r.get("status") not in STATUSES:
            print(f"  ERROR {name}: status {r.get('status')!r} not in {STATUSES}"); errs += 1
        opts = r.get("options") or []
        chosen = [o for o in opts if o.get("chosen")]
        if len(opts) < 2:
            print(f"  ERROR {name}: {len(opts)} option(s) recorded — a decision with one "
                  f"option is not a decision"); errs += 1
        if len(chosen) != 1:
            print(f"  ERROR {name}: {len(chosen)} options marked chosen, expected exactly 1")
            errs += 1
        errs += lint_fit(name, opts, r.get("override_reason"))
        for o in opts:
            if o.get("chosen"):
                if not (o.get("why") or "").strip() or (o.get("why") or "").startswith("<"):
                    print(f"  ERROR {name}: chosen option {o.get('name')!r} has no `why` "
                          f"(the deciding factor)"); errs += 1
            else:
                if not (o.get("why_not") or "").strip() or (o.get("why_not") or "").startswith("<"):
                    print(f"  ERROR {name}: rejected option {o.get('name')!r} has no "
                          f"`why_not` — it was listed, not considered"); errs += 1
        asms = r.get("assumptions") or []
        if not asms:
            print(f"  ERROR {name}: no assumptions recorded — every decision rests on "
                  f"something that could stop being true"); errs += 1
        for asm in asms:
            if not (asm.get("claim") or "").strip() or (asm.get("claim") or "").startswith("<"):
                print(f"  ERROR {name}: assumption {asm.get('id')} has no claim"); errs += 1
            if not (asm.get("revisit_when") or "").strip() or \
               (asm.get("revisit_when") or "").startswith("<"):
                print(f"  ERROR {name}: assumption {asm.get('id')} has no `revisit_when` — "
                      f"nothing will ever prompt a re-check"); errs += 1
        if "## Gaps accepted" in (r.get("_body") or "") and \
           "| gap |" in (r.get("_body") or ""):
            body = r["_body"].split("## Gaps accepted", 1)[1]
            rows = [l for l in body.splitlines()
                    if l.startswith("|") and not set(l) <= set("|-: ")
                    and "| gap |" not in l]
            if not rows:
                print(f"  WARN  {name}: Gaps accepted table is empty — claiming nothing "
                      f"was left unhandled")
    print(f"\ndecide lint: {len(recs)} record(s), {errs} error(s)")
    return 1 if errs else 0


def cmd_check(a):
    rc = 0
    print("=== lint ===");   rc |= cmd_lint(a)
    print("\n=== index ==="); rc |= cmd_index(a)
    print("\n=== drift ==="); rc |= cmd_drift(a)
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("title")
    n.add_argument("--affects", action="append", help="glob of code this governs (repeatable)")
    n.add_argument("--tag", action="append")
    n.add_argument("--by", default="claude")
    n.add_argument("--dry-run", action="store_true",
                    help="print what would be created; write nothing")
    n.set_defaults(fn=cmd_new)
    for name, fn in (("verify", cmd_verify),
                     ("drift", cmd_drift), ("check", cmd_check), ("lint", cmd_lint)):
        p = sub.add_parser(name); p.set_defaults(fn=fn)
    ix = sub.add_parser("index")
    ix.add_argument("--dry-run", action="store_true",
                     help="print the index diff; write nothing")
    ix.set_defaults(fn=cmd_index)
    t = sub.add_parser("trace"); t.add_argument("path"); t.set_defaults(fn=cmd_trace)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
