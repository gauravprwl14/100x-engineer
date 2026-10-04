#!/usr/bin/env python3
"""Task-graph checker for orchestrated work: lint a plan.json, print its waves, pick what runs next.

The failure this prevents: parallel agents that collide. Two tasks with no ordering
between them both edit the shared types file; a consumer starts before the contract it
builds on exists; an acceptance criterion in the spec is owned by nobody and silently
never gets built. Each of those is visible in the plan before any agent starts, so
docs/OPERATING-MODEL.md §6 makes `plan_dag lint` the gate in front of every task.

    plan_dag.py lint plan.json [--spec spec.md] [--agents-dir agents/]
    plan_dag.py waves plan.json [--json]
    plan_dag.py next plan.json --done T0,T1 [--blocked T2] [--json]

Exit codes: 0 clean (warnings allowed), 1 findings, 2 unreadable input.
Python stdlib only.
"""
import argparse, fnmatch, json, pathlib, re, sys
from functools import lru_cache

from testplan import parse_acs

# Must track the roster table in docs/OPERATING-MODEL.md §1; tests/test_plan_dag.sh
# fails if a name here is missing from that table.
ROSTER = (
    "requirements-analyst", "solution-architect", "backend-engineer",
    "frontend-engineer", "mobile-engineer", "qa-engineer", "code-reviewer",
    "security-reviewer", "independent-verifier", "comprehension-mapper",
    "rca-investigator",
)
PLAN_FIELDS = {"feature", "tier", "tasks"}
TASK_FIELDS = {"id", "title", "owner", "depends_on", "files", "acceptance", "verify",
               "contract", "consumes"}
WILD = set("*?[")


# ---------------------------------------------------------------- glob overlap
#
# Whether two globs can match a common path is undecidable in general for fnmatch
# syntax, so this is a deliberately one-sided approximation: it may report an overlap
# that cannot happen, and must never miss one that can. A false collision costs a
# reworded plan; a missed one costs two agents overwriting each other.
#
#   - Paths are split on "/"; "**" matches zero or more whole segments, a trailing
#     "/" means "everything under", and "./" prefixes are ignored.
#   - literal segment vs literal: equal strings.
#   - literal vs glob segment: fnmatch.
#   - glob vs glob segment: overlapping unless their literal prefixes (before the
#     first wildcard) or literal suffixes (after the last) are incompatible, so
#     `*.ts` vs `*.tsx` is disjoint but `*foo*` vs `*bar*` is reported as overlapping.
#   - Brace sets `{a,b}` are not fnmatch syntax and are compared literally.

def _segs(p):
    p = p.strip()
    while p.startswith("./"):
        p = p[2:]
    if p.endswith("/"):
        p += "**"
    return tuple(s for s in p.strip("/").split("/") if s not in ("", "."))


def _is_glob(s):
    return any(c in WILD for c in s)


def _lit_prefix(s):
    i = min((s.index(c) for c in WILD if c in s), default=len(s))
    return s[:i]


def _lit_suffix(s):
    i = max((s.rindex(c) for c in "*?]" if c in s), default=-1)
    return s[i + 1:]


def _seg_compat(x, y):
    gx, gy = _is_glob(x), _is_glob(y)
    if not gx and not gy:
        return x == y
    if not gx:
        return fnmatch.fnmatchcase(x, y)
    if not gy:
        return fnmatch.fnmatchcase(y, x)
    px, py = _lit_prefix(x), _lit_prefix(y)
    sx, sy = _lit_suffix(x), _lit_suffix(y)
    return ((px.startswith(py) or py.startswith(px))
            and (sx.endswith(sy) or sy.endswith(sx)))


def globs_overlap(a, b):
    A, B = _segs(a), _segs(b)

    @lru_cache(maxsize=None)
    def ov(i, j):
        if i == len(A) and j == len(B):
            return True
        if i < len(A) and A[i] == "**":
            if ov(i + 1, j) or (j < len(B) and ov(i, j + 1)):
                return True
        if j < len(B) and B[j] == "**":
            if ov(i, j + 1) or (i < len(A) and ov(i + 1, j)):
                return True
        if i == len(A) or j == len(B):
            return False
        if A[i] == "**" or B[j] == "**":
            return False
        return _seg_compat(A[i], B[j]) and ov(i + 1, j + 1)

    return ov(0, 0)


def path_owned(path, patterns):
    """True when a concrete changed path falls under any owned glob."""
    return any(globs_overlap(path, p) for p in patterns)


# ---------------------------------------------------------------- loading

def load_plan(path):
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except FileNotFoundError:
        print(f"plan_dag: {path}: no such file", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"plan_dag: {path}: not valid JSON ({e})", file=sys.stderr)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        print(f"plan_dag: {path}: expected an object with a \"tasks\" list", file=sys.stderr)
        return None
    return data


def _ids(v):
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def graph(tasks):
    """id -> task, and id -> set of ids it transitively depends on (cycle-safe)."""
    by_id = {t["id"]: t for t in tasks if isinstance(t, dict) and isinstance(t.get("id"), str)}
    anc = {}
    # A fresh walk per task rather than memoised recursion: memoising inside a cycle
    # caches a partial ancestor set and then reports false "does not depend" errors.
    for tid in by_id:
        seen, todo = set(), list(_ids(by_id[tid].get("depends_on")))
        while todo:
            d = todo.pop()
            if d in by_id and d not in seen:
                seen.add(d)
                todo.extend(_ids(by_id[d].get("depends_on")))
        seen.discard(tid)
        anc[tid] = seen
    return by_id, anc


def find_cycle(by_id):
    color, path = {}, []

    def dfs(n):
        color[n] = 1
        path.append(n)
        for d in _ids(by_id[n].get("depends_on")):
            if d not in by_id:
                continue
            if color.get(d) == 1:
                return path[path.index(d):] + [d]
            if not color.get(d):
                c = dfs(d)
                if c:
                    return c
        color[n] = 2
        path.pop()
        return None

    for n in by_id:
        if not color.get(n):
            c = dfs(n)
            if c:
                return c
    return None


def levels(by_id):
    """Topological levels; None when the graph has a cycle."""
    remaining = dict(by_id)
    done, out = set(), []
    while remaining:
        wave = sorted(t for t, task in remaining.items()
                      if all(d in done or d not in by_id for d in _ids(task.get("depends_on"))))
        if not wave:
            return None
        out.append(wave)
        done.update(wave)
        for t in wave:
            del remaining[t]
    return out


# ---------------------------------------------------------------- lint

def lint(plan, spec=None, agents_dir=None):
    errors, warns = [], []
    tasks = plan["tasks"]

    known = set(ROSTER)
    if agents_dir and pathlib.Path(agents_dir).is_dir():
        known |= {p.stem for p in pathlib.Path(agents_dir).glob("*.md")}

    for k in sorted(set(plan) - PLAN_FIELDS):
        warns.append(f"unknown top-level field '{k}' — known: {', '.join(sorted(PLAN_FIELDS))}")

    seen = set()
    for n, t in enumerate(tasks):
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t["id"].strip():
            errors.append(f"task #{n + 1}: needs a non-empty string \"id\"")
            continue
        tid = t["id"]
        if tid in seen:
            errors.append(f"{tid}: duplicate task id — give each task a unique id")
        seen.add(tid)
        for k in sorted(set(t) - TASK_FIELDS):
            warns.append(f"{tid}: unknown field '{k}' — known: {', '.join(sorted(TASK_FIELDS))}")
        owner = t.get("owner")
        if owner not in known:
            hint = (f"add {agents_dir}/{owner}.md" if agents_dir
                    else "or pass --agents-dir with a matching <name>.md")
            errors.append(f"{tid}: owner {owner!r} is not a known agent — use one of "
                          f"{', '.join(sorted(known))}, {hint}")
        for field, what in (("files", "the globs this task may edit"),
                            ("verify", "the commands that prove it"),
                            ("acceptance", "the AC ids it delivers")):
            v = t.get(field)
            if (not isinstance(v, list) or not v
                    or not all(isinstance(x, str) and x.strip() for x in v)):
                errors.append(f"{tid}: \"{field}\" must be a non-empty list of strings ({what})")
        for field in ("depends_on", "consumes"):
            v = t.get(field, [])
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errors.append(f"{tid}: \"{field}\" must be a list of task ids")
        if "contract" in t and not isinstance(t["contract"], bool):
            errors.append(f"{tid}: \"contract\" must be true or false")

    by_id, anc = graph(tasks)
    for tid, t in by_id.items():
        for d in _ids(t.get("depends_on")):
            if d not in by_id:
                errors.append(f"{tid}: depends_on {d!r}, which is not a task in this plan")
        for c in _ids(t.get("consumes")):
            if c not in by_id:
                errors.append(f"{tid}: consumes {c!r}, which is not a task in this plan")

    cyc = find_cycle(by_id)
    if cyc:
        errors.append(f"dependency cycle {' -> '.join(cyc)} — break it by removing one "
                      f"depends_on edge or splitting a task")

    def files(tid):
        return _ids(by_id[tid].get("files"))

    ordered = sorted(by_id)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if a in anc[b] or b in anc[a]:
                continue
            clashes = [(x, y) for x in files(a) for y in files(b) if globs_overlap(x, y)]
            if clashes:
                x, y = clashes[0]
                errors.append(f"{a} and {b} can run in parallel but both own files "
                              f"({x!r} overlaps {y!r}) — make one depend on the other, or "
                              f"move the shared file into a contract task both depend on")

    contracts = {t for t, v in by_id.items() if v.get("contract") is True}
    consumed = set()
    for tid, t in by_id.items():
        for c in _ids(t.get("consumes")):
            if c not in by_id:
                continue
            consumed.add(c)
            if c not in contracts:
                errors.append(f"{tid}: consumes {c}, which is not a contract task — mark "
                              f"{c} \"contract\": true or drop it from consumes")
            if c not in anc[tid]:
                errors.append(f"{tid}: consumes {c} but does not depend on it — add {c} to "
                              f"{tid}'s depends_on so it starts after the contract lands")
            owned = [(x, y) for x in files(tid) for y in files(c) if globs_overlap(x, y)]
            if owned:
                x, y = owned[0]
                errors.append(f"{tid}: consumer owns contract {c}'s files ({x!r} overlaps "
                              f"{y!r}) — a consumer reads the contract, only {c} edits it")
    for c in sorted(contracts - consumed):
        warns.append(f"{c}: contract task with no consumer — list it in a dependent's "
                     f"\"consumes\" or drop \"contract\": true")

    if spec:
        try:
            text = pathlib.Path(spec).read_text()
        except OSError as e:
            errors.append(f"--spec {spec}: cannot read ({e})")
            text = ""
        # Only DEFINED criteria count (testplan.parse_acs, the parser every AC tool
        # shares): a verification row or a prose line that merely mentions `AC-3`
        # must not make AC-3 look like a criterion the plan has to deliver.
        spec_ids = set(parse_acs(text))
        if text and not spec_ids:
            errors.append(f"--spec {spec} defines no acceptance criteria — write each "
                          f"as a line `AC-<n>: <observable outcome> (R<k>)`; with none, "
                          f"coverage cannot be checked")
        covered = {a for t in by_id.values() for a in _ids(t.get("acceptance"))}
        for ac in sorted(spec_ids - covered, key=_ac_key):
            errors.append(f"{ac} in {spec} is covered by no task — add it to the "
                          f"\"acceptance\" of the task that delivers it")
        for ac in sorted(covered - spec_ids, key=_ac_key):
            warns.append(f"{ac} is claimed by a task but is not defined in {spec}")
    return errors, warns


def _ac_key(s):
    m = re.search(r"(\d+)$", s)
    return (int(m.group(1)) if m else 0, s)


def cmd_lint(a):
    plan = load_plan(a.plan)
    if plan is None:
        return 2
    errors, warns = lint(plan, a.spec, a.agents_dir)
    for w in warns:
        print(f"  WARN  {w}")
    for n, e in enumerate(errors, 1):
        print(f"  {n}. {e}")
    print(f"\nplan_dag lint: {len(plan['tasks'])} tasks, {len(errors)} errors, "
          f"{len(warns)} warnings")
    return 1 if errors else 0


def cmd_waves(a):
    plan = load_plan(a.plan)
    if plan is None:
        return 2
    by_id, _ = graph(plan["tasks"])
    lv = levels(by_id)
    if lv is None:
        print(f"plan_dag waves: dependency cycle {' -> '.join(find_cycle(by_id))}; "
              f"run `plan_dag lint` first", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps([{"wave": i + 1, "tasks": w} for i, w in enumerate(lv)], indent=2))
        return 0
    print("| wave | task | owner | title |\n|--:|---|---|---|")
    for i, w in enumerate(lv, 1):
        for t in w:
            print(f"| {i} | {t} | {by_id[t].get('owner', '')} | {by_id[t].get('title', '')} |")
    print(f"\n{len(lv)} waves, {len(by_id)} tasks; widest wave runs "
          f"{max((len(w) for w in lv), default=0)} in parallel")
    return 0


def _csv(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def cmd_next(a):
    plan = load_plan(a.plan)
    if plan is None:
        return 2
    by_id, anc = graph(plan["tasks"])
    if levels(by_id) is None:
        print("plan_dag next: dependency cycle; run `plan_dag lint` first", file=sys.stderr)
        return 1
    done, blocked = set(_csv(a.done)), set(_csv(a.blocked))
    unknown = sorted((done | blocked) - set(by_id))
    if unknown:
        print(f"plan_dag next: unknown task id(s) {', '.join(unknown)}", file=sys.stderr)
        return 2
    ready, held, waiting = [], {}, {}
    for tid in sorted(by_id):
        if tid in done or tid in blocked:
            continue
        hold = sorted(anc[tid] & blocked)
        if hold:
            held[tid] = hold
            continue
        pending = sorted(d for d in _ids(by_id[tid].get("depends_on"))
                         if d in by_id and d not in done)
        if pending:
            waiting[tid] = pending
        else:
            ready.append(tid)
    if a.json:
        print(json.dumps({"ready": ready, "held": held, "waiting": waiting,
                          "done": sorted(done), "blocked": sorted(blocked)}, indent=2))
        return 0
    print(f"ready now: {', '.join(ready) if ready else '(none)'}")
    for t, why in held.items():
        print(f"held:      {t} (depends on blocked {', '.join(why)})")
    for t, why in waiting.items():
        print(f"waiting:   {t} (on {', '.join(why)})")
    if not ready and not waiting and not held:
        print("all tasks done or blocked")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint", help="validate a plan.json")
    p.add_argument("plan")
    p.add_argument("--spec", help="spec whose AC-<n> ids must all be covered")
    p.add_argument("--agents-dir", help="directory of <agent>.md files accepted as owners")
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("waves", help="tasks that can run in parallel, level by level")
    p.add_argument("plan")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_waves)
    p = sub.add_parser("next", help="tasks that can start now")
    p.add_argument("plan")
    p.add_argument("--done", default="", help="comma-separated finished task ids")
    p.add_argument("--blocked", default="", help="comma-separated paused task ids")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_next)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
