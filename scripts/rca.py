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
falsifiable hypothesis list, an honest five-whys chain (or a fault tree when
several causes combined), contributing factors, and a regression-test reference.

Incident fields follow the postmortem practice in Google's SRE book, ch. 15
"Postmortem Culture: Learning from Failure"
(https://sre.google/sre-book/postmortem-culture/) and the SRE workbook's
"Postmortem Culture" chapter (https://sre.google/workbook/postmortem-culture/):
quantified impact, a timeline, "where we got lucky", and action items that each
carry an owner and are tracked. Severity is an enum, SEV1-SEV4, adapted from
PagerDuty's published levels (https://response.pagerduty.com/before/severity_levels/,
source `PagerDuty/incident-response-docs`), with its SEV-5 folded into SEV4.
`lint` rejects a free-text severity, missing impact, a timestamp that is not
ISO-8601 with a timezone, and an action item with no owner, due date or type. `link` records when an existing decision's assumption
turned out to be the root cause — the connection to decide.py is deliberate: a
decision whose assumption silently stopped holding is a classic root cause, and
`decide.py drift` is one of the tools used to find it.

    rca.py new "Sessions dropped after deploy" --affects "src/auth/**" --severity SEV2
    rca.py durations [RCA-0001]                   # detection -> mitigation -> resolution
    rca.py index                                  # regenerate rca/INDEX.md
    rca.py lint                                    # completeness gate
    rca.py link RCA-0001 --decision ADR-0001       # record an assumption was violated

Python stdlib only.
"""
import argparse, datetime, json, pathlib, re, subprocess, sys
import _mutation_guard as mg
import _paths

PLUGIN = pathlib.Path(__file__).resolve().parent.parent


def rel(p):
    """Display path relative to the git root, resilient to a target outside it."""
    return _paths.show(p, ROOT)


# ROOT is the user's git root, not the plugin's directory (records written into the
# installed plugin are invisible to the project and lost on upgrade); RCA records live under
# the records root (_paths.py). Outside a repo ROOT falls back to cwd for reads only.
ROOT, IN_GIT_REPO = _paths.git_root()
DIR = _paths.resolve(ROOT)[0] / "rca"
META_RX = re.compile(r"```json meta\s*\n(.*?)\n```", re.S)
STATUSES = ("open", "root-caused", "fixed", "closed", "wontfix")
SEVERITIES = {
    "SEV1": "critical: broad outage, data loss or a security breach; warrants executive "
            "and public communication",
    "SEV2": "major: a core function unavailable or badly degraded for many users",
    "SEV3": "minor: limited or partial impact, a workaround exists; needs prompt owner "
            "attention",
    "SEV4": "low: no user-facing impact, a near miss, or cosmetic",
}
# `new` still accepts the old words so existing commands keep working; the record
# itself always stores the enum.
LEGACY_SEVERITY = {"critical": "SEV1", "high": "SEV2", "medium": "SEV3", "low": "SEV4"}
EVENT_TYPES = ("started", "detected", "escalated", "mitigated", "resolved", "note")
ACTION_TYPES = ("prevent", "detect", "mitigate")
IMPACT_FIELDS = ("users_affected", "duration_minutes", "data_impact", "revenue_or_sla_impact")
ISO_TZ_RX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$")
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Heuristic only, so it warns: phrasing that names a person's failing instead of the
# system gap that let it ship (SRE book ch. 15, "blameless").
BLAME_RX = re.compile(r"\b(human error|should have|careless\w*|negligen\w*|forgot|"
                      r"failed to notice|(?:his|her|their) fault|incompeten\w*|sloppy|"
                      r"didn't bother|lazy)\b", re.I)


def sh(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def blank(s):
    """True for missing, empty, or still-template-placeholder text ('<...>')."""
    s = (s or "").strip()
    return not s or s.startswith("<")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def parse_ts(s):
    """A timezone-aware datetime, or None when `s` is not ISO-8601 with an offset."""
    if not isinstance(s, str) or not ISO_TZ_RX.match(s.strip()):
        return None
    try:
        return datetime.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def first_event(timeline, kind):
    ts = [parse_ts(e.get("at", e.get("when"))) for e in timeline
          if isinstance(e, dict) and e.get("type") == kind]
    ts = [x for x in ts if x]
    return min(ts) if ts else None


def durations(r):
    """Minutes between the first event of each type; None where an end is missing."""
    tl = r.get("timeline") or []
    ev = {k: first_event(tl, k) for k in ("started", "detected", "mitigated", "resolved")}

    def mins(a, b):
        return round((ev[b] - ev[a]).total_seconds() / 60, 1) if ev[a] and ev[b] else None
    return {
        "time_to_detect": mins("started", "detected"),
        "time_to_mitigate": mins("detected", "mitigated"),
        "time_to_resolve": mins("detected", "resolved"),
        "impact_window": mins("started", "resolved") if ev["started"] else None,
    }


def fault_leaves(node, errs, depth=0):
    """Leaf causes of a fault tree; appends structural problems to errs."""
    if not isinstance(node, dict) or blank(node.get("event")):
        errs.append("fault-tree node has no event")
        return 0
    kids = node.get("children") or []
    if not kids:
        return 1
    if node.get("gate") not in ("AND", "OR"):
        errs.append(f"fault-tree node {node.get('event')!r} has children but gate "
                    f"{node.get('gate')!r} is not AND/OR")
    return sum(fault_leaves(k, errs, depth + 1) for k in kids)


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if not k.startswith("_"):
                yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


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

## Impact and severity

<!-- `impact` in the meta block: users_affected, duration_minutes, data_impact,
     revenue_or_sla_impact. Estimates are fine and say so; "unknown" is not. Severity
     is SEV1-SEV4 (see `rca.py new --help`), never a free-text word. -->

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

<!-- Typed events in the meta block: {{"at": ISO-8601 WITH timezone, "type":
     started|detected|escalated|mitigated|resolved|note, "event": "..."}}. `rca.py
     durations` computes time to detect, mitigate and resolve from them. Reconstruct
     from alerts, chat, `git log`, `git bisect`, deploy times and `decide.py drift`; a
     commit sha goes in the event text, not in `at`. -->

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

## Fault tree (when several causes combined)

<!-- Optional instead of five whys: {{"event": top event, "gate": "AND"|"OR",
     "children": [...]}}. Use it when the incident needed several conditions at once;
     forcing those into one five-whys chain hides all but one of them. -->

## Contributing factors vs root cause

<!-- Conditions that made this worse or more likely without themselves being the root
     cause. An empty section here is a claim that the root cause acted completely alone,
     which is rarely true. -->

## Where we got lucky

<!-- Things that limited the damage by chance, not by design. Each one is a latent
     failure waiting for a less lucky day, and usually deserves an action item. -->

## Action items

<!-- Each: {{"what", "owner", "due": YYYY-MM-DD, "type": prevent|detect|mitigate,
     "ticket"}}. An item with no owner is a wish; `rca.py lint` rejects it. -->

## Regression test

<!-- The permanent test that would have caught this. This is the actual deliverable of
     an RCA -- everything above exists to produce this one committed artifact. -->

## Decision links

<!-- Does an existing decision (`decisions/ADR-*`) rest on an assumption this incident
     violated? Record it with `python3 scripts/rca.py link {id} --decision ADR-000X`. -->

## Blameless framing

<!-- This record explains the system and process that allowed the bug, not who wrote it.
     Assume everyone acted in good faith on the information they had. Write "the deploy
     pipeline has no canary stage", not "X pushed without checking". `rca.py lint` warns
     on phrases like "human error" or "should have". -->
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
        "severity": LEGACY_SEVERITY.get(a.severity, a.severity),
        "date": datetime.date.today().isoformat(),
        "reported_by": a.by,
        "tags": [t for t in (a.tag or [])],
        "affects": [p for p in (a.affects or [])],
        "commit": sh(["git", "rev-parse", "--short", "HEAD"])[1] or None,
        "impact": {
            "users_affected": "<count or bounded estimate, e.g. 1200 or '~5% of EU users'>",
            "duration_minutes": "<number: user-visible impact start to resolution>",
            "data_impact": "<none | delayed | corrupted | lost -- and how much>",
            "revenue_or_sla_impact": "<SLO budget burned, SLA credits, lost orders, or none>",
        },
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
            {"at": "<ISO-8601 with timezone, e.g. 2026-09-28T14:02:00Z>",
             "type": "detected", "event": "<what happened>"}
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
        "fault_tree": None,
        "lucky": ["<what limited the damage by chance rather than by design>"],
        "action_items": [
            {"what": "<specific, verifiable change>", "owner": "<one person or team>",
             "due": "<YYYY-MM-DD>", "type": "<prevent|detect|mitigate>",
             "ticket": "<tracker id or URL>"}
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
        print(f"[dry-run] would also regenerate {rel(DIR / 'INDEX.md')}; nothing written")
        return 0
    path.write_text(new_text)
    print(f"created {rel(path)}")
    if a.severity in LEGACY_SEVERITY:
        print(f"severity {a.severity!r} recorded as {meta['severity']} "
              f"({SEVERITIES[meta['severity']]})")
    print("Reproduce first, and see it fail, before reading code. Then fill: impact, a "
          "typed timeline with timezone-aware timestamps, >=1 falsifiable hypothesis, five "
          "whys (>=2 real levels) or a fault tree, contributing factors, where you got "
          "lucky, action items with owner/due/type, a root cause that differs from the "
          "symptom, and the regression test path once the fix lands.")
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
        has_test = "yes" if not blank(r.get("regression_test")) else "no"
        d = durations(r)
        fmt = lambda v: "—" if v is None else f"{v:g}m"
        rows.append((r.get("id", "?"), r.get("title", "?"), r.get("status", "?"),
                     r.get("severity", "?"), r.get("date", "?"),
                     fmt(d["time_to_mitigate"]), fmt(d["time_to_resolve"]),
                     len(r.get("action_items") or []), has_test,
                     len(r.get("decision_links") or []),
                     ", ".join(r.get("affects") or []) or "—", r["_path"].name))
    rows.sort(key=lambda x: x[0])
    out = ["# RCA index", "",
           f"{len(rows)} record(s). Regenerate with `100x rca index`.", "",
           "| id | title | status | severity | date | time to mitigate | time to resolve | "
           "action items | regression test | decision links | affects |",
           "|---|---|---|---|---|--:|--:|--:|---|--:|---|"]
    for i, t_, s, sev, d_, ttm, ttr, nai, ht, nl, af, fn in rows:
        out.append(f"| [{i}]({fn}) | {t_} | {s} | {sev} | {d_} | {ttm} | {ttr} | {nai} | "
                   f"{ht} | {nl} | `{af}` |")
    if bad:
        out += ["", "## Malformed records", ""]
        out += [f"- `{r['_path'].name}` — {r['_error']}" for r in bad]
    out += ["", "## How to use this", "",
            "- `rca.py lint` is the completeness gate: free-text severity, missing impact, "
            "a timestamp without a timezone, an action item with no owner/due/type, no "
            "reproduction, no falsifiable hypothesis, root cause identical to the symptom, "
            "fewer than 2 five-whys levels and no fault tree, empty contributing factors, "
            "or no regression test reference all fail it.",
            "- Severity: " + "; ".join(f"{k} {v}" for k, v in SEVERITIES.items()) + ".",
            "- `rca.py link RCA-0001 --decision ADR-0001` records that an existing "
            "decision's assumption was checked against this incident — a decision whose "
            "assumption silently stopped holding is a classic root cause.",
            "- Cross-check the timeline against `python3 scripts/decide.py drift`.", ""]
    new_text = "\n".join(out)
    if dry:
        old_text = (DIR / "INDEX.md").read_text() if (DIR / "INDEX.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, str(rel(DIR / "INDEX.md")))
        return 1 if bad else 0
    (DIR / "INDEX.md").write_text(new_text)
    print(f"wrote {rel(DIR / 'INDEX.md')} ({len(rows)} record(s)"
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

        def e(msg):
            nonlocal errs
            print(f"  ERROR {name}: {msg}"); errs += 1

        if r.get("severity") not in SEVERITIES:
            e(f"severity {r.get('severity')!r} is free text — use one of "
              f"{', '.join(SEVERITIES)} (`rca.py new --help` defines them)")

        impact = r.get("impact")
        if not isinstance(impact, dict):
            e("no impact recorded — users affected, duration, data and revenue/SLA impact")
        else:
            for f in IMPACT_FIELDS:
                v = impact.get(f)
                if v is None or (isinstance(v, str) and blank(v)):
                    e(f"impact.{f} missing")
            dm = impact.get("duration_minutes")
            if dm is not None and not (isinstance(dm, str) and blank(dm)) and \
                    (not isinstance(dm, (int, float)) or isinstance(dm, bool) or dm < 0):
                e(f"impact.duration_minutes must be a non-negative number, got {dm!r}")

        tl = [x for x in (r.get("timeline") or []) if isinstance(x, dict)
              and not blank(x.get("event"))]
        for x in tl:
            at = x.get("at", x.get("when"))
            if blank(at if isinstance(at, str) else ""):
                continue
            if not parse_ts(at):
                e(f"timeline timestamp {at!r} is not ISO-8601 with a timezone "
                  f"(e.g. 2026-09-28T14:02:00Z or +09:00)")
            if x.get("type") not in EVENT_TYPES:
                e(f"timeline event type {x.get('type')!r} not in {EVENT_TYPES}")
        if tl and not first_event(tl, "detected"):
            e("timeline has no 'detected' event")
        if r.get("status") in ("fixed", "closed"):
            for need in ("mitigated", "resolved"):
                if tl and not first_event(tl, need):
                    e(f"status {r.get('status')} but timeline has no '{need}' event")
        order = [first_event(tl, k) for k in ("started", "detected", "mitigated", "resolved")]
        known = [o for o in order if o]
        if known != sorted(known):
            e("timeline order is impossible: started <= detected <= mitigated <= resolved")

        items = [x for x in (r.get("action_items") or []) if isinstance(x, dict)
                 and not blank(x.get("what"))]
        if not items:
            e("no action items — an incident review that changes nothing will recur")
        for x in items:
            w = x.get("what", "")[:50]
            if blank(x.get("owner")):
                e(f"action item {w!r} has no owner")
            if blank(x.get("due")) or not DATE_RX.match(str(x.get("due"))):
                e(f"action item {w!r} has no due date (YYYY-MM-DD), got {x.get('due')!r}")
            if x.get("type") not in ACTION_TYPES:
                e(f"action item {w!r} type {x.get('type')!r} not in {ACTION_TYPES}")
            if blank(x.get("ticket")):
                print(f"  WARN  {name}: action item {w!r} has no ticket — untracked items "
                      f"are the ones that never ship")

        if not [x for x in (r.get("lucky") or []) if not blank(x)]:
            print(f"  WARN  {name}: 'where we got lucky' is empty — chance that limited "
                  f"the damage is a latent failure worth naming")

        for s in strings(r):
            m = BLAME_RX.search(s)
            if m:
                print(f"  WARN  {name}: blame phrasing {m.group(0)!r} — name the system "
                      f"gap, not the person: {s[:70]!r}")
                break

        d = durations(r)
        if any(v is not None for v in d.values()):
            print(f"  info  {name}: " + ", ".join(
                f"{k.replace('_', ' ')} {v:g}m" for k, v in d.items() if v is not None))

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

        timeline = [t for t in tl if not blank(t.get("event"))]
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
        tree = r.get("fault_tree")
        tree_errs, leaves = [], 0
        if tree:
            leaves = fault_leaves(tree, tree_errs)
            for te in tree_errs:
                e(te)
        if len(whys) < 2 and leaves < 2:
            e(f"five-whys has {len(whys)} real level(s), need >= 2 — or a fault tree "
              f"with >= 2 leaf causes when several conditions combined")

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


def cmd_durations(a):
    recs = [r for r in load_all() if not r.get("_error")]
    if a.id:
        recs = [r for r in recs if r.get("id") == a.id]
        if not recs:
            print(f"no such RCA record: {a.id}")
            return 2
    out = {r["id"]: durations(r) for r in recs}
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    for rid, d in out.items():
        cells = ", ".join(f"{k.replace('_', ' ')} " + ("—" if v is None else f"{v:g} min")
                          for k, v in d.items())
        print(f"{rid}: {cells}")
    return 0


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

    adr_dir = DIR.parent / "decisions"
    hits = list(adr_dir.glob(f"{a.decision}*.md")) if adr_dir.exists() else []
    if not hits:
        print(f"warning: no decision record found for {a.decision} under {rel(adr_dir)}/ — "
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
    n.add_argument("--severity", default="SEV3",
                   choices=list(SEVERITIES) + list(LEGACY_SEVERITY),
                   help="; ".join(f"{k} = {v}" for k, v in SEVERITIES.items())
                        + ". Legacy words map critical/high/medium/low -> SEV1-SEV4.")
    n.add_argument("--tag", action="append")
    n.add_argument("--by", default="claude")
    n.add_argument("--dry-run", action="store_true",
                    help="print what would be created; write nothing")
    n.set_defaults(fn=cmd_new)
    p = sub.add_parser("lint"); p.set_defaults(fn=cmd_lint)
    du = sub.add_parser("durations", help="time to detect, mitigate and resolve")
    du.add_argument("id", nargs="?")
    du.add_argument("--json", action="store_true")
    du.set_defaults(fn=cmd_durations)
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
