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

    plan_feature.py new login --kind auth --work api,web-ui --tier small --stack nestjs
    plan_feature.py audit docs/engineering/specs/login   # or specs/login, or login

Specs live under the root `_paths.py` resolves (docs/engineering/ by default).
    plan_feature.py index

Python stdlib only.
"""
import argparse, datetime, json, pathlib, re, sys
import _md as md
import _mutation_guard as mg
import _paths
import baseline as bl
from _md import AC_TAG, parse_criteria, rows_of, section_body

PLUGIN = pathlib.Path(__file__).resolve().parent.parent


def rel(p):
    """Display path relative to the git root, resilient to a target outside it."""
    return _paths.show(p, ROOT)


# ROOT is the user's git root (never the plugin's directory: records written into the
# installed plugin are invisible to the project and lost on upgrade). Outside a repo it
# falls back to cwd for READS only; writers check IN_GIT_REPO via
# mg.require_git_root() first. Records live under RECORDS, see _paths.py.
ROOT, IN_GIT_REPO = _paths.git_root()
RECORDS, _ = _paths.resolve(ROOT)
DATA = PLUGIN / "scripts" / "data"
SPECS = RECORDS / "specs"
PRDS = RECORDS / "prds"
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

TIERS = json.loads((DATA / "scale_tiers.json").read_text())
TIER_ORDER = TIERS["_order"]
RISK_ORDER = TIERS["_risk"]["order"]
BASELINE = bl.load()
BASE_BY_ID = {i["id"]: i for i in BASELINE["items"]}

# Status vocabulary for the implicit-requirements and edge-case tables. Anything
# else is rejected, so a cell cannot drift into "done?", "mostly" or "later".
PLAIN_STATUS = ("covered", "accepted", "deferred", "applied")
ARG_STATUS = ("waived", "n/a", "ASK", "ASSUMED")
STATUS_RX = re.compile(r"^(?P<word>waived|n/a|ASK|ASSUMED)\((?P<arg>.*)\)$", re.S)

# Design-doc cross-cutting sections every spec carries (owner decision d). Testing
# plan is §8, rollout/rollback §9 and open questions §6; these are the rest.
DESIGN_SECTIONS = ["10. Security", "11. Privacy", "12. Observability", "13. Migration",
                   "14. Cost"]
QUESTION_TYPES = ("must-ask", "default")
MAX_QUESTIONS = 5


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


def esc(x):
    return str(x).replace("|", "\\|")


def baseline_rows(work, tier, risk, prefilled):
    """§0b rows: every applicable baseline item, C items as unanswered ASK rows."""
    rows = []
    for i in bl.applicable(work, tier, risk, BASELINE):
        if i["class"] == "C":
            default = f"ASK: {i['ask']}"
            status = prefilled.get(i["id"], "ASK")
            evidence = f"source: {i['source']}"
        else:
            default = i["default"]
            status = "TODO"
            evidence = f"_suggested:_ {i['enforced_by']}"
        rows.append(f"| {i['id']} | {esc(default)} | {esc(status)} | {esc(evidence)} |")
    return rows


def cmd_new(a):
    kinds = [k.strip() for k in a.kind.split(",") if k.strip()]
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        print(f"unknown kind(s): {bad}. available: {KINDS}", file=sys.stderr)
        return 2
    if not a.tier:
        print(f"--tier is required: one of {TIER_ORDER}. There is no default tier; "
              f"declaring one is the point (skills/scale-appropriateness/SKILL.md)",
              file=sys.stderr)
        return 2
    tier_name = a.tier.strip()
    if tier_name not in TIER_ORDER:
        print(f"unknown --tier '{tier_name}'. available: {TIER_ORDER} "
              f"(see skills/scale-appropriateness/SKILL.md)", file=sys.stderr)
        return 2
    if a.risk not in RISK_ORDER:
        print(f"unknown --risk '{a.risk}'. available: {RISK_ORDER}", file=sys.stderr)
        return 2
    work, bad_work = bl.parse_work(a.work, BASELINE)
    if bad_work:
        print(f"unknown --work type(s): {bad_work}. available: {bl.work_types(BASELINE)} "
              f"(aliases: {bl.WORK_ALIASES})", file=sys.stderr)
        return 2
    risk = bl.risk_floor(kinds, a.risk)
    tier = TIERS[tier_name]
    if mg.safe_record_name(a.name, "plan_feature.py new") is None:
        return 2
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "plan_feature.py new", ROOT):
        return 2
    d = SPECS / a.name
    if d.exists() and not a.force:
        print(f"{rel(d)} already exists (use --force)", file=sys.stderr)
        return 2
    edges, decs = gather(kinds)
    today = datetime.date.today().isoformat()
    prefilled = {}
    if "public-api" in (a.work or ""):
        prefilled["ask.api-audience"] = "ASK(public — declared with --work public-api)"
    base = baseline_rows(work, tier_name, risk, prefilled)
    n_ask = sum(1 for r in base if "| ASK: " in r)
    work_arg = ",".join(work) or '""'

    prd_dir = PRDS / a.name
    prd_link = str(rel(prd_dir)) if (prd_dir / "prd.md").exists() else "none"
    s = [f"# {a.name} — spec", "",
         f"| field | value |", "|---|---|",
         f"| feature | {a.name} |",
         f"| kinds | {', '.join(kinds)} |",
         f"| stack | {a.stack or 'unspecified'} |",
         f"| prd | {prd_link} |",
         f"| baseline | {bl.version(BASELINE)} |",
         f"| created | {today} |",
         f"| status | **draft — not ready to implement** |", "",
         "Status becomes `ready` only when `100x plan_feature audit` passes. "
         "Until then the spec is incomplete by definition, not by opinion.", "",
         "## 0. Non-functional requirements", "",
         "Load tier and risk are DECLARED here, never defaulted — see "
         "`skills/scale-appropriateness/SKILL.md`. Risk adds security and compliance "
         "items without adding capacity items. Changing either after this spec is "
         "written is a re-plan: it needs an ADR (`100x decide new`).", "",
         "| field | value |", "|---|---|",
         f"| scale tier | {tier_name} |",
         f"| risk | {risk} |",
         f"| work types | {', '.join(work) or 'none (cross-cutting baseline only)'} |",
         f"| expected users / requests | {esc(tier['users_requests'])} |",
         f"| data volume | {esc(tier['data_volume'])} |",
         f"| p95 latency budget | {tier['p95_budget_ms']}ms — {esc(tier['p95_note'])} |",
         f"| availability target | {esc(tier['availability_target'])} |",
         f"| required at this tier | {esc('; '.join(tier['required']))} |",
         f"| explicitly NOT required at this tier | {esc('; '.join(tier['not_required']))} |",
         "",
         "## 0b. Implicit requirements", "",
         f"{len(base)} baseline item(s) for work={work_arg}, "
         f"tier={tier_name}, risk={risk} (`100x baseline show --work "
         f"{work_arg} --tier {tier_name} --risk {risk}`). Status is one of "
         "covered, applied, accepted, deferred, waived(<reason or ADR>), n/a(<reason>), "
         "ASK(<answer>), ASSUMED(<recommendation>). Class C rows are asked, never "
         "defaulted; residency, retention, compliance regime and cost must be answered "
         "with ASK(<answer>) before the spec is ready.", "",
         "| id | default | status | evidence |", "|---|---|---|---|", *base, "",
         "## 1. Outcome", "",
         "<!-- One paragraph. What a user can do after this ships that they cannot do now."
         " Not a description of the implementation. -->", "",
         "## 2. In scope / out of scope", "",
         "| # | in scope | | # | explicitly OUT of scope |", "|---|---|---|---|---|",
         "| S1 | <!-- --> | | O1 | <!-- the thing a reader would assume is included --> |", "",
         "Out-of-scope is load-bearing: it is the difference between a gap and a decision.", "",
         "## 2b. Acceptance criteria", "",
         "One line per criterion, `AC-<n>: <observable outcome> (R<k>, S<k>)`. The outcome "
         "is something a test can observe (a response, a stored state, what a screen "
         "shows), not an implementation step. `R<k>` names the PRD requirement it "
         "satisfies and is required when the feature has a PRD; `S<k>` names the in-scope "
         "row(s) above it delivers, and every in-scope row needs at least one criterion. "
         "Ids are unique and never renumbered: tests and `plan.json` reference them "
         "(`100x testplan trace`, `100x plan_dag lint --spec`), so a removed criterion "
         "leaves a gap and its id is not reused.", "",
         "AC-1: <!-- observable outcome --> (R1, S1)", "",
         "## 3. Interfaces touched", "",
         "| # | surface | change | backward compatible? |", "|---|---|---|---|",
         "| I1 | <!-- endpoint / screen / event / table --> | <!-- --> | <!-- yes/no + why --> |", "",
         "## 4. Sequence", "",
         "```mermaid", "sequenceDiagram", "  actor U as User",
         "  participant C as Client", "  participant A as API", "  participant D as Store",
         "  U->>C: <!-- action -->", "  C->>A: <!-- request -->",
         "  A->>D: <!-- write -->", "  A-->>C: <!-- response -->", "```", "",
         "`100x design_drift` checks that every participant and message here has a "
         "counterpart in the implementation, and reports what drifted.", "",
         "## 5. Decisions required", "",
         "Each row has a recommended DEFAULT. Accept it by leaving `chosen` as `default`, "
         "or write your choice. Anything still marked `default` at audit time is recorded "
         "as an accepted default, not as an open question.", "",
         "| # | decision | options | deciding factor | default (recommended) | chosen | ADR |",
         "|---|---|---|---|---|---|---|"]
    for i, (kind, name, options, factor, default) in enumerate(decs, 1):
        s.append(f"| D{i} | {esc(name)} | {esc(options)} | {esc(factor)} | "
                 f"{esc(default)} | default | — |")
    s += ["", "Record any decision that departs from the default, or that is "
          "architecturally load-bearing, with:", "",
          "```bash", f"100x decide new \"<decision>\" --affects \"<glob>\" --tag {kinds[0]}",
          "```", "",
          "## 6. Open questions", "",
          f"At most {MAX_QUESTIONS}, ordered by impact. `type` is `must-ask` (a class C "
          "item: the user's call) or `default` (proceeding on the recommendation). Every "
          "question carries a recommendation so work continues while it is unanswered.", "",
          "| # | type | question | why it matters | recommendation (proceeding with this) | answered |",
          "|---|---|---|---|---|---|",
          "| Q1 | <!-- must-ask or default --> | <!-- --> | <!-- --> | <!-- --> | no |", "",
          "## 7. Edge cases", "",
          f"{len(edges)} seeded from the catalogue for kinds: {', '.join(kinds)}. "
          "Every row needs a `status` of `covered` (with a test reference), `accepted`, "
          "`deferred` (with a follow-up reference), `n/a(<reason>)` or "
          "`waived(<reason or ADR>)`.", "",
          "| # | source | edge case | why it gets missed | status | test / reference |",
          "|---|---|---|---|---|---|"]
    for i, (kind, what, why, test) in enumerate(edges, 1):
        s.append(f"| E{i} | {kind} | {esc(what)} | {esc(why)} | TODO | "
                 f"_suggested:_ {esc(test)} |")
    s += ["", "## 8. Verification plan", "",
          "`covers` lists the acceptance criteria a row proves (`—` for a row that proves "
          "none, such as types); every AC needs at least one row.", "",
          "| # | check | command | gate | covers |", "|---|---|---|---|---|",
          "| V1 | types | <!-- --> | pre-commit | — |",
          "| V2 | unit | <!-- --> | pre-commit | AC-1 |",
          "| V3 | integration | <!-- --> | pre-PR | AC-1 |",
          "| V4 | the edge cases above | <!-- --> | pre-PR | — |", "",
          "Bind these to the code with `100x verified` so a passing result cannot "
          "be reused after an edit.", "",
          "## 9. Rollout and reversal", "",
          "| aspect | plan |", "|---|---|",
          "| feature flag | <!-- name, default off --> |",
          "| migration | <!-- expand/contract? reversible? --> |",
          "| rollback | <!-- the exact command or step --> |",
          "| blast radius if wrong | <!-- who is affected and how badly --> |", "",
          "## 10. Security", "",
          "<!-- Threat model paragraph: assets, trust boundaries crossed, top abuse cases "
          "and the control for each. 'N/A because <reason>' is allowed; blank is not. -->", "",
          "## 11. Privacy", "",
          "<!-- Personal data touched, lawful basis or consent, retention, where it is "
          "stored. 'N/A because <reason>' is allowed; blank is not. -->", "",
          "## 12. Observability", "",
          "<!-- Signals, dashboards and alerts that prove this works in production. -->", "",
          "## 13. Migration", "",
          "<!-- Schema or data migration shape, backfill, reversibility; or 'N/A because "
          "<reason>'. -->", "",
          "## 14. Cost", "",
          "<!-- New recurring spend and what drives it; or 'N/A because <reason>'. -->", ""]
    new_text = "\n".join(s) + "\n"

    if dry:
        old_text = (d / "spec.md").read_text() if (d / "spec.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, str(rel(d / "spec.md")))
        print(f"[dry-run] would also regenerate {rel(SPECS / 'INDEX.md')}; nothing written")
        return 0

    _paths.safe_write_text(d / "spec.md", new_text, ROOT, "plan_feature new")

    print(f"created {rel(d / 'spec.md')}")
    print(f"  scale tier: {tier_name} (p95 starting point {tier['p95_budget_ms']}ms)")
    if risk != a.risk:
        print(f"  risk: {risk} (raised from {a.risk}: kinds {', '.join(kinds)} imply "
              f"at least {risk})")
    else:
        print(f"  risk: {risk}")
    if not work:
        print("  no --work given: only cross-cutting baseline items were seeded "
              f"(work types: {', '.join(bl.work_types(BASELINE))})")
    print(f"  {len(base)} implicit requirements seeded ({n_ask} to ask)")
    print(f"  {len(decs)} decisions pre-answered with defaults")
    print(f"  {len(edges)} edge cases seeded (all TODO)")
    print(f"\nNext: fill §0b and sections 1-14, then `100x plan_feature audit {rel(d)}`")
    cmd_index(a)
    return 0


def parse_status(cell):
    """('covered', None) | ('n/a', 'reason') | (None, None) when not in the allowlist."""
    c = cell.strip()
    if c in PLAIN_STATUS:
        return c, None
    m = STATUS_RX.match(c)
    if m and m.group("arg").strip() and "<!--" not in m.group("arg"):
        return m.group("word"), m.group("arg").strip()
    return None, None


def no_evidence(cell):
    c = cell.strip()
    return not c or c in ("-", "—") or c.startswith("_suggested:")


NA_BARE = re.compile(r"^n/?a\.?$", re.I)


def pinned_baseline(text, errs, warns):
    """The catalogue version the spec was written against (`| baseline | <n> |`). A
    spec without the field predates pinning and is checked against the current one."""
    current = bl.version(BASELINE)
    raw = md.header_field(text, "baseline")
    if not raw:
        warns.append(f"no `| baseline | <n> |` header field — checked against the current "
                     f"baseline v{current}; add `| baseline | {current} |` to pin it")
        return current
    if not raw.isdigit() or not 1 <= int(raw) <= current:
        errs.append(f"`| baseline | {raw} |` is not a baseline version (1..{current})")
        return current
    return int(raw)


def audit_baseline(text, work, tier, risk, errs, warns):
    rows = rows_of(text, "| id | default | status | evidence |")
    if "## 0b. Implicit requirements" not in text or not rows:
        errs.append("no '## 0b. Implicit requirements' table — regenerate with "
                    "`100x plan_feature new <name> --tier ... --work ...` and merge")
        return rows
    pin = pinned_baseline(text, errs, warns)
    expected = {i["id"] for i in bl.applicable(work, tier, risk, BASELINE, upto=pin)}
    newer = sorted({i["id"] for i in bl.applicable(work, tier, risk, BASELINE)} - expected)
    present = {r[0] for r in rows if r}
    missing = sorted(expected - present)
    if missing:
        errs.append(f"{len(missing)} applicable baseline item(s) missing from §0b "
                    f"(first: {missing[0]})")
    later = [x for x in newer if x not in present]
    if later:
        warns.append(f"{len(later)} baseline item(s) added after the pinned v{pin}: "
                     f"{', '.join(later)} — add them and bump `| baseline |`, or record "
                     f"why not")
    unknown = sorted(present - set(BASE_BY_ID))
    if unknown:
        warns.append(f"§0b row(s) not in scripts/data/baseline.json: {', '.join(unknown)}")
    retired = sorted(x for x in present if BASE_BY_ID.get(x, {}).get("deprecated"))
    if retired:
        warns.append(f"§0b row(s) for deprecated baseline item(s): {', '.join(retired)}")
    blocking = bl.blocking_ids(BASELINE)
    bad, todo, unanswered, assumed_block, wrong_class, no_ev, nowaive = ([] for _ in range(7))
    for r in rows:
        if len(r) < 4:
            bad.append(r[0] if r else "?")
            continue
        iid, status_cell, ev = r[0], r[2], r[3]
        item = BASE_BY_ID.get(iid, {})
        word, arg = parse_status(status_cell)
        if word is None:
            cell = status_cell.strip()
            (unanswered if cell == "ASK" else todo if cell == "TODO" else bad).append(iid)
            continue
        is_c = item.get("class") == "C"
        if is_c and word not in ("ASK", "ASSUMED", "n/a"):
            wrong_class.append(f"{iid} is class C: answer it with ASK(<answer>), not {word}")
        if not is_c and word in ("ASK", "ASSUMED"):
            wrong_class.append(f"{iid} is class {item.get('class', '?')}: "
                               f"{word}(...) is only for class C questions")
        if word == "ASSUMED" and iid in blocking:
            assumed_block.append(iid)
        if word in ("covered", "applied", "deferred") and no_evidence(ev):
            no_ev.append(f"{iid} ({word})")
        if word == "waived" and item and not item.get("waivable", True):
            nowaive.append(iid)
    if bad:
        errs.append(f"{len(bad)} §0b status(es) outside the allowlist "
                    f"covered|applied|accepted|deferred|waived(..)|n/a(..)|ASK(..)|"
                    f"ASSUMED(..) (first: {bad[0]}) — a bare n/a or waived needs a reason")
    if todo:
        errs.append(f"{len(todo)} of {len(rows)} §0b implicit requirement(s) still TODO "
                    f"(first: {todo[0]})")
    if unanswered:
        errs.append(f"{len(unanswered)} class C question(s) unanswered in §0b "
                    f"(first: {unanswered[0]}) — ASK(<answer>) or ASSUMED(<recommendation>)")
    if assumed_block:
        errs.append(f"{len(assumed_block)} blocking question(s) only ASSUMED: "
                    f"{', '.join(assumed_block)} — residency, retention, compliance regime "
                    f"and cost must be answered (ASK(<answer>)) before `ready`")
    for w in wrong_class:
        errs.append(w)
    if no_ev:
        errs.append(f"{len(no_ev)} §0b row(s) with no evidence (first: {no_ev[0]}) — "
                    f"covered/applied need a test or check, deferred a follow-up")
    if nowaive:
        errs.append(f"{len(nowaive)} non-waivable baseline item(s) waived: "
                    f"{', '.join(nowaive)}")
    return rows


AC_CANONICAL = re.compile(r"^AC-\d+: \S")
MIN_OUTCOME_WORDS = 3


def linked_prd(text, spec_dir):
    """The PRD this spec answers to: the header's `prd` field (a directory relative to
    the git root), else <records>/prds/<feature>/. None when there is no PRD."""
    m = re.search(r"^\|\s*prd\s*\|\s*(.+?)\s*\|\s*$", text, re.I | re.M)
    if m and m.group(1).strip().lower() not in ("none", "-", "—", ""):
        d = pathlib.Path(m.group(1).strip().strip("`"))
        p = (d if d.is_absolute() else ROOT / d)
        p = p if p.name == "prd.md" else p / "prd.md"
        return p if p.exists() else ("missing", m.group(1).strip())
    p = PRDS / spec_dir.name / "prd.md"
    return p if p.exists() else None


def prd_requirement_ids(prd_text):
    return [r[0].strip() for r in rows_of(prd_text, "| # | requirement |")
            if len(r) > 1 and r[1].strip() and "<!--" not in r[1]]


def audit_acceptance(text, spec_dir, errs, warns):
    """The acceptance-criteria rules. Returns the parsed criteria of §2b.

    AC ids are the join key of the whole pipeline -- PRD requirement -> AC -> task in
    plan.json -> tagged test -- so a missing link here is a gap every later tool
    inherits silently."""
    _, body = md.ac_section(text)
    if body is None:
        errs.append("no '## 2b. Acceptance criteria' section — write each criterion as "
                    "`AC-<n>: <observable outcome> (R<k>, S<k>)`")
        return []
    crits = parse_criteria(body)
    if not crits:
        errs.append("§2b has no acceptance criteria — at least one "
                    "`AC-<n>: <observable outcome> (R<k>, S<k>)` line is required")
        return []
    for c in crits:
        if not AC_CANONICAL.match(c["raw"]):
            errs.append(f"{c['id']}: write it as `{c['id']}: <observable outcome> "
                        f"(R<k>, S<k>)` on its own line (got {c['raw'].strip()[:50]!r})")
    everywhere = parse_criteria(text, scoped=False)
    counts = {}
    for c in everywhere:
        counts[c["id"]] = counts.get(c["id"], 0) + 1
    dups = sorted((k for k, v in counts.items() if v > 1), key=lambda k: int(k[3:]))
    if dups:
        errs.append(f"acceptance criterion id(s) defined more than once: {', '.join(dups)} "
                    f"— ids are unique and never renumbered; give a new criterion the "
                    f"next unused number")
    here = {c["id"] for c in crits}
    outside = sorted({c["id"] for c in everywhere} - here, key=lambda k: int(k[3:]))
    if outside:
        errs.append(f"acceptance criteria defined outside §2b: {', '.join(outside)} — "
                    f"keep them in one section so every tool reads the same list")
    vague = [c["id"] for c in crits if "<!--" in c["text"]
             or len(re.findall(r"[A-Za-z]{2,}", c["text"])) < MIN_OUTCOME_WORDS]
    if vague:
        errs.append(f"{len(vague)} acceptance criterion/criteria with no observable "
                    f"outcome (first: {vague[0]}) — state what a test would see")

    scope = [r[0].strip() for r in rows_of(text, "| # | in scope |")
             if len(r) > 1 and r[0].strip() and r[1].strip() and "<!--" not in r[1]]
    s_links = {s for c in crits for s in c["links"] if s.startswith("S")}
    unmapped = [s for s in scope if s not in s_links]
    if unmapped:
        errs.append(f"in-scope item(s) with no acceptance criterion: {', '.join(unmapped)} "
                    f"— add `(… {unmapped[0]})` to the AC that delivers it, or move it out "
                    f"of scope")
    unknown_s = sorted(s_links - set(scope))
    if unknown_s and scope:
        errs.append(f"acceptance criteria link in-scope row(s) that do not exist: "
                    f"{', '.join(unknown_s)}")

    prd = linked_prd(text, spec_dir)
    if isinstance(prd, tuple):
        errs.append(f"the header's prd field names {prd[1]!r}, which has no prd.md")
    elif prd is not None:
        req_ids = set(prd_requirement_ids(prd.read_text(errors="replace")))
        nolink = [c["id"] for c in crits if not any(l.startswith("R") for l in c["links"])]
        if nolink:
            errs.append(f"{len(nolink)} acceptance criterion/criteria with no PRD "
                        f"requirement link (first: {nolink[0]}) — {rel(prd)} exists, so "
                        f"each AC names the R<k> it satisfies")
        bad_r = sorted({l for c in crits for l in c["links"]
                        if l.startswith("R") and l not in req_ids})
        if bad_r:
            errs.append(f"acceptance criteria link requirement(s) not in {rel(prd)}: "
                        f"{', '.join(bad_r)}")
    elif any(l.startswith("R") for c in crits for l in c["links"]):
        warns.append("acceptance criteria name R<k> requirements but no PRD was found "
                     "(header `prd` field, or prds/<feature>/prd.md) — the links are "
                     "unchecked")

    verif = rows_of(text, "| # | check |")
    proven = {f"AC-{n}" for r in verif for cell in r[1:] for n in AC_TAG.findall(cell)}
    unproven = [c["id"] for c in crits if c["id"] not in proven]
    if verif and unproven:
        errs.append(f"acceptance criteria no verification row covers: "
                    f"{', '.join(unproven)} — list each in the `covers` column of §8")
    ghost = sorted(proven - {c["id"] for c in everywhere}, key=lambda k: int(k[3:]))
    if ghost:
        errs.append(f"verification plan covers undefined criteria: {', '.join(ghost)}")
    return crits


def audit_seeded(text, kinds, edges, decisions, errs):
    """Mirror of the §0b missing-row rule for §7 and §5: a seeded row is answered
    (n/a(<reason>), waived(<reason>), a chosen option), never deleted, or the audit
    would pass a spec that dropped the edge case nobody wanted to think about."""
    def norm(s):
        return re.sub(r"\s+", " ", s).strip().lower()
    want_e, want_d = gather([k for k in kinds if k in KINDS])
    have_e = {norm(r[2]) for r in edges if len(r) > 2}
    have_d = {norm(r[1]) for r in decisions if len(r) > 1}
    gone_e = [w for _, w, *_ in want_e if norm(w) not in have_e]
    gone_d = [n for _, n, *_ in want_d if norm(n) not in have_d]
    if gone_e:
        errs.append(f"{len(gone_e)} seeded edge case(s) deleted from §7 (first: "
                    f"{gone_e[0][:60]!r}) — mark a row n/a(<reason>) or waived(<reason>) "
                    f"instead of removing it")
    if gone_d:
        errs.append(f"{len(gone_d)} seeded decision(s) deleted from §5 (first: "
                    f"{gone_d[0][:60]!r}) — keep the row and accept the default or "
                    f"record a choice")


def cmd_audit(a):
    sp = md.find_record(a.dir, "specs", "spec.md", ROOT, RECORDS)
    if sp is None:
        print(md.not_found(a.dir, "specs", "spec.md", RECORDS, rel), file=sys.stderr)
        return 2
    d = sp.parent
    text = sp.read_text()
    errs, warns = [], []

    # template comments anywhere — prose, tables or diagrams — mean an unfilled spec
    ph = [l.strip()[:70] for l in text.splitlines() if "<!--" in l]
    if ph:
        errs.append(f"{len(ph)} line(s) still contain a template placeholder "
                    f"(first: {ph[0]})")
    tbd = [l.strip()[:70] for l in text.splitlines()
           if re.search(r"\|\s*(TBD|FIXME)\s*\|", l)]
    if tbd:
        errs.append(f"{len(tbd)} table cell(s) still TBD/FIXME (first: {tbd[0]})")

    def nfr_field(name):
        m = re.search(rf"^\|\s*{re.escape(name)}\s*\|\s*(.+?)\s*\|\s*$", text, re.I | re.M)
        return m.group(1).strip() if m else ""

    def is_blank(v):
        return not v or v in ("", "-", "—") or "<!--" in v

    kinds = [k.strip() for k in nfr_field("kinds").split(",") if k.strip()]
    tier_val = nfr_field("scale tier")
    risk_val = nfr_field("risk")
    work, bad_work = bl.parse_work(nfr_field("work types").split("(")[0]
                                   .replace("none", ""), BASELINE)
    tier_ok = "## 0. Non-functional requirements" in text and tier_val in TIER_ORDER
    if "## 0. Non-functional requirements" not in text:
        errs.append("no '## 0. Non-functional requirements' section — a load tier must be "
                    "declared (skills/scale-appropriateness/SKILL.md)")
    elif tier_val not in TIER_ORDER:
        errs.append(f"scale tier {tier_val or '(missing)'!r} is not one of {TIER_ORDER}")
    if risk_val not in RISK_ORDER:
        errs.append(f"risk {risk_val or '(missing)'!r} is not one of {RISK_ORDER}")
        risk_val = "none"
    else:
        floor = bl.risk_floor(kinds, risk_val)
        if floor != risk_val:
            errs.append(f"risk '{risk_val}' is below the floor '{floor}' implied by "
                        f"kinds {', '.join(kinds)}")
            risk_val = floor
    if bad_work:
        errs.append(f"unknown work type(s) {bad_work}; available: "
                    f"{bl.work_types(BASELINE)}")
    if tier_ok:
        nfr_fields = ["expected users / requests", "data volume", "p95 latency budget",
                      "availability target", "required at this tier",
                      "explicitly NOT required at this tier"]
        empty_nfr = [f for f in nfr_fields if is_blank(nfr_field(f))]
        if empty_nfr:
            errs.append(f"non-functional requirements table has {len(empty_nfr)} "
                        f"unfilled field(s): {', '.join(empty_nfr)}")
        base_rows = audit_baseline(text, work, tier_val, risk_val, errs, warns)
    else:
        base_rows = []

    # edge cases
    edges = rows_of(text, "| # | source | edge case |")
    todo = [r for r in edges if len(r) > 4 and r[4].upper() == "TODO"]
    covered = [r for r in edges if len(r) > 4 and r[4].lower() == "covered"]
    off_list = [r for r in edges if len(r) > 4 and r[4].upper() != "TODO"
                and (parse_status(r[4])[0] not in ("covered", "accepted", "deferred",
                                                   "n/a", "waived"))]
    nodeferref = [r for r in edges if len(r) > 5 and r[4].lower() == "deferred"
                  and no_evidence(r[5])]
    noref = [r for r in edges if len(r) > 5 and r[4].lower() == "covered"
             and no_evidence(r[5])]
    if todo:
        errs.append(f"{len(todo)} of {len(edges)} edge cases still TODO "
                    f"(first: {todo[0][2][:60]})")
    if off_list:
        errs.append(f"{len(off_list)} edge case status(es) outside the allowlist "
                    f"(first: {off_list[0][0]} '{off_list[0][4]}')")
    if noref:
        errs.append(f"{len(noref)} edge case(s) marked covered with no test reference")
    if nodeferref:
        errs.append(f"{len(nodeferref)} edge case(s) deferred with no follow-up reference")

    unknown_kinds = [k for k in kinds if k not in KINDS]
    if unknown_kinds:
        errs.append(f"unknown kind(s) in the header: {', '.join(unknown_kinds)}; "
                    f"available: {', '.join(KINDS)}")
    audit_seeded(text, kinds, edges, rows_of(text, "| # | decision |"), errs)

    # open questions: at most five, each typed, each with a recommendation
    qs = [r for r in rows_of(text, "| # | type | question |") if r and r[0]]
    if "## 6. Open questions" in text and not qs and rows_of(text, "| # | question |"):
        errs.append("open questions table has no `type` column — each question must be "
                    "tagged must-ask or default")
    if len(qs) > MAX_QUESTIONS:
        errs.append(f"{len(qs)} open questions; at most {MAX_QUESTIONS} — batch by impact, "
                    f"default the rest")
    untyped = [r for r in qs if len(r) > 1 and r[1] not in QUESTION_TYPES]
    if untyped:
        errs.append(f"{len(untyped)} open question(s) not tagged must-ask|default "
                    f"(first: {untyped[0][0]})")
    noreco = [r for r in qs if len(r) > 4 and (not r[4] or "<!--" in r[4])]
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
                    f"reference (run `100x decide new`)")

    # verification plan must name commands
    vs = rows_of(text, "| # | check |")
    novcmd = [r for r in vs if len(r) > 2 and (not r[2] or "<!--" in r[2])]
    if novcmd:
        errs.append(f"{len(novcmd)} verification row(s) with no command")

    crits = audit_acceptance(text, d, errs, warns)

    if "sequenceDiagram" not in text:
        warns.append("no mermaid sequenceDiagram — design_drift.py has nothing to check")

    # design-doc cross-cutting sections: present, and not blank or a bare N/A
    for sec in DESIGN_SECTIONS:
        body = section_body(text, sec)
        if body is None:
            errs.append(f"missing section '## {sec}' — write it, or 'N/A because <reason>'")
        elif not re.sub(r"<!--.*?-->", "", body, flags=re.S).strip() or NA_BARE.match(body):
            errs.append(f"section '## {sec}' is blank — 'N/A because <reason>' is allowed, "
                        f"empty is not")

    status_ready = re.search(r"\|\s*status\s*\|\s*\*?\*?ready", text, re.I)

    print(f"audit {rel(sp)}")
    print(f"  scale tier : {tier_val or '(none declared)'}   risk: {risk_val}   "
          f"work: {', '.join(work) or '-'}")
    print(f"  baseline   : {len(base_rows)} implicit requirement row(s)")
    print(f"  edge cases : {len(edges)} total, {len(covered)} covered, {len(todo)} TODO")
    print(f"  decisions  : {len(ds)} total, {len(defaults)} accepted as default")
    print(f"  questions  : {len(qs)}")
    print(f"  acceptance : {len(crits)} criteria")
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
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "plan_feature.py index", ROOT):
        return 2
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
            "`100x plan_feature audit <name>` explains why.", ""]
    new_text = "\n".join(out)
    if dry:
        old_text = (SPECS / "INDEX.md").read_text() if (SPECS / "INDEX.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, str(rel(SPECS / "INDEX.md")))
        return 0
    _paths.safe_write_text(SPECS / "INDEX.md", new_text, ROOT, "plan_feature index")
    print(f"wrote {rel(SPECS / 'INDEX.md')} ({len(rows)} specs)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("name")
    n.add_argument("--kind", required=True, help=f"comma-separated: {','.join(KINDS)}")
    n.add_argument("--stack", default=None)
    n.add_argument("--tier", "--scale", dest="tier", default=None,
                    help=f"REQUIRED load tier: {'|'.join(TIER_ORDER)} "
                         f"(see skills/scale-appropriateness/SKILL.md)")
    n.add_argument("--risk", default="none",
                    help=f"risk axis: {'|'.join(RISK_ORDER)}; kinds "
                         f"{','.join(bl.RISK_BY_KIND)} raise it to at least elevated")
    n.add_argument("--work", default="",
                    help=f"comma-separated work types: {','.join(bl.work_types(BASELINE))} "
                         f"(alias public-api -> api); selects the implicit-requirement baseline")
    n.add_argument("--force", action="store_true")
    n.add_argument("--dry-run", action="store_true",
                    help="print what would be created/changed; write nothing")
    n.set_defaults(fn=cmd_new)
    au = sub.add_parser("audit")
    au.add_argument("dir", help="the spec directory, its spec.md, specs/<name> under the "
                                "records root, or the bare name")
    au.set_defaults(fn=cmd_audit)
    ix = sub.add_parser("index")
    ix.add_argument("--dry-run", action="store_true",
                     help="print the index diff; write nothing")
    ix.set_defaults(fn=cmd_index)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
