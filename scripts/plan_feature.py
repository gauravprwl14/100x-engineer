#!/usr/bin/env python3
"""Scaffold a feature spec that surfaces gaps before code, then audit it for completeness.

The problem: asked to "build login", an agent writes plausible code and the gaps show
up in review, or in production. The gaps are knowable in advance — they are the same
gaps every time — so they belong in a checklist generated before the first line.

Design constraints taken from how this gets used in practice:
  - Questions are pre-answered. Every required decision ships a DEFAULT, so the agent
    proceeds alone and the human overrides only where they disagree.
  - Everything is a table with stable ids, so it can be reviewed, diffed and indexed.
  - `audit` is mechanical: an incomplete spec fails, so "we'll decide later" cannot
    silently become "nobody decided".

    plan_feature.py new login --kind auth --stack nestjs
    plan_feature.py audit specs/login
    plan_feature.py index

Python stdlib only.
"""
import argparse, datetime, json, pathlib, re, sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent

def project_root():
    """Where the USER's decisions/specs live: the git root of the current directory,
    not the plugin's own directory.

    Resolving these against the plugin root meant a consumer project's records were
    written into the installed plugin — invisible to their repo and lost on upgrade.
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
DATA = PLUGIN / "scripts" / "data"
SPECS = ROOT / "specs"
EDGE = json.loads((DATA / "edge_cases.json").read_text())

# Component-keyed failure modes (cache, queue, cron, webhook, ...) live in a
# separate catalogue so the two can be maintained independently -- merged here
# so `--kind` accepts either without the caller needing to know which file a
# kind came from. Optional: a repo without the infra catalogue still works.
INFRA_PATH = DATA / "edge_cases_infra.json"
if INFRA_PATH.exists():
    EDGE_INFRA = json.loads(INFRA_PATH.read_text())
    for k, v in EDGE_INFRA.items():
        if k.startswith("_"):
            continue
        if k in EDGE:
            print(f"warning: kind '{k}' defined in both edge_cases.json and "
                  f"edge_cases_infra.json; the infra catalogue wins", file=sys.stderr)
        EDGE[k] = v

DECS = json.loads((DATA / "decisions_required.json").read_text())
KINDS = [k for k in EDGE if not k.startswith("_")]


def gather(kinds):
    edges, decs = [], []
    seen = set()
    for k in ["universal"] + [k for k in kinds if k != "universal"]:
        for e in EDGE.get(k, []):
            if e[0] not in seen:
                seen.add(e[0]); edges.append((k, *e))
        for d in DECS.get(k, []):
            decs.append((k, *d))
    return edges, decs


def cmd_new(a):
    kinds = [k.strip() for k in a.kind.split(",") if k.strip()]
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        print(f"unknown kind(s): {bad}. available: {KINDS}", file=sys.stderr)
        return 2
    d = SPECS / a.name
    if d.exists() and not a.force:
        print(f"{rel(d)} already exists (use --force)", file=sys.stderr)
        return 2
    d.mkdir(parents=True, exist_ok=True)
    edges, decs = gather(kinds)
    today = datetime.date.today().isoformat()

    s = [f"# {a.name} — spec", "",
         f"| field | value |", "|---|---|",
         f"| kinds | {', '.join(kinds)} |",
         f"| stack | {a.stack or 'unspecified'} |",
         f"| created | {today} |",
         f"| status | **draft — not ready to implement** |", "",
         "Status becomes `ready` only when `plan_feature.py audit` passes. "
         "Until then the spec is incomplete by definition, not by opinion.", "",
         "## 1. Outcome", "",
         "<!-- One paragraph. What a user can do after this ships that they cannot do now."
         " Not a description of the implementation. -->", "",
         "## 2. In scope / out of scope", "",
         "| # | in scope | | # | explicitly OUT of scope |", "|---|---|---|---|---|",
         "| S1 | <!-- --> | | O1 | <!-- the thing a reader would assume is included --> |", "",
         "Out-of-scope is load-bearing: it is the difference between a gap and a decision.", "",
         "## 3. Interfaces touched", "",
         "| # | surface | change | backward compatible? |", "|---|---|---|---|",
         "| I1 | <!-- endpoint / screen / event / table --> | <!-- --> | <!-- yes/no + why --> |", "",
         "## 4. Sequence", "",
         "```mermaid", "sequenceDiagram", "  actor U as User",
         "  participant C as Client", "  participant A as API", "  participant D as Store",
         "  U->>C: <!-- action -->", "  C->>A: <!-- request -->",
         "  A->>D: <!-- write -->", "  A-->>C: <!-- response -->", "```", "",
         "`scripts/design_drift.py` checks that every participant and message here has a "
         "counterpart in the implementation, and reports what drifted.", "",
         "## 5. Decisions required", "",
         "Each row has a recommended DEFAULT. Accept it by leaving `chosen` as `default`, "
         "or write your choice. Anything still marked `default` at audit time is recorded "
         "as an accepted default, not as an open question.", "",
         "| # | decision | options | deciding factor | default (recommended) | chosen | ADR |",
         "|---|---|---|---|---|---|---|"]
    def esc(x):
        return str(x).replace("|", "\\|")
    for i, (kind, name, options, factor, default) in enumerate(decs, 1):
        s.append(f"| D{i} | {esc(name)} | {esc(options)} | {esc(factor)} | "
                 f"{esc(default)} | default | — |")
    s += ["", "Record any decision that departs from the default, or that is "
          "architecturally load-bearing, with:", "",
          "```bash", f"python3 scripts/decide.py new \"<decision>\" --affects \"<glob>\" --tag {kinds[0]}",
          "```", "",
          "## 6. Open questions", "",
          "Only questions whose answer changes the design belong here, and each must "
          "carry a recommendation so work continues while it is unanswered.", "",
          "| # | question | why it matters | recommendation (proceeding with this) | answered |",
          "|---|---|---|---|---|",
          "| Q1 | <!-- --> | <!-- --> | <!-- --> | no |", "",
          "## 7. Edge cases", "",
          f"{len(edges)} seeded from the catalogue for kinds: {', '.join(kinds)}. "
          "Every row needs a `status` of `covered`, `accepted`, or `deferred`, and a "
          "`test` reference when covered. `deferred` requires a follow-up reference.", "",
          "| # | source | edge case | why it gets missed | status | test / reference |",
          "|---|---|---|---|---|---|"]
    for i, (kind, what, why, test) in enumerate(edges, 1):
        s.append(f"| E{i} | {kind} | {esc(what)} | {esc(why)} | TODO | "
                 f"_suggested:_ {esc(test)} |")
    s += ["", "## 8. Verification plan", "",
          "| # | check | command | gate |", "|---|---|---|---|",
          "| V1 | types | <!-- --> | pre-commit |",
          "| V2 | unit | <!-- --> | pre-commit |",
          "| V3 | integration | <!-- --> | pre-PR |",
          "| V4 | the edge cases above | <!-- --> | pre-PR |", "",
          "Bind these to the code with `scripts/verified.py` so a passing result cannot "
          "be reused after an edit.", "",
          "## 9. Rollout and reversal", "",
          "| aspect | plan |", "|---|---|",
          "| feature flag | <!-- name, default off --> |",
          "| migration | <!-- expand/contract? reversible? --> |",
          "| rollback | <!-- the exact command or step --> |",
          "| blast radius if wrong | <!-- who is affected and how badly --> |", ""]
    (d / "spec.md").write_text("\n".join(s) + "\n")

    print(f"created {(d / 'spec.md').relative_to(ROOT)}")
    print(f"  {len(decs)} decisions pre-answered with defaults")
    print(f"  {len(edges)} edge cases seeded (all TODO)")
    print(f"\nNext: fill sections 1-4 and 8-9, then `plan_feature.py audit specs/{a.name}`")
    cmd_index(a)
    return 0


TABLE_RX = re.compile(r"^\|(.+)\|\s*$")


CELL_SPLIT = re.compile(r"(?<!\\)\|")


def _cells(inner):
    r"""Split a markdown table row on unescaped pipes; a cell may legitimately
    contain an escaped pipe, e.g. an options list 'a \| b \| c'."""
    return [c.strip().replace("\\|", "|") for c in CELL_SPLIT.split(inner)]


def rows_of(text, header_contains):
    """Extract data rows of the markdown table whose header contains a marker."""
    lines = text.splitlines()
    out, in_tbl = [], False
    for i, l in enumerate(lines):
        m = TABLE_RX.match(l)
        if not m:
            in_tbl = False
            continue
        cells = _cells(m.group(1))
        if header_contains in l:
            in_tbl = True
            continue
        if in_tbl:
            if set("".join(cells)) <= set("-: "):
                continue
            out.append(cells)
    return out


def cmd_audit(a):
    d = pathlib.Path(a.dir)
    if not d.is_absolute():
        d = ROOT / d
    sp = d / "spec.md"
    if not sp.exists():
        print(f"no spec.md at {d}", file=sys.stderr)
        return 2
    text = sp.read_text()
    errs, warns = [], []

    # placeholders left behind
    ph = [l for l in text.splitlines() if "<!--" in l and "-->" in l
          and not l.strip().startswith("<!-- ") is False]
    unfilled = [l.strip()[:80] for l in text.splitlines()
                if re.search(r"\|\s*<!--", l)]
    if unfilled:
        errs.append(f"{len(unfilled)} table cell(s) still contain a placeholder comment")

    # edge cases
    edges = rows_of(text, "| # | source | edge case |")
    todo = [r for r in edges if len(r) > 4 and r[4].upper() == "TODO"]
    covered = [r for r in edges if len(r) > 4 and r[4].lower() == "covered"]
    nodeferref = [r for r in edges if len(r) > 5 and r[4].lower() == "deferred"
                  and (not r[5] or r[5].startswith("_suggested:"))]
    noref = [r for r in edges if len(r) > 5 and r[4].lower() == "covered"
             and (not r[5] or r[5].startswith("_suggested:"))]
    if todo:
        errs.append(f"{len(todo)} of {len(edges)} edge cases still TODO "
                    f"(first: {todo[0][2][:60]})")
    if noref:
        errs.append(f"{len(noref)} edge case(s) marked covered with no test reference")
    if nodeferref:
        errs.append(f"{len(nodeferref)} edge case(s) deferred with no follow-up reference")

    # open questions must carry a recommendation
    qs = rows_of(text, "| # | question |")
    noreco = [r for r in qs if len(r) > 3 and (not r[3] or "<!--" in r[3])]
    if noreco:
        errs.append(f"{len(noreco)} open question(s) with no recommendation — the agent "
                    f"cannot proceed independently on these")

    # decisions: departures from default need an ADR
    ds = rows_of(text, "| # | decision |")
    dep = [r for r in ds if len(r) > 6 and r[5].lower() not in ("default", "")
           and (not r[6] or r[6] == "—")]
    defaults = [r for r in ds if len(r) > 5 and r[5].lower() == "default"]
    if dep:
        errs.append(f"{len(dep)} decision(s) depart from the default with no ADR "
                    f"reference (run scripts/decide.py new)")

    # verification plan must name commands
    vs = rows_of(text, "| # | check |")
    novcmd = [r for r in vs if len(r) > 2 and (not r[2] or "<!--" in r[2])]
    if novcmd:
        errs.append(f"{len(novcmd)} verification row(s) with no command")

    # sequence diagram present and non-placeholder
    if "sequenceDiagram" not in text:
        warns.append("no mermaid sequenceDiagram — design_drift.py has nothing to check")
    elif text.count("<!-- action -->") or text.count("<!-- request -->"):
        errs.append("sequence diagram still contains template placeholders")

    status_ready = re.search(r"\|\s*status\s*\|\s*\*?\*?ready", text, re.I)

    print(f"audit {rel(sp)}")
    print(f"  edge cases : {len(edges)} total, {len(covered)} covered, {len(todo)} TODO")
    print(f"  decisions  : {len(ds)} total, {len(defaults)} accepted as default")
    print(f"  questions  : {len(qs)}")
    for w in warns:
        print(f"  WARN  {w}")
    for e in errs:
        print(f"  ERROR {e}")
    if errs:
        print(f"\nspec is NOT ready to implement: {len(errs)} blocking issue(s)")
        return 1
    if not status_ready:
        print("\nno blocking issues — set `status` to `ready` in the header table")
        return 0
    print("\nspec is ready to implement")
    return 0


def cmd_index(a):
    SPECS.mkdir(parents=True, exist_ok=True)
    rows = []
    for sp in sorted(SPECS.glob("*/spec.md")):
        t = sp.read_text()
        def field(n):
            m = re.search(rf"\|\s*{n}\s*\|\s*(.+?)\s*\|", t, re.I)
            return (m.group(1) if m else "?").replace("**", "")
        edges = rows_of(t, "| # | source | edge case |")
        todo = sum(1 for r in edges if len(r) > 4 and r[4].upper() == "TODO")
        rows.append((sp.parent.name, field("kinds"), field("stack"), field("status"),
                     len(edges), todo, sp.parent.name + "/spec.md"))
    out = ["# Spec index", "",
           f"{len(rows)} spec(s). Regenerate with `python3 scripts/plan_feature.py index`.",
           "", "| feature | kinds | stack | status | edge cases | still TODO |",
           "|---|---|---|---|--:|--:|"]
    for n, k, st, stat, ne, nt, link in rows:
        out.append(f"| [{n}]({link}) | {k} | {st} | {stat} | {ne} | {nt} |")
    out += ["", "A spec with TODO edge cases is not implementable; "
            "`plan_feature.py audit specs/<name>` explains why.", ""]
    (SPECS / "INDEX.md").write_text("\n".join(out))
    print(f"wrote specs/INDEX.md ({len(rows)} specs)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("name")
    n.add_argument("--kind", required=True, help=f"comma-separated: {','.join(KINDS)}")
    n.add_argument("--stack", default=None)
    n.add_argument("--force", action="store_true")
    n.set_defaults(fn=cmd_new)
    au = sub.add_parser("audit"); au.add_argument("dir"); au.set_defaults(fn=cmd_audit)
    ix = sub.add_parser("index"); ix.set_defaults(fn=cmd_index)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
