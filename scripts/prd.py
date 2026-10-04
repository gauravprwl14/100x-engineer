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
  - `audit` is mechanical and structural. `align` is mechanical and ID-LEVEL: it
    follows the links the documents declare — each spec acceptance criterion names
    the requirement it satisfies, `AC-3: ... (R2, S1)`, and each success metric's
    measurement method cites a verification row (`spec V4`) — rather than matching
    shared words. A declared link proves the trace exists, not that the criterion
    really satisfies the requirement; the output says so, because a false sense of
    semantic coverage is worse than no check at all.

    prd.py new login --kind auth --tier small
    prd.py audit docs/engineering/prds/login
    prd.py align docs/engineering/prds/login docs/engineering/specs/login

Records live under the root `_paths.py` resolves (docs/engineering/ by default).
    prd.py index

Python stdlib only.
"""
import argparse, datetime, json, pathlib, re, sys
import _mutation_guard as mg
import _paths
import baseline as bl
from testplan import parse_criteria

PLUGIN = pathlib.Path(__file__).resolve().parent.parent


def rel(p):
    """Display path relative to the git root, resilient to a target outside it."""
    return _paths.show(p, ROOT)


# ROOT is the user's git root, not the plugin's directory (records written into the
# installed plugin are invisible to the project and lost on upgrade); records live
# under RECORDS (_paths.py). Outside a repo ROOT falls back to cwd for reads only.
ROOT, IN_GIT_REPO = _paths.git_root()
RECORDS, _ = _paths.resolve(ROOT)
PRDS = RECORDS / "prds"
SPECS = RECORDS / "specs"
DATA = PLUGIN / "scripts" / "data"

TIERS = json.loads((DATA / "scale_tiers.json").read_text())
TIER_ORDER = TIERS["_order"]
RISK_ORDER = TIERS["_risk"]["order"]

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

def find_section(text, name):
    """Body of '## [N. ]<name>' (number-agnostic, case-insensitive), or None."""
    rx = re.compile(rf"^##\s+(?:\d+[a-z]?\.\s+)?{re.escape(name)}\s*$", re.I)
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if rx.match(l.strip()):
            out = []
            for m in lines[i + 1:]:
                if m.startswith("## "):
                    break
                out.append(m)
            return "\n".join(out)
    return None


SOURCES = ("user", "assumed", "default", "code")
# Sections a design document carries (owner decision d). Each may say
# "N/A because <reason>"; blank, missing or a bare "N/A" is rejected.
DESIGN_SECTIONS = ["Goals", "Design overview", "Security", "Privacy", "Observability",
                   "Rollout / rollback", "Migration", "Test plan", "Cost", "Dependencies",
                   "Open questions / assumptions", "Approvers"]
NA_BARE = re.compile(r"^n/?a\.?$", re.I)
# approach-selection weights, fit excluded: fit is a pass/fail filter applied first.
# Defined once in decide.py so a PRD's options table and the ADR recording the same
# choice cannot score it differently.
from decide import WEIGHTS
OPT_HEADER = ("| # | option | pros | cons | reversibility x3 | blast radius x3 | "
              "moving parts x2 | already-in-use x2 | exit cost x1 | fit (pass/fail) | "
              "weighted score |")


def cmd_new(a):
    if mg.safe_record_name(a.name, "prd.py new") is None:
        return 2
    if not a.tier:
        print(f"--tier is required: one of {TIER_ORDER}. There is no default tier "
              f"(skills/scale-appropriateness/SKILL.md)", file=sys.stderr)
        return 2
    tier_name = a.tier.strip()
    if tier_name not in TIER_ORDER:
        print(f"unknown --tier '{tier_name}'. available: {TIER_ORDER} "
              f"(see skills/scale-appropriateness/SKILL.md)", file=sys.stderr)
        return 2
    if a.risk not in RISK_ORDER:
        print(f"unknown --risk '{a.risk}'. available: {RISK_ORDER}", file=sys.stderr)
        return 2
    kinds = [k.strip() for k in a.kind.split(",") if k.strip()]
    risk = bl.risk_floor(kinds, a.risk)
    tier = TIERS[tier_name]
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "prd.py new", ROOT):
        return 2
    d = PRDS / a.name
    if d.exists() and not a.force:
        print(f"{rel(d)} already exists (use --force)", file=sys.stderr)
        return 2
    today = datetime.date.today().isoformat()
    stack = a.stack or f"<!-- one of: {STACK_HINT}, or a combination -->"
    stack_src = "user" if a.stack else "<!-- user|assumed|default|code -->"
    spec_guess = (f"{rel(SPECS / a.name / 'spec.md')} (run `100x plan_feature new {a.name} "
                  f"--tier {tier_name} --risk {risk} --kind ... --work ...` for it)")
    ph = "<!-- -->"
    src = "<!-- user|assumed|default|code -->"

    def prose(name, hint):
        return [f"## {name}", "", f"<!-- {hint} 'N/A because <reason>' is allowed; "
                "blank is not. -->", ""]

    s = [f"# {a.name} — PRD", "",
         "| field | value |", "|---|---|",
         f"| kind | {esc(a.kind)} |",
         f"| stack | {esc(stack)} |",
         f"| scale tier | {tier_name} |",
         f"| risk | {risk} |",
         f"| linked spec | {spec_guess} |",
         f"| created | {today} |",
         "| status | **draft — not ready to hand to a spec** |", "",
         "Status becomes `ready` only when `100x prd audit` passes. Every number and "
         "constraint carries a `source` (user, assumed, default, code); a `ready` PRD "
         "may not rest on an `assumed` target or constraint.", "",
         f"**Load tier `{tier_name}`** ({esc(tier['users_requests'])}), **risk `{risk}`** "
         "— declared, never defaulted; see `skills/scale-appropriateness/SKILL.md`. "
         "The spec this PRD seeds must carry the same tier (`100x prd align` checks).", "",
         "## 1. Problem", "",
         "| field | answer |", "|---|---|",
         "| who has this problem | <!-- a specific segment, not \"users\" --> |",
         "| what they do today | <!-- the workaround, competitor, or manual process this replaces --> |",
         "| what \"better\" means, measurably | <!-- point at Success metrics below --> |", "",
         "## 2. Users", "",
         "| # | segment | current workaround | why they would adopt this |",
         "|---|---|---|---|", f"| U1 | {ph} | {ph} | {ph} |", "",
         "## 3. Goals", "",
         "| # | goal | measured by |", "|---|---|---|", f"| G1 | {ph} | <!-- M1 --> |", "",
         "## 4. Success metrics", "",
         "Every metric needs a number, a way to measure it, and where the number came "
         "from. `assumed` is allowed while drafting and rejected once `ready`.", "",
         "| # | metric | target (must include a number) | baseline | measurement method | source |",
         "|---|---|---|---|---|---|",
         f"| M1 | {ph} | <!-- e.g. <300ms p95 --> | <!-- N/A, new feature --> | {ph} | {src} |", "",
         "## 5. Constraints", "",
         "| constraint | value | source |", "|---|---|---|",
         f"| team size and skills | {ph} | {src} |",
         f"| existing stack | {esc(stack)} | {stack_src} |",
         f"| deadline | <!-- a date, or \"none\" stated explicitly --> | {src} |",
         f"| budget | <!-- spend ceiling, or \"existing infrastructure only\" --> | {src} |",
         f"| compliance / regulatory | <!-- none, GDPR, APPI, HIPAA, PCI DSS, SOC 2 --> | {src} |",
         f"| data residency | <!-- region, or N/A because no personal data --> | {src} |",
         f"| data retention | <!-- per data class, or N/A because ... --> | {src} |",
         f"| what cannot change | {ph} | {src} |", "",
         "## 6. Requirements", "",
         "| # | requirement | why it matters |", "|---|---|---|", f"| R1 | {ph} | {ph} |", "",
         "## 7. Options analysis", "",
         "`fit` is a pass/fail FILTER applied first: an option that does not solve the "
         "stated problem is out, whatever it scores. Fit-passing options are then scored "
         "1-5 on the `approach-selection` weights (reversibility x3, blast radius x3, "
         "moving parts x2, already-in-use x2, exit cost x1); the audit recomputes every "
         "weighted score. Always include do-nothing.", "",
         OPT_HEADER, "|---|---|---|---|---|---|---|---|---|---|---|",
         "| O1 | Do nothing / smallest possible change | zero new moving parts; zero new "
         "blast radius; ships today | does not solve the problem — mark fit `pass` only "
         "if the status quo is now acceptable, which is itself a decision | 5 | 5 | 5 | 5 "
         "| 5 | fail | 55 |",
         f"| O2 | {ph} | {ph} | {ph} | {ph} | {ph} | {ph} | {ph} | {ph} | {ph} | {ph} |", "",
         "## 8. Recommendation", "",
         "| field | answer |", "|---|---|",
         f"| chosen option | <!-- an option id, e.g. O2 --> |",
         "| single deciding factor | <!-- the one thing that made this win --> |",
         "| what would change it | <!-- the observation that would flip this choice --> |",
         "| override reason (if not the top fit-passing score) | none |", "",
         *prose("9. Design overview", "A level-1 diagram (<=12 nodes) and one paragraph "
                "of the recommended system shape."),
         "## 10. Risks", "",
         "Likelihood and impact are integers 1-5; the audit recomputes L x I. A risk with "
         "no mitigation is a worry, not a plan.", "",
         "| # | risk | likelihood (1-5) | impact (1-5) | L x I | mitigation | source |",
         "|---|---|---|---|---|---|---|",
         "| RI1 | Adoption is lower than the success metric assumes | TODO | TODO | TODO | "
         f"_suggested:_ ship behind a flag to a small cohort first | {src} |",
         "| RI2 | Effort estimate is wrong and scope grows mid-build | TODO | TODO | TODO | "
         f"_suggested:_ timebox phase 1 to the smallest slice that proves the core assumption | {src} |",
         "| RI3 | The existing codebase makes the recommended option more expensive than "
         "scored | TODO | TODO | TODO | _suggested:_ spike the riskiest integration point "
         f"first | {src} |", "",
         "## 11. Phasing", "",
         "| # | phase | ships | proves | kill criteria | source |", "|---|---|---|---|---|---|",
         f"| P1 | Phase 1 — smallest slice | {ph} | <!-- the riskiest assumption --> | "
         f"<!-- the signal that means stop --> | {src} |", "",
         "## 12. Non-goals (out of scope)", "",
         "| # | explicitly out of scope |", "|---|---|", f"| X1 | {ph} |", "",
         *prose("13. Security", "Assets, trust boundaries, top abuse cases."),
         *prose("14. Privacy", "Personal data touched, lawful basis, retention, residency."),
         *prose("15. Observability", "How you will know it works, and that it broke."),
         *prose("16. Rollout / rollback", "Flag, cohort, and the exact undo step."),
         *prose("17. Migration", "Data or schema migration and its reversal."),
         *prose("18. Test plan", "Which levels test what; the critical journeys."),
         *prose("19. Cost", "New recurring spend against the budget constraint."),
         *prose("20. Dependencies", "Teams, services and vendors this waits on."),
         *prose("21. Open questions / assumptions", "At most five, each with a "
                "recommendation; every `assumed` source above appears here."),
         *prose("22. Approvers", "Roles that must approve before `ready`."),
         "## 23. Existing-code note", "",
         "<!-- Written before or after the code? If after, name what in the code drove "
         "each requirement. -->", ""]
    new_text = "\n".join(s) + "\n"

    if dry:
        old_text = (d / "prd.md").read_text() if (d / "prd.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, str(rel(d / "prd.md")))
        print(f"[dry-run] would also regenerate {rel(PRDS / 'INDEX.md')}; nothing written")
        return 0

    d.mkdir(parents=True, exist_ok=True)
    (d / "prd.md").write_text(new_text)
    print(f"created {rel(d / 'prd.md')}")
    print(f"  tier {tier_name}, risk {risk}"
          + (f" (raised from {a.risk} by kind)" if risk != a.risk else ""))
    if TIER_ORDER.index(tier_name) < TIER_ORDER.index("growth"):
        print(f"  note: a PRD is optional below the growth tier; the spec alone may do")
    print("  1 option pre-answered (do-nothing), 3 risks seeded, rest to fill")
    print(f"\nNext: fill every section, then `100x prd audit {rel(d)}`")
    cmd_index(a)
    return 0


def _int15(v):
    return v.strip() if re.fullmatch(r"[1-5]", v.strip()) else None


def audit_options(text, rec, errs):
    options = rows_of(text, "| # | option |")
    real = [o for o in options if len(o) > 3 and not is_placeholder(o[1])]
    no_con = [o for o in real if is_placeholder(o[3])]
    if len(real) < 2:
        errs.append(f"options table has {len(real)} option(s), need >=2 "
                    f"(including do-nothing) — a choice with one option was not considered")
    if no_con:
        errs.append(f"{len(no_con)} option(s) with no con (first: {no_con[0][1][:50]!r}) "
                    f"— an option with no downside was not really evaluated")
    if real and OPT_HEADER not in text:
        errs.append("options table must use the fit pass/fail column: "
                    + OPT_HEADER)
        return real
    scored = {}
    for o in real:
        if len(o) < 11:
            errs.append(f"option {o[0]} has {len(o)} cells, expected 11")
            continue
        vals = [_int15(o[4 + k]) for k in range(len(WEIGHTS))]
        if None in vals:
            errs.append(f"option {o[0]}: every score must be an integer 1-5")
            continue
        fit = o[9].strip().lower()
        if fit not in ("pass", "fail"):
            errs.append(f"option {o[0]}: fit must be pass or fail, got {o[9]!r}")
            continue
        total = sum(int(v) * w for v, (_, w) in zip(vals, WEIGHTS))
        if o[10].strip() != str(total):
            errs.append(f"option {o[0]}: weighted score {o[10]!r} does not match the "
                        f"recomputed {total}")
        scored[o[0]] = (fit, total)
    passing = {k: v[1] for k, v in scored.items() if v[0] == "pass"}
    if scored and not passing:
        errs.append("no option passes the fit filter — none solves the stated problem")
    chosen = rec.get("chosen option", "")
    if is_placeholder(chosen):
        return real
    m = re.search(r"\bO\d+\b", chosen)
    if not m:
        errs.append("chosen option must name an option id from the table (e.g. O2)")
        return real
    cid = m.group(0)
    override = rec.get("override reason (if not the top fit-passing score)", "")
    has_override = not is_placeholder(override) and override.strip().lower() not in ("none", "n/a")
    if cid in scored and scored[cid][0] == "fail":
        errs.append(f"chosen option {cid} fails the fit filter — it does not solve the problem")
    elif cid in passing and passing[cid] < max(passing.values()) and not has_override:
        top = max(passing, key=passing.get)
        errs.append(f"chosen option {cid} ({passing[cid]}) is not the top fit-passing "
                    f"score ({top}, {passing[top]}) and no override reason is recorded")
    elif cid not in scored and scored:
        errs.append(f"chosen option {cid} is not in the options table")
    return real


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
    status_ready = re.search(r"^\|\s*status\s*\|\s*\*?\*?ready", text, re.I | re.M)

    ph = [l.strip()[:80] for l in text.splitlines() if "<!--" in l]
    if ph:
        errs.append(f"{len(ph)} line(s) still contain a placeholder comment "
                    f"(first: {ph[0]})")

    def field(n):
        m = re.search(rf"^\|\s*{re.escape(n)}\s*\|\s*(.+?)\s*\|\s*$", text, re.I | re.M)
        return m.group(1).strip() if m else ""
    tier_val, risk_val = field("scale tier"), field("risk")
    if tier_val not in TIER_ORDER:
        errs.append(f"scale tier {tier_val or '(missing)'!r} is not one of {TIER_ORDER} "
                    f"— a tier must be declared")
    if risk_val not in RISK_ORDER:
        errs.append(f"risk {risk_val or '(missing)'!r} is not one of {RISK_ORDER}")
    else:
        kinds = [k.strip() for k in field("kind").split(",") if k.strip()]
        floor = bl.risk_floor(kinds, risk_val)
        if floor != risk_val:
            errs.append(f"risk '{risk_val}' is below the floor '{floor}' implied by "
                        f"kind {', '.join(kinds)}")

    # sources: every numbers/constraints table names where each value came from
    sourced = {"success metric": rows_of(text, "| # | metric |"),
               "constraint": rows_of(text, "| constraint | value |"),
               "risk": rows_of(text, "| # | risk |"),
               "phase": rows_of(text, "| # | phase |")}
    for label, rows in sourced.items():
        real = [r for r in rows if len(r) > 1 and not is_placeholder(r[1])]
        nosrc = [r for r in real if r[-1].strip().lower() not in SOURCES]
        if nosrc:
            errs.append(f"{len(nosrc)} {label} row(s) with no source in "
                        f"{'|'.join(SOURCES)} (first: {nosrc[0][1][:40]!r})")
        if label in ("success metric", "constraint"):
            assumed = [r for r in real if r[-1].strip().lower() == "assumed"]
            if assumed and status_ready:
                errs.append(f"{len(assumed)} {label}(s) rest on an `assumed` source in a "
                            f"`ready` PRD (first: {assumed[0][1][:40]!r}) — get the number "
                            f"from the user, the code, or a cited default")
            elif assumed:
                warns.append(f"{len(assumed)} {label}(s) are `assumed`; allowed in a draft, "
                             f"rejected once `ready`")

    metrics = sourced["success metric"]
    real_metrics = [m for m in metrics if len(m) > 1 and not is_placeholder(m[1])]
    no_number = [m for m in real_metrics if len(m) > 2 and not re.search(r"\d", m[2])]
    no_method = [m for m in real_metrics if len(m) > 4 and is_placeholder(m[4])]
    if no_number:
        errs.append(f"{len(no_number)} success metric(s) with no number in the target "
                    f"(first: {no_number[0][1][:50]!r})")
    if no_method:
        errs.append(f"{len(no_method)} success metric(s) with no measurement method "
                    f"(first: {no_method[0][1][:50]!r})")

    rec = kv_table(find_section(text, "Recommendation") or "")
    if is_placeholder(rec.get("chosen option", "")):
        errs.append("no recommendation named ('chosen option')")
    if is_placeholder(rec.get("single deciding factor", "")):
        errs.append("no deciding factor named ('single deciding factor')")
    real_opts = audit_options(text, rec, errs)

    risks = sourced["risk"]
    bad_risks, bad_nums = [], []
    for r in risks:
        if len(r) < 6 or is_placeholder(r[1]):
            continue
        mit = r[5].strip()
        if is_placeholder(mit) or mit.startswith("_suggested:"):
            bad_risks.append(r)
        li, im = _int15(r[2]), _int15(r[3])
        if li is None or im is None:
            bad_nums.append(f"{r[0]}: likelihood and impact must be integers 1-5")
        elif r[4].strip() != str(int(li) * int(im)):
            bad_nums.append(f"{r[0]}: L x I {r[4]!r} does not match {int(li) * int(im)}")
    if bad_risks:
        errs.append(f"{len(bad_risks)} risk(s) with no mitigation "
                    f"(first: {bad_risks[0][1][:50]!r})")
    for b in bad_nums:
        errs.append(f"risk {b}")

    oos = rows_of(text, "| # | explicitly out of scope |")
    real_oos = [o for o in oos if len(o) > 1 and not is_placeholder(o[1])]
    if not real_oos:
        errs.append("no out-of-scope items — out-of-scope is what turns a gap into "
                    "a decision")

    reqs = rows_of(text, "| # | requirement |")
    real_reqs = [r for r in reqs if len(r) > 1 and not is_placeholder(r[1])]
    if not real_reqs:
        errs.append("no requirements recorded — `prd.py align` needs at least one "
                    "to check against the spec")

    for sec in DESIGN_SECTIONS:
        body = find_section(text, sec)
        if body is None:
            errs.append(f"missing section '{sec}' — write it, or 'N/A because <reason>'")
            continue
        b = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()
        if not b or NA_BARE.match(b):
            errs.append(f"section '{sec}' is blank — 'N/A because <reason>' is allowed, "
                        f"empty is not")

    print(f"audit {rel(p)}")
    print(f"  scale tier      : {tier_val or '(none declared)'}   risk: {risk_val or '-'}")
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

def spec_scope_items(spec_text):
    """The spec's '## 2. In scope / out of scope' dual table: in-scope column only."""
    out = []
    for cells in rows_of(spec_text, "| # | in scope |"):
        if len(cells) >= 2 and cells[0].strip() and not is_placeholder(cells[1]):
            out.append((cells[0].strip(), cells[1].strip()))
    return out


V_ID = re.compile(r"\bV\d+\b")


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
    print("(id-level tracing: the R<k> links on each acceptance criterion and the V<k> "
          "rows each metric cites. A link proves the trace was declared, not that the "
          "criterion really satisfies the requirement — review the wording.)")
    print()

    prd_text = prd_path.read_text()

    if not spec_path.exists():
        print(f"no spec.md at {spec_dir} yet — nothing to check. A PRD may "
              f"legitimately precede its spec; re-run once one exists.")
        return 0

    spec_text = spec_path.read_text()

    # 0. scale tier: the PRD's declared tier vs the spec's declared tier. A tier
    # change after planning invalidates decisions made under the old one -- it is
    # a re-plan, not a patch (skills/scale-appropriateness/SKILL.md).
    def tier_of(t):
        m = re.search(r"\|\s*scale tier\s*\|\s*(.+?)\s*\|", t, re.I)
        return m.group(1).strip() if m else ""
    prd_tier = tier_of(prd_text)
    spec_tier = tier_of(spec_text)
    tier_mismatch = bool(prd_tier and spec_tier and prd_tier != spec_tier)
    print("Scale tier: PRD <-> spec:")
    if not prd_tier or not spec_tier:
        print(f"  (skipped — PRD tier: {prd_tier or 'none declared'}, "
              f"spec tier: {spec_tier or 'none declared'})")
    elif tier_mismatch:
        print(f"  MISMATCH  PRD declares '{prd_tier}', spec declares '{spec_tier}' — "
              f"a tier change after planning is a re-plan, not a patch "
              f"(skills/scale-appropriateness/SKILL.md)")
    else:
        print(f"  OK    both declare '{prd_tier}'")
    print()

    reqs = [(r[0].strip(), r[1]) for r in rows_of(prd_text, "| # | requirement |")
            if len(r) > 1 and not is_placeholder(r[1])]
    req_ids = {rid for rid, _ in reqs}
    crits = {}
    for c in parse_criteria(spec_text):
        crits.setdefault(c["id"], c)
    if not crits:
        print(f"{rel(spec_path)} defines no acceptance criteria — nothing traces to the "
              f"PRD. Write each as `AC-<n>: <observable outcome> (R<k>, S<k>)` in the "
              f"spec's '2b. Acceptance criteria' section.")
        return 1

    def r_links(c):
        return [l for l in c["links"] if l.startswith("R")]

    # 1. every PRD requirement is satisfied by at least one acceptance criterion
    missing_reqs = []
    print("Requirements -> acceptance criteria:")
    if not reqs:
        print("  (none recorded)")
    for rid, text in reqs:
        by = [k for k, c in crits.items() if rid in r_links(c)]
        if by:
            print(f"  OK    {rid}  {text[:60]}  <- {', '.join(by)}")
        else:
            missing_reqs.append(rid)
            print(f"  MISS  {rid}  {text[:70]}")
            print(f"        no acceptance criterion in {rel(spec_path)} names {rid}")
    print()

    # 2. every acceptance criterion traces back to a PRD requirement
    orphan_acs = []
    print("Acceptance criteria -> requirements:")
    for k, c in crits.items():
        links = r_links(c)
        unknown = [l for l in links if l not in req_ids]
        if links and not unknown:
            print(f"  OK    {k}  -> {', '.join(links)}")
        else:
            orphan_acs.append(k)
            why = (f"names {', '.join(unknown)}, not in {rel(prd_path)}" if unknown
                   else "names no requirement — add `(R<k>)`, or it builds something "
                        "the PRD never asked for")
            print(f"  MISS  {k}  {c['text'][:60]}")
            print(f"        {why}")
    print()

    # 3. spec in-scope items -> PRD, through the criteria that deliver them
    missing_scope = []
    print("Spec in-scope -> PRD (via acceptance criteria):")
    scope = spec_scope_items(spec_text)
    if not scope:
        print("  (spec has no in-scope table)")
    for sid, text in scope:
        by = [k for k, c in crits.items() if sid in c["links"]]
        traced = [k for k in by if k not in orphan_acs]
        if traced:
            print(f"  OK    {sid}  {text[:60]}  <- {', '.join(traced)}")
        else:
            missing_scope.append(sid)
            print(f"  MISS  {sid}  {text[:70]}")
            print(f"        " + ("its criteria (" + ", ".join(by) + ") trace to no PRD "
                                 "requirement" if by else "no acceptance criterion delivers it")
                  + " — implements nothing the PRD asked for")
    print()

    # 4. success metrics -> spec verification plan, by cited row id
    metrics = [(m[0].strip(), m[1], m[4]) for m in rows_of(prd_text, "| # | metric |")
               if len(m) > 4 and not is_placeholder(m[1])]
    verif_rows = rows_of(spec_text, "| # | check |")
    v_ids = {v[0].strip() for v in verif_rows if v}
    missing_metrics = []
    print("Success metrics -> spec verification plan:")
    if not metrics:
        print("  (none recorded)")
    if not verif_rows:
        print("  (spec has no verification plan table)")
    for mid, name, method in metrics:
        cited = [v for v in V_ID.findall(method) if v in v_ids]
        named = [v[0].strip() for v in verif_rows
                 if any(re.search(rf"\b{re.escape(mid)}\b", c) for c in v[1:])]
        if cited or named:
            print(f"  OK    {mid}  {name[:50]}  <- {', '.join(sorted(set(cited + named)))}")
        else:
            missing_metrics.append(mid)
            print(f"  MISS  {mid}  {name[:60]}")
            print(f"        its measurement method cites no verification row of the spec "
                  f"(e.g. `spec V4`), and no row names {mid}")
    print()

    total = (len(missing_reqs) + len(missing_scope) + len(missing_metrics)
             + len(orphan_acs) + (1 if tier_mismatch else 0))
    print(f"{len(missing_reqs)} requirement(s) with no spec coverage, "
          f"{len(missing_scope)} spec item(s) implementing nothing in the PRD, "
          f"{len(missing_metrics)} metric(s) with no verification step, "
          f"{len(orphan_acs)} acceptance criterion/criteria tracing to no requirement"
          f"{', scale tier mismatch' if tier_mismatch else ''}")
    return 1 if total else 0


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

def cmd_index(a):
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "prd.py index", ROOT):
        return 2
    if not dry:
        PRDS.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted(PRDS.glob("*/prd.md")):
        t = p.read_text()
        def field(n):
            m = re.search(rf"\|\s*{n}\s*\|\s*(.+?)\s*\|", t, re.I)
            return (m.group(1) if m else "?").replace("**", "")
        rec = kv_table(find_section(t, "Recommendation") or "")
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
    new_text = "\n".join(out)
    if dry:
        old_text = (PRDS / "INDEX.md").read_text() if (PRDS / "INDEX.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, str(rel(PRDS / "INDEX.md")))
        return 0
    (PRDS / "INDEX.md").write_text(new_text)
    print(f"wrote {rel(PRDS / 'INDEX.md')} ({len(rows)} PRDs)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("name")
    n.add_argument("--kind", default="product")
    n.add_argument("--stack", default=None)
    n.add_argument("--tier", "--scale", dest="tier", default=None,
                    help=f"REQUIRED load tier: {'|'.join(TIER_ORDER)} "
                         f"(see skills/scale-appropriateness/SKILL.md)")
    n.add_argument("--risk", default="none",
                    help=f"risk axis: {'|'.join(RISK_ORDER)}; kinds "
                         f"{','.join(bl.RISK_BY_KIND)} raise it to at least elevated")
    n.add_argument("--force", action="store_true")
    n.add_argument("--dry-run", action="store_true",
                    help="print what would be created; write nothing")
    n.set_defaults(fn=cmd_new)
    au = sub.add_parser("audit"); au.add_argument("dir"); au.set_defaults(fn=cmd_audit)
    al = sub.add_parser("align")
    al.add_argument("prd_dir"); al.add_argument("spec_dir")
    al.set_defaults(fn=cmd_align)
    ix = sub.add_parser("index")
    ix.add_argument("--dry-run", action="store_true",
                     help="print the index diff; write nothing")
    ix.set_defaults(fn=cmd_index)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
