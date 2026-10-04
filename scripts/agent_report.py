#!/usr/bin/env python3
"""Agent report checker: extract, lint, replay and merge the reports specialist agents return.

A subagent's "done, tests pass" is a claim made by the party being evaluated. This turns
the report contract in docs/OPERATING-MODEL.md §3 into something the main session can
check without trusting it:

  - `lint` rejects reports that contradict themselves or the decision policy. With
    `--graph plan.json --cwd <worktree>` it stops trusting the report's own `changes`:
    it asks git which files actually changed in the worktree since the task's base
    (committed, staged, unstaged and untracked), and rejects any outside the task's
    owned files, and any claimed change that is not there. The base is `--base`, else
    plan.json's top-level "base", else the worktree's fork point from the main
    checkout, else HEAD. A done report must also carry every one of the task's
    declared `verify` commands with exit 0, and come from the task's owner. A
    read-only role (a reviewer) whose task_id is not a plan task gets the report-level
    checks only.
  - `replay` re-runs evidence, but only the commands the PLAN declared for the task:
    an evidence command is text another agent wrote, so it is never executed because
    the report contains it. Each declared command runs as an argv (shlex.split, no
    shell); a plan that needs shell syntax writes `sh -c '...'`, which is shown before
    it runs. Anything the verification hook classifies as a commit, push, tag or
    publish is refused. A timeout kills the command's whole process group.

  Evidence matches a declared command when their argvs are equal, so whitespace and
  quoting style do not matter, and `100x verified --name X -- <cmd>` counts as `<cmd>`:
  replay runs the plain declared command, never the wrapper.

    agent_report.py extract message.md [-o report.json]   # LAST ```json block
    agent_report.py lint report.json|message.md [--graph plan.json --cwd WT [--base REV]]
    agent_report.py replay report.json --graph plan.json [--cwd WT] [--timeout 600] --yes
    agent_report.py summary report1.json report2.json ... [--json]

Exit codes: 0 clean, 1 findings or replay mismatch, 2 unreadable input or a missing
--graph/--cwd, 3 replay ran nothing (no --yes) or left something unreplayed
(undeclared or refused commands).
Python stdlib only.
"""
import argparse, difflib, json, os, pathlib, re, shlex, signal, subprocess, sys

import _paths
import plan_dag

SCHEMA = 1
STATUSES = ("done", "needs-decision", "blocked", "failed")
DOORS = ("two-way", "one-way")
LIST_KEYS = ("inputs_read", "assumptions", "questions", "plan_issues", "decisions",
             "changes", "evidence", "follow_ups")
REQUIRED = ("agent", "task_id", "status", "understanding") + LIST_KEYS
KNOWN_KEYS = {"schema", "findings"} | set(REQUIRED)
SEVERITIES = ("critical", "major", "minor", "trivial")
CONFIDENCES = ("definite", "probable", "possible")
# The "writes code? no" rows of the roster in docs/OPERATING-MODEL.md §1; the test
# suite fails when this drifts from that table. These roles review a task rather than
# own one, so their report's task_id need not be a plan task.
READ_ONLY_ROLES = ("requirements-analyst", "solution-architect", "code-reviewer",
                   "security-reviewer", "independent-verifier")
COMMIT_HINT = ("did the agent commit? pass --base <fork point>, or set \"base\" in "
               "plan.json")
MAX_QUESTIONS = 5  # §5: one batch of at most five
TAIL_LINES = 15
CLOSE_FENCE = re.compile(r"^```\s*$")


def json_blocks(text):
    """Every fenced ```json block, in one linear pass over the lines. A regex with a
    lazy body backtracks from every later opener when a fence is never closed, which
    made 80KB of unclosed fences take seconds."""
    blocks, cur = [], None
    for line in text.split("\n"):
        if cur is None:
            if line.startswith("```json"):
                cur = []
        elif CLOSE_FENCE.match(line):
            blocks.append("\n".join(cur))
            cur = None
        else:
            cur.append(line)
    return blocks


def extract_json(text):
    """The LAST fenced json block, per §3. Earlier blocks are examples or drafts."""
    blocks = json_blocks(text)
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


def _git(top, *args):
    return subprocess.run(["git", "-C", str(top), *args], capture_output=True, text=True)


def actual_changes(cwd, base, exclude=()):
    """(paths changed in the worktree since `base`, None) or (None, why not).

    Committed after base, staged, unstaged and untracked-but-not-ignored, repo-relative.
    Renames count as both paths, so moving a file out of an owned directory is seen."""
    r = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, f"--cwd {cwd} is not inside a git work tree"
    top = pathlib.Path(r.stdout.strip())
    if _git(top, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode != 0:
        return None, f"--base {base!r} does not name a commit in {top}"
    diff = _git(top, "diff", "--name-only", "--no-renames", "-z", base)
    if diff.returncode != 0:
        return None, f"git diff against {base} failed: {diff.stderr.strip()}"
    untracked = _git(top, "ls-files", "--others", "--exclude-standard", "-z")
    paths = {x for x in (diff.stdout + untracked.stdout).split("\0") if x}
    for ex in exclude:
        try:
            paths.discard(str(pathlib.Path(ex).resolve().relative_to(top.resolve())))
        except ValueError:  # fail-open: an excluded path outside the worktree simply is not in the change set
            pass
    return sorted(paths), None


def cmd_key(cmd):
    """A command's comparison key: its argv, with a `100x verified [--name X] --`
    wrapper removed. Unparseable text falls back to whitespace-collapsed words."""
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return tuple(cmd.split())
    if len(argv) > 2 and os.path.basename(argv[0]) == "100x" and argv[1] == "verified" \
            and "--" in argv:
        i = argv.index("--")
        if argv[2:i] == [] or (len(argv[2:i]) == 2 and argv[2] == "--name"):
            return tuple(argv[i + 1:])
    return tuple(argv)


def git_head(cwd):
    r = _git(cwd, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    return r.stdout.strip() if r.returncode == 0 else None


def fork_point(cwd):
    """The merge-base of a linked worktree's HEAD with the main checkout's HEAD, or
    None when `cwd` is not a linked worktree or either side cannot be resolved."""
    def path(*args):
        r = _git(cwd, "rev-parse", *args)
        return (pathlib.Path(cwd) / r.stdout.strip()).resolve() if r.returncode == 0 else None
    common, gitdir = path("--git-common-dir"), path("--git-dir")
    if common is None or gitdir is None or common == gitdir or common.name != ".git":
        return None
    main_head = git_head(common.parent)
    if main_head is None:
        return None
    r = _git(cwd, "merge-base", "HEAD", main_head)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def resolve_base(cwd, plan, explicit):
    """(base revision, where it came from)."""
    if explicit:
        return explicit, "--base"
    pb = plan.get("base") if isinstance(plan, dict) else None
    if isinstance(pb, str) and pb.strip():
        return pb.strip(), 'plan.json "base"'
    fp = fork_point(cwd)
    if fp:
        return fp, "the worktree's fork point from the main checkout"
    return "HEAD", "HEAD (no --base, no plan \"base\", no fork point)"


def _check_findings(r, errors):
    if "findings" not in r:
        return
    if not isinstance(r["findings"], list):
        errors.append("\"findings\" must be a list")
        return
    for n, f in enumerate(r["findings"]):
        if not isinstance(f, dict):
            errors.append(f"findings[{n}] must be an object")
            continue
        for k in ("id", "location", "issue", "fix"):
            if not isinstance(f.get(k), str) or not f[k].strip():
                errors.append(f"findings[{n}]: \"{k}\" must be a non-empty string")
        if f.get("severity") not in SEVERITIES:
            errors.append(f"findings[{n}]: \"severity\" {f.get('severity')!r} is not one "
                          f"of {', '.join(SEVERITIES)}")
        if f.get("confidence") not in CONFIDENCES:
            errors.append(f"findings[{n}]: \"confidence\" {f.get('confidence')!r} is not "
                          f"one of {', '.join(CONFIDENCES)}")
        if not isinstance(f.get("blocking"), bool):
            errors.append(f"findings[{n}]: \"blocking\" must be true or false")


def lint(r, plan=None, actual=None, notes=None, base_hint=None):
    """Every row of the §3 rejection table, plus shape checks. Returns (errors, warns).

    `actual` is the worktree's real changed-file list (actual_changes); with a plan it
    replaces trust in the report's own `changes`. `notes` collects informational lines;
    `base_hint` is appended to a "claimed change is not there" error."""
    errors, warns = [], []
    notes = [] if notes is None else notes
    for k in r:
        if k not in KNOWN_KEYS:
            near = difflib.get_close_matches(k, sorted(KNOWN_KEYS), n=1, cutoff=0.6)
            errors.append(f"unknown key \"{k}\" — "
                          + (f"did you mean \"{near[0]}\"?" if near
                             else f"known: {', '.join(sorted(KNOWN_KEYS))}"))
    if "schema" not in r:
        warns.append(f"no \"schema\" field — read as schema {SCHEMA}; add \"schema\": {SCHEMA}")
    elif r["schema"] != SCHEMA:
        errors.append(f"\"schema\": {r['schema']!r} is not supported — this agent_report "
                      f"reads schema {SCHEMA}")

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
        if "expect_exit" in e and type(e["expect_exit"]) is not int:
            errors.append(f"evidence[{n}]: \"expect_exit\" must be an integer")
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
    _check_findings(r, errors)

    # --- the §3 rejection table, row by row ---
    evidence = _items(r, "evidence")
    if status == "done":
        if not evidence:
            errors.append("status done with no evidence — done without proof is a claim; "
                          "run the task's verify commands and record each with its exit code")
        for e in evidence:
            want = e.get("expect_exit", 0)
            if type(e.get("exit_code")) is int and type(want) is int \
                    and e["exit_code"] != want:
                errors.append(f"status done but evidence {e.get('cmd')!r} exited "
                              f"{e['exit_code']}"
                              + (f", expected {want}" if want != 0 else "")
                              + " — fix it, or report failed/needs-decision")
    for d in _items(r, "decisions"):
        door = d.get("door")
        if door == "one-way":
            errors.append(f"decision {d.get('id', '?')} is a one-way door — one-way doors "
                          f"are questions (§4): move it to questions with options and a "
                          f"recommendation")
        elif door not in DOORS:
            errors.append(f"decision {d.get('id', '?')}: \"door\" must be two-way or one-way")
    blocking = ([q for q in _items(r, "questions") if q.get("blocking") is True]
                + [p for p in _items(r, "plan_issues") if p.get("blocking") is True]
                + [f for f in _items(r, "findings") if f.get("blocking") is True])
    if status == "needs-decision" and not blocking:
        errors.append("status needs-decision with no blocking question, plan issue or "
                      "finding — a stop must say what unblocks it")
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
        agent = r.get("agent")
        if task is None and agent in READ_ONLY_ROLES:
            notes.append(f"task_id {r.get('task_id')!r} is not a plan task and {agent} is "
                         f"a read-only role: owned-file, owner and declared-verify checks "
                         f"skipped; report-level checks still apply")
        elif task is None:
            errors.append(f"task_id {r.get('task_id')!r} is not a task in the supplied plan"
                          + (f" — {agent} writes files, so it needs a task that owns them"
                             if agent in plan_dag.ROSTER else ""))
        else:
            if isinstance(agent, str) and agent != task.get("owner"):
                errors.append(f"agent {agent!r} is not {r['task_id']}'s owner "
                              f"{task.get('owner')!r} — a task's report comes from the "
                              f"agent the plan assigned it to")
            errors += _plan_checks(r, task, status, evidence, actual, warns, base_hint)
    if status == "blocked" and not blocking:
        errors.append("status blocked with no blocking question, plan issue or finding — "
                      "a block must say what unblocks it (§3)")
    if status == "failed" and not evidence:
        errors.append("status failed with no evidence — a failure must show what failed (§3)")
    return errors, warns


def _plan_checks(r, task, status, evidence, actual, warns, base_hint=None):
    errors, tid = [], r["task_id"]
    owned = plan_dag._ids(task.get("files"))
    owned_s = ", ".join(owned) or "none"
    claimed = [c["path"] for c in _items(r, "changes") if isinstance(c.get("path"), str)]
    for p in claimed:
        if not plan_dag.path_owned(p, owned):
            errors.append(f"change {p!r} is outside {tid}'s owned files ({owned_s}) — "
                          f"collisions break parallel work; revert it or raise a plan issue")
    if actual is not None:
        for p in actual:
            if not plan_dag.path_owned(p, owned):
                errors.append(f"the worktree changed {p!r}, outside {tid}'s owned files "
                              f"({owned_s}) — whatever the report says, this file differs "
                              f"from the task's base; revert it or raise a plan issue")
        missing = [p for p in claimed if p not in actual]
        for p in missing:
            errors.append(f"change {p!r} is claimed but the worktree has no change to it "
                          f"since the task's base — the report describes work that is "
                          f"not there" + (f" ({base_hint})" if base_hint else ""))
        if status == "done" and not actual:
            warns.append(f"status done but no file changed since the task's base — "
                         f"right only for a verification-only task")
    if status == "done":
        ran = {cmd_key(e["cmd"]) for e in evidence
               if isinstance(e.get("cmd"), str) and e.get("exit_code") == 0}
        for v in plan_dag._ids(task.get("verify")):
            if cmd_key(v) not in ran:
                errors.append(f"status done but {tid}'s declared verify command {v!r} is "
                              f"not in the evidence with exit 0 — run it as the plan "
                              f"writes it (bare, or via `100x verified --name X -- …`) "
                              f"and record the result")
    return errors


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
        # -o is an explicit destination and may sit outside the repository (the
        # main session saves reports next to its worktrees); what must not happen
        # is a planted symlink at that path redirecting the write.
        dest = pathlib.Path(a.output).absolute()
        repo, in_git = _paths.git_root()
        inside = in_git and pathlib.Path(repo).resolve() in dest.parent.resolve().parents \
            or dest.parent.resolve() == pathlib.Path(repo).resolve()
        _paths.safe_write_text(dest, out, repo if inside else dest.parent,
                               "agent_report extract -o")
        print(f"wrote {a.output}")
    else:
        sys.stdout.write(out)
    return 0


def cmd_lint(a):
    r, err = load_report(a.report)
    if err:
        print(f"agent_report lint: {err}", file=sys.stderr)
        return 2
    plan = actual = base_hint = None
    notes = []
    if a.graph:
        if not a.cwd:
            print("agent_report lint: --graph needs --cwd <the task's worktree>: owned "
                  "files are checked against what git says changed there, not against "
                  "the report's own list", file=sys.stderr)
            return 2
        plan = plan_dag.load_plan(a.graph)
        if plan is None:
            return 2
        exclude = [a.graph] + ([a.report] if a.report != "-" else [])
        cwd = pathlib.Path(a.cwd)
        base, source = resolve_base(cwd, plan, a.base)
        actual, why = actual_changes(cwd, base, exclude)
        if why:
            print(f"agent_report lint: {why} (base from {source})", file=sys.stderr)
            return 2
        notes.append(f"base {base} — from {source}")
        base_sha = _git(cwd, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
        if base_sha.stdout.strip() == git_head(cwd):
            base_hint = COMMIT_HINT
    errors, warns = lint(r, plan, actual, notes, base_hint)
    for n_ in notes:
        print(f"  NOTE  {n_}")
    for w in warns:
        print(f"  WARN  {w}")
    for n, e in enumerate(errors, 1):
        print(f"  {n}. {e}")
    print(f"\nagent_report lint: {r.get('task_id', '?')} ({r.get('agent', '?')}, "
          f"{r.get('status', '?')}): {len(errors)} errors, {len(warns)} warnings")
    return 1 if errors else 0


def _tail(s, n=TAIL_LINES):
    return "\n".join(s.rstrip().splitlines()[-n:])


def run_argv(argv, cwd, timeout):
    """(exit code | "timeout", combined output). No shell. The command gets its own
    session so a timeout can kill everything it started, not just the direct child
    (a test runner's workers would otherwise outlive the replay)."""
    try:
        p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, start_new_session=True)
    except OSError as e:
        return 127, f"{argv[0]}: {e.strerror or e}"
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (AttributeError, ProcessLookupError, PermissionError):
            p.kill()
        out, _ = p.communicate()
        return "timeout", out or ""


def argv_problems(cmd, argv, cwd):
    """Screen the argv replay is about to execute, not the text plan_dag linted. The
    hook's parser reads `#` as a comment wherever a token starts, while shlex.split and
    sh only treat it so at a word start: `env A=1#x git tag v9` linted clean and then
    tagged. So the argv is re-quoted before parsing, and an `sh -c` script, which the
    shell will read itself, is screened with every `#` neutralised; that can only
    refuse more, never less."""
    extra = getattr(plan_dag, "replay_argv_problems", None)
    out = list(extra(cmd, cwd)) if extra is not None else []
    texts = [shlex.join(argv)]
    script = plan_dag.shell_wrapped(argv)
    if script is not None:
        texts += [script, script.replace("#", "_")]
    gated = []
    for t in texts:
        gated += plan_dag.gated_actions(t, cwd)
    if gated:
        out.append(f"performs a gated action ({', '.join(dict.fromkeys(gated))}) in the "
                   f"argv replay would run — a verify command proves the work, it never "
                   f"ships it")
    return out


def plan_replay(r, task, cwd):
    """Sort every evidence entry into run / undeclared / refused, and list declared
    verify commands the report has no evidence for."""
    declared = {}
    for v in plan_dag._ids(task.get("verify")):
        declared.setdefault(cmd_key(v), v.strip())
    run, undeclared, refused = [], [], []
    for e in _items(r, "evidence"):
        cmd = declared.get(cmd_key(e["cmd"]))
        if cmd is None:
            undeclared.append(e)
            continue
        problems = plan_dag.command_problems(cmd, cwd)
        argv = None if problems else shlex.split(cmd)
        if argv is not None:
            problems = argv_problems(cmd, argv, cwd)
        if problems:
            refused.append((e, problems[0]))
            continue
        run.append((e, argv, cmd))
    have = {cmd_key(e["cmd"]) for e in _items(r, "evidence")}
    missing = [v for k, v in declared.items() if k not in have]
    return run, undeclared, refused, missing


def cmd_replay(a):
    r, err = load_report(a.report)
    if err:
        print(f"agent_report replay: {err}", file=sys.stderr)
        return 2
    if not a.graph:
        print("agent_report replay: --graph plan.json is required — only the commands the "
              "plan declares as the task's `verify` are ever run; evidence text alone is "
              "never executed", file=sys.stderr)
        return 2
    plan = plan_dag.load_plan(a.graph)
    if plan is None:
        return 2
    by_id, _ = plan_dag.graph(plan.get("tasks", []))
    task = by_id.get(r.get("task_id"))
    if task is None:
        print(f"agent_report replay: task_id {r.get('task_id')!r} is not a task in "
              f"{a.graph}", file=sys.stderr)
        return 2
    cwd = pathlib.Path(a.cwd or ".").resolve()
    if not cwd.is_dir():
        print(f"agent_report replay: --cwd {cwd} is not a directory", file=sys.stderr)
        return 2
    if len(_items(r, "evidence")) != len(_list(r, "evidence")) or any(
            not isinstance(e.get("cmd"), str) or type(e.get("exit_code")) is not int
            for e in _items(r, "evidence")):
        print("agent_report replay: some evidence entries lack a cmd string or an integer "
              "exit_code; run `agent_report lint` first", file=sys.stderr)
        return 1
    run, undeclared, refused, missing = plan_replay(r, task, cwd)
    tid = r.get("task_id", "?")
    print(f"agent_report replay: {tid} in {cwd}")
    for e, argv, cmd in run:
        script = plan_dag.shell_wrapped(argv)
        print(f"  declared  $ {e['cmd']}    (claimed exit {e['exit_code']})")
        if cmd != e["cmd"].strip():
            print(f"            runs the plan's form: {cmd}")
        if script is not None:
            print(f"            runs a shell script: {script}")
    for e in undeclared:
        print(f"  not replayed (undeclared)  $ {e['cmd']}  — not one of {tid}'s verify "
              f"commands in {a.graph}")
    for e, why in refused:
        print(f"  refused   $ {e['cmd']}  — {why}")
    for v in missing:
        print(f"  MISSING   $ {v}  — declared verify command with no evidence entry")
    if not run and not undeclared and not refused and not missing:
        if r.get("status") == "done":
            print("agent_report replay: status done but there is no evidence to replay")
            return 1
        print("agent_report replay: no evidence to replay")
        return 0
    if not a.yes:
        print(f"\nNothing has been run. Re-run with --yes to execute the {len(run)} "
              f"declared command(s) above.")
        return 3
    mismatches = 0
    for e, argv, _ in run:
        actual, out = run_argv(argv, cwd, a.timeout)
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
    skipped = len(undeclared) + len(refused)
    print(f"\nagent_report replay: {tid}: {len(run) - mismatches}/{len(run)} "
          f"reproduced, {mismatches} mismatch(es), {len(missing)} missing, "
          f"{skipped} not replayed")
    if mismatches or missing:
        return 1
    return 3 if skipped else 0


def cmd_summary(a):
    questions, issues, findings, seen = [], [], [], set()
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
        for f in _items(r, "findings"):
            findings.append({"from": who, "id": f.get("id"), "severity": f.get("severity"),
                             "confidence": f.get("confidence"),
                             "location": f.get("location"), "issue": f.get("issue"),
                             "fix": f.get("fix"), "blocking": f.get("blocking") is True})
    # stable sort keeps report order inside each group, which is the agents' impact order
    questions.sort(key=lambda q: not q["blocking"])
    issues.sort(key=lambda p: not p["blocking"])
    rank = {s: n for n, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (not f["blocking"], rank.get(f["severity"], len(rank))))
    for q in questions:
        del q["_key"]
    batch, deferred = questions[:MAX_QUESTIONS], questions[MAX_QUESTIONS:]
    if a.json:
        print(json.dumps({"questions": batch, "deferred_questions": deferred,
                          "plan_issues": issues, "findings": findings},
                         indent=2, ensure_ascii=False))
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
    print(f"\nFindings ({len(findings)}, blocking first, then by severity):")
    for f in findings:
        tag = "BLOCKING" if f["blocking"] else "non-blocking"
        print(f"- [{tag}] {f['from']} {f['id'] or '?'} {f['severity']}/{f['confidence']} "
              f"at {f['location']}: {f['issue']}")
        if f["fix"]:
            print(f"    fix: {f['fix']}")
    if not findings:
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
    p.add_argument("--graph", help="plan.json: check the worktree's real changes stay in "
                                   "the task's owned files and every verify command ran")
    p.add_argument("--cwd", help="the task's worktree (required with --graph)")
    p.add_argument("--base",
                   help="the commit the task started from (default: plan.json's "
                        "\"base\", else the worktree's fork point from the main "
                        "checkout, else HEAD)")
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("replay", help="re-run the task's declared verify commands and "
                                      "compare exit codes with the evidence")
    p.add_argument("report")
    p.add_argument("--graph", help="plan.json (required): only its verify commands run")
    p.add_argument("--cwd", help="directory to run the commands in (default: current)")
    p.add_argument("--timeout", type=int, default=600, help="seconds per command")
    p.add_argument("--yes", action="store_true",
                   help="actually run the declared commands; without it they are only "
                        "printed")
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("summary", help="merge questions, plan issues and findings "
                                       "across reports")
    p.add_argument("reports", nargs="+")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_summary)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
