#!/usr/bin/env python3
"""Check, reduce and build an explain-skill `scenario.json` (schema 1).

The agent writes only data; this checks it against the code and the timeline against a
pure reducer, so a page cannot cite a line that is not there or claim a cache hit the
steps do not produce. The schema is skills/explain/references/schema.md; the action
vocabulary and reducer semantics are skills/explain/references/actions.md.

    flow.py new <slug> [--out FILE] [--force]
    flow.py check <scenario.json> [--tier light|heavy] [--repo CLONE] [--rev REV] [--json]
    flow.py reduce <scenario.json> [--scenario ID] [--json]
    flow.py build <scenario.json> [--tier light|heavy] --out DIR [--assets DIR] [--repo CLONE]

check   structure, action arity and node refs, evidence anchors at their SHA (`git show`),
        counted absences (`git grep`), bare numbers in prose, tier budgets, every issue
        fixed or open, each step's `expect` and `hazard` against the reducer.
reduce  the state after every step; `--json` is the golden format tests/flow/states.json.
build   inlines skills/explain/assets/{shell.html,flow-player.js,flow-player.css} and the
        scenario into <out>/index.html, and writes the <out>/explain.md export; refuses
        what check rejects at the same tier (evidence only when --repo is given).

Exit codes: 0 clean, 1 findings, 2 unreadable input, not a git repo, or missing assets.
Python stdlib only; git via subprocess.
"""
import argparse, difflib, html, json, math, pathlib, re, subprocess, sys

from _mutation_guard import safe_record_name

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills" / "explain" / "assets"
ASSET_FILES = ("shell.html", "flow-player.js", "flow-player.css")
SHELL_TOKEN_RX = re.compile(r"\{\{(flow_[a-z]+)\}\}")
REQUIRED_SHELL_TOKENS = ("flow_css", "flow_js", "flow_data")

SCHEMA = 1
ROLES = ("client", "edge", "service", "queue", "worker", "cache", "store", "external")
SCENARIO_KINDS = ("happy", "edge", "failure", "race", "load", "issue", "fix")
SEVERITIES = ("low", "medium", "high", "critical")
SUBJECT_KINDS = ("pr", "concept", "plan")
NUMBER_TAGS = ("verified", "measured", "estimated")
STEP_TAGS = ("verified", "inferred")
HAZARDS = ("stale-writeback",)
FITS = ("pass", "fail")
TIERS = ("light", "heavy")
BUDGETS = {"light": {"nodes": 8, "scenarios": 2, "steps": 8},
           "heavy": {"nodes": 12, "scenarios": 5, "steps": 12}}
MAX_WORKER_SLOTS = 12
TIME_UNITS_MS = {"ms": 1, "s": 1000, "min": 60000, "h": 3600000}
ANCHOR_WINDOW = 2
HTTP_STATUS_MIN, HTTP_STATUS_MAX = 100, 599

ID_RX = re.compile(r"^[a-z][a-z0-9_-]*$")
EV_ID_RX = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
NAME_RX = re.compile(r"^[a-z][a-z0-9_]*$")
SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHA_RX = re.compile(r"^[0-9a-f]{7,40}$")
# A path may hold '@' (packages/@scope/x.ts); only a trailing @<7-40 hex> is the revision.
AT_RX = re.compile(r"^(?P<path>[^:]+):(?P<line>[1-9][0-9]*)(?:@(?P<rev>[0-9a-f]{7,40}))?$")
HTTP_CLASS_RX = re.compile(r"^[1-5]xx$", re.I)
PLACEHOLDER_RX = re.compile(r"\{\{\s*([^}]*?)\s*\}\}")
WORD_RX = re.compile(r"[A-Za-z0-9_]+")

KEYS = {
    "top": ({"schema", "title", "subject", "nodes", "scenarios"},
            {"tier", "numbers", "evidence", "initial", "decision", "checks", "compare"}),
    "subject": ({"kind", "lede"}, {"repo", "sha", "base", "pr"}),
    "node": ({"id", "role", "label"}, {"ref", "ev", "outside_diff", "slots"}),
    "number": ({"v", "unit", "tag"}, {"ev", "source", "basis"}),
    "evidence-at": ({"at", "anchor"}, set()),
    "evidence-absent": ({"absent", "git_grep", "path", "hits"}, set()),
    "initial": (set(), {"stores", "caches"}),
    "scenario": ({"id", "kind", "title", "steps"}, {"severity", "fixed_by", "open", "branch"}),
    "branch": ({"from", "at"}, set()),
    "step": ({"t", "do"}, {"d", "expect", "hazard", "time", "ev", "tag"}),
    "expect": (set(), {"hit", "vars", "cache", "stale", "store", "queues", "counters"}),
    "decision": ({"options", "chosen", "deciding_factor", "revisit_when", "source"}, set()),
    "option": ({"id", "label", "fit", "pros", "cons"}, {"scenario"}),
    "check": ({"scenario", "step", "q", "answer"}, set()),
}

# action -> argument kinds; a trailing "?" marks an optional argument.
ACTIONS = {
    "send": ("node", "node", "text?"),
    "reply": ("node", "node", "text?"),
    "enqueue": ("node:queue", "job"),
    "pickup": ("node:queue", "node:worker"),
    "free": ("node:worker", "job?"),
    "cache.get": ("node:cache", "key"),
    "cache.set": ("node:cache", "key", "value"),
    "cache.set-if-fresh": ("node:cache", "key", "varref"),
    "cache.del": ("node:cache", "key"),
    "cache.expire": ("node:cache", "key"),
    "mark-stale": ("node:cache", "key"),
    "db.read": ("node:store", "key", "var?"),
    "db.write": ("node:store", "key", "value"),
    "wait": ("duration",),
    "counter": ("name", "int"),
    "fail": ("node", "text?"),
    "note": ("text",),
}
DEFAULT_READ_VAR = "read"


class Unreadable(Exception):
    pass


class Findings:
    def __init__(self):
        self.items, self.notes, self.hazards = [], [], []

    def add(self, loc, msg):
        self.items.append((loc, msg))

    def note(self, msg):
        self.notes.append(msg)


# ---------------------------------------------------------------- shape helpers

def check_keys(value, kind, loc, f):
    if not isinstance(value, dict):
        f.add(loc, f"must be an object, got {type(value).__name__}")
        return False
    required, optional = KEYS[kind]
    for k in sorted(required - value.keys()):
        f.add(loc, f"missing required key '{k}'")
    for k in sorted(value.keys() - required - optional):
        near = difflib.get_close_matches(k, sorted(required | optional), n=1)
        f.add(loc, f"unknown key '{k}'" + (f" (did you mean '{near[0]}'?)" if near else ""))
    return True


def is_text(v):
    if isinstance(v, str):
        return bool(v.strip())
    return (isinstance(v, dict) and isinstance(v.get("en"), str) and bool(v["en"].strip())
            and set(v) <= {"en", "ja"} and isinstance(v.get("ja", ""), str))


def subject_of(doc):
    """The subject object, or {} when it is malformed (already a structural finding)."""
    sub = doc.get("subject")
    return sub if isinstance(sub, dict) else {}


def obj(v):
    return v if isinstance(v, dict) else {}


def seq(v):
    return v if isinstance(v, list) else []


def known(sid, table):
    return isinstance(sid, str) and sid in table


def text_en(v):
    return v if isinstance(v, str) else (v or {}).get("en", "")


def text_variants(v):
    if isinstance(v, str):
        return [("", v)]
    return [("." + lang, s) for lang, s in v.items() if isinstance(s, str)]


def is_value(v):
    """Scalar state values: string, integer, boolean or null. Floats are excluded so a
    Python and a JS reducer compare values the same way."""
    return v is None or isinstance(v, (str, bool)) or (isinstance(v, int))


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------- structure

def validate(doc, f):
    """Structural checks. Returns a context dict the reducer and later checks use."""
    if not check_keys(doc, "top", "scenario.json", f):
        return None
    if doc.get("tier") is not None and doc["tier"] not in TIERS:
        f.add("tier", f"must be one of {', '.join(TIERS)}")
    if not is_text(doc.get("title")):
        f.add("title", "must be text: a string or {\"en\": …, \"ja\"?: …}")
    validate_subject(doc, f)
    evidence = validate_evidence(doc, f)
    numbers = validate_numbers(doc, evidence, f)
    nodes = validate_nodes(doc, evidence, f)
    ctx = {"doc": doc, "nodes": nodes, "numbers": numbers, "evidence": evidence,
           "initial": validate_initial(doc, nodes, f), "scenarios": index_scenarios(doc, f)}
    for sid, scenario in ctx["scenarios"].items():
        validate_scenario(sid, scenario, ctx, f)
    validate_extras(doc, ctx, f)
    return ctx


def validate_subject(doc, f):
    sub = doc.get("subject")
    if check_keys(sub, "subject", "subject", f):
        if sub.get("kind") not in SUBJECT_KINDS:
            f.add("subject.kind", f"must be one of {', '.join(SUBJECT_KINDS)}")
        if not is_text(sub.get("lede")):
            f.add("subject.lede", "must be text")
        for k in ("sha", "base"):
            if k in sub and not (isinstance(sub[k], str) and SHA_RX.match(sub[k])):
                f.add(f"subject.{k}", "must be a hex commit SHA (7-40 chars)")
        if sub.get("kind") == "pr" and "sha" not in sub:
            f.add("subject.sha", "subject.kind pr needs subject.sha: evidence must be pinned")
        if "pr" in sub and not (is_int(sub["pr"]) and sub["pr"] > 0):
            f.add("subject.pr", "must be a positive integer")


def validate_evidence(doc, f):
    evidence = doc.get("evidence", {})
    if not isinstance(evidence, dict):
        f.add("evidence", "must be an object keyed by evidence id")
        evidence = {}
    for eid, e in evidence.items():
        loc = f"evidence.{eid}"
        if not EV_ID_RX.match(eid):
            f.add(loc, "evidence id must match [A-Za-z][A-Za-z0-9_.-]*")
        if isinstance(e, dict) and "absent" in e:
            if check_keys(e, "evidence-absent", loc, f):
                if not is_text(e.get("absent")):
                    f.add(loc + ".absent", "must be text naming what is absent")
                for k in ("git_grep", "path"):
                    if not (isinstance(e.get(k), str) and e[k].strip()):
                        f.add(f"{loc}.{k}", "must be a non-empty string")
                if not (is_int(e.get("hits")) and e["hits"] >= 0):
                    f.add(loc + ".hits", "must be a non-negative integer")
        elif check_keys(e, "evidence-at", loc, f):
            if not (isinstance(e.get("at"), str) and AT_RX.match(e["at"])):
                f.add(loc + ".at", "must be 'path:line' or 'path:line@<hex sha>'")
            if not (isinstance(e.get("anchor"), str) and e["anchor"].strip()):
                f.add(loc + ".anchor", "must be a non-empty token found on the cited line")
    return evidence


def validate_numbers(doc, evidence, f):
    numbers = doc.get("numbers", {})
    if not isinstance(numbers, dict):
        f.add("numbers", "must be an object keyed by number name")
        numbers = {}
    for name, n in numbers.items():
        loc = f"numbers.{name}"
        if not NAME_RX.match(name):
            f.add(loc, "number name must match [a-z][a-z0-9_]*")
        if not check_keys(n, "number", loc, f):
            continue
        if not (isinstance(n.get("v"), (int, float)) and not isinstance(n.get("v"), bool)):
            f.add(loc + ".v", "must be a number")
        if not (isinstance(n.get("unit"), str) and n["unit"].strip()):
            f.add(loc + ".unit", "must be a non-empty string")
        tag = n.get("tag")
        if tag not in NUMBER_TAGS:
            f.add(loc + ".tag", f"must be one of {', '.join(NUMBER_TAGS)}")
        elif tag == "verified" and not known(n.get("ev"), evidence):
            f.add(loc + ".ev", "a verified number cites an evidence id that exists")
        elif tag == "measured" and not is_text(n.get("source")):
            f.add(loc + ".source", "a measured number names the command or dashboard it came from")
        elif tag == "estimated" and not is_text(n.get("basis")):
            f.add(loc + ".basis", "an estimated number states its inputs and arithmetic")
        if "ev" in n and not known(n["ev"], evidence):
            f.add(loc + ".ev", f"unknown evidence id '{n['ev']}'")
    return numbers


def validate_nodes(doc, evidence, f):
    nodes = {}
    raw_nodes = doc.get("nodes")
    if not (isinstance(raw_nodes, list) and raw_nodes):
        f.add("nodes", "must be a non-empty list")
        raw_nodes = []
    for i, n in enumerate(raw_nodes):
        loc = f"nodes[{i}]"
        if not check_keys(n, "node", loc, f):
            continue
        nid = n.get("id")
        if not (isinstance(nid, str) and ID_RX.match(nid)):
            f.add(loc + ".id", "must match [a-z][a-z0-9_-]*")
            continue
        if nid in nodes:
            f.add(loc + ".id", f"duplicate node id '{nid}'")
        if n.get("role") not in ROLES:
            f.add(loc + ".role", f"must be one of {', '.join(ROLES)}")
        if not is_text(n.get("label")):
            f.add(loc + ".label", "must be text")
        if "ev" in n and not known(n["ev"], evidence):
            f.add(loc + ".ev", f"unknown evidence id '{n['ev']}'")
        if "outside_diff" in n and not isinstance(n["outside_diff"], bool):
            f.add(loc + ".outside_diff", "must be true or false")
        if "slots" in n:
            if n.get("role") != "worker":
                f.add(loc + ".slots", "only a worker node has slots")
            elif not (is_int(n["slots"]) and 1 <= n["slots"] <= MAX_WORKER_SLOTS):
                f.add(loc + ".slots", f"must be an integer from 1 to {MAX_WORKER_SLOTS}")
        nodes[nid] = n
    return nodes


def validate_initial(doc, nodes, f):
    initial = doc.get("initial", {})
    if check_keys(initial, "initial", "initial", f):
        for kind, role in (("stores", "store"), ("caches", "cache")):
            block = initial.get(kind, {})
            if not isinstance(block, dict):
                f.add(f"initial.{kind}", "must be an object keyed by node id")
                continue
            for nid, kv in block.items():
                loc = f"initial.{kind}.{nid}"
                if nid not in nodes:
                    f.add(loc, f"unknown node '{nid}'")
                elif nodes[nid].get("role") != role:
                    f.add(loc, f"node '{nid}' is not a {role}")
                if not (isinstance(kv, dict) and all(is_value(v) for v in kv.values())):
                    f.add(loc, "must map keys to string, integer, boolean or null values")
        return initial
    return {}


def index_scenarios(doc, f):
    scenarios = {}
    raw_sc = doc.get("scenarios")
    if not (isinstance(raw_sc, list) and raw_sc):
        f.add("scenarios", "must be a non-empty list")
        raw_sc = []
    for i, s in enumerate(raw_sc):
        loc = f"scenarios[{i}]"
        if not check_keys(s, "scenario", loc, f):
            continue
        sid = s.get("id")
        if not (isinstance(sid, str) and ID_RX.match(sid)):
            f.add(loc + ".id", "must match [a-z][a-z0-9_-]*")
            continue
        if sid in scenarios:
            f.add(loc + ".id", f"duplicate scenario id '{sid}'")
        scenarios[sid] = s
    return scenarios


def validate_scenario(sid, s, ctx, f):
    loc = f"scenario {sid}"
    if s.get("kind") not in SCENARIO_KINDS:
        f.add(loc + ".kind", f"must be one of {', '.join(SCENARIO_KINDS)}")
    if not is_text(s.get("title")):
        f.add(loc + ".title", "must be text")
    sev = s.get("severity")
    if sev is not None and sev not in SEVERITIES:
        f.add(loc + ".severity", f"must be one of {', '.join(SEVERITIES)}")
    if s.get("kind") == "issue" and sev is None:
        f.add(loc + ".severity", "an issue scenario states its severity")
    if s.get("kind") in ("happy", "fix") and sev is not None:
        f.add(loc + ".severity", f"a {s['kind']} scenario is not an issue: drop severity")
    if "open" in s and not isinstance(s["open"], bool):
        f.add(loc + ".open", "must be true or false")
    fixed_by = s.get("fixed_by")
    if fixed_by is not None:
        if not (isinstance(fixed_by, list) and fixed_by and all(isinstance(x, str) for x in fixed_by)):
            f.add(loc + ".fixed_by", "must be a non-empty list of fix scenario ids")
        else:
            for fid in fixed_by:
                target = ctx["scenarios"].get(fid)
                if target is None:
                    f.add(loc + ".fixed_by", f"unknown scenario '{fid}'")
                elif target.get("kind") != "fix":
                    f.add(loc + ".fixed_by", f"scenario '{fid}' is kind {target.get('kind')}, not fix")
    if sev is not None and not fixed_by and s.get("open") is not True:
        f.add(loc, "issue has neither fixed_by nor open: true")
    br = s.get("branch")
    if br is not None and check_keys(br, "branch", loc + ".branch", f):
        src = ctx["scenarios"].get(br.get("from")) if isinstance(br.get("from"), str) else None
        if src is None:
            f.add(loc + ".branch.from", f"unknown scenario '{br.get('from')}'")
        elif not (is_int(br.get("at")) and br["at"] >= 1):
            f.add(loc + ".branch.at", "must be a positive integer")
    steps = s.get("steps")
    if not (isinstance(steps, list) and steps):
        f.add(loc + ".steps", "must be a non-empty list")
        return
    for j, st in enumerate(steps):
        validate_step(f"{loc} step {j}", st, ctx, f)


def validate_step(loc, st, ctx, f):
    if not check_keys(st, "step", loc, f):
        return
    for k in ("t", "d", "time"):
        if k in st and not is_text(st[k]):
            f.add(f"{loc}.{k}", "must be text")
    ev = st.get("ev", [])
    if not (isinstance(ev, list) and all(isinstance(x, str) for x in ev)):
        f.add(loc + ".ev", "must be a list of evidence ids")
        ev = []
    for eid in ev:
        if eid not in ctx["evidence"]:
            f.add(loc + ".ev", f"unknown evidence id '{eid}'")
    tag = st.get("tag")
    if tag is not None and tag not in STEP_TAGS:
        f.add(loc + ".tag", f"must be one of {', '.join(STEP_TAGS)}")
    acts = st.get("do")
    guarded = isinstance(acts, list) and any(isinstance(a, list) and a[:1] == ["cache.set-if-fresh"] for a in acts)
    if not ev and guarded:
        f.add(loc, "cache.set-if-fresh is atomic only in the reducer: cite in ev the primitive "
                   "that makes it atomic in the code (CAS, Lua script, version column or lock)")
    elif not ev and tag != "inferred":
        f.add(loc, "step has no evidence: cite ev ids or tag it inferred")
    hz = st.get("hazard")
    if hz is not None:
        for h in ([hz] if isinstance(hz, str) else hz if isinstance(hz, list) else [None]):
            if h not in HAZARDS:
                f.add(loc + ".hazard", f"must be one of {', '.join(HAZARDS)} (or a list of them)")
    if "expect" in st:
        validate_expect(loc + ".expect", st["expect"], ctx, f)
    if not (isinstance(acts, list) and acts):
        f.add(loc + ".do", "must be a non-empty list of [action, …args]")
        return
    for k, a in enumerate(acts):
        validate_action(f"{loc}.do[{k}]", a, ctx, f)


def validate_expect(loc, ex, ctx, f):
    if not check_keys(ex, "expect", loc, f):
        return
    if "hit" in ex and ex["hit"] not in ("hit", "miss", None):
        f.add(loc + ".hit", "must be 'hit', 'miss' or null")
    roles = {"cache": "cache", "stale": "cache", "store": "store", "queues": "queue"}
    for k, role in roles.items():
        block = ex.get(k)
        if block is None:
            continue
        if not isinstance(block, dict):
            f.add(f"{loc}.{k}", "must be an object keyed by node id")
            continue
        for nid, v in block.items():
            node = ctx["nodes"].get(nid)
            if node is None or node.get("role") != role:
                f.add(f"{loc}.{k}.{nid}", f"unknown node '{nid}' or not a {role}")
            elif k == "queues" and not (is_int(v) and v >= 0):
                f.add(f"{loc}.{k}.{nid}", "must be the expected queue length")
            elif k != "queues" and not (isinstance(v, dict) and all(
                    isinstance(x, bool) if k == "stale" else is_value(x) for x in v.values())):
                f.add(f"{loc}.{k}.{nid}", "must map keys to expected values")
    for k in ("vars", "counters"):
        block = ex.get(k)
        if block is not None and not (isinstance(block, dict) and all(
                is_int(v) if k == "counters" else is_value(v) for v in block.values())):
            f.add(f"{loc}.{k}", "must map names to expected values")


def validate_action(loc, a, ctx, f):
    if not (isinstance(a, list) and a and isinstance(a[0], str)):
        f.add(loc, "must be [action, …args]")
        return
    name, args = a[0], a[1:]
    spec = ACTIONS.get(name)
    if spec is None:
        near = difflib.get_close_matches(name, ACTIONS, n=1)
        f.add(loc, f"unknown action '{name}'" + (f" (did you mean '{near[0]}'?)" if near else ""))
        return
    lo = sum(1 for k in spec if not k.endswith("?"))
    if not lo <= len(args) <= len(spec):
        want = str(lo) if lo == len(spec) else f"{lo}-{len(spec)}"
        f.add(loc, f"wrong arity: {name} takes {want} argument(s), got {len(args)}")
        return
    for kind, v in zip(spec, args):
        kind = kind.rstrip("?")
        where = f"{loc} {name}"
        if kind.startswith("node"):
            node = ctx["nodes"].get(v) if isinstance(v, str) else None
            if node is None:
                f.add(where, f"unknown node '{v}'")
            elif ":" in kind and node.get("role") != kind.split(":")[1]:
                f.add(where, f"node '{v}' is a {node.get('role')}, {name} needs a {kind.split(':')[1]}")
        elif kind in ("key", "job"):
            if not (isinstance(v, str) and v.strip()):
                f.add(where, f"{kind} must be a non-empty string")
        elif kind == "value":
            if isinstance(v, str) and v.startswith("$"):
                if not NAME_RX.match(v[1:]):
                    f.add(where, f"variable '{v}' must be $[a-z][a-z0-9_]*")
            elif not is_value(v):
                f.add(where, "value must be a string, integer, boolean, null or $variable")
        elif kind == "varref":
            if not (isinstance(v, str) and v.startswith("$") and NAME_RX.match(v[1:])):
                f.add(where, f"{name} needs a $variable bound by db.read, got {json.dumps(v)}")
        elif kind in ("var", "name"):
            if not (isinstance(v, str) and NAME_RX.match(v)):
                f.add(where, f"{kind} must match [a-z][a-z0-9_]*")
        elif kind == "int":
            if not is_int(v):
                f.add(where, "delta must be an integer")
        elif kind == "text":
            if not is_text(v):
                f.add(where, "must be text")
        elif kind == "duration":
            m = PLACEHOLDER_RX.fullmatch(v) if isinstance(v, str) else None
            n = ctx["numbers"].get(m.group(1)) if m else None
            if not isinstance(n, dict):
                f.add(where, "duration must be a {{name}} placeholder of a number in numbers")
            elif not known(n.get("unit"), TIME_UNITS_MS):
                f.add(where, f"number '{m.group(1)}' has unit {n.get('unit')!r}; wait needs "
                             f"one of {', '.join(TIME_UNITS_MS)}")


def validate_extras(doc, ctx, f):
    scenarios = ctx["scenarios"]
    dec = doc.get("decision")
    if dec is not None and check_keys(dec, "decision", "decision", f):
        opts = dec.get("options")
        ids = []
        if not (isinstance(opts, list) and len(opts) >= 2):
            f.add("decision.options", "must list at least two options")
            opts = opts if isinstance(opts, list) else []
        for i, o in enumerate(opts):
            loc = f"decision.options[{i}]"
            if not check_keys(o, "option", loc, f):
                continue
            ids.append(o.get("id"))
            if not is_text(o.get("label")):
                f.add(loc + ".label", "must be text")
            if o.get("fit") not in FITS:
                f.add(loc + ".fit", "must be 'pass' or 'fail' (does it solve the problem at all?)")
            for k in ("pros", "cons"):
                if not (isinstance(o.get(k), list) and all(is_text(x) for x in o[k])):
                    f.add(f"{loc}.{k}", "must be a list of text")
            if "scenario" in o and not known(o["scenario"], scenarios):
                f.add(loc + ".scenario", f"unknown scenario '{o['scenario']}'")
        if len({json.dumps(i) for i in ids}) != len(ids):
            f.add("decision.options", "option ids must be unique")
        chosen = next((o for o in opts if isinstance(o, dict) and o.get("id") == dec.get("chosen")), None)
        if chosen is None:
            f.add("decision.chosen", f"'{dec.get('chosen')}' is not an option id")
        elif chosen.get("fit") != "pass":
            f.add("decision.chosen", "the chosen option fails the fit filter")
        for k in ("deciding_factor", "revisit_when"):
            if not is_text(dec.get(k)):
                f.add(f"decision.{k}", "must be text")
        if not (isinstance(dec.get("source"), str) and dec["source"].strip()):
            f.add("decision.source", "must name where the decision is recorded")
    checks = doc.get("checks")
    if checks is not None:
        if not isinstance(checks, list):
            f.add("checks", "must be a list")
            checks = []
        for i, c in enumerate(checks):
            loc = f"checks[{i}]"
            if not check_keys(c, "check", loc, f):
                continue
            if not known(c.get("scenario"), scenarios):
                f.add(loc + ".scenario", f"unknown scenario '{c.get('scenario')}'")
            elif not is_int(c.get("step")) or c["step"] < 0:
                f.add(loc + ".step", "must be a step index")
            for k in ("q", "answer"):
                if not is_text(c.get(k)):
                    f.add(f"{loc}.{k}", "must be text")
    cmp_ = doc.get("compare")
    if cmp_ is not None:
        if not (isinstance(cmp_, list) and len(set(map(str, cmp_))) >= 2 and len(set(map(str, cmp_))) == len(cmp_)):
            f.add("compare", "must list at least two distinct scenario ids")
        else:
            for sid in cmp_:
                if not known(sid, scenarios):
                    f.add("compare", f"unknown scenario '{sid}'")


# ---------------------------------------------------------------- prose numbers

def prose_fields(doc):
    """Yield (location, text, allow_http_status) for every prose field."""
    yield "title", doc.get("title"), False
    yield "subject.lede", subject_of(doc).get("lede"), False
    for i, n in enumerate(seq(doc.get("nodes"))):
        if isinstance(n, dict):
            yield f"nodes[{i}].label", n.get("label"), False
    for eid, e in obj(doc.get("evidence")).items():
        if isinstance(e, dict) and "absent" in e:
            yield f"evidence.{eid}.absent", e.get("absent"), False
    for s in seq(doc.get("scenarios")):
        if not isinstance(s, dict):
            continue
        loc = f"scenario {s.get('id')}"
        yield loc + ".title", s.get("title"), False
        for j, st in enumerate(seq(s.get("steps"))):
            if not isinstance(st, dict):
                continue
            for k in ("t", "d", "time"):
                yield f"{loc} step {j}.{k}", st.get(k), False
            for k, a in enumerate(seq(st.get("do"))):
                if not (isinstance(a, list) and a and isinstance(a[0], str) and a[0] in ACTIONS):
                    continue
                for kind, v in zip(ACTIONS[a[0]], a[1:]):
                    if kind.rstrip("?") == "text":
                        yield f"{loc} step {j}.do[{k}]", v, a[0] == "reply"
    dec = obj(doc.get("decision"))
    for i, o in enumerate(seq(dec.get("options"))):
        if isinstance(o, dict):
            yield f"decision.options[{i}].label", o.get("label"), False
            for k in ("pros", "cons"):
                for x in seq(o.get(k)):
                    yield f"decision.options[{i}].{k}", x, False
    for k in ("deciding_factor", "revisit_when"):
        yield f"decision.{k}", dec.get(k), False
    for i, c in enumerate(seq(doc.get("checks"))):
        if isinstance(c, dict):
            yield f"checks[{i}].q", c.get("q"), False
            yield f"checks[{i}].answer", c.get("answer"), False


def bare_numbers(text, allow_http_status, pr=None):
    """Digits that should be a {{name}}. Exempt: ids such as C3, an HTTP class such as 5xx,
    the subject's own PR number, and a status code in a reply label."""
    out = []
    for w in WORD_RX.findall(PLACEHOLDER_RX.sub(" ", text)):
        if not w[0].isdigit() or HTTP_CLASS_RX.match(w) or w == pr:
            continue
        if allow_http_status and w.isdigit() and HTTP_STATUS_MIN <= int(w) <= HTTP_STATUS_MAX:
            continue
        out.append(w)
    return out


def check_prose(doc, numbers, f):
    pr = subject_of(doc).get("pr")
    pr = str(pr) if is_int(pr) and pr > 0 else None
    for loc, value, http in prose_fields(doc):
        if value is None or not is_text(value):
            continue
        for suffix, s in text_variants(value):
            for name in PLACEHOLDER_RX.findall(s):
                if name not in numbers:
                    f.add(loc + suffix, f"unknown number '{{{{{name}}}}}': add it to numbers with a tag")
            bare = bare_numbers(s, http, pr)
            if bare:
                f.add(loc + suffix, f"bare number {', '.join(repr(b) for b in bare)} in prose: "
                                    "use a {{name}} placeholder backed by numbers")


# ---------------------------------------------------------------- reducer

class ReduceError(Exception):
    pass


def effective_steps(sid, scenarios, seen=None):
    """[(step, origin_scenario_id, origin_index)] for a scenario, branches expanded."""
    seen = seen or []
    if sid in seen:
        raise ReduceError(f"branch cycle: {' -> '.join(seen + [sid])}")
    s = scenarios[sid]
    own = [(st, sid, j) for j, st in enumerate(s["steps"])]
    br = s.get("branch")
    if not br:
        return own
    parent = effective_steps(br["from"], scenarios, seen + [sid])
    if br["at"] > len(parent):
        raise ReduceError(f"scenario {sid}: branch.at {br['at']} is past the {len(parent)} "
                          f"step(s) of {br['from']}")
    return parent[:br["at"]] + own


def initial_state(ctx):
    nodes, init = ctx["nodes"], ctx["initial"]
    by_role = lambda r: [nid for nid, n in nodes.items() if n.get("role") == r]
    return {
        "clock_ms": 0,
        "queues": {q: [] for q in by_role("queue")},
        "workers": {w: [None] * nodes[w].get("slots", 1) for w in by_role("worker")},
        "caches": {c: {k: {"v": v, "stale": False, "src": None}
                       for k, v in (init.get("caches") or {}).get(c, {}).items()}
                   for c in by_role("cache")},
        "stores": {s: dict((init.get("stores") or {}).get(s, {})) for s in by_role("store")},
        "vars": {},
        "counters": {},
        "failed": [],
    }


def ms_of(placeholder, numbers):
    n = numbers[PLACEHOLDER_RX.fullmatch(placeholder).group(1)]
    return int(math.floor(n["v"] * TIME_UNITS_MS[n["unit"]] + 0.5))  # JS Math.round


def apply(state, step_out, action, numbers):
    name, args = action[0], action[1:]
    touch = lambda nid: step_out["active"].append(nid) if nid not in step_out["active"] else None
    if name in ("send", "reply"):
        touch(args[0]); touch(args[1])
        step_out["messages"].append({"kind": name, "from": args[0], "to": args[1],
                                     "label": args[2] if len(args) > 2 else None})
        return
    touch(args[0]) if name not in ("wait", "counter", "note") else None
    if name == "enqueue":
        state["queues"][args[0]].append(args[1])
    elif name == "pickup":
        touch(args[1])
        q, slots = state["queues"][args[0]], state["workers"][args[1]]
        if not q:
            raise ReduceError(f"pickup: queue '{args[0]}' is empty")
        if None not in slots:
            raise ReduceError(f"pickup: worker '{args[1]}' has no free slot")
        slots[slots.index(None)] = q.pop(0)
    elif name == "free":
        slots = state["workers"][args[0]]
        target = args[1] if len(args) > 1 else next((j for j in slots if j is not None), None)
        if target is None or target not in slots:
            raise ReduceError(f"free: worker '{args[0]}' holds no job"
                              + (f" '{args[1]}'" if len(args) > 1 else ""))
        slots[slots.index(target)] = None
    elif name == "cache.get":
        step_out["hit"] = "hit" if args[1] in state["caches"][args[0]] else "miss"
    elif name == "cache.set":
        cache, key, value = args
        src = None
        if isinstance(value, str) and value.startswith("$"):
            var = state["vars"].get(value[1:])
            if var is None:
                raise ReduceError(f"cache.set: variable '{value}' is unbound")
            value, src = var["v"], var["src"]
        stale = False
        if src is not None:
            store, skey = src
            current = state["stores"][store].get(skey)
            if not same(current, value):
                stale = True
                step_out["hazards"].append({"kind": "stale-writeback", "cache": cache, "key": key,
                                            "store": store, "store_key": skey})
        state["caches"][cache][key] = {"v": value, "stale": stale, "src": src}
    elif name == "cache.set-if-fresh":
        cache, key, ref = args
        var = state["vars"].get(ref[1:])
        if var is None:
            raise ReduceError(f"cache.set-if-fresh: variable '{ref}' is unbound")
        store, skey = var["src"]
        current = state["stores"][store].get(skey)
        if same(current, var["v"]):
            state["caches"][cache][key] = {"v": var["v"], "stale": False, "src": var["src"]}
        else:
            step_out["skipped"].append({"cache": cache, "key": key, "store": store, "store_key": skey,
                                        "read": var["v"], "current": current})
    elif name in ("cache.del", "cache.expire"):
        state["caches"][args[0]].pop(args[1], None)
    elif name == "mark-stale":
        entry = state["caches"][args[0]].get(args[1])
        if entry is None:
            raise ReduceError(f"mark-stale: cache '{args[0]}' has no key '{args[1]}'")
        entry["stale"] = True
    elif name == "db.read":
        var = args[2] if len(args) > 2 else DEFAULT_READ_VAR
        state["vars"][var] = {"v": state["stores"][args[0]].get(args[1]), "src": [args[0], args[1]]}
    elif name == "db.write":
        store, skey, value = args
        if isinstance(value, str) and value.startswith("$"):
            var = state["vars"].get(value[1:])
            if var is None:
                raise ReduceError(f"db.write: variable '{value}' is unbound")
            value = var["v"]
        state["stores"][store][skey] = value
        for entries in state["caches"].values():
            for entry in entries.values():
                if entry["src"] == [store, skey] and not same(entry["v"], value):
                    entry["stale"] = True
    elif name == "wait":
        state["clock_ms"] += ms_of(args[0], numbers)
    elif name == "counter":
        state["counters"][args[0]] = state["counters"].get(args[0], 0) + args[1]
    elif name == "fail":
        if args[0] not in state["failed"]:
            state["failed"].append(args[0])
        step_out["failures"].append({"node": args[0], "label": args[1] if len(args) > 1 else None})
    elif name == "note":
        step_out["notes"].append(args[0])


def reduce_scenario(sid, ctx):
    """States after each effective step. Raises ReduceError naming the failing step."""
    scenarios = ctx["scenarios"]
    steps = effective_steps(sid, scenarios)
    state, states = initial_state(ctx), []
    for i, (st, origin, j) in enumerate(steps):
        out = {"active": [], "messages": [], "hit": None, "failures": [], "notes": [], "hazards": [],
               "skipped": []}
        for a in st["do"]:
            try:
                apply(state, out, a, ctx["numbers"])
            except ReduceError as e:
                raise ReduceError(f"scenario {origin} step {j}: {e}")
        snap = json.loads(json.dumps(state))
        states.append({"step": i, "origin": origin, "origin_step": j, "inherited": origin != sid,
                       "clock_ms": snap["clock_ms"], "active": out["active"],
                       "messages": out["messages"], "hit": out["hit"],
                       "queues": snap["queues"], "workers": snap["workers"],
                       "caches": snap["caches"], "stores": snap["stores"], "vars": snap["vars"],
                       "counters": snap["counters"], "failed": snap["failed"],
                       "failures": out["failures"], "notes": out["notes"],
                       "hazards": out["hazards"], "skipped": out["skipped"]})
    return states


def reduce_all(ctx, f, only=None):
    result = {}
    for sid in ctx["scenarios"]:
        if only and sid != only:
            continue
        try:
            result[sid] = reduce_scenario(sid, ctx)
        except ReduceError as e:
            f.add("reducer", str(e))
    return result


def check_expectations(ctx, states, f):
    for sid, sts in states.items():
        for state in sts:
            if state["inherited"]:
                continue  # checked once, in the scenario that owns the step
            st = ctx["scenarios"][sid]["steps"][state["origin_step"]]
            loc = f"scenario {sid} step {state['origin_step']}"
            produced = sorted({h["kind"] for h in state["hazards"]})
            for h in state["hazards"]:
                f.hazards.append(f"{sid}#{state['step']}: {h['kind']} cache {h['cache']} key "
                                 f"{h['key']} <- store {h['store']} key {h['store_key']}")
            hz = st.get("hazard")
            declared = sorted(set([hz] if isinstance(hz, str) else hz or []))
            for h in sorted(set(produced) - set(declared)):
                f.add(loc, f"undeclared hazard: the reducer produces {h}; add \"hazard\": \"{h}\"")
            for h in sorted(set(declared) - set(produced)):
                f.add(loc, f"expect contradicts reducer: hazard {h} is declared but not produced")
            for k, want, got in expectation_pairs(st.get("expect") or {}, state):
                if not same(want, got):
                    f.add(loc, f"expect contradicts reducer: {k} expected "
                               f"{json.dumps(want)}, reducer has {json.dumps(got)}")


def expectation_pairs(ex, state):
    if "hit" in ex:
        yield "hit", ex["hit"], state["hit"]
    for name, v in (ex.get("vars") or {}).items():
        var = state["vars"].get(name)
        yield f"vars.{name}", v, var["v"] if var else None
    for cache, kv in (ex.get("cache") or {}).items():
        for key, v in kv.items():
            entry = state["caches"][cache].get(key)
            yield f"cache.{cache}[{key}]", v, entry["v"] if entry else None
    for cache, kv in (ex.get("stale") or {}).items():
        for key, v in kv.items():
            entry = state["caches"][cache].get(key)
            yield f"stale.{cache}[{key}]", v, bool(entry and entry["stale"])
    for store, kv in (ex.get("store") or {}).items():
        for key, v in kv.items():
            yield f"store.{store}[{key}]", v, state["stores"][store].get(key)
    for q, n in (ex.get("queues") or {}).items():
        yield f"queues.{q}", n, len(state["queues"][q])
    for name, n in (ex.get("counters") or {}).items():
        yield f"counters.{name}", n, state["counters"].get(name, 0)


# ---------------------------------------------------------------- budgets

def check_budget(ctx, states, tier, f):
    b = BUDGETS[tier]
    if len(ctx["nodes"]) > b["nodes"]:
        f.add("nodes", f"over budget ({tier}): {len(ctx['nodes'])} nodes, max {b['nodes']}")
    if len(ctx["scenarios"]) > b["scenarios"]:
        f.add("scenarios", f"over budget ({tier}): {len(ctx['scenarios'])} scenarios, max "
                           f"{b['scenarios']}" + ("; split it or use --tier heavy" if tier == "light" else ""))
    for sid, sts in states.items():
        if len(sts) > b["steps"]:
            f.add(f"scenario {sid}", f"over budget ({tier}): {len(sts)} steps incl. inherited, "
                                     f"max {b['steps']}")
    for c in seq(ctx["doc"].get("checks")):
        if isinstance(c, dict) and known(c.get("scenario"), states) and is_int(c.get("step")) \
                and c["step"] >= len(states[c["scenario"]]):
            f.add("checks", f"step {c['step']} is past the end of scenario {c['scenario']}")
    if tier == "light":
        for k in ("compare", "checks"):
            if ctx["doc"].get(k):
                f.note(f"{k} is a heavy-tier field; the light renderer ignores it")


# ---------------------------------------------------------------- evidence

def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True)
    return p.returncode, p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace").strip()


def check_evidence(ctx, repo, rev_flag, f):
    evidence = ctx["evidence"]
    if not evidence:
        return
    rc, _, err = git(repo, "rev-parse", "--show-toplevel")
    if rc != 0:
        raise Unreadable(f"not a git repository: {repo} (evidence needs --repo <clone>)")
    sha = subject_of(ctx["doc"]).get("sha")
    default_rev = (sha if isinstance(sha, str) and SHA_RX.match(sha) else None) or rev_flag or "HEAD"
    resolved, files = {}, {}

    def resolve(rev):
        if rev not in resolved:
            rc, out, _ = git(repo, "rev-parse", "--verify", "--quiet", rev + "^{commit}")
            resolved[rev] = out.strip() if rc == 0 else None
        return resolved[rev]

    for eid, e in evidence.items():
        loc = f"evidence.{eid}"
        if not isinstance(e, dict):
            continue
        if "absent" in e:
            if not (isinstance(e.get("git_grep"), str) and isinstance(e.get("path"), str)
                    and is_int(e.get("hits"))):
                continue  # already a structural finding
            rev = default_rev
            sha = resolve(rev)
            if sha is None:
                f.add(loc, f"absence: revision {rev} not found in {repo}")
                continue
            rc, out, err = git(repo, "grep", "-n", "-E", "-e", e["git_grep"], sha, "--", e["path"])
            if rc not in (0, 1):
                f.add(loc, f"absence: git grep failed: {err}")
                continue
            hits = len([l for l in out.splitlines() if l.strip()])
            if hits != e["hits"]:
                f.add(loc, f"absence contradicted: says {e['hits']} hit(s) for /{e['git_grep']}/ in "
                           f"{e['path']}, git grep finds {hits} at {sha[:12]}")
            continue
        m = AT_RX.match(e["at"]) if isinstance(e.get("at"), str) else None
        if not m or not (isinstance(e.get("anchor"), str) and e["anchor"].strip()):
            continue  # already a structural finding
        rev = m.group("rev") or default_rev
        sha = resolve(rev)
        if sha is None:
            f.add(loc, f"bad anchor: revision {rev} not found in {repo}")
            continue
        path, line = m.group("path"), int(m.group("line"))
        if (sha, path) not in files:
            rc, out, _ = git(repo, "show", f"{sha}:{path}")
            files[(sha, path)] = out.splitlines() if rc == 0 else None
        lines = files[(sha, path)]
        if lines is None:
            f.add(loc, f"bad anchor: {path} does not exist at {sha[:12]}")
        elif line > len(lines):
            f.add(loc, f"bad anchor: {path} has {len(lines)} lines at {sha[:12]}, cited line {line}")
        else:
            lo, hi = max(1, line - ANCHOR_WINDOW), min(len(lines), line + ANCHOR_WINDOW)
            if not any(e["anchor"] in lines[n - 1] for n in range(lo, hi + 1)):
                f.add(loc, f"bad anchor: '{e['anchor']}' not within ±{ANCHOR_WINDOW} lines of "
                           f"{path}:{line} at {sha[:12]}")


# ---------------------------------------------------------------- commands

def load(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise Unreadable(f"cannot read {path}: {e}")
    except json.JSONDecodeError as e:
        raise Unreadable(f"cannot read {path}: invalid JSON: {e}")


def prepare(path):
    doc = load(path)
    if not isinstance(doc, dict):
        raise Unreadable(f"cannot read {path}: top level must be an object")
    if doc.get("schema") != SCHEMA:
        raise Unreadable(f"cannot read {path}: schema must be {SCHEMA}, got {doc.get('schema')!r}")
    f = Findings()
    ctx = validate(doc, f)
    return doc, ctx, f


def run_checks(doc, ctx, f, tier, repo, rev):
    """Every check `flow check` runs, shared with `flow build`. Evidence needs a clone
    (repo None skips it) and a structurally clean file: on a malformed one it would only
    add noise, or call git with garbage."""
    states = {}
    if ctx is None:
        return states
    structural = bool(f.items)
    if not structural:
        states = reduce_all(ctx, f)
        check_expectations(ctx, states, f)
    check_prose(doc, ctx["numbers"], f)
    check_budget(ctx, states, tier, f)
    if repo is not None and not structural:
        check_evidence(ctx, repo, rev, f)
    return states


def run_check(path, tier, repo, rev, as_json):
    doc, ctx, f = prepare(path)
    tier = tier or (doc.get("tier") if doc.get("tier") in TIERS else None) or "light"
    run_checks(doc, ctx, f, tier, repo, rev)
    if as_json:
        print(json.dumps({"file": str(path), "tier": tier,
                          "findings": [{"loc": l, "message": m} for l, m in f.items],
                          "hazards": f.hazards, "notes": f.notes}, indent=2, ensure_ascii=False))
    else:
        print(f"flow check: {path} (tier {tier})")
        for l, m in f.items:
            print(f"  FINDING {l}: {m}")
        for h in f.hazards:
            print(f"  HAZARD {h}")
        for n in f.notes:
            print(f"  NOTE {n}")
        print(f"flow check: {len(f.items)} finding(s), {len(f.hazards)} hazard(s)")
    return 1 if f.items else 0


def structural_or_exit(path):
    doc, ctx, f = prepare(path)
    if ctx is None or f.items:
        for l, m in f.items:
            print(f"  FINDING {l}: {m}", file=sys.stderr)
        return doc, None, f
    return doc, ctx, f


def run_reduce(path, only, as_json):
    doc, ctx, f = structural_or_exit(path)
    if ctx is None:
        return 1
    if only and only not in ctx["scenarios"]:
        print(f"flow reduce: unknown scenario '{only}'", file=sys.stderr)
        return 2
    states = reduce_all(ctx, f, only)
    if f.items:
        for l, m in f.items:
            print(f"  FINDING {l}: {m}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps({"schema": SCHEMA, "scenarios": states}, indent=1, ensure_ascii=False))
        return 0
    for sid, sts in states.items():
        print(f"scenario {sid}: {len(sts)} step(s)")
        for s in sts:
            caches = {c: {k: e["v"] + (" (stale)" if e["stale"] else "") if isinstance(e["v"], str)
                          else e["v"] for k, e in kv.items()} for c, kv in s["caches"].items()}
            hz = "".join(f"  HAZARD {h['kind']}" for h in s["hazards"])
            hz += "".join(f"  SKIPPED {k['cache']}[{k['key']}]" for k in s["skipped"])
            print(f"  #{s['step']}{' (inherited)' if s['inherited'] else ''} active={','.join(s['active'])}"
                  f" hit={s['hit']} caches={json.dumps(caches)} stores={json.dumps(s['stores'])}{hz}")
    return 0


def build(scenario, tier, out_dir, assets_dir=ASSETS):
    """Inline the engine assets and the scenario into <out_dir>/index.html.

    The shell must carry {{flow_css}}, {{flow_js}} and {{flow_data}}; it may carry
    {{flow_tier}} and {{flow_title}}. Data goes inside <script type="application/json">,
    so every '<' in it is written as \\u003c: no '</script' or '<!--' can close the block.
    """
    assets_dir = pathlib.Path(assets_dir)
    missing = [n for n in ASSET_FILES if not (assets_dir / n).is_file()]
    if missing:
        raise Unreadable(f"engine assets not found in {assets_dir}: {', '.join(missing)}")
    shell, js, css = ((assets_dir / n).read_text(encoding="utf-8") for n in ASSET_FILES)
    absent = [t for t in REQUIRED_SHELL_TOKENS if "{{" + t + "}}" not in shell]
    if absent:
        raise Unreadable(f"shell.html lacks {', '.join('{{' + t + '}}' for t in absent)}")
    payload = json.dumps({"tier": tier, "scenario": scenario}, ensure_ascii=False).replace("<", "\\u003c")
    table = {"flow_css": css.replace("</style", "<\\/style"),
             "flow_js": js.replace("</script", "<\\/script"),
             "flow_data": payload, "flow_tier": tier,
             "flow_title": html.escape(text_en(scenario.get("title")))}
    page = SHELL_TOKEN_RX.sub(lambda m: table.get(m.group(1), m.group(0)), shell)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "index.html"
    target.write_text(page, encoding="utf-8")
    return target


# ---------------------------------------------------------------- markdown export

MD_EXPORT = "explain.md"
NO_SPACE_UNITS = ("%", "×", "x")


def fmt_number(n):
    v = n["v"]
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    unit = n.get("unit", "")
    return f"{v:,}" + ("" if unit in NO_SPACE_UNITS else " ") + unit


def md_text(value, numbers):
    """English text with {{name}} placeholders filled in, safe inside a table cell."""
    s = text_en(value) if value is not None else ""
    s = PLACEHOLDER_RX.sub(lambda m: fmt_number(numbers[m.group(1)]) if m.group(1) in numbers
                           else m.group(0), s)
    return s.replace("|", "\\|").replace("\n", " ").strip()


def md_value(v):
    return "absent" if v is None else f"`{json.dumps(v, ensure_ascii=False)}`"


def describe_evidence_md(eid, doc):
    e = (doc.get("evidence") or {}).get(eid)
    if not isinstance(e, dict):
        return f"`{eid}`"
    if "absent" in e:
        return (f"absent: {md_text(e.get('absent'), {})} (`git grep` finds {e.get('hits')} "
                f"in `{e.get('path')}`)")
    m = AT_RX.match(e.get("at", ""))
    if not m:
        return f"`{eid}`"
    sub = doc.get("subject") or {}
    rev, repo = m.group("rev") or sub.get("sha"), sub.get("repo") or ""
    label = f"`{m.group('path')}:{m.group('line')}`"
    if rev and repo.startswith(("https://", "http://")):
        return f"[{label}]({repo.rstrip('/')}/blob/{rev}/{m.group('path')}#L{m.group('line')})"
    return label


def describe_changes_md(prev, cur, numbers):
    """What one step changed, as short clauses: the 'state after' cell."""
    out = []
    if cur["hit"]:
        out.append(f"cache {cur['hit']}")
    for c, kv in cur["caches"].items():
        before = prev["caches"].get(c, {})
        for key in list(before) + [k for k in kv if k not in before]:
            a, b = before.get(key), kv.get(key)
            if a == b:
                continue
            out.append(f"{c}[{key}] removed" if b is None else
                       f"{c}[{key}] = {md_value(b['v'])}" + (" (stale)" if b["stale"] else ""))
    for st, kv in cur["stores"].items():
        before = prev["stores"].get(st, {})
        for key, v in kv.items():
            if key not in before or not same(before[key], v):
                out.append(f"{st}[{key}] = {md_value(v)}")
    for name, var in cur["vars"].items():
        if not same(prev["vars"].get(name), var):
            out.append(f"holds {name} = {md_value(var['v'])}")
    for q, jobs in cur["queues"].items():
        if prev["queues"].get(q) != jobs:
            out.append(f"{q}: {len(jobs)} waiting")
    for w, slots in cur["workers"].items():
        if prev["workers"].get(w) != slots:
            out.append(f"{w}: {sum(1 for j in slots if j is not None)}/{len(slots)} busy")
    for name, n in cur["counters"].items():
        if prev["counters"].get(name) != n:
            out.append(f"{name} = {n:,}")
    if cur["clock_ms"] != prev["clock_ms"]:
        out.append(f"clock {cur['clock_ms']:,} ms")
    for fl in cur["failures"]:
        out.append(f"**{fl['node']} failed**" + (f" ({md_text(fl['label'], numbers)})" if fl["label"] else ""))
    for h in cur["hazards"]:
        out.append(f"**HAZARD {h['kind']}**: {h['cache']}[{h['key']}] filled from a read of "
                   f"{h['store']}[{h['store_key']}] that a later write replaced")
    for k in cur["skipped"]:
        out.append(f"fill skipped: {k['store']}[{k['store_key']}] changed from {md_value(k['read'])} "
                   f"to {md_value(k['current'])} since the read")
    for note in cur["notes"]:
        out.append(md_text(note, numbers))
    return "; ".join(out) or "no change"


def render_markdown(doc, ctx, states, tier):
    numbers = ctx["numbers"]
    sub = doc.get("subject") or {}
    meta = [sub.get("kind", "")] + [f"{k} `{sub[k]}`" for k in ("repo", "sha", "base", "pr") if k in sub]
    lines = [f"# {md_text(doc.get('title'), numbers)}", "", md_text(sub.get("lede"), numbers), "",
             "| | |", "|---|---|", f"| subject | {' · '.join(meta)} |", f"| tier | {tier} |",
             "| generated | `100x flow build` from `scenario.json`; regenerate it, do not edit |", "",
             "## Map", "", "| node | role | code |", "|---|---|---|"]
    for nid, n in ctx["nodes"].items():
        ref = f"`{n['ref']}`" if n.get("ref") else ""
        ctxt = " (outside the diff)" if n.get("outside_diff") else ""
        lines.append(f"| {md_text(n.get('label'), numbers)}{ctxt} | {n.get('role')} | {ref} |")
    init = initial_state(ctx)
    for sid, s in ctx["scenarios"].items():
        sts = states.get(sid, [])
        head = [s.get("kind", "")] + ([f"severity {s['severity']}"] if s.get("severity") else [])
        lines += ["", f"## {md_text(s.get('title'), numbers)}", "", f"`{sid}` · {' · '.join(head)}", ""]
        if s.get("fixed_by"):
            lines.append(f"Fixed by: {', '.join('`' + x + '`' for x in s['fixed_by'])}.")
        elif s.get("open"):
            lines.append("Open: no fix is shown yet.")
        own = [st for st in sts if not st["inherited"]]
        if s.get("branch"):
            n_in = len(sts) - len(own)
            lines += ["", f"Steps 1–{n_in} are the same as `{s['branch']['from']}`; this table starts "
                          f"where it diverges."]
        lines += ["", "| # | what happens | state after | evidence |", "|---|---|---|---|"]
        for st in own:
            step = s["steps"][st["origin_step"]]
            prev = sts[st["step"] - 1] if st["step"] else init
            what = f"**{md_text(step.get('t'), numbers)}**"
            if step.get("d"):
                what += f" {md_text(step.get('d'), numbers)}"
            if step.get("time"):
                what += f" ({md_text(step.get('time'), numbers)})"
            ev = ", ".join(describe_evidence_md(e, doc) for e in step.get("ev") or []) or "*inferred*"
            if step.get("ev") and step.get("tag") == "inferred":
                ev += " · *inferred*"
            lines.append(f"| {st['step'] + 1} | {what} | {describe_changes_md(prev, st, numbers)} | {ev} |")
    dec = doc.get("decision")
    if dec:
        lines += ["", "## Decision", "", "| option | solves it | pros | cons |", "|---|---|---|---|"]
        for o in dec.get("options") or []:
            mark = " **(chosen)**" if o.get("id") == dec.get("chosen") else ""
            pros = "<br>".join(md_text(x, numbers) for x in o.get("pros") or [])
            cons = "<br>".join(md_text(x, numbers) for x in o.get("cons") or [])
            lines.append(f"| {md_text(o.get('label'), numbers)}{mark} | {o.get('fit')} | {pros} | {cons} |")
        lines += ["", f"**Deciding factor:** {md_text(dec.get('deciding_factor'), numbers)}",
                  f"**Revisit when:** {md_text(dec.get('revisit_when'), numbers)}",
                  f"**Source:** {md_text(dec.get('source'), {})}"]
    if numbers:
        lines += ["", "## Numbers", "", "| name | value | tag | backed by |", "|---|---|---|---|"]
        for name, n in numbers.items():
            back = (describe_evidence_md(n["ev"], doc) if n.get("tag") == "verified" and n.get("ev")
                    else md_text(n.get("source") or n.get("basis"), {}))
            lines.append(f"| `{name}` | {fmt_number(n)} | {n.get('tag')} | {back} |")
    return "\n".join(lines) + "\n"


def run_build(path, tier, out_dir, assets_dir, repo=None):
    doc, ctx, f = prepare(path)
    tier = tier or (doc.get("tier") if doc.get("tier") in TIERS else None) or "light"
    states = run_checks(doc, ctx, f, tier, repo, None)
    if ctx is None or f.items:
        for l, m in f.items:
            print(f"  FINDING {l}: {m}", file=sys.stderr)
        print(f"flow build: refused, {len(f.items)} finding(s) at tier {tier}", file=sys.stderr)
        return 1
    target = build(doc, tier, out_dir, assets_dir)
    md = pathlib.Path(out_dir) / MD_EXPORT
    md.write_text(render_markdown(doc, ctx, states, tier), encoding="utf-8")
    print(f"flow build: wrote {target} and {md} (tier {tier})")
    return 0


def starter(slug):
    return {
        "schema": SCHEMA, "tier": "light",
        "title": {"en": f"{slug}: what happens, what can go wrong, what fixes it"},
        "subject": {"kind": "concept", "lede": {"en": "One sentence: what this explains and for whom."}},
        "nodes": [{"id": "client", "role": "client", "label": "Client"},
                  {"id": "api", "role": "service", "label": "API"},
                  {"id": "db", "role": "store", "label": "Database"}],
        "numbers": {"timeout": {"v": 1, "unit": "s", "tag": "estimated",
                                "basis": "Replace: the inputs and arithmetic behind this number."}},
        "evidence": {},
        "scenarios": [{"id": "happy", "kind": "happy", "title": "Happy path", "steps": [
            {"t": "Client sends the request", "do": [["send", "client", "api", "request"]],
             "tag": "inferred"},
            {"t": "API reads the row and replies within {{timeout}}",
             "do": [["db.read", "db", "row"], ["reply", "api", "client", "200 OK"]],
             "tag": "inferred"}]}],
    }


def run_new(slug, out, force):
    if safe_record_name(slug, "flow new") is None:
        return 2
    if not SLUG_RX.match(slug):
        print(f"flow new: slug must match [a-z0-9][a-z0-9-]*, got {slug!r}", file=sys.stderr)
        return 2
    target = pathlib.Path(out or f"{slug}.json")
    if target.exists() and not force:
        print(f"flow new: {target} exists (pass --force to overwrite)", file=sys.stderr)
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(starter(slug), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"flow new: wrote {target}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="flow", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="write a starter scenario.json")
    p.add_argument("slug"); p.add_argument("--out"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("check", help="check a scenario against the code and the reducer")
    p.add_argument("file"); p.add_argument("--tier", choices=TIERS)
    p.add_argument("--repo", default=".", help="git clone the evidence cites (default: .)")
    p.add_argument("--rev", help="revision for unpinned evidence when subject.sha is absent (default HEAD)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("reduce", help="print the state after every step")
    p.add_argument("file"); p.add_argument("--scenario"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("build", help="inline the engine and the scenario into one HTML file")
    p.add_argument("file"); p.add_argument("--tier", choices=TIERS); p.add_argument("--out", required=True)
    p.add_argument("--assets", default=str(ASSETS))
    p.add_argument("--repo", help="also check evidence against this clone, as check does (default: skip)")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "new":
            return run_new(a.slug, a.out, a.force)
        if a.cmd == "check":
            return run_check(a.file, a.tier, a.repo, a.rev, a.json)
        if a.cmd == "reduce":
            return run_reduce(a.file, a.scenario, a.json)
        return run_build(a.file, a.tier, a.out, a.assets, a.repo)
    except Unreadable as e:
        print(f"flow {a.cmd}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
