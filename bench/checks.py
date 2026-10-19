#!/usr/bin/env python3
"""Deterministic graders for bench/cases, run after the agent sessions finish.

`claude plugin eval` has no script grader type (only regex, tool_used, tool_order,
file_exists, llm and baseline), so anything that must execute code -- hidden behaviour
tests, tests run with the fix reverted, craft_check and prose_check -- runs here, over the
workspaces that `--keep-temp` preserves. Each check_<NN> returns {check name: bool}.

The agent's workspace is compared with a pristine copy rebuilt from the same scaffold.sh
(fixture commits use fixed dates, so they are byte-identical). Git never runs inside the
harness's kept directory: workspaces are copied out first, and git runs with system,
global and hook configuration disabled.

    checks.py score <case> <workspace> [--text FILE] [--tools-root DIR]

prints the check results as JSON. compare.py imports this module. Python stdlib only.
"""
import argparse
import ast
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from functools import cached_property
from pathlib import Path

BENCH = Path(__file__).resolve().parent
CASES = BENCH / "cases"
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", ".100x", ".claude"}
TEST_RX = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$)")
EXEC_TIMEOUT = 60


def _clean_env(home):
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"}


def git(repo, *args):
    # The repo may have been written by the agent under test: no hooks, no fsmonitor.
    cmd = ["git", "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false",
           "-c", "safe.directory=*", *args]
    done = subprocess.run(cmd, cwd=repo, env=_clean_env(repo), capture_output=True,
                          text=True, timeout=EXEC_TIMEOUT)
    return done.returncode, done.stdout


def scaffold(case, dest):
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["bash", str(CASES / case / "scaffold.sh")], cwd=dest, env=_clean_env(dest),
                   check=True, capture_output=True, timeout=120)


def tree(root):
    files = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and not path.is_symlink() and not SKIP_PARTS & set(rel.split("/")):
            files[rel] = path
    return files


def read(path):
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def is_test(rel):
    return bool(TEST_RX.search(rel))


def run_python(cwd, code):
    """Run code in cwd and return its last stdout line parsed as JSON, or None."""
    try:
        done = subprocess.run([sys.executable, "-c", code], cwd=cwd, env=_clean_env(cwd),
                              capture_output=True, text=True, timeout=EXEC_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None
    lines = done.stdout.strip().splitlines()
    try:
        return json.loads(lines[-1]) if lines else None
    except ValueError:
        return None


def unittest_exit(cwd):
    try:
        return subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=cwd,
                              env=_clean_env(cwd), capture_output=True,
                              timeout=EXEC_TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        return 124


class Run:
    """One agent result: its workspace, the pristine fixture, and its final message."""

    def __init__(self, case, workspace, text, tools_root, scratch):
        self.case, self.ws, self.text = case, Path(workspace), text or ""
        self.tools_root, self.scratch = Path(tools_root), Path(scratch)

    @cached_property
    def base(self):
        base = self.scratch / "base"
        scaffold(self.case, base)
        return base

    @cached_property
    def changes(self):
        """rel path -> (old text or None, new text or None) for every differing file."""
        old, new = tree(self.base), tree(self.ws)
        out = {}
        for rel in sorted(set(old) | set(new)):
            before = read(old[rel]) if rel in old else None
            after = read(new[rel]) if rel in new else None
            if before != after:
                out[rel] = (before, after)
        return out

    def added_lines(self, rel):
        before, after = self.changes.get(rel, ("", ""))
        diff = difflib.ndiff((before or "").splitlines(), (after or "").splitlines())
        return [line[2:] for line in diff if line.startswith("+ ")]

    def added_text(self, source_only=False, tests_only=False):
        chosen = [rel for rel in self.changes if not (source_only and is_test(rel))
                  and not (tests_only and not is_test(rel))]
        return "\n".join(line for rel in chosen for line in self.added_lines(rel))

    def new_files(self):
        return [rel for rel, (before, after) in self.changes.items() if before is None and after]

    def file(self, rel):
        return read(self.ws / rel)

    @cached_property
    def overlay(self):
        """A git repo whose HEAD is the pristine fixture and whose tree is the agent's."""
        repo = self.scratch / "overlay"
        shutil.copytree(self.base, repo, symlinks=True)
        for rel in tree(repo):
            (repo / rel).unlink()
        for rel, path in tree(self.ws).items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, repo / rel)
        git(repo, "add", "-A")
        return repo

    def tests_pass(self):
        return unittest_exit(self.ws) == 0

    def copy_with(self, replacements):
        """A copy of the workspace with some files restored to their pristine content."""
        target = Path(tempfile.mkdtemp(dir=self.scratch))
        shutil.copytree(self.ws, target, symlinks=True, dirs_exist_ok=True)
        for rel in replacements:
            shutil.copy2(self.base / rel, target / rel)
        return target


# ---------------------------------------------------------------- shared checks
VERBS = {"get", "find", "list", "select", "filter", "collect", "compute", "calculate",
         "count", "build", "make", "fetch", "load", "read", "return", "is", "has", "can",
         "check", "mark", "apply", "create", "add", "remove", "send", "parse", "format",
         "validate", "ensure", "to", "query", "search", "determine", "extract", "yield"}
ABBREVIATIONS = {"inv", "invs", "amt", "dt", "tmp", "res", "val", "vals", "cnt", "idx",
                 "num", "lst", "arr", "obj", "cust", "acct", "calc", "info", "ret", "resp",
                 "req", "ctx", "cfg", "msg", "str", "dct", "elem", "itm", "od", "ovd"}
LOOP_NAMES = {"i", "j", "k", "_"}


def new_functions(run, rel):
    """FunctionDef nodes in rel whose names did not exist in the pristine file."""
    def defs(source):
        try:
            return {node.name: node for node in ast.walk(ast.parse(source or ""))
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        except SyntaxError:
            return {}
    before, after = defs(read(run.base / rel)), defs(run.file(rel))
    return [node for name, node in after.items() if name not in before]


def bad_names(func):
    """Names the bench's own (plugin-independent) naming rule rejects."""
    found = []
    if func.name.lstrip("_").split("_")[0] not in VERBS:
        found.append(func.name)
    names = {arg.arg for arg in func.args.args + func.args.kwonlyargs}
    names |= {node.id for node in ast.walk(func)
              if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
    for name in names - LOOP_NAMES - {"self", "cls"}:
        if len(name) < 3 or set(name.lower().split("_")) & ABBREVIATIONS:
            found.append(name)
    return found


def craft_naming_clean(run):
    tool = run.tools_root / "scripts" / "craft_check.py"
    wanted = ["short-names", "abbreviations", "boolean-predicate", "function-verb", "vague-names"]
    listed = subprocess.run([sys.executable, str(tool), "--list"], capture_output=True,
                            text=True).stdout
    only = [name for name in wanted if name in listed]
    done = subprocess.run([sys.executable, str(tool), "--base", "HEAD", "--only", ",".join(only)],
                          cwd=run.overlay, env=_clean_env(run.overlay), capture_output=True,
                          text=True, timeout=EXEC_TIMEOUT)
    match = re.search(r"(\d+) blocking, (\d+) advisory", done.stdout)
    return bool(match) and match.group(1) == match.group(2) == "0"


def prose_findings(run, text, kind, diff_lines=None):
    sys.path.insert(0, str(run.tools_root / "scripts"))
    try:
        import prose_check
    finally:
        sys.path.pop(0)
    return prose_check.check_text(text, kind=kind, diff_lines=diff_lines)


def paragraphs(text):
    """Prose paragraphs: blank-line separated blocks that are not lists, tables, code or headings."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    prose = []
    for block in blocks:
        lines = [line for line in block.splitlines()
                 if not re.match(r"\s*([-*+|>#]|\d+[.)])", line)]
        if lines:
            prose.append(lines)
    return prose


def no_wall_paragraph(text):
    return all(len(lines) <= 3 and len(" ".join(lines)) <= 300 for lines in paragraphs(text))


# ---------------------------------------------------------------- per case
def check_01(run):
    funcs = new_functions(run, "invoices/reports.py")
    name = funcs[0].name if funcs else "missing_function"
    probe = f"""
import json, datetime as d
from invoices.models import Invoice
from invoices.reports import {name} as f
on = d.date(2026, 3, 10)
rows = [Invoice("late", "c", 100, d.date(2026, 3, 1)),
        Invoice("today", "c", 100, on),
        Invoice("paid", "c", 100, d.date(2026, 3, 1), paid_on=d.date(2026, 3, 2)),
        Invoice("future", "c", 100, d.date(2026, 4, 1))]
for args in ((rows, on), (on, rows)):
    try:
        print(json.dumps(sorted(i.invoice_id for i in f(*args)))); break
    except Exception:
        pass
"""
    return {
        "craft_naming_clean": craft_naming_clean(run),
        "bench_names_clean": bool(funcs) and not any(bad_names(func) for func in funcs),
        "rule_correct": run_python(run.ws, probe) == ["late"],
        "test_added": bool(funcs) and name in run.added_text(tests_only=True),
        "tests_pass": run.tests_pass(),
    }


def check_02(run):
    source = run.added_text(source_only=True)
    outside_utils = "\n".join(line for rel in run.changes if not is_test(rel)
                              and not rel.startswith("bookings/utils/")
                              for line in run.added_lines(rel))
    probe = """
import json, datetime as d
from bookings.models import Booking
from bookings.cancellation import refund_percentage
booking = Booking("b1", "g1", d.date(2026, 2, 16), d.date(2026, 2, 18))
days = [d.date(2026, 2, 9), d.date(2026, 2, 10), d.date(2026, 2, 12), d.date(2026, 2, 13), d.date(2026, 2, 14)]
values = [float(refund_percentage(booking, day)) for day in days]
if max(values) <= 1:
    values = [v * 100 for v in values]
print(json.dumps([round(v) for v in values]))
"""
    return {
        "reuses_helper": "business_days_between" in source,
        "no_duplicate_weekday_logic": not re.search(
            r"weekday\(|isoweekday\(|timedelta\(days=1\)|def \w*business", outside_utils),
        "helper_untouched": "bookings/utils/dates.py" not in run.changes,
        "rule_correct": run_python(run.ws, probe) == [100, 50, 50, 0, 0],
        "tests_pass": run.tests_pass(),
    }


ENV_RX = re.compile(r"""(?:environ\.get|getenv|environ\[|environ\.setdefault)\(?\s*["']([A-Za-z0-9_]+)""")


def check_03(run):
    added = run.added_text()
    names = ENV_RX.findall(added)
    new_source = [rel for rel in run.new_files() if rel.endswith(".py") and not is_test(rel)]
    env_outside = [line for rel in run.changes if rel != "services/config.py"
                   and not is_test(rel) for line in run.added_lines(rel)
                   if re.search(r"\bos\.environ|\bgetenv\(|\benviron\b", line)]
    return {
        "env_names_prefixed": bool(names) and all(re.fullmatch(r"TODO_[A-Z0-9_]+", n) for n in names)
        and any("SMTP" in n or "MAIL" in n for n in names),
        "env_read_only_in_config": not env_outside,
        "module_directly_in_services": bool(new_source)
        and all(Path(rel).parent.as_posix() == "services" for rel in new_source),
        "tests_pass": run.tests_pass(),
    }


def check_04(run):
    probe = """
import json
from todo_api.pagination import paginate
items = list(range(45))
print(json.dumps([paginate(items, 1, 20), paginate(items, 3, 20), paginate(items, 4, 20)]))
"""
    tests_changed = any(is_test(rel) for rel in run.changes)
    reverted = run.copy_with(["todo_api/pagination.py"])
    return {
        "fix_correct": run_python(run.ws, probe) == [list(range(20)), list(range(40, 45)), []],
        "tests_added": tests_changed,
        "tests_pass": run.tests_pass(),
        "tests_fail_without_fix": tests_changed and unittest_exit(reverted) != 0,
    }


NEGATIVE_CASES = {
    "empty_or_missing": r"""["']\s*["']|\bdel\s|\bpop\(|missing|empty|required|blank""",
    "too_long": r"""\*\s*\d{2,}|too_?long|max(imum)?_?len|length|overlong""",
    "bad_dates": r"before|after|invalid_?date|not-a-date|date_?order|end_?date.*start|past",
    "unauthenticated": r"Request\(\s*None|user\s*=\s*None|unauth|401|anonymous|Unauthorized",
}


def check_05(run):
    tests = run.added_text(tests_only=True)
    covered = [name for name, rx in NEGATIVE_CASES.items() if re.search(rx, tests, re.I)]
    probe = """
import json
from bookings.api import create_booking
from bookings.http import Request, User
from bookings.store import BOOKINGS
user = User("u-1", "t-1")
good = {"guest_name": "Ada", "room": "101", "start_date": "2026-03-01", "end_date": "2026-03-03"}
def outcome(request):
    before = len(BOOKINGS)
    try:
        status = create_booking(request)["status"]
    except Exception:
        status = 400
    return status, len(BOOKINGS) - before
bad = [Request(user, {k: v for k, v in good.items() if k != "guest_name"}),
       Request(user, dict(good, guest_name="")),
       Request(user, dict(good, end_date="2026-02-27")),
       Request(None, dict(good))]
rejected = all(s >= 400 and stored == 0 for s, stored in map(outcome, bad))
print(json.dumps([rejected, outcome(Request(user, dict(good)))[0] == 201]))
"""
    return {
        "negative_tests_3_of_4": len(covered) >= 3,
        "rejects_bad_input": run_python(run.ws, probe) == [True, True],
        "tests_pass": run.tests_pass(),
    }


def check_06(run):
    probe = """
import json
from bookings.api import get_booking
from bookings.http import Request, User
def outcome(user, booking_id):
    try:
        response = get_booking(Request(user), booking_id)
    except Exception as error:
        return [type(error).__name__, getattr(error, "status", None), False]
    body = response.get("body") if isinstance(response, dict) else response
    leaked = isinstance(body, dict) and body.get("id") == 3
    return ["response", response.get("status") if isinstance(response, dict) else None, leaked]
alice = User("u-1", "t-1")
print(json.dumps([outcome(alice, 1), outcome(alice, 3), outcome(alice, 999), outcome(None, 1)]))
"""
    result = run_python(run.ws, probe)
    own, other, missing, anonymous = result if isinstance(result, list) and len(result) == 4 else [None] * 4
    blocked = bool(other) and not other[2] and (other[0] != "response" or other[1] in (403, 404))
    return {
        "own_booking_returned": bool(own) and own[:2] == ["response", 200],
        "cross_tenant_blocked": blocked,
        "no_existence_leak": blocked and other[:2] == (missing or [])[:2],
        "unauthenticated_rejected": bool(anonymous)
        and (anonymous[0] != "response" or anonymous[1] == 401),
        "tests_pass": run.tests_pass(),
    }


def diff_line_count(repo, base_ref, head_ref):
    _, out = git(repo, "diff", "--numstat", f"{base_ref}...{head_ref}")
    return sum(int(a) + int(b) for a, b, *_ in (line.split("\t") for line in out.splitlines())
               if a.isdigit() and b.isdigit())


def check_07(run):
    body = run.file("PR_BODY.md")
    lines = diff_line_count(run.base, "main", "feature/late-fee")
    return {
        "body_written": bool(body.strip()),
        "prose_check_clean": bool(body.strip()) and not prose_findings(run, body, "pr", lines),
        "length_budget": 0 < len(body) <= max(600, 8 * lines),
        "no_filler_or_ticked_boxes": not re.search(r"This PR|^\s*[-*]\s+\[[xX]\]", body, re.M),
        "links_issue": "#42" in body,
        "no_wall_paragraph": no_wall_paragraph(body),
    }


def review_comments(text):
    """Split a review file into comments at headings, rules, or severity-tagged lines."""
    chunks, current = [], []
    for line in text.splitlines():
        starts = re.match(r"\s*(#{1,4}\s|---\s*$|[-*]?\s*\**\[?(MUST|SHOULD|NIT|ASK|IMO|blocking|"
                          r"issue|suggestion|nit|question)\b)", line, re.I)
        if starts and current:
            chunks.append("\n".join(current))
            current = []
        if not re.match(r"\s*---\s*$", line):
            current.append(line)
    chunks.append("\n".join(current))
    return [c.strip() for c in chunks if len(re.sub(r"^#.*$", "", c, flags=re.M).strip()) > 20]


def check_08(run):
    review = run.file("REVIEW.md")
    comments = review_comments(review)
    bug_rx = r"(exceed|more than|greater than|larger than|over-?refund|beyond|upper bound|cap\b|> ?amount)"
    bug = [c for c in comments if re.search(r"refund", c, re.I) and re.search(bug_rx, c, re.I)]
    return {
        "bug_found": bool(bug),
        "bug_marked_blocking": any(re.search(r"\[MUST\]|blocking|must[- ]fix|critical|\bhigh\b",
                                             c, re.I) for c in bug),
        "prose_check_clean": bool(comments) and not any(
            prose_findings(run, c, "review-comment") for c in comments),
        "size_budget": 0 < len(review) <= 1500,
        "code_unchanged": "invoices/payments.py" not in run.changes,
    }


def check_09(run):
    reply = run.file("REPLY.md")
    _, base_head = git(run.base, "rev-parse", "feature/discounts")
    _, log = git(run.ws, "log", "--format=%H", "feature/discounts", "--not", base_head.strip())
    shas = log.split()
    probe = """
import json
from invoices.pricing import apply_discount
def value(*args):
    try:
        return apply_discount(*args)
    except Exception:
        return "raised"
print(json.dumps([value(1000, 10), value(1000, 0), value(1000, 100), value(1000, -20), value(1000, 150)]))
"""
    return {
        "fix_correct": run_python(run.ws, probe) == [900, 1000, 0, "raised", "raised"],
        "fix_committed": bool(shas),
        "reply_cites_sha": any(sha[:7] in reply for sha in shas),
        "prose_check_clean": bool(reply.strip()) and not prose_findings(run, reply, "reply"),
        "reply_short": 0 < len(reply.strip()) <= 500 and len(reply.strip().splitlines()) <= 6,
        "tests_pass": run.tests_pass(),
    }


RETRY_FACTS = [r"\b4\b|four|3 retries|three retries", r"Idempotency-Key", r"429",
               r"jitter|random", r"Retry-After", r"\b30\b", r"\bPOST\b", r"\b8\b"]


def check_10(run):
    text = run.text
    blocks = paragraphs(text)
    return {
        "prose_check_clean": bool(text.strip()) and not prose_findings(run, text, "chat"),
        "summary_first": bool(blocks) and len(" ".join(blocks[0])) <= 300
        and not re.match(r"\s*#", text.strip()),
        "no_wall_paragraph": no_wall_paragraph(text),
        "facts_6_of_8": sum(bool(re.search(rx, text)) for rx in RETRY_FACTS) >= 6,
        "length_under_2500_chars": 0 < len(text) <= 2500,
    }


def check_11(run):
    _, base_b = git(run.base, "rev-parse", "feature-b")
    code, names = git(run.ws, "diff", "--name-only", "main", "feature-a")
    touched = names.split()
    allowed = all(rel == "invoices/export.py" or re.fullmatch(r"tests/test_export\w*\.py", rel)
                  for rel in touched)
    _, export = git(run.ws, "show", "feature-a:invoices/export.py")
    sandbox = Path(tempfile.mkdtemp(dir=run.scratch))
    shutil.copytree(run.base / "invoices", sandbox / "invoices")
    (sandbox / "invoices" / "export.py").write_text(export)
    probe = """
import json
from invoices.export import invoices_to_csv
from invoices.models import Invoice
print(json.dumps(len(invoices_to_csv([Invoice("i1", "a", 100), Invoice("i2", "b", 250)]).splitlines())))
"""
    _, head_b = git(run.ws, "rev-parse", "feature-b")
    _, tree_b = git(run.ws, "ls-tree", "-r", "--name-only", "feature-b")
    return {
        "fix_on_feature_a": code == 0 and run_python(sandbox, probe) == 3,
        "feature_a_scope_clean": code == 0 and allowed,
        "feature_b_untouched": head_b.strip() == base_b.strip(),
        "wip_preserved": (run.ws / "invoices/tag_filters.py").exists()
        or "invoices/tag_filters.py" in tree_b.split(),
    }


def check_12(run):
    added = [line for line in run.added_text(source_only=True).splitlines() if line.strip()]
    funcs = new_functions(run, "todo/todo_list.py")
    name = funcs[0].name if funcs else "missing_method"
    probe = f"""
import json
from todo.todo_list import TodoList
todos = TodoList()
first, second = todos.add("a"), todos.add("b")
todos.{name}(first.todo_id)
print(json.dumps([first.done, second.done, [t.todo_id for t in todos.open_todos()]]))
"""
    return {
        "no_new_source_files": not [rel for rel in run.new_files() if not is_test(rel)],
        "source_lines_within_budget": len(added) <= 20,
        "no_new_class": not any(re.match(r"\s*class\s", line) for line in added),
        "works": run_python(run.ws, probe) == [True, False, [2]],
        "tests_pass": run.tests_pass(),
    }


CHECKS = {path.name: globals()[f"check_{path.name[:2]}"]
          for path in sorted(CASES.iterdir()) if path.is_dir() and path.name[:2].isdigit()}


def score(case, workspace, text="", tools_root=BENCH.parent):
    """{"checks": {name: bool}, "error": str | None}; an error scores as one failed check."""
    with tempfile.TemporaryDirectory(prefix="bench-score-") as scratch:
        try:
            return {"checks": CHECKS[case](Run(case, workspace, text, tools_root, scratch)),
                    "error": None}
        except Exception as error:  # fail-open: one broken workspace must not stop scoring
            return {"checks": {"scorer_ran": False}, "error": f"{type(error).__name__}: {error}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("score")
    one.add_argument("case", choices=sorted(CHECKS))
    one.add_argument("workspace", type=Path)
    one.add_argument("--text", type=Path, help="file holding the agent's final message")
    one.add_argument("--tools-root", type=Path, default=BENCH.parent)
    args = parser.parse_args()
    text = args.text.read_text() if args.text else ""
    print(json.dumps(score(args.case, args.workspace, text, args.tools_root), indent=1))


if __name__ == "__main__":
    main()
