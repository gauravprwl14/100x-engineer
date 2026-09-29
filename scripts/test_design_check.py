#!/usr/bin/env python3
"""Diff-scoped checks for test-CASE-SELECTION defects, not test-execution defects.

bloat_check.py already catches whether a test can fail at all (assertionless,
focused/skipped). This tool is downstream of that: it assumes the test runs and
asks whether the *cases chosen* are any good — determinism, naming as
specification, assertion count, boundary coverage, mock ownership, and the
refactor/behaviour-change conflation `skills/legacy-change` forbids.

Python tests are inspected with `ast` (exact). JS/TS/Go tests are inspected with
regexes bounded at the next test declaration (heuristic, same windowing
bloat_check.py's assertionless check uses) — stated explicitly per check below,
not left implicit.

    test_design_check.py                 # check staged+unstaged vs HEAD
    test_design_check.py --base origin/main
    test_design_check.py --only sleep,test-name
    test_design_check.py --strict         # advisory findings also fail

Exit 1 if any blocking check finds a violation (or any enabled check, --strict).
"""
import argparse, ast, json, os, pathlib, re, subprocess, sys

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt", ".swift"}
TEST_RX = re.compile(r"(^|/)(tests?|__tests__|spec)/|[._](test|spec)\.[a-z]+$|_test\.(go|py)$|^test_", re.I)

ASSERT_RX = re.compile(
    r"\b(assert\w*\s*\(|assert\s|expect\(|should\.|require\.|t\.Error|t\.Fatal|"
    r"assertEqual|assertTrue|toBe\(|toEqual\(|toThrow\(|verify\(|XCTAssert)")

MAX_ASSERTS = 4     # overridden by --max-asserts
MAX_FILES = 15       # overridden by --max-files


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed(base):
    """(added, modified) paths in the diff. Same shape as bloat_check.py's."""
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--name-status", "--diff-filter=AM"] + rng)
    added, mod = [], []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        (added if parts[0].startswith("A") else mod).append(parts[-1])
    for p in sh(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        if p and p not in added:
            added.append(p)
    return added, mod


def added_lines(path, base):
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--unified=0"] + rng + ["--", path])
    if not out:
        try:
            return pathlib.Path(path).read_text(errors="replace").splitlines()
        except OSError:
            return []
    return [l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]


def diff_pm_lines(path, base):
    """(added_lines, removed_lines) — the only check needing both sides (refactor-behaviour)."""
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--unified=0"] + rng + ["--", path])
    add_l, rem_l = [], []
    for l in out.splitlines():
        if l.startswith("+++") or l.startswith("---"):
            continue
        if l.startswith("+"):
            add_l.append(l[1:])
        elif l.startswith("-"):
            rem_l.append(l[1:])
    return add_l, rem_l


def local_names():
    """Best-effort set of 'this repo's own' top-level names, for the mock-ownership
    check. Directory names at the repo root, plus the root package.json `name`.
    Heuristic by construction -- a monorepo workspace package two levels down
    will not be recognised as local, which biases the check toward false
    positives there, not false negatives (see Failure modes in the skill)."""
    names = set()
    try:
        for e in os.listdir("."):
            if e.startswith(".") or e in {"node_modules", "dist", "build", "venv",
                                           ".venv", "__pycache__", "vendor"}:
                continue
            if os.path.isdir(e):
                names.add(e)
    except OSError:
        pass
    try:
        pkg = json.loads(pathlib.Path("package.json").read_text())
        n = pkg.get("name", "")
        if n:
            names.add(n.split("/")[-1])
    except Exception:
        pass
    return names


def test_blocks(path, src):
    """Yield (name, lineno, body, decorators) per test in one file.

    Python: ast-exact, any function whose name starts with 'test'.
    JS/TS/Go: regex, bounded at the NEXT test declaration -- a fixed-size window
    would bleed into the following test and mask a defect in this one (verified
    failure mode, see bloat_check.py's check_assertionless).
    """
    if path.endswith(".py"):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                body = ast.get_source_segment(src, node) or ""
                decos = " ".join(ast.get_source_segment(src, d) or "" for d in node.decorator_list)
                yield node.name, node.lineno, body, decos
        return
    decl = re.compile(
        r"^[ \t]*(?:async\s+)?(?:it|test)(?:\.\w+)?\s*\(\s*[\"'`]([^\"'`]{0,120})"
        r"|^func\s+(Test\w+)\s*\(", re.M)
    hits = list(decl.finditer(src))
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(src)
        body = src[m.end():end]
        name = (m.group(1) or m.group(2) or "?").strip()
        ln = src[:m.start()].count("\n") + 1
        yield name, ln, body, ""


# ---------------- checks ----------------

SLEEP_RX = re.compile(r"\btime\.sleep\s*\(|\basyncio\.sleep\s*\(|\bsetTimeout\s*\(|\bsetInterval\s*\("
                       r"|\bThread\.sleep\s*\(")
FAKE_TIMER_RX = re.compile(r"useFakeTimers|freeze_time|time_machine|FakeClock|fake_clock|setSystemTime")


def check_sleep(added, mod, base):
    """A real delay in a test is non-determinism: it is flaky under CI load and
    slows the suite for no signal. Python + JS/TS only -- `Thread.sleep` is
    included for Kotlin/Java test files but not otherwise inspected."""
    out = []
    for p in added + mod:
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        try:
            src = pathlib.Path(p).read_text(errors="replace")
        except OSError:
            continue
        if FAKE_TIMER_RX.search(src):
            continue  # clock is mocked/frozen in this file -- not real nondeterminism
        for name, ln, body, decos in test_blocks(p, src):
            if SLEEP_RX.search(body):
                out.append((f"{p}:{ln}",
                             f"test `{name}` sleeps / uses a real timer delay — flaky under "
                             f"load, slows the suite; inject a clock or fake the timer instead"))
    return out


TIME_RX = re.compile(r"\bdatetime\.now\(\)|\bdatetime\.utcnow\(\)|\btime\.time\(\)|\bDate\.now\(\)"
                      r"|\bnew Date\(\)(?!\.)")
FREEZE_RX = re.compile(r"freeze_time|time_machine|freezegun|setSystemTime|useFakeTimers"
                        r"|monkeypatch\.setattr\([^)]*(time|datetime)")


def check_realtime(added, mod, base):
    """The real clock in a test with no freeze/injection is a latent flake: it
    passes today and fails at a timezone boundary, a DST change, or under a slow
    CI runner. Advisory because a handful of legitimate uses exist (logging a
    timestamp with no assertion on it)."""
    out = []
    for p in added + mod:
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        try:
            src = pathlib.Path(p).read_text(errors="replace")
        except OSError:
            continue
        if FREEZE_RX.search(src):
            continue
        for name, ln, body, decos in test_blocks(p, src):
            if TIME_RX.search(body):
                out.append((f"{p}:{ln}",
                             f"test `{name}` reads the real clock with no freeze/injection — "
                             f"time-dependent flake waiting to happen"))
    return out


def check_assert_count(added, mod, base):
    """More than MAX_ASSERTS assertions in one test: the first failure stops the
    test, so every assertion after it is untested until the first is fixed —
    this hides later failures rather than reporting them."""
    out = []
    for p in added + mod:
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        try:
            src = pathlib.Path(p).read_text(errors="replace")
        except OSError:
            continue
        for name, ln, body, decos in test_blocks(p, src):
            n = len(ASSERT_RX.findall(body))
            if n > MAX_ASSERTS:
                out.append((f"{p}:{ln}",
                             f"test `{name}` has {n} assertions (>{MAX_ASSERTS}) — a failure in "
                             f"the first hides whether the rest would also fail; split by behaviour"))
    return out


PY_NUMBERED_RX = re.compile(r"^test_?\d+$")
PY_SINGLEWORD_RX = re.compile(r"^test_?[A-Z][a-z0-9]*$")   # 'testFoo', 'test_Add' -- one word, camelCase
JS_BAD_NAMES = {"works", "should work", "it works", "test", "ok", "success",
                "passes", "should pass", "works correctly", "test case"}
JS_NUMBERED_RX = re.compile(r"^\d+$|^test ?\d+$", re.I)


def check_test_names(added, mod, base):
    """A test name is the spec entry a reader sees in the test list. Python is
    exact (function name via ast). JS/TS is a small blocklist of known-vague
    phrases plus a numeric pattern -- deliberately narrow to avoid punishing
    legitimate short names, per the false-positive priority in this checker's
    tests. Go is NOT checked here: `TestAdd`-shaped names that name the unit
    under test, not a sentence, are the sanctioned convention
    (k3s-io/k3s:tests/TESTING.md), so flagging them would be a false positive
    against real production style, not a catch."""
    out = []
    for p in added + mod:
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        if p.endswith(".go"):
            continue
        try:
            src = pathlib.Path(p).read_text(errors="replace")
        except OSError:
            continue
        for name, ln, body, decos in test_blocks(p, src):
            if p.endswith(".py"):
                if name == "test" or PY_NUMBERED_RX.match(name) or PY_SINGLEWORD_RX.match(name):
                    out.append((f"{p}:{ln}",
                                 f"test name `{name}` does not describe a behaviour — "
                                 f"name it after what it verifies, not the function under test"))
            else:
                nm = name.strip().strip("'\"`").lower()
                if nm in JS_BAD_NAMES or JS_NUMBERED_RX.match(nm):
                    out.append((f"{p}:{ln}",
                                 f"test name '{name}' does not describe a behaviour — "
                                 f"name it after what it verifies"))
    return out


NUMERIC_ARG_RX = re.compile(r"\((?:[^()]*,)*\s*-?\d+(?:\.\d+)?\s*[,)]")
TABLE_DRIVEN_RX = re.compile(
    r"\]struct\s*\{|\bit\.each\s*\(|\btest\.each\s*\(|@pytest\.mark\.parametrize"
    r"|\btestCases\b|\bcases\s*:?=\s*\[|\btable\s*:?=\s*\[")


def check_single_value_boundary(added, mod, base):
    """Heuristic, advisory, stated honestly as low-precision: a newly ADDED test
    file (not a modified one — an existing file's shape wasn't this diff's
    choice) with exactly one test, no table-driven/parametrize marker anywhere
    in the file, and a numeric literal call argument in that one test. That
    shape is consistent with 'this bounded input was tested at one value' but
    is not proof — it cannot see whether a sibling boundary test lives in
    another file."""
    out = []
    for p in added:
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        try:
            src = pathlib.Path(p).read_text(errors="replace")
        except OSError:
            continue
        if TABLE_DRIVEN_RX.search(src):
            continue
        blocks = list(test_blocks(p, src))
        if len(blocks) != 1:
            continue
        name, ln, body, decos = blocks[0]
        if "parametrize" in decos:
            continue
        if NUMERIC_ARG_RX.search(body):
            out.append((f"{p}:{ln}",
                         f"only test in the file (`{name}`) exercises a numeric/sized input at "
                         f"one value — missing min/max/empty boundary siblings? (heuristic)"))
    return out


PY_MOCK_RX = re.compile(
    r"(?:mock\.patch(?:\.object)?|(?<![.\w])patch(?:\.object)?|monkeypatch\.setattr)"
    r"\s*\(\s*[\"']([\w\.]+)[\"']")
JS_MOCK_RX = re.compile(r"(?:jest|vi|sinon)\.mock\s*\(\s*[\"']([^\"']+)[\"']")
PY_STDLIB = {"os", "sys", "time", "datetime", "json", "re", "subprocess", "pathlib",
             "socket", "shutil", "tempfile", "logging", "threading", "asyncio",
             "collections", "itertools", "functools", "uuid", "hashlib", "random",
             "typing", "io", "copy", "contextlib", "enum", "dataclasses", "abc",
             "math", "string", "warnings"}
JS_BUILTIN = {"fs", "path", "os", "http", "https", "crypto", "url", "events",
              "stream", "util", "child_process", "net", "dns", "buffer", "assert",
              "querystring", "zlib"}


def check_mock_thirdparty(added, mod, base):
    """'Do not mock what you do not own' (skills/test-design). A mock of a
    dependency's internals couples the test to that dependency's implementation,
    not its contract; a version bump can pass the mocked test and break in
    production. Python: dotted path's top segment checked against the stdlib
    allowlist and the repo's own top-level directories. JS/TS: bare (non-relative)
    module specifier checked against Node builtins and local package names --
    both heuristics, both err toward flagging (see Failure modes)."""
    out = []
    locals_ = local_names()
    for p in added + mod:
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        for line in added_lines(p, base):
            if p.endswith(".py"):
                m = PY_MOCK_RX.search(line)
                if not m:
                    continue
                top = m.group(1).split(".")[0]
                if top in PY_STDLIB or top in locals_:
                    continue
                out.append((p, f"mocks third-party path `{m.group(1)}` — do not mock what you "
                               f"do not own; wrap it behind your own port and fake that instead"))
            else:
                m = JS_MOCK_RX.search(line)
                if not m:
                    continue
                spec = m.group(1)
                if spec.startswith((".", "/")):
                    continue
                top = spec.split("/")[0].lstrip("@")
                if top in JS_BUILTIN or top in locals_ or spec.split("/")[-1] in locals_:
                    continue
                out.append((p, f"mocks third-party module `{spec}` — do not mock what you do "
                               f"not own; wrap it behind your own port and fake that instead"))
    return out


SNAPSHOT_PATH_RX = re.compile(r"__snapshots__/|\.snap$|\.ambr$|\.approved\.\w+$|approved_files/")


def check_snapshot_same_diff(added, mod, base):
    """A snapshot recorded by the same diff as the code it approves proves
    nothing — it asserts 'the output is what the new code produces', which is
    true by construction. It only becomes evidence once a human reads it."""
    snap_files = [p for p in added + mod if SNAPSHOT_PATH_RX.search(p)]
    if not snap_files:
        return []
    prod_files = [p for p in added + mod
                  if p.endswith(tuple(CODE_EXT)) and not TEST_RX.search(p)
                  and not SNAPSHOT_PATH_RX.search(p)]
    if not prod_files:
        return []
    extra = f" (+{len(prod_files) - 1} more)" if len(prod_files) > 1 else ""
    return [(s, f"snapshot changed alongside production code ({prod_files[0]}{extra}) — a "
                f"snapshot written by the change it approves proves nothing; read it before accepting")
            for s in snap_files]


def check_refactor_and_behavior(added, mod, base):
    """Refactor and behaviour change in one commit is the single highest-value
    rule in skills/legacy-change — this is its mechanical half. A diff over
    MAX_FILES files where a MODIFIED test file's expected value changed at the
    same time as production logic changed is exactly that shape: too big to be
    'just a rename', and the test's own expectation moved, so it cannot be
    reviewed as 'behaviour preserved.'"""
    total = len(added) + len(mod)
    if total <= MAX_FILES:
        return []
    if not any(p.endswith(tuple(CODE_EXT)) and not TEST_RX.search(p) for p in added + mod):
        return []
    out = []
    for p in mod:  # only a MODIFIED test file has a prior expectation to compare against
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        add_l, rem_l = diff_pm_lines(p, base)
        if any(ASSERT_RX.search(l) for l in rem_l) and any(ASSERT_RX.search(l) for l in add_l):
            out.append((p, f"expected value changed in a {total}-file diff that also touches "
                           f"production logic — refactor and behaviour change in one commit? split them"))
    return out


CHECKS = {
    "sleep": check_sleep,
    "realtime": check_realtime,
    "assert-count": check_assert_count,
    "test-name": check_test_names,
    "single-value": check_single_value_boundary,
    "mock-thirdparty": check_mock_thirdparty,
    "snapshot-same-diff": check_snapshot_same_diff,
    "refactor-behavior": check_refactor_and_behavior,
}
# checks that need judgement, not a hard failure -- see skills/test-design and
# skills/legacy-change for what each protects against.
ADVISORY = {"realtime", "assert-count", "single-value", "mock-thirdparty",
            "snapshot-same-diff", "refactor-behavior"}


def main():
    global MAX_ASSERTS, MAX_FILES
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="compare against this ref (default: HEAD)")
    ap.add_argument("--only", default=None, help="comma-separated subset of checks")
    ap.add_argument("--strict", action="store_true", help="treat advisory checks as failures")
    ap.add_argument("--max-asserts", type=int, default=4, help="assert-count threshold (default 4)")
    ap.add_argument("--max-files", type=int, default=15, help="refactor-behavior file-count threshold")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    MAX_ASSERTS, MAX_FILES = a.max_asserts, a.max_files
    if a.list:
        for k in CHECKS:
            print(f"{k}{' (advisory)' if k in ADVISORY else ''}")
        return 0

    names = [n.strip() for n in a.only.split(",")] if a.only else list(CHECKS)
    bad = [n for n in names if n not in CHECKS]
    if bad:
        print(f"unknown check(s): {', '.join(bad)}", file=sys.stderr)
        return 2

    added, mod = changed(a.base)
    if not added and not mod:
        print("test_design_check: no changes to inspect")
        return 0

    hard = advisory = 0
    for n in names:
        try:
            res = CHECKS[n](added, mod, a.base)
        except Exception as e:
            print(f"  ! {n} errored: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if not res:
            continue
        adv = n in ADVISORY and not a.strict
        print(f"\n[{'ADVISORY' if adv else 'FAIL'}] {n}")
        for loc, msg in res[:12]:
            print(f"  {loc}: {msg}")
        if len(res) > 12:
            print(f"  ... {len(res) - 12} more")
        if adv:
            advisory += len(res)
        else:
            hard += len(res)

    print(f"\ntest_design_check: {len(added)} added, {len(mod)} modified | "
          f"{hard} blocking, {advisory} advisory")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
