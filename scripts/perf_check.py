#!/usr/bin/env python3
"""Diff-scoped checks for the performance shapes an LLM reliably produces.

Per skills/performance-budgets/SKILL.md, the plugin already gates bundle bytes
(typescript-verification) and binary bytes (mobile-release-safety). Neither catches
runtime cost: N+1 loops, unbounded queries, missing timeouts, unbounded
concurrency, or a heavy dependency slipped into a diff. This fills that gap,
scoped to the current diff so it is runnable on a large existing codebase.

Detection method, stated plainly because a heuristic that hides its own shape is
worse than none: **Python checks use `ast`** (structural, parses the real syntax
tree). **TS/JS checks are regex + brace/paren-counting heuristics** (no stdlib JS
parser exists) — they read the whole current file to resolve loop/call bodies
correctly, then discard any match whose line was not actually touched in this
diff, so a heuristic false match in unrelated code never surfaces.

    perf_check.py                 # check staged+unstaged vs HEAD
    perf_check.py --base origin/main
    perf_check.py --only n-plus-one,no-timeout
    perf_check.py --list

Exit 1 if any blocking (non-advisory) check finds a violation.
"""
import argparse, ast, os, re, subprocess, sys, pathlib

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs"}
DEP_FILES = {"package.json", "requirements.txt", "pyproject.toml", "Pipfile"}

# ---------------------------------------------------------------------------
# shared git helpers -- same shape as scripts/bloat_check.py, deliberately.
# ---------------------------------------------------------------------------

def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed(base):
    """(added, modified) paths in the diff."""
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
    """Content of '+' lines only, in diff order (may skip unchanged context)."""
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--unified=0"] + rng + ["--", path])
    if not out:
        try:
            return pathlib.Path(path).read_text(errors="replace").splitlines()
        except OSError:
            return []
    return [l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]


def added_line_numbers(path, base):
    """1-based new-file line numbers touched by this diff (from hunk headers).

    Lets a structural check parse the *whole* current file -- necessary to resolve
    a loop or call body correctly -- while still only reporting a match whose line
    was actually added or modified. A brand-new/untracked file counts every line.
    """
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--unified=0"] + rng + ["--", path])
    if not out:
        try:
            n = len(pathlib.Path(path).read_text(errors="replace").splitlines())
            return set(range(1, n + 1))
        except OSError:
            return set()
    nums = set()
    for line in out.splitlines():
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if m:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count == 0:
                continue
            nums.update(range(start, start + count))
    return nums


def read(path):
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except OSError:
        return None


def span_touched(lineno, end_lineno, touched):
    return any(n in touched for n in range(lineno, (end_lineno or lineno) + 1))


def capture_braces(text, open_idx):
    """text[open_idx] == '{' -> substring between it and its matching '}'."""
    depth, i = 0, open_idx
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], i
        i += 1
    return text[open_idx + 1:], len(text)


def capture_parens(text, open_idx):
    """text[open_idx] == '(' -> substring between it and its matching ')'."""
    depth, i = 0, open_idx
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], i
        i += 1
    return text[open_idx + 1:], len(text)


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


# ---------------------------------------------------------------------------
# N+1: await / DB call / HTTP call inside a loop  -- BLOCKING
# ---------------------------------------------------------------------------

PY_IO_RX = re.compile(
    r"\brequests\.(get|post|put|patch|delete)\s*\("
    r"|\bhttpx\.(get|post|put|patch|delete)\s*\("
    r"|\burlopen\s*\("
    r"|\.objects\.(get|filter|create|update|all)\s*\("
    r"|\bsession\.query\s*\("
    r"|\b(cursor|conn|connection|db|engine)\.execute\s*\("
    r"|\.find_one\s*\("
    r"|\.fetchone\s*\(|\.fetchall\s*\("
)

JS_LOOP_START_RX = re.compile(r"\bfor\s*\(|\bwhile\s*\(|\.(?:map|forEach)\s*\(")
PROMISE_ALL_WRAP_RX = re.compile(r"Promise\.all\s*\(\s*[\w.$\[\]]*\s*$")

JS_IO_RX = re.compile(
    r"\bawait\b"
    r"|\bfetch\s*\("
    r"|\baxios\.(get|post|put|patch|delete)\s*\("
    r"|\.findOne\s*\("
    r"|\bdb\.\w+\.(find|findOne|query)\s*\("
    r"|\.query\s*\("
    r"|\bhttp\.(get|post)\s*\("
)


def find_js_loop_bodies(src):
    """Yield (start_idx, receiver_text, body_text) for each for/while/.map/.forEach.

    `receiver_text` is the loop header's paren content for for/while (so
    `of db.users.find({})` is visible), or the expression just before `.map(`/
    `.forEach(` for those (so `db.users.find({}).forEach(...)` is visible).
    Parens are balanced with capture_parens rather than matched with a single
    regex, so a header containing its own object literal (`for (const r of
    db.users.find({})) {`) does not break header/body detection -- a fixed-shape
    regex was tried first and undercounted exactly this case.
    """
    for m in JS_LOOP_START_RX.finditer(src):
        is_map = m.group(0).lstrip().startswith(".")
        if is_map and PROMISE_ALL_WRAP_RX.search(src[max(0, m.start() - 40):m.start()]):
            continue  # Promise.all(items.map(...)) is the bounded-concurrency fix,
            # not the sequential N+1 shape this check targets.
        open_idx = src.find("(", m.start())
        if open_idx == -1:
            continue
        args, end_idx = capture_parens(src, open_idx)
        if is_map:
            line_start = src.rfind("\n", 0, m.start()) + 1
            receiver = src[max(line_start, m.start() - 80):m.start()]
            yield m.start(), receiver, args
            continue
        # for(...) / while(...): body is the braced block right after the header.
        j = end_idx + 1
        while j < len(src) and src[j] in " \t\n":
            j += 1
        if j >= len(src) or src[j] != "{":
            continue
        body, _ = capture_braces(src, j)
        yield m.start(), args, body


def check_n_plus_one(added, mod, base):
    out = []
    for p in added + mod:
        ext = pathlib.Path(p).suffix
        if ext not in CODE_EXT:
            continue
        src = read(p)
        if src is None:
            continue
        touched = added_line_numbers(p, base)
        if not touched:
            continue
        if ext == ".py":
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                    continue
                if not span_touched(node.lineno, node.end_lineno, touched):
                    continue
                seg = ast.get_source_segment(src, node) or ""
                if re.search(r"\bawait\b", seg):
                    out.append((f"{p}:{node.lineno}",
                                "await inside a loop -- sequential per-iteration "
                                "I/O (N+1 shape); batch, prefetch, or gather instead"))
                elif PY_IO_RX.search(seg):
                    m = PY_IO_RX.search(seg)
                    out.append((f"{p}:{node.lineno}",
                                f"call matching `{m.group(0).strip('(')}` inside a "
                                "loop -- likely N+1; batch or prefetch"))
        else:
            for start, _receiver, body in find_js_loop_bodies(src):
                lineno = line_of(src, start)
                if not span_touched(lineno, lineno + body.count("\n"), touched):
                    continue
                if re.search(r"\bawait\b", body):
                    out.append((f"{p}:{lineno}",
                                "await inside a loop/.map -- sequential N+1 shape; "
                                "batch or Promise.all a bounded chunk instead"))
                else:
                    m = JS_IO_RX.search(body)
                    if m:
                        out.append((f"{p}:{lineno}",
                                    f"call matching `{m.group(0)}` inside a loop -- "
                                    "likely N+1; batch or prefetch"))
    return out


# ---------------------------------------------------------------------------
# unbounded query on a list endpoint / repository method -- advisory
# ---------------------------------------------------------------------------

QUERY_RX = re.compile(
    r"\bSELECT\b[^;]*\bFROM\b"
    r"|\.objects\.all\(\)"
    r"|\bfind_all\(|findAll\(|findMany\(|\.all\(\)"
    r"|\.find\(\s*\{",  # mongo-style filter object -- excludes bare Array.find(x=>..)
    re.I,
)
LIMIT_RX = re.compile(r"\blimit\b|\btake\(|\bfirst\(|\bLIMIT\b|\[:\d|\bslice\(0", re.I)


def check_unbounded_query(added, mod, base):
    out = []
    for p in added + mod:
        if pathlib.Path(p).suffix not in CODE_EXT | {".sql"}:
            continue
        lines = added_lines(p, base)
        for i, line in enumerate(lines):
            if not QUERY_RX.search(line):
                continue
            window = "\n".join(lines[i:i + 4])
            if not LIMIT_RX.search(window):
                out.append((p, f"query with no limit/take/first nearby: "
                               f"{line.strip()[:70]}"))
    return out


# ---------------------------------------------------------------------------
# hot-path sort/filter over a just-fetched unbounded collection -- advisory
# ---------------------------------------------------------------------------

SORT_RX = re.compile(
    r"\.sort\(|\.sorted\(|\.sort_values\(|sort_by\(|\bsorted\(|\.filter\(", re.I)


def check_hot_path_sort(added, mod, base):
    out = []
    for p in added + mod:
        if pathlib.Path(p).suffix not in CODE_EXT:
            continue
        lines = added_lines(p, base)
        for i, line in enumerate(lines):
            if not QUERY_RX.search(line):
                continue
            window_lines = lines[i:i + 8]
            window = "\n".join(window_lines)
            if LIMIT_RX.search(window):
                continue  # already bounded -- not this check's concern
            tail = "\n".join(window_lines[1:])
            if SORT_RX.search(tail):
                out.append((p, "sort/filter runs in application code over a "
                               f"just-fetched unbounded collection: {line.strip()[:60]}"))
    return out


# ---------------------------------------------------------------------------
# SELECT * -- advisory
# ---------------------------------------------------------------------------

SELECT_STAR_RX = re.compile(r"select\s+\*\s+from", re.I)


def check_select_star(added, mod, base):
    out = []
    for p in added + mod:
        if pathlib.Path(p).suffix not in CODE_EXT | {".sql"}:
            continue
        for line in added_lines(p, base):
            if SELECT_STAR_RX.search(line):
                out.append((p, f"SELECT * -- {line.strip()[:70]}"))
    return out


# ---------------------------------------------------------------------------
# HTTP client call with no timeout -- BLOCKING
# ---------------------------------------------------------------------------

PY_HTTP_CALL_RX = re.compile(
    r"\b(?:requests|httpx)\.(?:get|post|put|patch|delete)\s*\("
    r"|\brequests\.Session\s*\(\s*\)"
    r"|\bhttpx\.Client\s*\("
)
JS_HTTP_CALL_RX = re.compile(
    r"\bfetch\s*\("
    r"|\baxios\.(?:get|post|put|patch|delete)\s*\("
    r"|\baxios\.create\s*\("
)
TIMEOUT_TOKEN_RX = re.compile(r"timeout|AbortController|signal\s*[:=]", re.I)


def check_no_timeout(added, mod, base):
    out = []
    for p in added + mod:
        ext = pathlib.Path(p).suffix
        if ext not in CODE_EXT:
            continue
        src = read(p)
        if src is None:
            continue
        touched = added_line_numbers(p, base)
        if not touched:
            continue
        rx = PY_HTTP_CALL_RX if ext == ".py" else JS_HTTP_CALL_RX
        for m in rx.finditer(src):
            open_idx = src.find("(", m.start())
            if open_idx == -1:
                continue
            args, end_idx = capture_parens(src, open_idx)
            lineno = line_of(src, m.start())
            end_lineno = line_of(src, end_idx)
            if not span_touched(lineno, end_lineno, touched):
                continue
            if not TIMEOUT_TOKEN_RX.search(args):
                out.append((f"{p}:{lineno}",
                            f"`{m.group(0).rstrip('(').strip()}(...)` has no timeout "
                            "-- an unstated timeout is a contract the client invents"))
    return out


# ---------------------------------------------------------------------------
# unbounded in-memory accumulation over a query-result loop -- advisory
# ---------------------------------------------------------------------------

PY_ITER_QUERY_RX = re.compile(
    r"\.objects\.(all|filter)\s*\("
    r"|\.fetchall\s*\("
    r"|session\.query\s*\("
    r"|\.find\s*\(\s*\{"
)
JS_ITER_QUERY_RX = re.compile(
    r"\bdb\.\w+\.find\s*\(|\.query\s*\(|\.findAll\s*\(|\.all\s*\("
)
CAP_GUARD_RX = re.compile(r"\bbreak\b|\blen\(\w+\)\s*[<>]=?|MAX_|\.slice\(0", re.I)


def check_unbounded_accumulation(added, mod, base):
    out = []
    for p in added + mod:
        ext = pathlib.Path(p).suffix
        if ext not in CODE_EXT:
            continue
        src = read(p)
        if src is None:
            continue
        touched = added_line_numbers(p, base)
        if not touched:
            continue
        if ext == ".py":
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.For, ast.AsyncFor)):
                    continue
                if not span_touched(node.lineno, node.end_lineno, touched):
                    continue
                iter_seg = ast.get_source_segment(src, node.iter) or ""
                if not PY_ITER_QUERY_RX.search(iter_seg):
                    continue
                body_seg = ast.get_source_segment(src, node) or ""
                if ".append(" not in body_seg:
                    continue
                if CAP_GUARD_RX.search(body_seg):
                    continue
                out.append((f"{p}:{node.lineno}",
                            "unbounded accumulation: appends every row of a "
                            "query-result loop with no cap or break"))
        else:
            for start, receiver, body in find_js_loop_bodies(src):
                if not JS_ITER_QUERY_RX.search(receiver):
                    continue
                if ".push(" not in body:
                    continue
                if CAP_GUARD_RX.search(body):
                    continue
                lineno = line_of(src, start)
                if not span_touched(lineno, lineno + body.count("\n"), touched):
                    continue
                out.append((f"{p}:{lineno}",
                            "unbounded accumulation: pushes every row of a "
                            "query-result loop with no cap or break"))
    return out


# ---------------------------------------------------------------------------
# Promise.all / asyncio.gather over an unbounded collection -- advisory
# ---------------------------------------------------------------------------

BOUNDED_TOKEN_RX = re.compile(
    r"chunk\(|batch\(|pLimit\(|p-limit|Semaphore\(|concurrency|\.slice\(0", re.I)


def check_unbounded_concurrency(added, mod, base):
    out = []
    for p in added + mod:
        ext = pathlib.Path(p).suffix
        if ext not in CODE_EXT:
            continue
        src = read(p)
        if src is None:
            continue
        touched = added_line_numbers(p, base)
        if not touched:
            continue
        if ext == ".py":
            rx = re.compile(r"asyncio\.gather\s*\(")
            shape_ok = lambda args: re.search(r"\bfor\s+\w+\s+in\b", args)
        else:
            rx = re.compile(r"Promise\.all\s*\(")
            shape_ok = lambda args: ".map(" in args
        for m in rx.finditer(src):
            open_idx = src.find("(", m.start())
            if open_idx == -1:
                continue
            args, end_idx = capture_parens(src, open_idx)
            if not shape_ok(args):
                continue
            if BOUNDED_TOKEN_RX.search(args):
                continue
            lineno = line_of(src, m.start())
            end_lineno = line_of(src, end_idx)
            if not span_touched(lineno, end_lineno, touched):
                continue
            fn = "asyncio.gather" if ext == ".py" else "Promise.all"
            out.append((f"{p}:{lineno}",
                        f"{fn} over an unbounded collection -- fan-out with no "
                        "concurrency limit; one slow/failing item blocks or "
                        "amplifies load on every downstream call"))
    return out


# ---------------------------------------------------------------------------
# new heavy dependency -- advisory
# ---------------------------------------------------------------------------

# A small, grounded list -- not exhaustive. See skills/performance-budgets/SKILL.md
# Sources for citations; entries marked "SOURCE: original" are common-knowledge
# package-size facts not independently re-measured in this session.
HEAVY_DEPS = {
    "moment": "legacy, in maintenance mode, ~70KB min -- prefer dayjs (~2KB) or date-fns "
              "(moment/moment:README.md)",
    "puppeteer": "downloads a full Chromium/Chrome binary at install time unless "
                 "puppeteer-core is used (puppeteer/puppeteer:README.md)",
    "lodash": "~70KB min if imported whole -- prefer lodash-es or per-function imports "
              "(SOURCE: original)",
    "aws-sdk": "monolithic v2 SDK, tens of MB -- prefer modular @aws-sdk/client-* v3 "
               "packages (SOURCE: original)",
    "pandas": "large compiled dependency surface (pulls in numpy) -- heavy for a "
              "lightweight service or function (SOURCE: original)",
    "torch": "hundreds of MB to multi-GB depending on CUDA build (SOURCE: original)",
    "tensorflow": "hundreds of MB to multi-GB depending on build (SOURCE: original)",
    "selenium": "drives a full browser -- heavy for CI and cold start (SOURCE: original)",
}


def check_heavy_dependency(added, mod, base):
    out = []
    for p in added + mod:
        name = os.path.basename(p)
        if name not in DEP_FILES:
            continue
        for line in added_lines(p, base):
            for dep, note in HEAVY_DEPS.items():
                if (re.search(rf'"{re.escape(dep)}"\s*:\s*"', line)
                        or re.match(rf'^\s*{re.escape(dep)}\s*[=<>!~\[]', line)):
                    out.append((p, f"new dependency `{dep}` has a large footprint -- {note}"))
    return out


CHECKS = {
    "n-plus-one": check_n_plus_one,
    "unbounded-query": check_unbounded_query,
    "hot-path-sort": check_hot_path_sort,
    "select-star": check_select_star,
    "no-timeout": check_no_timeout,
    "unbounded-accumulation": check_unbounded_accumulation,
    "unbounded-concurrency": check_unbounded_concurrency,
    "heavy-dependency": check_heavy_dependency,
}
# checks that need human judgement to confirm -- non-blocking by default
ADVISORY = {
    "unbounded-query", "hot-path-sort", "select-star",
    "unbounded-accumulation", "unbounded-concurrency", "heavy-dependency",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="compare against this ref (default: HEAD)")
    ap.add_argument("--only", default=None, help="comma-separated subset of checks")
    ap.add_argument("--strict", action="store_true", help="treat advisory checks as failures")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
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
        print("perf_check: no changes to inspect")
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
            print(f"  ... {len(res)-12} more")
        if adv:
            advisory += len(res)
        else:
            hard += len(res)

    print(f"\nperf_check: {len(added)} added, {len(mod)} modified | "
          f"{hard} blocking, {advisory} advisory")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
