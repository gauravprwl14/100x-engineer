#!/usr/bin/env python3
"""Task-graph checker for orchestrated work: lint a plan.json, print its waves, pick what runs next.

The failure this prevents: parallel agents that collide. Two tasks with no ordering
between them both edit the shared types file; a consumer starts before the contract it
builds on exists; an acceptance criterion in the spec is owned by nobody and silently
never gets built. Each of those is visible in the plan before any agent starts, so
docs/OPERATING-MODEL.md §6 makes `plan_dag lint` the gate in front of every task.

    plan_dag.py lint plan.json [--spec spec.md] [--agents-dir agents/]
    plan_dag.py stamp plan.json [--spec spec.md]
    plan_dag.py waves plan.json [--json]
    plan_dag.py next plan.json --done T0,T1 [--blocked T2] [--json]

A plan carries "schema": 1, a required "feature" (the spec directory name), an optional
"tier" from scripts/data/scale_tiers.json, and "tasks"; `stamp` adds "spec" (its path
from the repository root), "spec_sha256" and "base" (HEAD when stamped). It lives at
<root>/specs/<feature>/plan.json, beside the spec. lint checks the plan against that
spec (or --spec): the spec must pass `plan_feature audit` with status `ready`, hash to
the stamped value, and define every AC a task claims. A field outside that set, or
outside a task's known fields, is an error with a did-you-mean: a misspelt
`depend_on` would otherwise drop an ordering edge silently. Ownership globs follow
scripts/_globs.py (no `{a,b}` braces; a bare extensionless path is a directory).
Each `verify` command must be replayable without a shell (`agent_report replay` runs
argv, never `sh`), so shell syntax is written `sh -c '...'`, and none may be a
commit, push, tag or publish.

Exit codes: 0 clean (warnings allowed), 1 findings, 2 unreadable input.
Python stdlib only.
"""
import argparse, contextlib, difflib, hashlib, importlib.util, io, json, os, pathlib, re
import shlex, subprocess, sys

import _md as md
import _paths
from _globs import globs_overlap, has_brace, path_owned  # path_owned: used by agent_report

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = 1
TIERS = json.loads((PLUGIN / "scripts" / "data" / "scale_tiers.json").read_text())["_order"]

# Must track the roster table in docs/OPERATING-MODEL.md §1; tests/test_plan_dag.sh
# fails if a name here is missing from that table.
ROSTER = (
    "requirements-analyst", "solution-architect", "backend-engineer",
    "frontend-engineer", "mobile-engineer", "qa-engineer", "code-reviewer",
    "security-reviewer", "independent-verifier", "comprehension-mapper",
    "rca-investigator",
)
PLAN_FIELDS = {"schema", "feature", "tier", "spec", "spec_sha256", "base", "tasks"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{7,64}$")
TASK_FIELDS = {"id", "title", "owner", "depends_on", "files", "acceptance", "verify",
               "contract", "consumes"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
OPERATOR_CHARS = set("();<>|&")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GATED_FALLBACK = re.compile(r"\bgit\b.*\b(commit|push|tag)\b|\bgh\s+(pr|release)\b|"
                            r"\bpublish\b|\btwine\b", re.S)


# ---------------------------------------------------------------- verify commands
#
# A task's `verify` commands are what `agent_report replay` re-runs, without a shell:
# argv from shlex.split. So a command that needs shell syntax (&&, |, >, $VAR, a
# leading VAR=x) must say so by being written `sh -c '...'`, which replay shows to the
# user before running, and nothing may be a completion-shaped action the verification
# hook gates (commit, push, tag, publish): a replay must never ship anything.

_hook_mod = None


def _hook():
    """hooks/require_verification.py, imported read-only for its command parser. It
    exits at import when its own dependencies fail; that is caught and the regex
    fallback below is used instead, which gates more, never less."""
    global _hook_mod
    if _hook_mod is None:
        try:
            spec = importlib.util.spec_from_file_location(
                "_100x_require_verification", PLUGIN / "hooks" / "require_verification.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _hook_mod = mod if hasattr(mod, "parse_command") else False
        except (Exception, SystemExit):
            _hook_mod = False
    return _hook_mod or None


def gated_actions(cmd, cwd="."):
    """Labels of the gated actions (git commit, npm publish, ...) a command performs."""
    hook = _hook()
    cwd = os.path.abspath(cwd)
    if hook is not None:
        # parse_command fills a State the way the hook does at runtime; passing anything
        # else used to raise inside a broad except and silently drop to the regex below.
        try:
            return [x.label for x in hook.parse_command(cmd, hook.State(cwd, cmd))]
        except ValueError:
            return [x.label for x in hook._fallback_actions(cmd, hook.State(cwd, cmd))]
    return ["completion-shaped command"] if GATED_FALLBACK.search(cmd) else []


SHELL_VALUE_LONG = {"--rcfile", "--init-file"}


def shell_wrapped(argv):
    """The script when argv is a shell run with -c (`sh -c '<script>'`, `bash -euo
    pipefail -c '...'`, `bash -O extglob -c '...'`), else None.

    -o/+o/-O/+O each consume the next word, including inside a combined flag such as
    -euo. When -c is present but the option list cannot be followed, the rest of the
    line is returned so it is still shown and screened rather than missed."""
    if not argv or os.path.basename(argv[0]) not in SHELLS:
        return None
    c_seen = any(len(x) > 1 and x[0] == "-" and not x.startswith("--") and "c" in x[1:]
                 for x in argv[1:])
    if not c_seen:
        return None
    i, n = 1, len(argv)
    while i < n:
        x = argv[i]
        if x == "--":
            i += 1
            break
        if x.startswith("--"):
            i += 2 if x in SHELL_VALUE_LONG else 1
            continue
        if len(x) > 1 and x[0] in "-+":
            i += 1 + sum(1 for f in x[1:] if f in "oO")
            continue
        break
    if i < n:
        return argv[i]
    return " ".join(argv[1:]) if i > n else ""


def _script_segments(script):
    """A shell script split into simple commands at its operators, with `#` kept as an
    ordinary character. shlex's default treats `#` as a comment even mid-word, so
    `echo a#b; <gated>` would otherwise hide everything after the `#`. A real `# ...`
    comment is screened as words too: that over-gates, it never under-gates."""
    lx = shlex.shlex(script, posix=True, punctuation_chars=";&|()<>\n")
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    lx.commenters = ""
    segs, cur = [], []
    for tok in lx:
        if tok and set(tok) <= set(";&|()<>\n"):
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs


def _gated_argv(argv, cwd, depth=0):
    """Gated actions in the exact argv replay executes, and in any `sh -c` script it
    carries. The hook parser tokenises with `#` as a comment, so it is handed a
    re-quoted argv (a quoted `#` is never a comment) as well as each script segment."""
    found = list(gated_actions(shlex.join(argv), cwd))
    script = shell_wrapped(argv)
    if script is not None and depth < 4:
        found += gated_actions(script, cwd)
        try:
            segs = _script_segments(script)
        except ValueError:
            segs = []
            found += ["completion-shaped command"] if GATED_FALLBACK.search(script) else []
        for seg in segs:
            found += _gated_argv(seg, cwd, depth + 1)
    return found


def replay_argv_problems(cmd, cwd="."):
    """Why a verify command cannot be replayed as written; [] when it can.

    The one screen for both `plan_dag lint` and `agent_report replay`: it checks
    shlex.split(cmd), the argv replay runs, so the two can never disagree about what a
    command does."""
    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        return [f"not parseable as an argv ({e})"]
    if not argv:
        return ["empty command"]
    out = []
    gated = gated_actions(cmd, cwd) + _gated_argv(argv, cwd)
    if gated:
        out.append(f"performs a gated action ({', '.join(dict.fromkeys(gated))}) — a "
                   f"verify command proves the work, it never ships it")
    if shell_wrapped(argv) is not None:
        return out
    if ENV_ASSIGN.match(argv[0]):
        out.append(f"starts with an assignment {argv[0]!r}, which needs a shell — write "
                   f"`env {argv[0]} ...` or `sh -c '...'`")
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lx.whitespace_split = True
    lx.commenters = ""
    ops = [tok for tok in lx if tok and set(tok) <= OPERATOR_CHARS]
    if ops:
        out.append(f"uses shell syntax {ops[0]!r}; replay runs commands without a shell, "
                   f"so write it as `sh -c '...'`")
    elif any("$" in x or "`" in x for x in argv):
        out.append("uses $ or ` expansion, which needs a shell — write it as `sh -c '...'`")
    return out


command_problems = replay_argv_problems


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

def _unknown(k, known):
    near = difflib.get_close_matches(k, sorted(known), n=1, cutoff=0.6)
    return (f"did you mean '{near[0]}'?" if near
            else f"known: {', '.join(sorted(known))}")


def lint(plan, spec=None, agents_dir=None, spec_label=None):
    errors, warns = [], []
    tasks = plan["tasks"]
    spec_label = spec_label or spec

    known = set(ROSTER)
    if agents_dir and pathlib.Path(agents_dir).is_dir():
        known |= {p.stem for p in pathlib.Path(agents_dir).glob("*.md")}

    # An unknown field is an error, not a warning: `depend_on` or `verfiy` silently
    # drops an ordering edge or the proof a task owes, and the plan still "passes".
    for k in sorted(set(plan) - PLAN_FIELDS):
        errors.append(f"unknown top-level field '{k}' — {_unknown(k, PLAN_FIELDS)}")
    if "schema" not in plan:
        warns.append(f"no \"schema\" field — read as schema {SCHEMA}; add "
                     f"\"schema\": {SCHEMA}")
    elif plan["schema"] != SCHEMA:
        errors.append(f"\"schema\": {plan['schema']!r} is not supported — this "
                      f"plan_dag reads schema {SCHEMA}")
    if not isinstance(plan.get("feature"), str) or not plan["feature"].strip():
        errors.append("missing top-level \"feature\" — the spec directory name "
                      "(<root>/specs/<feature>/), the namespace tests tag "
                      "`<feature>/AC-<n>` with")
    if "tier" in plan and plan["tier"] not in TIERS:
        errors.append(f"\"tier\": {plan['tier']!r} is not one of {', '.join(TIERS)} "
                      f"(scripts/data/scale_tiers.json)")
    errors += stamp_field_errors(plan)

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
            errors.append(f"{tid}: unknown field '{k}' — {_unknown(k, TASK_FIELDS)}")
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
        for f in _ids(t.get("files")):
            if has_brace(f):
                errors.append(f"{tid}: file glob {f!r} uses {{a,b}} braces, which are not "
                              f"glob syntax here and would own nothing — list each path")
        for c in _ids(t.get("verify")):
            for why in command_problems(c):
                errors.append(f"{tid}: verify command {c!r} {why}")

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
            errors.append(f"--spec {spec_label}: cannot read ({e})")
            text = ""
        # Only DEFINED criteria count (_md.parse_acs, the parser every AC tool
        # shares): a verification row or a prose line that merely mentions `AC-3`
        # must not make AC-3 look like a criterion the plan has to deliver.
        spec_ids = set(md.parse_acs(text))
        if text and not spec_ids:
            errors.append(f"--spec {spec_label} defines no acceptance criteria — write each "
                          f"as a line `AC-<n>: <observable outcome> (R<k>)`; with none, "
                          f"coverage cannot be checked")
        covered = {a for t in by_id.values() for a in _ids(t.get("acceptance"))}
        for ac in sorted(spec_ids - covered, key=md.ac_key):
            errors.append(f"{ac} in {spec_label} is covered by no task — add it to the "
                          f"\"acceptance\" of the task that delivers it")
        # An error, not a warning: a typo'd `AC-12` for `AC-2` passes coverage for
        # nothing, and the task's report would later claim a criterion nobody wrote.
        for ac in sorted(covered - spec_ids, key=md.ac_key):
            who = sorted(tid for tid, t in by_id.items() if ac in _ids(t.get("acceptance")))
            errors.append(f"{ac} is claimed by {', '.join(who)} but {spec_label} does not "
                          f"define it — fix the id, or add the criterion to the spec's "
                          f"§2b and re-approve the spec")
    return errors, warns


def stamp_field_errors(plan):
    """Shape of the fields `plan_dag stamp` writes; whether they still hold is
    spec_gate's job."""
    out = []
    if "spec" in plan:
        s = plan["spec"]
        raw = pathlib.PurePosixPath(s.replace("\\", "/")) if isinstance(s, str) else None
        if raw is None or not s.strip() or raw.is_absolute() or ".." in raw.parts:
            out.append(f"\"spec\": {s!r} must be the spec's path relative to the repository "
                       f"root, with no '..' — `plan_dag stamp` writes it")
    if "spec_sha256" in plan:
        if not (isinstance(plan["spec_sha256"], str) and SHA256.match(plan["spec_sha256"])):
            out.append(f"\"spec_sha256\": {plan['spec_sha256']!r} is not a sha256 hex "
                       f"digest — `plan_dag stamp` writes it")
        if "spec" not in plan:
            out.append("\"spec_sha256\" without \"spec\" — the hash says nothing without "
                       "the file it was taken of; run `plan_dag stamp`")
    if "base" in plan and not (isinstance(plan["base"], str) and GIT_SHA.match(plan["base"])):
        out.append(f"\"base\": {plan['base']!r} is not a git commit id — `plan_dag stamp` "
                   f"records HEAD")
    return out


# ---------------------------------------------------------------- spec approval
#
# A plan is only as good as the spec it was cut from. lint --spec therefore requires
# the spec to pass plan_feature's audit with status `ready`, and requires it to be the
# same bytes the plan was stamped against: an AC edited after planning would otherwise
# be built from a plan that never saw it.

def file_sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _is_ready(status):
    return str(status or "").strip().strip("*` ").lower().startswith("ready")


def _header_status(path):
    try:
        text = pathlib.Path(path).read_text(errors="replace")
    except OSError:
        return ""
    m = re.search(r"^\|\s*status\s*\|\s*(.+?)\s*\|\s*$", text, re.I | re.M)
    return m.group(1).strip().strip("*` ") if m else ""


def audit_spec(path):
    """(errors, warnings, status) from plan_feature's audit of `path`.

    plan_feature.audit_spec when that module exposes it; otherwise `plan_feature.py
    audit` as a subprocess, its ERROR/WARN lines read back. Either way the verdict is
    plan_feature's, never a second implementation of it here."""
    path = pathlib.Path(path).resolve()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import plan_feature
        fn = getattr(plan_feature, "audit_spec", None)
    except (Exception, SystemExit):
        fn = None
    if fn is not None:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                errs, warns, status = fn(path)
            return list(errs), list(warns), status
        except (Exception, SystemExit):  # fail-closed: fall back to the CLI's own verdict below
            pass
    repo, _ = _paths.git_root(path.parent)
    r = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "plan_feature.py"),
                        "audit", str(path)], cwd=str(repo), capture_output=True, text=True)
    out = r.stdout or ""
    errs = [l.strip()[len("ERROR"):].strip() for l in out.splitlines()
            if l.strip().startswith("ERROR")]
    warns = [l.strip()[len("WARN"):].strip() for l in out.splitlines()
             if l.strip().startswith("WARN")]
    if r.returncode not in (0, 1) or (r.returncode == 1 and not errs):
        tail = (r.stderr or out).strip().splitlines()[-1:] or ["no output"]
        errs.append(f"plan_feature audit exited {r.returncode}: {tail[0]}")
    status = "ready" if "spec is ready to implement" in out else _header_status(path)
    return errs, warns, status


def spec_gate(plan, spec, label):
    """Errors when `spec` is not an approved spec, or not the one the plan was made
    from."""
    errors = []
    errs, _, status = audit_spec(spec)
    if errs:
        errors.append(f"spec {label} does not pass `100x plan_feature audit` "
                      f"({len(errs)} blocking issue(s), first: {errs[0]}) — a plan is cut "
                      f"from an audited, ready spec; fix the spec and re-run the audit")
    elif not _is_ready(status):
        errors.append(f"spec {label} has status {status or '(none)'!r}, not `ready` — "
                      f"approve it (set `| status | ready |` once the audit passes) "
                      f"before linting a plan against it")
    recorded = plan.get("spec_sha256")
    if not isinstance(recorded, str) or not SHA256.match(recorded):
        errors.append(f"plan is not stamped against {label} — run `100x plan_dag stamp "
                      f"<plan.json>` to record the spec path, its sha256 and the base commit")
    else:
        now = file_sha256(spec)
        if now != recorded:
            errors.append(f"spec {label} changed since the plan was stamped (sha256 "
                          f"{recorded[:12]}… recorded, {now[:12]}… now) — re-plan or "
                          f"re-approve: check the tasks against the edited spec, then "
                          f"`100x plan_dag stamp <plan.json>`")
    return errors


def resolve_spec(arg, repo=None, verb="--spec"):
    if repo is None:
        repo, _ = _paths.git_root()
    records, _ = _paths.resolve(repo)
    p = md.find_record(arg, "specs", "spec.md", repo, records)
    if p is None:
        print(f"plan_dag: {verb}: "
              + md.not_found(arg, "specs", "spec.md", records, lambda x: _paths.show(x, repo)),
              file=sys.stderr)
    return p


def plan_repo(plan_path):
    """The repository the plan lives in: its "spec" path is relative to that root."""
    return _paths.git_root(pathlib.Path(plan_path).absolute().parent)


def recorded_spec(plan, repo):
    """(path, label) for the plan's own "spec" field, or (None, message)."""
    s = plan.get("spec")
    if not isinstance(s, str) or not s.strip() or stamp_field_errors({"spec": s}):
        return None, None
    p = pathlib.Path(repo) / pathlib.PurePosixPath(s.replace("\\", "/"))
    if not p.is_file():
        return None, (f"plan records \"spec\": {s!r}, but there is no such file under "
                      f"{repo} — restore it, or re-stamp with `plan_dag stamp --spec <spec>`")
    return p, s


def cmd_lint(a):
    plan = load_plan(a.plan)
    if plan is None:
        return 2
    repo, _ = plan_repo(a.plan)
    pre, warns_pre = [], []
    spec, label = None, None
    rec, rec_label = recorded_spec(plan, repo)
    if rec is None and rec_label:
        pre.append(rec_label)
    if a.spec:
        spec = resolve_spec(a.spec)
        if spec is None:
            return 2
        label = a.spec
        if rec is not None and spec.resolve() != rec.resolve():
            pre.append(f"--spec {a.spec} is not the spec this plan was stamped against "
                       f"({rec_label}) — lint against {rec_label}, or re-stamp")
    elif rec is not None:
        spec, label = rec, rec_label
    elif not rec_label:
        warns_pre.append("no spec: acceptance coverage and spec approval were not checked "
                         "— pass --spec, or record it with `plan_dag stamp`")
    errors, warns = lint(plan, spec, a.agents_dir, label)
    errors = pre + errors
    warns = warns_pre + warns
    if spec is not None:
        errors += spec_gate(plan, spec, label)
    for w in warns:
        print(f"  WARN  {w}")
    for n, e in enumerate(errors, 1):
        print(f"  {n}. {e}")
    print(f"\nplan_dag lint: {len(plan['tasks'])} tasks, {len(errors)} errors, "
          f"{len(warns)} warnings")
    return 1 if errors else 0


STAMP_ORDER = ("schema", "feature", "tier", "spec", "spec_sha256", "base", "tasks")


def cmd_stamp(a):
    plan = load_plan(a.plan)
    if plan is None:
        return 2
    repo, in_git = plan_repo(a.plan)
    if not in_git:
        print(f"plan_dag stamp: refusing to write — {a.plan} is not inside a git "
              f"repository, so there is no root for \"spec\" and no base commit",
              file=sys.stderr)
        return 2
    if a.spec:
        spec = resolve_spec(a.spec, repo)
    else:
        spec, why = recorded_spec(plan, repo)
        if spec is None and why:
            print(f"plan_dag stamp: {why}", file=sys.stderr)
            return 2
        if spec is None and isinstance(plan.get("feature"), str) and plan["feature"].strip():
            spec = resolve_spec(plan["feature"], repo, "feature")
        elif spec is None:
            print("plan_dag stamp: no spec to stamp against — pass --spec, or set the "
                  "plan's \"feature\" to its spec directory name", file=sys.stderr)
            return 2
    if spec is None:
        return 2
    try:
        rel = spec.resolve().relative_to(pathlib.Path(repo).resolve()).as_posix()
    except ValueError:
        print(f"plan_dag stamp: spec {spec} is outside the repository {repo}",
              file=sys.stderr)
        return 2
    errs, _, status = audit_spec(spec)
    if errs or not _is_ready(status):
        why = (f"{len(errs)} blocking issue(s), first: {errs[0]}" if errs
               else f"status {status or '(none)'!r}, not `ready`")
        print(f"plan_dag stamp: refusing — {rel} is not an approved spec ({why}). Run "
              f"`100x plan_feature audit {rel}` and mark it ready first.", file=sys.stderr)
        return 1
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    if head.returncode != 0 or not GIT_SHA.match(head.stdout.strip()):
        print(f"plan_dag stamp: {repo} has no commit to record as \"base\" — commit "
              f"first", file=sys.stderr)
        return 2
    plan["spec"], plan["spec_sha256"] = rel, file_sha256(spec)
    plan["base"] = head.stdout.strip()
    ordered = {k: plan[k] for k in STAMP_ORDER if k in plan}
    ordered.update({k: v for k, v in plan.items() if k not in ordered})
    _paths.safe_write_text(pathlib.Path(a.plan).resolve(),
                           json.dumps(ordered, indent=2, ensure_ascii=False) + "\n",
                           repo, "plan_dag stamp")
    print(f"stamped {a.plan}: spec {rel} sha256 {plan['spec_sha256'][:12]}… base "
          f"{plan['base'][:12]}\nnext: `100x plan_dag lint {a.plan}`")
    return 0


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
    p.add_argument("--spec", help="spec whose AC-<n> ids must all be covered: the file, its "
                   "directory, specs/<name> under the records root, or the bare name "
                   "(default: the plan's own \"spec\")")
    p.add_argument("--agents-dir", help="directory of <agent>.md files accepted as owners")
    p.set_defaults(fn=cmd_lint)
    p = sub.add_parser("stamp", help="record the approved spec's path, sha256 and the base "
                       "commit in plan.json")
    p.add_argument("plan")
    p.add_argument("--spec", help="the spec (default: the plan's \"spec\", else its "
                   "\"feature\" resolved like a record name)")
    p.set_defaults(fn=cmd_stamp)
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
