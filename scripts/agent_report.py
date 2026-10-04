#!/usr/bin/env python3
"""Agent report checker: extract, lint, replay and merge the reports specialist agents return.

A subagent's "done, tests pass" is a claim made by the party being evaluated. This turns
the report contract in docs/OPERATING-MODEL.md §3 into something the main session can
check without trusting it: `lint` rejects reports that contradict themselves or the
decision policy, and `replay` re-runs every evidence command and compares exit codes, so
a done task is one whose proof still reproduces.

    agent_report.py extract message.md [-o report.json]   # LAST ```json block
    agent_report.py lint report.json|message.md [--graph plan.json]
    agent_report.py replay report.json [--cwd DIR] [--timeout 600] --yes
    agent_report.py summary report1.json report2.json ... [--json]

Exit codes: 0 clean, 1 findings or replay mismatch, 2 unreadable input,
3 replay refused without --yes (nothing was run).
Python stdlib only.
"""
import argparse, json, pathlib, re, subprocess, sys

import plan_dag

STATUSES = ("done", "needs-decision", "blocked", "failed")
DOORS = ("two-way", "one-way")
LIST_KEYS = ("inputs_read", "assumptions", "questions", "plan_issues", "decisions",
             "changes", "evidence", "follow_ups")
REQUIRED = ("agent", "task_id", "status", "understanding") + LIST_KEYS
MAX_QUESTIONS = 5  # §5: one batch of at most five
TAIL_LINES = 15
FENCE_RX = re.compile(r"^```json[^\n]*\n(.*?)^```\s*$", re.S | re.M)


def extract_json(text):
    """The LAST fenced json block, per §3. Earlier blocks are examples or drafts."""
    blocks = FENCE_RX.findall(text)
    if not blocks:
        return None, "no fenced ```json block found"
    try:
        return json.loads(blocks[-1]), None
    except json.JSONDecodeError as e:
        return None, f"the last ```json block is not valid JSON ({e})"


def read_input(src):
    text = sys.stdin.read() if src == "-" else pathlib.Path(src).read_text()
    return text


def load_report(src):
    """Accept either a bare JSON report or a whole agent message containing one."""
    try:
        text = read_input(src)
    except OSError as e:
        return None, f"{src}: cannot read ({e})"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data, err = extract_json(text)
        if err:
            return None, f"{src}: {err}"
    if not isinstance(data, dict):
        return None, f"{src}: report must be a JSON object"
    return data, None


def _list(r, k):
    v = r.get(k)
    return v if isinstance(v, list) else []


def _items(r, k):
    return [x for x in _list(r, k) if isinstance(x, dict)]


def lint(r, plan=None):
    """Every row of the §3 rejection table, plus shape checks. Returns (errors, warns)."""
    errors, warns = [], []

    for k in REQUIRED:
        if k not in r:
            errors.append(f"missing required key \"{k}\" (use [] for an empty list)")
    for k in ("agent", "task_id", "understanding"):
        if k in r and (not isinstance(r[k], str) or not r[k].strip()):
            errors.append(f"\"{k}\" must be a non-empty string")
    for k in LIST_KEYS:
        if k in r and not isinstance(r[k], list):
            errors.append(f"\"{k}\" must be a list")
    status = r.get("status")
    if "status" in r and status not in STATUSES:
        errors.append(f"status {status!r} is not one of {', '.join(STATUSES)}")
    for k in LIST_KEYS:
        if k in ("inputs_read", "follow_ups"):
            continue
        for n, x in enumerate(_list(r, k)):
            if not isinstance(x, dict):
                errors.append(f"{k}[{n}] must be an object")

    for n, e in enumerate(_items(r, "evidence")):
        if not isinstance(e.get("cmd"), str) or not e["cmd"].strip():
            errors.append(f"evidence[{n}]: \"cmd\" must be a non-empty command string")
        if type(e.get("exit_code")) is not int:
            errors.append(f"evidence[{n}]: \"exit_code\" must be an integer")
        if "output_tail" in e and not isinstance(e["output_tail"], str):
            errors.append(f"evidence[{n}]: \"output_tail\" must be a string")
    for n, q in enumerate(_items(r, "questions")):
        if not isinstance(q.get("question"), str) or not q["question"].strip():
            errors.append(f"questions[{n}]: \"question\" must be a non-empty string")
        if not isinstance(q.get("blocking"), bool):
            errors.append(f"questions[{n}]: \"blocking\" must be true or false")
        if "options" in q and not isinstance(q["options"], list):
            errors.append(f"questions[{n}]: \"options\" must be a list")
    for n, p in enumerate(_items(r, "plan_issues")):
        if not isinstance(p.get("issue"), str) or not p["issue"].strip():
            errors.append(f"plan_issues[{n}]: \"issue\" must be a non-empty string")
        if not isinstance(p.get("blocking"), bool):
            errors.append(f"plan_issues[{n}]: \"blocking\" must be true or false")
    for n, c in enumerate(_items(r, "changes")):
        if not isinstance(c.get("path"), str) or not c["path"].strip():
            errors.append(f"changes[{n}]: \"path\" must be a non-empty string")

    # --- the §3 rejection table, row by row ---
    evidence = _items(r, "evidence")
    if status == "done":
        if not evidence:
            errors.append("status done with no evidence — done without proof is a claim; "
                          "run the task's verify commands and record each with its exit code")
        for e in evidence:
            if type(e.get("exit_code")) is int and e["exit_code"] != 0:
                errors.append(f"status done but evidence {e.get('cmd')!r} exited "
                              f"{e['exit_code']} — fix it, or report failed/needs-decision")
    for d in _items(r, "decisions"):
        door = d.get("door")
        if door == "one-way":
            errors.append(f"decision {d.get('id', '?')} is a one-way door — one-way doors "
                          f"are questions (§4): move it to questions with options and a "
                          f"recommendation")
        elif door not in DOORS:
            errors.append(f"decision {d.get('id', '?')}: \"door\" must be two-way or one-way")
    blocking = ([q for q in _items(r, "questions") if q.get("blocking") is True]
                + [p for p in _items(r, "plan_issues") if p.get("blocking") is True])
    if status == "needs-decision" and not blocking:
        errors.append("status needs-decision with no blocking question or plan issue — a "
                      "stop must say what unblocks it")
    if status == "done" and blocking:
        ids = ", ".join(str(x.get("id", "?")) for x in blocking)
        errors.append(f"status done while blocking item(s) {ids} are still listed — "
                      f"contradictory; resolve them or report needs-decision")
    for a in _items(r, "assumptions"):
        cls = a.get("class")
        if cls == "C":
            errors.append(f"assumption {a.get('id', '?')} is class C — C items are asked, "
                          f"never assumed (§5): move it to questions")
        elif cls not in ("A", "B"):
            errors.append(f"assumption {a.get('id', '?')}: \"class\" must be A or B")
    if plan is not None:
        by_id, _ = plan_dag.graph(plan.get("tasks", []))
        task = by_id.get(r.get("task_id"))
        if task is None:
            errors.append(f"task_id {r.get('task_id')!r} is not a task in the supplied plan")
        else:
            owned = plan_dag._ids(task.get("files"))
            for c in _items(r, "changes"):
                p = c.get("path")
                if isinstance(p, str) and not plan_dag.path_owned(p, owned):
                    errors.append(f"change {p!r} is outside {r['task_id']}'s owned files "
                                  f"({', '.join(owned) or 'none'}) — collisions break "
                                  f"parallel work; revert it or raise a plan issue")
    if status in ("blocked", "failed") and not (blocking or evidence):
        warns.append(f"status {status} with no evidence and no blocking item — say what "
                     f"failed or what would unblock it")
    return errors, warns


def cmd_extract(a):
    try:
        text = read_input(a.message)
    except OSError as e:
        print(f"agent_report extract: {e}", file=sys.stderr)
        return 2
    data, err = extract_json(text)
    if err:
        print(f"agent_report extract: {err}", file=sys.stderr)
        return 2
    out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if a.output:
        pathlib.Path(a.output).write_text(out)
        print(f"wrote {a.output}")
    else:
        sys.stdout.write(out)
    return 0


def cmd_lint(a):
    r, err = load_report(a.report)
    if err:
        print(f"agent_report lint: {err}", file=sys.stderr)
        return 2
    plan = None
    if a.graph:
        plan = plan_dag.load_plan(a.graph)
        if plan is None:
            return 2
    errors, warns = lint(r, plan)
    for w in warns:
        print(f"  WARN  {w}")
    for n, e in enumerate(errors, 1):
        print(f"  {n}. {e}")
    print(f"\nagent_report lint: {r.get('task_id', '?')} ({r.get('agent', '?')}, "
          f"{r.get('status', '?')}): {len(errors)} errors, {len(warns)} warnings")
    return 1 if errors else 0


def _tail(s, n=TAIL_LINES):
    return "\n".join(s.rstrip().splitlines()[-n:])


def cmd_replay(a):
    r, err = load_report(a.report)
    if err:
        print(f"agent_report replay: {err}", file=sys.stderr)
        return 2
    cwd = pathlib.Path(a.cwd or ".").resolve()
    if not cwd.is_dir():
        print(f"agent_report replay: --cwd {cwd} is not a directory", file=sys.stderr)
        return 2
    ev = [e for e in _items(r, "evidence")
          if isinstance(e.get("cmd"), str) and type(e.get("exit_code")) is int]
    if len(ev) != len(_list(r, "evidence")):
        print("agent_report replay: some evidence entries lack a cmd string or an integer "
              "exit_code; run `agent_report lint` first", file=sys.stderr)
        return 1
    if not ev:
        if r.get("status") == "done":
            print("agent_report replay: status done but there is no evidence to replay")
            return 1
        print("agent_report replay: no evidence to replay")
        return 0
    # Evidence commands are arbitrary shell written by another agent; nothing runs until
    # the caller has seen them, the same consent rule as ledger shard's --yes.
    if not a.yes:
        print(f"agent_report replay: would run {len(ev)} command(s) in {cwd}. "
              f"Nothing has been run.\n")
        for e in ev:
            print(f"  $ {e['cmd']}    (claimed exit {e['exit_code']})")
        print("\nRe-run with --yes to execute them.")
        return 3
    mismatches = 0
    for e in ev:
        try:
            p = subprocess.run(e["cmd"], shell=True, cwd=cwd, capture_output=True,
                               text=True, timeout=a.timeout)
            actual, out = p.returncode, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired as t:
            actual = "timeout"
            out = (t.stdout or b"").decode(errors="replace") if isinstance(t.stdout, bytes) \
                else (t.stdout or "")
        if actual == e["exit_code"]:
            print(f"  ok        $ {e['cmd']}  (exit {actual})")
            continue
        mismatches += 1
        print(f"  MISMATCH  $ {e['cmd']}")
        print(f"            claimed exit {e['exit_code']}, actual {actual}"
              + (f" after {a.timeout}s" if actual == "timeout" else ""))
        if e.get("output_tail"):
            print("            claimed output tail:")
            print("\n".join("              " + l for l in str(e["output_tail"]).splitlines()))
        print("            actual output tail:")
        print("\n".join("              " + l for l in (_tail(out) or "(no output)").splitlines()))
    print(f"\nagent_report replay: {r.get('task_id', '?')}: {len(ev) - mismatches}/{len(ev)} "
          f"reproduced, {mismatches} mismatch(es)")
    return 1 if mismatches else 0


def cmd_summary(a):
    questions, issues, seen = [], [], set()
    for src in a.reports:
        r, err = load_report(src)
        if err:
            print(f"agent_report summary: {err}", file=sys.stderr)
            return 2
        who = f"{r.get('task_id', '?')}/{r.get('agent', '?')}"
        for q in _items(r, "questions"):
            key = re.sub(r"\s+", " ", str(q.get("question", ""))).strip().lower()
            if key in seen:
                for prev in questions:
                    if prev["_key"] == key:
                        prev["from"].append(who)
                        prev["blocking"] = prev["blocking"] or q.get("blocking") is True
                continue
            seen.add(key)
            questions.append({"_key": key, "from": [who], "id": q.get("id"),
                              "question": q.get("question"),
                              "why_it_matters": q.get("why_it_matters"),
                              "options": q.get("options") or [],
                              "recommendation": q.get("recommendation"),
                              "blocking": q.get("blocking") is True})
        for p in _items(r, "plan_issues"):
            issues.append({"from": who, "id": p.get("id"), "issue": p.get("issue"),
                           "impact": p.get("impact"), "proposal": p.get("proposal"),
                           "blocking": p.get("blocking") is True})
    # stable sort keeps report order inside each group, which is the agents' impact order
    questions.sort(key=lambda q: not q["blocking"])
    issues.sort(key=lambda p: not p["blocking"])
    for q in questions:
        del q["_key"]
    batch, deferred = questions[:MAX_QUESTIONS], questions[MAX_QUESTIONS:]
    if a.json:
        print(json.dumps({"questions": batch, "deferred_questions": deferred,
                          "plan_issues": issues}, indent=2, ensure_ascii=False))
        return 0
    print(f"Questions ({len(batch)} of {len(questions)}, blocking first):")
    for n, q in enumerate(batch, 1):
        tag = "BLOCKING" if q["blocking"] else "non-blocking"
        print(f"\n{n}. [{tag}] {q['question']}  (from {', '.join(q['from'])})")
        if q["why_it_matters"]:
            print(f"   why it matters: {q['why_it_matters']}")
        for o in q["options"]:
            print(f"   - {o}")
        if q["recommendation"]:
            print(f"   recommendation: {q['recommendation']}")
    if deferred:
        print(f"\n{len(deferred)} more question(s) deferred to the next batch (max "
              f"{MAX_QUESTIONS} per §5): "
              + "; ".join(f"{q['id'] or '?'} from {', '.join(q['from'])}" for q in deferred))
    print(f"\nPlan issues ({len(issues)}):")
    for p in issues:
        tag = "BLOCKING" if p["blocking"] else "non-blocking"
        print(f"- [{tag}] {p['from']} {p['id'] or '?'}: {p['issue']}")
        if p["proposal"]:
            print(f"    proposal: {p['proposal']}")
    if not issues:
        print("- none")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="pull the last ```json block from a message")
    p.add_argument("message", help="message file, or - for stdin")
    p.add_argument("-o", "--output", help="write the JSON here instead of stdout")
    p.set_defaults(fn=cmd_extract)
    p = sub.add_parser("lint", help="check a report against the §3 contract")
    p.add_argument("report", help="report JSON or a whole agent message, or -")
    p.add_argument("--graph", help="plan.json, to check changes stay in owned files")
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("replay", help="re-run every evidence command and compare exit codes")
    p.add_argument("report")
    p.add_argument("--cwd", help="directory to run the commands in (default: current)")
    p.add_argument("--timeout", type=int, default=600, help="seconds per command")
    p.add_argument("--yes", action="store_true",
                   help="actually run the commands; without it they are only printed")
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("summary", help="merge questions and plan issues across reports")
    p.add_argument("reports", nargs="+")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_summary)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
