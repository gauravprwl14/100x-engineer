#!/usr/bin/env python3
"""Show and lint the implicit-requirements baseline (scripts/data/baseline.json).

A request never states "keyboard accessible", "authorize every endpoint" or "don't log
the session id"; a senior engineer applies them anyway. The baseline writes those
defaults down per WORK TYPE, filtered by the declared load tier and risk level, each
with the standard it comes from, so an agent applies them silently (class A/B) and
asks only what is genuinely the user's call (class C).

    baseline.py show --work web-ui,api --tier small --risk elevated
    baseline.py show --work api --tier growth --json
    baseline.py lint [--file other.json]

Python stdlib only.
"""
import argparse, json, pathlib, re, shlex, sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
DATA = PLUGIN / "scripts" / "data"
BASELINE_PATH = DATA / "baseline.json"

_tiers = json.loads((DATA / "scale_tiers.json").read_text())
TIER_ORDER = _tiers["_order"]
RISK_ORDER = _tiers["_risk"]["order"]
RISK_BY_KIND = _tiers["_risk"]["implied_by_kind"]

# Skills being written in parallel; an owner_skill naming one of these is not an
# error yet. Once the skill directory exists, lint asks for it to leave this list.
PENDING_SKILLS: set = set()

# enforced_by may name an external tool; it must be one a reader can install, not prose.
EXTERNAL_TOOLS = {"npx", "gitleaks", "semgrep", "checkov", "trivy", "syft", "buf",
                  "k6", "terraform", "scorecard", "osv-scanner", "zizmor", "tflint",
                  "pnpm", "npm", "pytest", "go", "cargo"}

WORK_ALIASES = {"public-api": "api"}
CLASSES = ("A", "B", "C")
REQUIRED_KEYS = ("id", "work", "class", "from_tier", "default", "assumption_text",
                 "source", "enforced_by", "owner_skill", "waivable")
OPTIONAL_KEYS = ("risk", "ask", "blocks_ready")
ID_RX = re.compile(r"^[a-z][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$")


def load(path=BASELINE_PATH):
    return json.loads(pathlib.Path(path).read_text())


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


def applies(item, work, tier, risk):
    if "*" not in item["work"] and not set(item["work"]) & set(work):
        return False
    if TIER_ORDER.index(tier) < TIER_ORDER.index(item["from_tier"]):
        return False
    return RISK_ORDER.index(risk) >= RISK_ORDER.index(item.get("risk", "none"))


def applicable(work, tier, risk, data=None):
    data = data or load()
    return [i for i in data["items"] if applies(i, work, tier, risk)]


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
    items = applicable(work, a.tier, a.risk, data)
    if a.json:
        print(json.dumps({"work": work, "tier": a.tier, "risk": a.risk, "items": items},
                         indent=2, ensure_ascii=False))
        return 0
    print(f"baseline for work={','.join(work) or '(cross-cutting only)'} "
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


def lint(data):
    errs, warns = [], []
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return ["no `items` list"], warns
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
        if cls == "B" and i.get("from_tier") == "prototype":
            e("class B is tier-dependent; from_tier 'prototype' makes it always-on (use A)")
        ok, why = enforced_ok(str(i.get("enforced_by", "")))
        if not ok:
            e(f"enforced_by: {why}")
        skill = i.get("owner_skill", "")
        if not (PLUGIN / "skills" / str(skill) / "SKILL.md").is_file():
            if skill not in PENDING_SKILLS:
                e(f"owner_skill '{skill}' does not exist and is not a known pending skill")
        if not isinstance(i.get("waivable"), bool):
            e("waivable must be true or false")
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
    errs, warns = lint(data)
    n = len(data.get("items", []) or [])
    by = {c: sum(1 for i in data.get("items", []) if i.get("class") == c) for c in CLASSES}
    print(f"lint {path.name}: {n} items (A {by['A']}, B {by['B']}, C {by['C']})")
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
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_show)
    li = sub.add_parser("lint")
    li.add_argument("--file", default=None, help="lint another baseline file")
    li.set_defaults(fn=cmd_lint)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
