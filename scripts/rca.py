#!/usr/bin/env python3
"""Root-cause analysis records: create, index, lint, and link to the decision log.

The gap this closes: a bug gets fixed, the fix ships, and the *why* evaporates —
symptom and root cause were the same paragraph, nobody wrote down what would have
caught it sooner, and the regression test (if one exists at all) lives only in CI
history, disconnected from the reasoning that produced it.

The backbone finding this implements is the fuzz-finding -> regression-test loop
that OSS-Fuzz itself prescribes: commit the crash/bug input as a permanent corpus
entry and make replaying it a normal test-suite target — no fuzzing infrastructure
required to adopt the pattern, a bug reporter's repro works exactly like a fuzzer's
crash file (`google/oss-fuzz@2cc3fa4:docs/advanced-topics/ideal_integration.md`,
concretely realised in `sqlite/sqlite@86876d2:test/fuzzcheck.c`'s in-tree corpus).
`lint` refuses to pass a record with no `regression_test` reference for exactly
this reason — the test is the actual deliverable, everything else here exists to
produce it honestly.

Every RCA is a file in rca/ with a machine-readable meta block (same shape as
decide.py's ADR meta) separating symptom / trigger / mechanism / root cause, a
falsifiable hypothesis list, an honest five-whys chain, contributing factors, and
a regression-test reference. `link` records when an existing decision's assumption
turned out to be the root cause — the connection to decide.py is deliberate: a
decision whose assumption silently stopped holding is a classic root cause, and
`decide.py drift` is one of the tools used to find it.

    rca.py new "Sessions dropped after deploy" --affects "src/auth/**" --severity high
    rca.py index                                  # regenerate rca/INDEX.md
    rca.py lint                                    # completeness gate
    rca.py link RCA-0001 --decision ADR-0001       # record an assumption was violated

Python stdlib only.
"""
import argparse, datetime, json, pathlib, re, subprocess, sys
import _mutation_guard as mg

PLUGIN = pathlib.Path(__file__).resolve().parent.parent


def project_root():
    """Where the USER's rca/ records live: the git root of the current directory,
    not the plugin's own directory.

    Resolving these against the plugin root meant a consumer project's records were
    written into the installed plugin — invisible to their repo and lost on upgrade.

    Returns (root, in_git_repo); see plan_feature.py's project_root for why.
    """
    import subprocess
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return pathlib.Path(r.stdout.strip()), True
    return pathlib.Path.cwd(), False


def rel(p):
    """Display path, resilient to a target outside ROOT.

    `Path.relative_to` raises rather than degrading, and symlinked temp dirs
    (/tmp vs /private/tmp on macOS) make that a real crash, not a corner case.
    """
    try:
        return pathlib.Path(p).resolve().relative_to(ROOT.resolve())
    except Exception:
        return pathlib.Path(p)


ROOT, IN_GIT_REPO = project_root()
DIR = ROOT / "rca"
META_RX = re.compile(r"```json meta\s*\n(.*?)\n```", re.S)
STATUSES = ("open", "root-caused", "fixed", "closed", "wontfix")


def sh(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def blank(s):
    """True for missing, empty, or still-template-placeholder text ('<...>')."""
    s = (s or "").strip()
    return not s or s.startswith("<")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def load_all():
    out = []
    if not DIR.exists():
        return out
    for p in sorted(DIR.glob("RCA-*.md")):
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
    ids = [int(m.group(1)) for p in DIR.glob("RCA-*.md")
           if (m := re.match(r"RCA-(\d+)", p.name))]
    return f"RCA-{max(ids, default=0) + 1:04d}"


TEMPLATE = '''# {id}: {title}

```json meta
{meta}
```

## Symptom

<!-- What was observed -- the user-visible or monitoring-visible effect. Not the cause. -->

## Trigger

<!-- The immediate event that set it off. Most "root cause analyses" stop here -- a
     trigger is necessary but never sufficient. -->

## Mechanism

<!-- How the trigger actually produces the symptom, step by step. If you cannot narrate
     this chain, you have a plausible story, not a diagnosis. -->

## Root cause

<!-- The underlying condition that made the trigger capable of causing this. Must not
     restate the symptom or the trigger -- `rca.py lint` rejects a root cause identical
     to the symptom. -->

## Timeline

<!-- Reconstructed from `git log`, `git bisect`, deploy times, and `decide.py drift`. A
     decision whose assumption silently stopped holding is a classic root cause -- check
     it explicitly, that is why `rca.py link` exists. -->

## Reproduction

<!-- The exact command run BEFORE reading code, and watched fail. An unreproduced bug is
     a guess. -->

## Hypotheses

<!-- One per candidate cause. State what evidence would falsify each BEFORE going to get
     it. Reject the first-plausible-cause trap. -->

## Five whys

<!-- Honest chain, >=2 real levels, with a stated stop condition. Known failure mode:
     forcing a single causal chain when the real incident had several contributing
     factors running in parallel -- see the next section. -->

## Contributing factors vs root cause

<!-- Conditions that made this worse or more likely without themselves being the root
     cause. An empty section here is a claim that the root cause acted completely alone,
     which is rarely true. -->

## Regression test

<!-- The permanent test that would have caught this. This is the actual deliverable of
     an RCA -- everything above exists to produce this one committed artifact. -->

## Decision links

<!-- Does an existing decision (`decisions/ADR-*`) rest on an assumption this incident
     violated? Record it with `python3 scripts/rca.py link {id} --decision ADR-000X`. -->

## Blameless framing

<!-- This record explains the system and process that allowed the bug, not who wrote it.
     No blame language, no names attached to the cause. If the honest answer involves a
     person's mistake, the finding is the process gap that let the mistake ship. -->
'''


def cmd_new(a):
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "rca.py new", ROOT):
        return 2
    if not dry:
        DIR.mkdir(parents=True, exist_ok=True)
    rid = next_id()
    meta = {
        "id": rid,
        "title": a.title,
        "status": "open",
        "severity": a.severity,
        "date": datetime.date.today().isoformat(),
        "reported_by": a.by,
        "tags": [t for t in (a.tag or [])],
        "affects": [p for p in (a.affects or [])],
        "commit": sh(["git", "rev-parse", "--short", "HEAD"])[1] or None,
        "symptom": "<what was observed -- the user-visible or monitoring-visible effect>",
        "trigger": "<the immediate event that set it off -- a deploy, an input, a config change>",
        "mechanism": "<how the trigger produces the symptom, mechanically, step by step -- "
                     "most RCAs stop before writing this>",
        "root_cause": "<the underlying condition that let the trigger cause this -- must "
                       "differ from the symptom>",
        "reproduction": {
            "command": "<shell command that reliably reproduces the bug -- exits non-zero "
                       "while the bug exists>",
            "verified": False,
        },
        "timeline": [
            {"when": "<ISO timestamp, commit sha, or deploy id>", "event": "<what happened>"}
        ],
        "hypotheses": [
            {"id": "H1", "claim": "<candidate cause>",
             "falsify_with": "<what evidence would rule this OUT -- go get it before believing it>",
             "result": "pending"}
        ],
        "five_whys": [
            {"level": 1, "why": "<why did the symptom happen>", "because": "<answer>"},
            {"level": 2, "why": "<why was that true>", "because": "<answer>"},
        ],
        "stop_condition": "<why the chain stopped here -- e.g. 'reached an accepted "
                          "tradeoff, not a bug' -- not just 'ran out of time'>",
        "contributing_factors": [
            "<a condition that made this worse or more likely, without itself being the root cause>"
        ],
        "regression_test": "<path to the committed test that reproduces this and now passes>",
        "decision_links": [],
        "revisit_by": None,
    }
    path = DIR / f"{rid}-{re.sub(r'[^a-z0-9]+', '-', a.title.lower()).strip('-')}.md"
    new_text = TEMPLATE.format(id=rid, title=a.title, meta=json.dumps(meta, indent=2))
    if dry:
        old_text = path.read_text() if path.exists() else ""
        mg.print_diff_or_noop(old_text, new_text, str(rel(path)))
        print(f"[dry-run] would also regenerate rca/INDEX.md; nothing written")
        return 0
    path.write_text(new_text)
    print(f"created {rel(path)}")
    print("Reproduce first, and see it fail, before reading code. Then fill: timeline, "
          ">=1 falsifiable hypothesis, five whys (>=2 real levels), contributing factors, "
          "a root cause that differs from the symptom, and the regression test path once "
          "the fix lands.")
    cmd_index(a)
    return 0


def cmd_index(a):
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "rca.py index", ROOT):
        return 2
    recs = load_all()
    if not dry:
        DIR.mkdir(parents=True, exist_ok=True)
    rows, bad = [], []
    for r in recs:
        if r.get("_error"):
            bad.append(r)
            continue
        nhyp = len(r.get("hypotheses") or [])
        has_test = "yes" if not blank(r.get("regression_test")) else "no"
        nlinks = len(r.get("decision_links") or [])
        rows.append((r.get("id", "?"), r.get("title", "?"), r.get("status", "?"),
                     r.get("severity", "?"), r.get("date", "?"), nhyp, has_test, nlinks,
                     ", ".join(r.get("tags") or []) or "—",
                     ", ".join(r.get("affects") or []) or "—",
                     r["_path"].name))
    rows.sort(key=lambda x: x[0])
    out = ["# RCA index", "",
           f"{len(rows)} record(s). Regenerate with `python3 scripts/rca.py index`.",
           "",
           "| id | title | status | severity | date | hypotheses | regression test | "
           "decision links | tags | affects |",
           "|---|---|---|---|---|--:|---|--:|---|---|"]
    for i, t, s, sev, d, nh, ht, nl, tg, af, fn in rows:
        out.append(f"| [{i}]({fn}) | {t} | {s} | {sev} | {d} | {nh} | {ht} | {nl} | {tg} | `{af}` |")
    if bad:
        out += ["", "## Malformed records", ""]
        out += [f"- `{r['_path'].name}` — {r['_error']}" for r in bad]
    out += ["", "## How to use this", "",
            "- `rca.py lint` is the completeness gate: no reproduction, no falsifiable "
            "hypothesis, root cause identical to the symptom, no timeline, fewer than 2 "
            "real five-whys levels, empty contributing factors, or no regression test "
            "reference all fail it.",
            "- `rca.py link RCA-0001 --decision ADR-0001` records that an existing "
            "decision's assumption was checked against this incident — a decision whose "
            "assumption silently stopped holding is a classic root cause.",
            "- Cross-check the timeline against `python3 scripts/decide.py drift`.", ""]
    new_text = "\n".join(out)
    if dry:
        old_text = (DIR / "INDEX.md").read_text() if (DIR / "INDEX.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, "rca/INDEX.md")
        return 1 if bad else 0
    (DIR / "INDEX.md").write_text(new_text)
    print(f"wrote rca/INDEX.md ({len(rows)} record(s)"
          + (f", {len(bad)} malformed)" if bad else ")"))
    return 1 if bad else 0


def cmd_lint(a):
    """Reject an RCA record that names a root cause without earning it.

    The common failure this catches is a "postmortem" that restates the trigger as the
    root cause, cites no falsifiable hypothesis (so the "cause" was never actually
    tested against alternatives), and ships no regression test — meaning the incident
    can recur and nothing will fail. That is a symptom description wearing an RCA's
    clothes.
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

        repro = r.get("reproduction") or {}
        if blank(repro.get("command")):
            print(f"  ERROR {name}: no reproduction recorded — an unreproduced bug is a "
                  f"guess"); errs += 1

        for field in ("symptom", "trigger", "mechanism"):
            if blank(r.get(field)):
                print(f"  ERROR {name}: no {field} recorded"); errs += 1

        root_cause = r.get("root_cause")
        if blank(root_cause):
            print(f"  ERROR {name}: no root cause recorded"); errs += 1
        elif norm(root_cause) == norm(r.get("symptom")):
            print(f"  ERROR {name}: root cause is identical to the symptom — this stopped "
                  f"at the trigger, not the cause"); errs += 1

        timeline = [t for t in (r.get("timeline") or []) if not blank(t.get("event"))]
        if not timeline:
            print(f"  ERROR {name}: no timeline recorded — reconstruct it from git log, "
                  f"git bisect, deploy times, or decide.py drift"); errs += 1

        hyps = r.get("hypotheses") or []
        real_hyps = [h for h in hyps if not blank(h.get("claim"))]
        if not real_hyps:
            print(f"  ERROR {name}: no hypotheses recorded"); errs += 1
        else:
            falsifiable = [h for h in real_hyps if not blank(h.get("falsify_with"))]
            if not falsifiable:
                print(f"  ERROR {name}: no hypothesis states falsifying evidence — a "
                      f"hypothesis nobody could reject is a guess that happened to be "
                      f"first"); errs += 1

        whys = [w for w in (r.get("five_whys") or [])
                if not blank(w.get("why")) and not blank(w.get("because"))]
        if len(whys) < 2:
            print(f"  ERROR {name}: five-whys has {len(whys)} real level(s), need >= 2"); errs += 1

        cfactors = [c for c in (r.get("contributing_factors") or []) if not blank(c)]
        if not cfactors:
            print(f"  ERROR {name}: contributing-factors section is empty — claiming the "
                  f"root cause acted completely alone"); errs += 1

        if blank(r.get("regression_test")):
            print(f"  ERROR {name}: no regression test reference — the test is the actual "
                  f"deliverable of an RCA"); errs += 1

        links = r.get("decision_links") or []
        if not links:
            print(f"  WARN  {name}: no decision link recorded — confirm no existing "
                  f"decision's assumption was silently violated (see `decide.py drift`, "
                  f"`rca.py link`)")
    print(f"\nrca lint: {len(recs)} record(s), {errs} error(s)")
    return 1 if errs else 0


def cmd_link(a):
    """Record that an existing decision's assumption was checked against this incident."""
    recs = {r.get("id"): r for r in load_all() if not r.get("_error")}
    r = recs.get(a.id)
    if not r:
        print(f"no such RCA record: {a.id}")
        return 2
    path = r["_path"]
    text = path.read_text()
    m = META_RX.search(text)
    if not m:
        print(f"{path.name}: no ```json meta block — cannot link")
        return 1
    meta = json.loads(m.group(1))
    entry = {"decision": a.decision, "assumption": a.assumption, "status": a.status,
              "note": a.note or ""}
    meta.setdefault("decision_links", []).append(entry)
    new_block = "```json meta\n" + json.dumps(meta, indent=2) + "\n```"
    new_text = text[:m.start()] + new_block + text[m.end():]

    if getattr(a, "dry_run", False):
        mg.print_diff_or_noop(text, new_text, str(rel(path)))
        return 0
    if mg.require_git_root(IN_GIT_REPO, "rca.py link", ROOT):
        return 2
    path.write_text(new_text)

    adr_dir = ROOT / "decisions"
    hits = list(adr_dir.glob(f"{a.decision}*.md")) if adr_dir.exists() else []
    if not hits:
        print(f"warning: no decision record found for {a.decision} under decisions/ — "
              f"link recorded anyway")
    print(f"linked {a.id} -> {a.decision}"
          + (f" ({a.assumption})" if a.assumption else "")
          + f" [{a.status}]")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("title")
    n.add_argument("--affects", action="append", help="glob of code this governs (repeatable)")
    n.add_argument("--severity", choices=["low", "medium", "high", "critical"], default="medium")
    n.add_argument("--tag", action="append")
    n.add_argument("--by", default="claude")
    n.add_argument("--dry-run", action="store_true",
                    help="print what would be created; write nothing")
    n.set_defaults(fn=cmd_new)
    p = sub.add_parser("lint"); p.set_defaults(fn=cmd_lint)
    ix = sub.add_parser("index")
    ix.add_argument("--dry-run", action="store_true",
                     help="print the index diff; write nothing")
    ix.set_defaults(fn=cmd_index)
    l = sub.add_parser("link"); l.add_argument("id")
    l.add_argument("--decision", required=True, help="ADR id, e.g. ADR-0001")
    l.add_argument("--assumption", default=None, help="assumption id within that ADR, e.g. A1")
    l.add_argument("--status", choices=["violated", "held", "unknown"], default="violated")
    l.add_argument("--note", default="")
    l.add_argument("--dry-run", action="store_true",
                    help="print the diff that would be written; write nothing")
    l.set_defaults(fn=cmd_link)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
