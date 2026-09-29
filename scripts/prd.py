#!/usr/bin/env python3
"""Scaffold a PRD, audit it for completeness, and check PRD <-> spec alignment.

This is the layer ABOVE `plan_feature.py`. A spec answers "how do we build this
correctly" for one feature; a PRD answers "should we build this, and what does
'worked' mean" before a spec exists at all. The two documents drift apart in
practice — a PRD promises something the spec never implements, or a spec grows
scope the PRD never asked for, or a success metric nobody wired a check for. That
three-way gap (PRD / spec / actual code) is the reason this tool exists rather than
just adding more columns to plan_feature.py's spec.

Design constraints, matching plan_feature.py:
  - Every required decision (constraints, the do-nothing option) ships a
    pre-answered default so the agent proceeds without interrogating the human.
  - Everything is a table with stable ids: reviewable, diffable, machine-checked.
  - `audit` is mechanical and structural. `align` is mechanical and NAME-LEVEL —
    it matches shared keywords between the PRD and the spec, not meaning. It says
    so in its own output, loudly, because a false sense of semantic coverage is
    worse than no check at all.

    prd.py new login --kind auth
    prd.py audit prds/login
    prd.py align prds/login specs/login
    prd.py index

Python stdlib only.
"""
import argparse, datetime, pathlib, re, sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent


def project_root():
    """Where the USER's prds/specs live: the git root of the current directory,
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
PRDS = ROOT / "prds"
SPECS = ROOT / "specs"

STACK_HINT = ("NestJS | Next.js/React | React Native/Expo | Flutter | native "
              "(Swift/Kotlin) | Kubernetes | AWS | GCP | Python")

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
    for l in lines:
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


def section_text(text, heading):
    """Lines between an exact '## N. Heading' line and the next '## ' heading."""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    except StopIteration:
        return ""
    out = []
    for l in lines[start + 1:]:
        if l.startswith("## "):
            break
        out.append(l)
    return "\n".join(out)


def kv_table(sec_text):
    """Parse a two-column `| field | value |` table into a dict keyed by field."""
    d = {}
    for l in sec_text.splitlines():
        m = TABLE_RX.match(l)
        if not m:
            continue
        cells = _cells(m.group(1))
        if len(cells) != 2:
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        if cells[0].strip().lower() in ("field", "constraint"):
            continue
        d[cells[0].strip().lower()] = cells[1].strip()
    return d


def is_placeholder(s):
    return not s or "<!--" in s or s.strip() in ("", "-", "—")


def esc(x):
    return str(x).replace("|", "\\|")


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

def cmd_new(a):
    d = PRDS / a.name
    if d.exists() and not a.force:
        print(f"{rel(d)} already exists (use --force)", file=sys.stderr)
        return 2
    d.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    stack = a.stack or f"<!-- one of: {STACK_HINT}, or a combination -->"
    spec_guess = f"specs/{a.name}/spec.md (run `plan_feature.py new {a.name} --kind ...` for it)"

    s = [f"# {a.name} — PRD", "",
         "| field | value |", "|---|---|",
         f"| kind | {esc(a.kind)} |",
         f"| stack | {esc(stack)} |",
         f"| linked spec | {spec_guess} |",
         f"| created | {today} |",
         "| status | **draft — not ready to hand to a spec** |", "",
         "Status becomes `ready` only when `prd.py audit` passes. A PRD that has not "
         "passed audit has no business seeding a spec — the spec would inherit its gaps.",
         "",

         "## 1. Problem", "",
         "Problem framing comes before solutions. If nobody can say who has this "
         "problem, what they do today, and what 'better' measurably means, there is "
         "nothing here to evaluate later — only a feature that felt right at the time.",
         "",
         "| field | answer |", "|---|---|",
         "| who has this problem | <!-- a specific segment, not \"users\" --> |",
         "| what they do today | <!-- the workaround, competitor, or manual process this replaces --> |",
         "| what \"better\" means, measurably | <!-- point at Success metrics below, don't restate a feeling here --> |",
         "",
         "<!-- One paragraph: the problem in prose, for the reader who skips tables. -->",
         "",

         "## 2. Users", "",
         "| # | segment | current workaround | why they would adopt this |",
         "|---|---|---|---|",
         "| U1 | <!-- --> | <!-- --> | <!-- --> |", "",

         "## 3. Success metrics", "",
         "Every metric needs a number and a way to measure it. \"Increase engagement\" "
         "cannot be evaluated in six months; \"D7 retention +5pp, measured from the "
         "`login_success` event\" can.", "",
         "| # | metric | target (must include a number) | baseline | measurement method |",
         "|---|---|---|---|---|",
         "| M1 | <!-- --> | <!-- e.g. +15% or <300ms --> | <!-- e.g. N/A, new feature --> | <!-- the event, dashboard, or test suite that proves it --> |",
         "",

         "## 4. Constraints", "",
         "Constraints are input to the options analysis, not an afterthought filled in "
         "after the choice is made.", "",
         "| constraint | value |", "|---|---|",
         "| team size and skills | <!-- headcount, and what they already know --> |",
         f"| existing stack | {esc(stack)} |",
         "| deadline | <!-- a date, or \"none\" stated explicitly --> |",
         "| budget | <!-- infra spend ceiling, or \"none stated\" --> |",
         "| compliance / regulatory | <!-- e.g. none, GDPR, HIPAA, SOC2 scope --> |",
         "| what cannot change | <!-- the thing options must not touch, e.g. the public API, the DB engine --> |",
         "",

         "## 5. Requirements", "",
         "What the recommended solution must satisfy. This table is what "
         "`prd.py align` checks against the spec's in-scope items — keep it "
         "concrete enough to be checkable, not a restatement of the problem.", "",
         "| # | requirement | why it matters |", "|---|---|---|",
         "| R1 | <!-- --> | <!-- --> |", "",

         "## 6. Options analysis", "",
         "Scored with the `approach-selection` rubric (`skills/approach-selection/"
         "SKILL.md`) — cross-reference it rather than re-deriving weights: "
         "reversibility x3, blast radius x3, moving parts x2, already-in-use x2, "
         "exit cost x1, fit x1, each scored 1-5. Highest weighted score wins; see "
         "that skill for tie-breaks. **Always include the do-nothing option** — it "
         "is frequently correct and usually the one left out.", "",
         "| # | option | pros | cons | reversibility x3 | blast radius x3 | moving parts x2 | already-in-use x2 | exit cost x1 | fit x1 | weighted score |",
         "|---|---|---|---|---|---|---|---|---|---|---|",
         "| O1 | Do nothing / smallest possible change | zero new moving parts; "
         "zero new blast radius; ships today | doesn't solve the problem — only "
         "choose this if the cost of the status quo is now acceptable, which is "
         "itself a decision worth recording | 5 | 5 | 5 | 5 | 5 | 1 | 56 |",
         "| O2 | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> | <!-- --> |",
         "",

         "## 7. Recommendation", "",
         "| field | answer |", "|---|---|",
         "| chosen option | <!-- --> |",
         "| single deciding factor | <!-- the one thing that made this win, not a list --> |",
         "| what would change it | <!-- the observation that would flip this choice --> |",
         "",

         "## 8. Risks", "",
         "Likelihood x impact, each 1-5, and a mitigation per risk — a risk with no "
         "mitigation is a worry, not a plan. Three are seeded because they recur on "
         "every PRD; replace the mitigation, don't just accept the seed.", "",
         "| # | risk | likelihood (1-5) | impact (1-5) | L x I | mitigation |",
         "|---|---|---|---|---|---|",
         "| RI1 | Adoption is lower than the success metric assumes | TODO | TODO | TODO | "
         "_suggested:_ ship behind a flag to a small cohort first; gate phase 2 on "
         "measured usage, not projected usage |",
         "| RI2 | Effort estimate is wrong and scope grows mid-build | TODO | TODO | TODO | "
         "_suggested:_ timebox phase 1 to the smallest slice that proves the core "
         "assumption (see Phasing); re-scope rather than extend the deadline |",
         "| RI3 | The existing codebase makes the recommended option more expensive "
         "than scored | TODO | TODO | TODO | "
         "_suggested:_ spike the riskiest integration point before committing the "
         "whole team to the option |",
         "",

         "## 9. Phasing", "",
         "What ships first, what it proves, and the kill criteria if it fails — not "
         "the smallest slice of the full feature, the smallest slice that tests the "
         "riskiest assumption.", "",
         "| # | phase | ships | proves | kill criteria |", "|---|---|---|---|---|",
         "| P1 | Phase 1 — smallest slice | <!-- --> | <!-- the riskiest assumption "
         "this validates --> | <!-- the signal that means stop and reconsider, not "
         "\"if it doesn't work\" --> |",
         "| P2 | <!-- --> | <!-- --> | <!-- --> | <!-- --> |", "",

         "## 10. Out of scope", "",
         "The thing a reader would assume is included. Out-of-scope is what turns a "
         "gap into a decision.", "",
         "| # | explicitly out of scope |", "|---|---|",
         "| X1 | <!-- --> |", "",

         "## 11. Existing-code note", "",
         "<!-- If code already exists for this problem: was this PRD written before "
         "or after it? If after (reverse-engineered), say so here and name what in "
         "the code drove each requirement above — a requirement with no code and no "
         "stated reason is speculative, not reverse-engineered. -->", "",
         ]
    (d / "prd.md").write_text("\n".join(s) + "\n")
    print(f"created {rel(d / 'prd.md')}")
    print("  1 option pre-answered (do-nothing), 3 risks seeded, rest to fill")
    print(f"\nNext: fill sections 1-7 and 9-10, then `prd.py audit prds/{a.name}`")
    cmd_index(a)
    return 0


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

def cmd_audit(a):
    d = pathlib.Path(a.dir)
    if not d.is_absolute():
        d = ROOT / d
    p = d / "prd.md"
    if not p.exists():
        print(f"no prd.md at {d}", file=sys.stderr)
        return 2
    text = p.read_text()
    errs, warns = [], []

    # 1. generic placeholder cells left behind
    unfilled = [l.strip()[:80] for l in text.splitlines() if re.search(r"\|\s*<!--", l)]
    if unfilled:
        errs.append(f"{len(unfilled)} table cell(s) still contain a placeholder "
                    f"comment (first: {unfilled[0]})")

    # 2. success metrics: each needs a number in the target, and a measurement method
    metrics = rows_of(text, "| # | metric |")
    real_metrics = [m for m in metrics if len(m) > 1 and not is_placeholder(m[1])]
    no_number = [m for m in real_metrics if len(m) > 2 and not re.search(r"\d", m[2])]
    no_method = [m for m in real_metrics if len(m) > 4 and is_placeholder(m[4])]
    if no_number:
        errs.append(f"{len(no_number)} success metric(s) with no number in the target "
                    f"(first: {no_number[0][1][:50]!r})")
    if no_method:
        errs.append(f"{len(no_method)} success metric(s) with no measurement method "
                    f"(first: {no_method[0][1][:50]!r})")

    # 3. options: >=2 real options, every real option needs a non-placeholder con
    options = rows_of(text, "| # | option |")
    real_opts = [o for o in options if len(o) > 3 and not is_placeholder(o[1])]
    no_con = [o for o in real_opts if is_placeholder(o[3])]
    if len(real_opts) < 2:
        errs.append(f"options table has {len(real_opts)} option(s), need >=2 "
                    f"(including do-nothing) — a choice with one option was not considered")
    if no_con:
        errs.append(f"{len(no_con)} option(s) with no con (first: {no_con[0][1][:50]!r}) "
                    f"— an option with no downside was not really evaluated")

    # 4/5. recommendation: chosen option and deciding factor
    rec = kv_table(section_text(text, "## 7. Recommendation"))
    if is_placeholder(rec.get("chosen option", "")):
        errs.append("no recommendation named (section 7, 'chosen option')")
    if is_placeholder(rec.get("single deciding factor", "")):
        errs.append("no deciding factor named (section 7, 'single deciding factor')")

    # 6. risks: every named risk needs a real mitigation, not a bare suggestion
    risks = rows_of(text, "| # | risk |")
    def unmitigated(r):
        if len(r) < 6 or is_placeholder(r[1]):
            return False
        mit = r[5].strip()
        return is_placeholder(mit) or mit.startswith("_suggested:")
    bad_risks = [r for r in risks if unmitigated(r)]
    if bad_risks:
        errs.append(f"{len(bad_risks)} risk(s) with no mitigation "
                    f"(first: {bad_risks[0][1][:50]!r})")

    # 7. out of scope must be non-empty
    oos = rows_of(text, "| # | explicitly out of scope |")
    real_oos = [o for o in oos if len(o) > 1 and not is_placeholder(o[1])]
    if not real_oos:
        errs.append("no out-of-scope items — out-of-scope is what turns a gap into "
                    "a decision")

    # requirements must be non-empty, or `align` has nothing to check
    reqs = rows_of(text, "| # | requirement |")
    real_reqs = [r for r in reqs if len(r) > 1 and not is_placeholder(r[1])]
    if not real_reqs:
        errs.append("no requirements recorded — `prd.py align` needs at least one "
                    "to check against the spec")

    status_ready = re.search(r"\|\s*status\s*\|\s*\*?\*?ready", text, re.I)

    print(f"audit {rel(p)}")
    print(f"  success metrics : {len(real_metrics)}")
    print(f"  options         : {len(real_opts)}")
    print(f"  risks           : {len(risks)}")
    print(f"  requirements    : {len(real_reqs)}")
    for w in warns:
        print(f"  WARN  {w}")
    for e in errs:
        print(f"  ERROR {e}")
    if errs:
        print(f"\nPRD is NOT ready: {len(errs)} blocking issue(s)")
        return 1
    if not status_ready:
        print("\nno blocking issues — set `status` to `ready` in the header table")
        return 0
    print("\nPRD is ready")
    return 0


# ---------------------------------------------------------------------------
# align
# ---------------------------------------------------------------------------

STOPWORDS = {"should", "which", "their", "there", "these", "those", "about",
             "where", "after", "before", "other", "using", "while", "every",
             "first", "being", "still", "would", "could", "within", "without"}
WORD_RX = re.compile(r"[a-z][a-z0-9_.\-]{4,}")


def keywords(text):
    """Lowercase words of 5+ chars, a handful of connective stopwords dropped.

    Deliberately crude: this is what makes `align` NAME-LEVEL rather than semantic,
    and both the skill and the tool's own output say so.
    """
    return {w for w in WORD_RX.findall((text or "").lower()) if w not in STOPWORDS}


def spec_scope_items(spec_text):
    """The spec's '## 2. In scope / out of scope' dual table: in-scope column only."""
    out = []
    for cells in rows_of(spec_text, "| # | in scope |"):
        if len(cells) >= 2 and cells[0].strip() and not is_placeholder(cells[1]):
            out.append((cells[0].strip(), cells[1].strip()))
    return out


def cmd_align(a):
    prd_dir = pathlib.Path(a.prd_dir)
    if not prd_dir.is_absolute():
        prd_dir = ROOT / prd_dir
    spec_dir = pathlib.Path(a.spec_dir)
    if not spec_dir.is_absolute():
        spec_dir = ROOT / spec_dir
    prd_path = prd_dir / "prd.md"
    spec_path = spec_dir / "spec.md"

    if not prd_path.exists():
        print(f"no prd.md at {prd_dir}", file=sys.stderr)
        return 2

    print(f"PRD <-> spec alignment: {rel(prd_dir)} <-> {rel(spec_dir)}")
    print("(keyword-level matching only — shared significant words, not meaning. A "
          "real match phrased differently is missed; a coincidental shared word can "
          "produce a false match. Treat findings as a lead for review, not proof.)")
    print()

    prd_text = prd_path.read_text()

    if not spec_path.exists():
        print(f"no spec.md at {spec_dir} yet — nothing to check. A PRD may "
              f"legitimately precede its spec; re-run once one exists.")
        return 0

    spec_text = spec_path.read_text()
    prd_kw = keywords(prd_text)
    spec_kw = keywords(spec_text)

    # 1. PRD requirements -> spec coverage
    reqs = [(r[0], r[1]) for r in rows_of(prd_text, "| # | requirement |")
            if len(r) > 1 and not is_placeholder(r[1])]
    missing_reqs = []
    print("Requirements -> spec coverage:")
    if not reqs:
        print("  (none recorded)")
    for rid, text in reqs:
        kw = keywords(text)
        if kw & spec_kw:
            print(f"  OK    {rid}  {text[:70]}")
        else:
            missing_reqs.append((rid, text))
            print(f"  MISS  {rid}  {text[:70]}")
            print(f"        no shared keyword with {rel(spec_path)}")
    print()

    # 2. spec in-scope items -> PRD coverage (scope creep the PRD never asked for)
    scope = spec_scope_items(spec_text)
    missing_scope = []
    print("Spec in-scope -> PRD coverage:")
    if not scope:
        print("  (spec has no in-scope table)")
    for sid, text in scope:
        kw = keywords(text)
        if kw & prd_kw:
            print(f"  OK    {sid}  {text[:70]}")
        else:
            missing_scope.append((sid, text))
            print(f"  MISS  {sid}  {text[:70]}")
            print(f"        no shared keyword with {rel(prd_path)} — implements "
                  f"nothing the PRD asked for")
    print()

    # 3. success metrics -> spec verification plan
    metrics = [(m[0], m[1], m[4]) for m in rows_of(prd_text, "| # | metric |")
               if len(m) > 4 and not is_placeholder(m[1])]
    verif_rows = rows_of(spec_text, "| # | check |")
    verif_kw = set()
    for v in verif_rows:
        verif_kw |= keywords(" ".join(v))
    missing_metrics = []
    print("Success metrics -> spec verification plan:")
    if not metrics:
        print("  (none recorded)")
    if not verif_rows:
        print("  (spec has no verification plan table)")
    for mid, name, method in metrics:
        kw = keywords(method) or keywords(name)
        if kw & verif_kw:
            print(f"  OK    {mid}  {name[:60]}")
        else:
            missing_metrics.append((mid, name))
            print(f"  MISS  {mid}  {name[:60]}")
            print(f"        measurement method has no counterpart in the spec's "
                  f"verification plan")
    print()

    total = len(missing_reqs) + len(missing_scope) + len(missing_metrics)
    print(f"{len(missing_reqs)} requirement(s) with no spec coverage, "
          f"{len(missing_scope)} spec item(s) implementing nothing in the PRD, "
          f"{len(missing_metrics)} metric(s) with no verification step")
    return 1 if total else 0


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

def cmd_index(a):
    PRDS.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted(PRDS.glob("*/prd.md")):
        t = p.read_text()
        def field(n):
            m = re.search(rf"\|\s*{n}\s*\|\s*(.+?)\s*\|", t, re.I)
            return (m.group(1) if m else "?").replace("**", "")
        rec = kv_table(section_text(t, "## 7. Recommendation"))
        chosen = rec.get("chosen option", "?")
        reqs = rows_of(t, "| # | requirement |")
        nreqs = sum(1 for r in reqs if len(r) > 1 and not is_placeholder(r[1]))
        spec_exists = (SPECS / p.parent.name / "spec.md").exists()
        rows.append((p.parent.name, field("kind"), field("status"), nreqs,
                     chosen if not is_placeholder(chosen) else "?",
                     "yes" if spec_exists else "no", p.parent.name + "/prd.md"))
    out = ["# PRD index", "",
           f"{len(rows)} PRD(s). Regenerate with `python3 scripts/prd.py index`.",
           "", "| PRD | kind | status | requirements | recommendation | spec exists |",
           "|---|---|---|--:|---|---|"]
    for n, k, st, nr, rec, sp, link in rows:
        out.append(f"| [{n}]({link}) | {k} | {st} | {nr} | {rec} | {sp} |")
    out += ["", "A PRD with `spec exists = yes` should pass "
            "`python3 scripts/prd.py align prds/<name> specs/<name>` before either "
            "document is trusted.", ""]
    (PRDS / "INDEX.md").write_text("\n".join(out))
    print(f"wrote prds/INDEX.md ({len(rows)} PRDs)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("name")
    n.add_argument("--kind", default="product")
    n.add_argument("--stack", default=None)
    n.add_argument("--force", action="store_true")
    n.set_defaults(fn=cmd_new)
    au = sub.add_parser("audit"); au.add_argument("dir"); au.set_defaults(fn=cmd_audit)
    al = sub.add_parser("align")
    al.add_argument("prd_dir"); al.add_argument("spec_dir")
    al.set_defaults(fn=cmd_align)
    ix = sub.add_parser("index"); ix.set_defaults(fn=cmd_index)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
