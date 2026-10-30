#!/usr/bin/env python3
"""Show and lint the implicit-requirements baseline (scripts/data/baseline.json).

A request never states "keyboard accessible", "authorize every endpoint" or "don't log
the session id"; a senior engineer applies them anyway. The baseline writes those
defaults down per WORK TYPE, filtered by the declared load tier and risk level, each
with the standard it comes from, so an agent applies them silently (class A/B) and
asks only what is genuinely the user's call (class C).

    baseline.py show --work web-ui,api --tier small --risk elevated
    baseline.py show --work api --tier growth --json
    baseline.py lint [--file other.json] [--against REV]

The catalogue is versioned. `"version"` is an integer that goes up whenever items are
added; an item's optional `"since"` names the version that added it (absent = 1). A
spec pins the version it was written against (`| baseline | <n> |`, written by
`plan_feature new`), so its audit requires only the items that existed then and WARNS
about newer ones instead of failing a finished spec overnight. For the same reason an
id is never renamed or deleted: a retired item stays, marked `"deprecated": true`, so
pinned specs that list it still resolve. `lint` compares against the committed copy
(`--against`, default HEAD) and fails when an id disappears.

Two optional keys scope the class C questions, because a batch is capped at five
(docs/OPERATING-MODEL.md section 5) and an irrelevant ask crowds out a relevant one:
`when_any` is a list of clauses, each a subset of {kinds, work, from_tier, risk}; the
item applies only when its own work/from_tier/risk match AND at least one clause
matches every key it names. `door` (one-way | two-way) ranks the questions after the
blocking ones: `ask_order` is blocking first, then one-way doors, then catalogue order.

Python stdlib only.
"""
import argparse, json, pathlib, re, shlex, subprocess, sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
DATA = PLUGIN / "scripts" / "data"
BASELINE_PATH = DATA / "baseline.json"

_tiers = json.loads((DATA / "scale_tiers.json").read_text())
TIER_ORDER = _tiers["_order"]
RISK_ORDER = _tiers["_risk"]["order"]
RISK_BY_KIND = _tiers["_risk"]["implied_by_kind"]
# Feature kinds a `when_any` clause may name: every edge-case catalogue's keys.
KNOWN_KINDS = {k for f in ("edge_cases.json", "edge_cases_infra.json", "edge_cases_ui.json")
               if (DATA / f).exists()
               for k in json.loads((DATA / f).read_text()) if not k.startswith("_")}

# Skills being written in parallel; an owner_skill naming one of these is not an
# error yet. Once the skill directory exists, lint asks for it to leave this list.
PENDING_SKILLS: set = set()
SCHEMA = 1

# enforced_by may name an external tool; it must be one a reader can install, not prose.
EXTERNAL_TOOLS = {"npx", "gitleaks", "semgrep", "checkov", "trivy", "syft", "buf",
                  "k6", "terraform", "scorecard", "osv-scanner", "zizmor", "tflint",
                  "pnpm", "npm", "pytest", "go", "cargo"}

WORK_ALIASES = {"public-api": "api"}
CLASSES = ("A", "B", "C")
REQUIRED_KEYS = ("id", "work", "class", "from_tier", "default", "assumption_text",
                 "source", "enforced_by", "owner_skill", "waivable")
OPTIONAL_KEYS = ("risk", "ask", "blocks_ready", "since", "deprecated", "when_any", "door")
CLAUSE_KEYS = ("kinds", "work", "from_tier", "risk")
DOORS = ("one-way", "two-way")
TOP_KEYS = ("_doc", "_work_types", "schema", "version", "items")
ID_RX = re.compile(r"^[a-z][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$")


def load(path=BASELINE_PATH):
    return json.loads(pathlib.Path(path).read_text())


def version(data):
    return data.get("version", 1)


def since(item):
    return item.get("since", 1)


def work_types(data):
    return data.get("_work_types", [])


def parse_work(raw, data):
    """Comma list -> (work types, unknown names). Aliases resolve to a work type."""
    out, bad = [], []
    for w in [x.strip() for x in (raw or "").split(",") if x.strip()]:
        w2 = WORK_ALIASES.get(w, w)
        if w2 not in work_types(data):
            bad.append(w)
        elif w2 not in out:
            out.append(w2)
    return out, bad


def risk_floor(kinds, risk):
    """Raise the declared risk to the floor a feature kind implies (decision a)."""
    floor = risk
    for k in kinds:
        implied = RISK_BY_KIND.get(k)
        if implied and RISK_ORDER.index(implied) > RISK_ORDER.index(floor):
            floor = implied
    return floor


def _clause_matches(clause, work, tier, risk, kinds):
    if "kinds" in clause and not set(clause["kinds"]) & set(kinds):
        return False
    if "work" in clause and not set(clause["work"]) & set(work):
        return False
    if "from_tier" in clause and TIER_ORDER.index(tier) < TIER_ORDER.index(clause["from_tier"]):
        return False
    return "risk" not in clause or RISK_ORDER.index(risk) >= RISK_ORDER.index(clause["risk"])


def applies(item, work, tier, risk, kinds=None):
    """`kinds` are the feature kinds (edge_cases*.json); None means none declared,
    so a `when_any` clause naming kinds does not match."""
    if "*" not in item["work"] and not set(item["work"]) & set(work):
        return False
    if TIER_ORDER.index(tier) < TIER_ORDER.index(item["from_tier"]):
        return False
    if RISK_ORDER.index(risk) < RISK_ORDER.index(item.get("risk", "none")):
        return False
    clauses = item.get("when_any")
    return not clauses or any(_clause_matches(c, work, tier, risk, kinds or [])
                              for c in clauses)


def applicable(work, tier, risk, data=None, upto=None, deprecated=False, kinds=None):
    """Items that apply to work x tier x risk (x kinds, for `when_any` clauses).
    `upto` keeps only items that existed in that catalogue version (a spec's pin);
    deprecated items are dropped unless asked for."""
    data = data or load()
    return [i for i in data["items"] if applies(i, work, tier, risk, kinds)
            and (deprecated or not i.get("deprecated"))
            and (upto is None or since(i) <= upto)]


def ask_order(items):
    """Class C items in the order a question batch takes them (OPERATING-MODEL.md
    section 5): blocking first, then one-way doors (section 4), then catalogue order,
    which is the tie-break."""
    cs = [i for i in items if i.get("class") == "C"]
    return sorted(cs, key=lambda i: (not i.get("blocks_ready"),
                                     i.get("door") != "one-way", cs.index(i)))


def blocking_ids(data=None):
    data = data or load()
    return {i["id"] for i in data["items"] if i.get("blocks_ready")}


def cmd_show(a):
    data = load()
    work, bad = parse_work(a.work, data)
    if bad:
        print(f"unknown work type(s): {bad}. available: {work_types(data)} "
              f"(aliases: {WORK_ALIASES})", file=sys.stderr)
        return 2
    if a.tier not in TIER_ORDER:
        print(f"unknown tier '{a.tier}'. available: {TIER_ORDER}", file=sys.stderr)
        return 2
    if a.risk not in RISK_ORDER:
        print(f"unknown risk '{a.risk}'. available: {RISK_ORDER}", file=sys.stderr)
        return 2
    kinds = [k.strip() for k in (a.kind or "").split(",") if k.strip()]
    items = applicable(work, a.tier, a.risk, data, kinds=kinds)
    if a.json:
        print(json.dumps({"version": version(data), "work": work, "tier": a.tier,
                          "risk": a.risk, "kinds": kinds, "items": items},
                         indent=2, ensure_ascii=False))
        return 0
    print(f"baseline v{version(data)} for work={','.join(work) or '(cross-cutting only)'} "
          f"tier={a.tier} risk={a.risk}: {len(items)} item(s)")
    titles = {"A": "A  always-on: apply silently, list as an assumption",
              "B": "B  tier-dependent: on at this tier, list as an assumption",
              "C": "C  must ask: never defaulted"}
    for c in CLASSES:
        group = [i for i in items if i["class"] == c]
        if not group:
            continue
        print(f"\n{titles[c]} ({len(group)})")
        for i in group:
            text = i["ask"] if c == "C" else i["default"]
            flag = "  [blocks ready]" if i.get("blocks_ready") else ""
            print(f"  {i['id']}{flag}\n      {text}\n      source: {i['source']}"
                  f"\n      enforced by: {i['enforced_by']}")
    return 0


def enforced_ok(cmd):
    """Each ` + `-separated part must be runnable or `review`/`convention`, so one item
    can name a mechanical check and the review that covers what it cannot see."""
    parts = [x.strip() for x in cmd.split(" + ")]
    if len(parts) > 1:
        for part in parts:
            ok, why = enforced_ok(part)
            if not ok:
                return ok, why
        return True, ""
    if cmd in ("review", "convention"):
        return True, ""
    try:
        toks = shlex.split(cmd)
    except ValueError as e:
        return False, f"unparseable command ({e})"
    if not toks:
        return False, "empty"
    if toks[0] == "100x":
        if len(toks) < 2 or not (PLUGIN / "scripts" / f"{toks[1]}.py").is_file():
            return False, f"`100x {toks[1] if len(toks) > 1 else ''}` is not a plugin tool"
        return True, ""
    if toks[0] in EXTERNAL_TOOLS:
        return True, ""
    return False, (f"'{toks[0]}' is neither `100x <tool>`, a known external tool "
                   f"{sorted(EXTERNAL_TOOLS)}, nor review/convention")


def committed_ids(path, rev):
    """Item ids in the copy of `path` committed at `rev`, or None when there is none
    (outside a git work tree, an untracked file, an unknown rev)."""
    path = pathlib.Path(path).resolve()
    top = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0:
        return None
    try:
        rel = path.relative_to(pathlib.Path(top.stdout.strip()).resolve())
    except ValueError:
        return None
    r = subprocess.run(["git", "-C", top.stdout.strip(), "show", f"{rev}:{rel.as_posix()}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return {i.get("id") for i in json.loads(r.stdout).get("items", [])}
    except (ValueError, AttributeError):
        return None


def clause_errors(clauses, valid_work):
    """Problems with a `when_any` value; [] when it is well formed."""
    if not isinstance(clauses, list) or not clauses:
        return ["must be a non-empty list of clauses"]
    out = []
    for n, c in enumerate(clauses):
        if not isinstance(c, dict) or not c:
            out.append(f"clause {n} must be a non-empty object")
            continue
        for k, v in c.items():
            if k not in CLAUSE_KEYS:
                out.append(f"clause {n}: unknown key '{k}' (known: {', '.join(CLAUSE_KEYS)})")
            elif k in ("kinds", "work") and (not isinstance(v, list) or not v
                                              or not all(isinstance(x, str) for x in v)):
                out.append(f"clause {n}: {k} must be a non-empty list of names")
            elif k == "kinds" and not set(v) <= KNOWN_KINDS:
                out.append(f"clause {n}: unknown kind(s) {sorted(set(v) - KNOWN_KINDS)}")
            elif k == "work" and not set(v) <= valid_work:
                out.append(f"clause {n}: work must be a subset of {sorted(valid_work)}")
            elif k == "from_tier" and v not in TIER_ORDER:
                out.append(f"clause {n}: from_tier must be one of {TIER_ORDER}")
            elif k == "risk" and v not in RISK_ORDER:
                out.append(f"clause {n}: risk must be one of {RISK_ORDER}")
    return out


def lint(data, previous_ids=None):
    errs, warns = [], []
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return ["no `items` list"], warns
    for k in data:
        if k not in TOP_KEYS:
            errs.append(f"unknown top-level key '{k}' (known: {', '.join(TOP_KEYS)})")
    if data.get("schema") != SCHEMA:
        errs.append(f"\"schema\" must be {SCHEMA}, got {data.get('schema')!r}")
    ver = data.get("version")
    if type(ver) is not int or ver < 1:
        errs.append(f"\"version\" must be a positive integer, got {ver!r} — specs pin it "
                    f"(| baseline | <n> |)")
        ver = None
    valid_work = set(work_types(data)) | {"*"}
    seen = set()
    for n, i in enumerate(items):
        iid = i.get("id", f"<item {n}>")
        def e(m):
            errs.append(f"{iid}: {m}")
        for k in REQUIRED_KEYS:
            if k not in i:
                e(f"missing key '{k}'")
        for k in i:
            if k not in REQUIRED_KEYS + OPTIONAL_KEYS:
                e(f"unknown key '{k}'")
        if not ID_RX.match(str(iid)):
            e("id must look like '<area>.<slug>'")
        if iid in seen:
            e("duplicate id")
        seen.add(iid)
        if not i.get("work") or not set(i.get("work", [])) <= valid_work:
            e(f"work must be a non-empty subset of {sorted(valid_work)}")
        cls = i.get("class")
        if cls not in CLASSES:
            e(f"class must be one of {CLASSES}")
        if i.get("from_tier") not in TIER_ORDER:
            e(f"from_tier must be one of {TIER_ORDER}")
        if "risk" in i and i["risk"] not in RISK_ORDER:
            e(f"risk must be one of {RISK_ORDER}")
        src = str(i.get("source") or "").strip()
        if not src or src.upper() in ("TODO", "TBD", "N/A"):
            e("no source: every default needs the standard it comes from")
        if cls == "C":
            if i.get("default") is not None:
                e("class C must have a null default: it is asked, never defaulted")
            if not str(i.get("ask") or "").strip():
                e("class C needs an `ask`")
        elif cls in ("A", "B"):
            if not str(i.get("default") or "").strip():
                e(f"class {cls} needs a default")
            if not str(i.get("assumption_text") or "").strip():
                e(f"class {cls} needs assumption_text")
            if i.get("blocks_ready"):
                e("blocks_ready applies only to class C")
            if "door" in i:
                e("door applies only to class C: it ranks questions")
        if cls == "B" and i.get("from_tier") == "prototype":
            e("class B is tier-dependent; from_tier 'prototype' makes it always-on (use A)")
        if cls == "A" and i.get("from_tier") not in (None, "prototype"):
            e(f"class A is always-on, so from_tier must be 'prototype'; an item that turns "
              f"on at '{i.get('from_tier')}' is tier-dependent (use B)")
        if "since" in i and (type(i["since"]) is not int or i["since"] < 1
                             or (ver is not None and i["since"] > ver)):
            e(f"since must be an integer from 1 to the catalogue version ({ver})")
        if "deprecated" in i and not isinstance(i["deprecated"], bool):
            e("deprecated must be true or false")
        if "door" in i and i["door"] not in DOORS:
            e(f"door must be one of {DOORS}")
        if "when_any" in i:
            for why in clause_errors(i["when_any"], valid_work):
                e(f"when_any: {why}")
        ok, why = enforced_ok(str(i.get("enforced_by", "")))
        if not ok:
            e(f"enforced_by: {why}")
        skill = i.get("owner_skill", "")
        if not (PLUGIN / "skills" / str(skill) / "SKILL.md").is_file():
            if skill not in PENDING_SKILLS:
                e(f"owner_skill '{skill}' does not exist and is not a known pending skill")
        if not isinstance(i.get("waivable"), bool):
            e("waivable must be true or false")
    if previous_ids:
        gone = sorted(x for x in previous_ids - seen if x)
        if gone:
            errs.append(f"id(s) removed since the committed catalogue: {', '.join(gone)} — "
                        f"ids are never renamed or deleted (pinned specs list them); keep "
                        f"the item and mark it \"deprecated\": true")
    for s in sorted(PENDING_SKILLS):
        if (PLUGIN / "skills" / s / "SKILL.md").is_file():
            warns.append(f"pending skill '{s}' now exists; drop it from PENDING_SKILLS")
    return errs, warns


def cmd_lint(a):
    path = pathlib.Path(a.file) if a.file else BASELINE_PATH
    try:
        data = load(path)
    except (OSError, json.JSONDecodeError) as ex:
        print(f"cannot read {path}: {ex}", file=sys.stderr)
        return 2
    against = a.against or (None if a.file else "HEAD")
    committed = committed_ids(BASELINE_PATH, against) if against else None
    if against and committed is None:
        # Skipping the id-retention check silently would report "valid" for a catalogue
        # nobody compared: say so, and refuse when the comparison was asked for by name.
        if a.against:
            print(f"cannot read the committed catalogue at {a.against!r} (not a git work "
                  f"tree, file not committed, or unknown revision)", file=sys.stderr)
            return 2
        print("  NOTE  committed-catalogue check skipped: no git history for "
              f"{BASELINE_PATH.name} here, so deleted or renamed ids are not detected")
    errs, warns = lint(data, committed)
    n = len(data.get("items", []) or [])
    by = {c: sum(1 for i in data.get("items", []) if i.get("class") == c) for c in CLASSES}
    print(f"lint {path.name}: version {data.get('version')}, {n} items "
          f"(A {by['A']}, B {by['B']}, C {by['C']})")
    for w in warns:
        print(f"  WARN  {w}")
    for x in errs:
        print(f"  ERROR {x}")
    if errs:
        print(f"\n{len(errs)} error(s)")
        return 1
    print("baseline is valid")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--work", default="", help="comma-separated work types; "
                   "omit for cross-cutting items only")
    s.add_argument("--tier", required=True, help="|".join(TIER_ORDER))
    s.add_argument("--risk", default="none", help="|".join(RISK_ORDER))
    s.add_argument("--kind", default="", help="comma-separated feature kinds; scopes the "
                   "items whose `when_any` names kinds")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_show)
    li = sub.add_parser("lint")
    li.add_argument("--file", default=None, help="lint another baseline file")
    li.add_argument("--against", default=None,
                    help="committed revision of scripts/data/baseline.json whose ids must "
                         "all still exist (default HEAD when linting the shipped file)")
    li.set_defaults(fn=cmd_lint)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
