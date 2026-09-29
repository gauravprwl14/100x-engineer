#!/usr/bin/env python3
"""Diff-scoped checks for code SHAPE -- naming, function size, nesting, coupling,
primitive obsession. Complements bloat_check.py (which covers diff VOLUME) and
does not duplicate it: nothing here counts files or diff size.

Python is checked with `ast` (exact). TypeScript/JavaScript is checked with
regex + a hand-rolled brace/string scanner (heuristic -- no real parser).
Each check function says which it is. Heuristics under-count on purpose where
precision is unclear (a missed violation is cheap; a false positive is what
gets a tool like this deleted).

Grounded thresholds (full citations in reviewers/_code-craft.md):
  function length    default 60, advisory  -- google/styleguide pyguide.md
                      section 3.18 gives a SOFT ~40-line prompt ("no hard
                      limit... think about it"); ESLint's own documented
                      default for max-lines-per-function is 50, but it ships
                      OFF in airbnb/javascript; rust-clippy's
                      too-many-lines-threshold defaults to 100 and IS
                      enforced by inheritance in zed-industries/zed (its
                      clippy.toml does not override it). 60 sits inside that
                      40-100 range.
  parameter count     default 5, advisory  -- ESLint max-params documented
                      default 3, OFF in airbnb/javascript AND facebook/react's
                      own .eslintrc.js; rust-clippy too-many-arguments-threshold
                      defaults to 7, enforced by inheritance in zed. 5 splits
                      the 3-7 range found.
  nesting depth       default 4, advisory  -- ESLint max-depth documented
                      default 4, OFF in airbnb/javascript and facebook/react;
                      rust-clippy's excessive-nesting-threshold defaults to 0,
                      i.e. DISABLED unless a project opts in (zed does not).
                      4 is the only live number found in the surveyed set.
  demeter chain depth default 3 dots, advisory  -- SOURCE: original. No
                      surveyed repo (google/styleguide, airbnb/javascript,
                      eslint-config-airbnb-base, facebook/react's .eslintrc,
                      golangci-lint configs for grafana/prometheus, rust-clippy)
                      enforces Law-of-Demeter chain depth mechanically.
  vague identifiers   advisory  -- SOURCE: original stoplist. Grounded in
                      google/styleguide pyguide.md 3.16.1 ("descriptiveness
                      should be proportional to the name's scope"), but no
                      repo enforces a stoplist: airbnb/javascript explicitly
                      disables the one ESLint rule built for this
                      (`id-denylist: 'off'`, eslint-config-airbnb-base
                      rules/style.js).
  money-as-float      advisory  -- SOURCE: original. No linter in the
                      surveyed set checks this; it is a fintech-specific
                      correctness practice (binary floats cannot represent
                      decimal currency exactly), not a style-guide rule.
  boolean flag arg    advisory  -- SOURCE: original. No surveyed repo's lint
                      config flags a literal boolean at a call site.
  bare except/catch   BLOCKING  -- mechanical, near-zero legitimate use,
                      same bar as bloat_check.py's assertionless-test check.

    craft_check.py                          # all checks vs HEAD
    craft_check.py --base origin/main
    craft_check.py --only vague-names,bare-except
    craft_check.py --strict                 # advisory findings also fail
    craft_check.py --func-len 80 --params 6 --depth 5 --demeter-depth 4

Exit 1 if any BLOCKING check finds a violation (or any check, under --strict).
"""
import argparse, ast, os, re, subprocess, sys, pathlib

PY_EXT = (".py",)
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
CODE_EXT = PY_EXT + JS_EXT
TEST_RX = re.compile(r"(^|/)(tests?|__tests__|spec)/|[._](test|spec)\.[a-z]+$|_test\.(go|py)$|^test_", re.I)

MONEY_WORDS = ("price", "amount", "total", "balance", "cost", "fee")
VAGUE_RX = re.compile(r"^(data|info|manager|helper|util|temp|obj|val|thing|stuff|handle|process|res)\d*$", re.I)
PY_KEYWORD_SKIP = {"self", "cls"}
LOGGING_NAME_RX = re.compile(r"(log|logger|logging|print|console|warn|debug)", re.I)

DEFAULTS = dict(func_len=60, params=5, depth=4, demeter=3)


# ---------------- shared helpers (diff plumbing, mirrors bloat_check.py) ----------------

def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed(base):
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


def touched_lines(path, base):
    """Line numbers (new-file numbering) this diff added. None means 'treat the
    whole file as touched' -- true for a brand-new/untracked file, and the safe
    default if git can't produce a diff at all."""
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--unified=0"] + rng + ["--", path])
    if not out:
        return None
    lines = set()
    for l in out.splitlines():
        if l.startswith("@@"):
            m = re.search(r"\+(\d+)(?:,(\d+))?", l)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                lines |= set(range(start, start + count))
    return lines


def overlaps(touched, start, end):
    if touched is None:
        return True
    return any(ln in touched for ln in range(start, end + 1))


def read(path):
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except OSError:
        return None


def is_py(p):
    return p.endswith(PY_EXT)


def is_js(p):
    return p.endswith(JS_EXT)


def split_top_level(s, seps=","):
    """Split on top-level commas, respecting (), [], {}, <>."""
    parts, depth, cur = [], 0, ""
    for c in s:
        if c in "([{<":
            depth += 1
        elif c in ")]}>":
            depth -= 1
        if c in seps and depth <= 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    if cur.strip():
        parts.append(cur)
    return [p for p in parts if p.strip()]


def vague_match(name):
    return bool(name) and VAGUE_RX.fullmatch(name.strip())


MONEY_SAFE_HINTS = ("cent", "minor", "subunit", "micros", "milli")


def looks_like_money(name):
    """A money-shaped identifier name -- but not one that already signals an
    integer minor unit (`totalCents`, `amount_minor`), which is the correct
    pattern this check exists to push people toward."""
    n = name.lower()
    if any(h in n for h in MONEY_SAFE_HINTS):
        return False
    return any(w in n for w in MONEY_WORDS)


# ---------------- JS/TS heuristic engine ----------------

RX_FUNC_DECL = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\(([^)]*)\)\s*[^{]*\{")
RX_ARROW = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?\(([^)]*)\)\s*(?::[^{=]+)?=>\s*\{")
RX_METHOD = re.compile(r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+|readonly\s+|get\s+|set\s+)*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::[^{]+)?\{")
JS_CONTROL_WORDS = {"if", "for", "while", "switch", "catch", "function", "return", "else", "do", "try", "finally"}


def scan_matching_brace(text, open_idx):
    """Index of the '}' matching the '{' at open_idx, skipping string/comment
    content on a best-effort basis (no real lexer)."""
    depth, i, n, state = 0, open_idx, len(text), None
    while i < n:
        c = text[i]
        if state == "//":
            if c == "\n":
                state = None
        elif state == "/*":
            if c == "*" and text[i + 1:i + 2] == "/":
                state = None
                i += 1
        elif state in ("'", '"', "`"):
            if c == "\\":
                i += 1
            elif c == state:
                state = None
        else:
            if c == "/" and text[i + 1:i + 2] == "/":
                state = "//"
                i += 1
            elif c == "/" and text[i + 1:i + 2] == "*":
                state = "/*"
                i += 1
            elif c in ("'", '"', "`"):
                state = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return n - 1


def js_functions(text):
    """Heuristic function finder: regex spots a declaration line, then a brace
    scanner finds the body end. Misses one-liner arrow functions with no block
    body (`const f = x => x + 1`) by design -- those have no shape to check."""
    lines = text.splitlines(keepends=True)
    offsets, off = [], 0
    for l in lines:
        offsets.append(off)
        off += len(l)
    out = []
    for ln, line in enumerate(lines, 1):
        stripped = line.strip()
        m = RX_FUNC_DECL.match(line) or RX_ARROW.match(line)
        name = params = None
        if m:
            name, params = m.group(1), m.group(2)
        else:
            m2 = RX_METHOD.match(line)
            first_word = re.match(r"[A-Za-z_$][\w$]*", stripped)
            if m2 and m2.group(1) not in JS_CONTROL_WORDS and not (first_word and first_word.group(0) in JS_CONTROL_WORDS):
                m, name, params = m2, m2.group(1), m2.group(2)
        if not m or name is None:
            continue
        brace_pos = m.group(0).rfind("{")
        if brace_pos == -1:
            continue
        open_idx = offsets[ln - 1] + brace_pos
        close_idx = scan_matching_brace(text, open_idx)
        end_line = text.count("\n", 0, close_idx) + 1
        out.append(dict(name=name, params=params or "", start=ln, end=end_line,
                         body=text[open_idx + 1:close_idx], indent=len(line) - len(line.lstrip(" \t"))))
    return out


CTRL_BEFORE_BRACE = re.compile(r"\b(?:if|for|while|switch|catch)\s*\([^{]*\)\s*$|\b(?:else|try|finally|do)\s*$")


def js_max_nesting(body):
    """Depth of control-flow blocks only (if/for/while/switch/catch/else), not
    plain blocks or object literals -- tracked by checking, at each '{', whether
    the ~200 chars before it end in a control-flow header."""
    depth = max_depth = 0
    stack = []
    i, n, state = 0, len(body), None
    while i < n:
        c = body[i]
        if state == "//":
            if c == "\n":
                state = None
        elif state == "/*":
            if c == "*" and body[i + 1:i + 2] == "/":
                state = None
                i += 1
        elif state in ("'", '"', "`"):
            if c == "\\":
                i += 1
            elif c == state:
                state = None
        else:
            if c == "/" and body[i + 1:i + 2] == "/":
                state = "//"
                i += 1
            elif c == "/" and body[i + 1:i + 2] == "*":
                state = "/*"
                i += 1
            elif c in ("'", '"', "`"):
                state = c
            elif c == "{":
                window = body[max(0, i - 200):i]
                is_ctrl = bool(CTRL_BEFORE_BRACE.search(window))
                stack.append(is_ctrl)
                if is_ctrl:
                    depth += 1
                    max_depth = max(max_depth, depth)
            elif c == "}":
                if stack and stack.pop():
                    depth -= 1
        i += 1
    return max_depth


# ---------------- Python (ast) helpers ----------------

PY_COMPOUND = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)


def py_funcs(tree):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def py_max_nesting(node, depth=0):
    best = depth
    for child in ast.iter_child_nodes(node):
        nxt = depth + 1 if isinstance(child, PY_COMPOUND) else depth
        best = max(best, py_max_nesting(child, nxt))
    return best


def py_param_count(node):
    a = node.args
    names = [x.arg for x in a.posonlyargs + a.args]
    n = len(names) + len(a.kwonlyargs) + (1 if a.vararg else 0) + (1 if a.kwarg else 0)
    if names and names[0] in PY_KEYWORD_SKIP:
        n -= 1
    return n


def py_param_names(node):
    a = node.args
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs if x.arg not in PY_KEYWORD_SKIP]


def parse_py(path):
    src = read(path)
    if src is None:
        return None, None
    try:
        return ast.parse(src), src
    except SyntaxError:
        return None, src


# ---------------- checks ----------------

def check_function_length(added, mod, base, threshold):
    out = []
    for p in added + mod:
        touched = touched_lines(p, base)
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is None:
                continue
            for fn in py_funcs(tree):
                length = (fn.end_lineno or fn.lineno) - fn.lineno + 1
                if length > threshold and overlaps(touched, fn.lineno, fn.end_lineno or fn.lineno):
                    out.append((f"{p}:{fn.lineno}", f"function `{fn.name}` is {length} lines (> {threshold})"))
        elif is_js(p):
            text = read(p)
            if text is None:
                continue
            for fn in js_functions(text):
                length = fn["end"] - fn["start"] + 1
                if length > threshold and overlaps(touched, fn["start"], fn["end"]):
                    out.append((f"{p}:{fn['start']}", f"function `{fn['name']}` is {length} lines (> {threshold})"))
    return out


def check_param_count(added, mod, base, threshold):
    out = []
    for p in added + mod:
        touched = touched_lines(p, base)
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is None:
                continue
            for fn in py_funcs(tree):
                n = py_param_count(fn)
                if n > threshold and overlaps(touched, fn.lineno, fn.lineno):
                    out.append((f"{p}:{fn.lineno}",
                                f"`{fn.name}` takes {n} parameters (> {threshold}) -- consider a parameter object"))
        elif is_js(p):
            text = read(p)
            if text is None:
                continue
            for fn in js_functions(text):
                n = len(split_top_level(fn["params"]))
                if n > threshold and overlaps(touched, fn["start"], fn["start"]):
                    out.append((f"{p}:{fn['start']}",
                                f"`{fn['name']}` takes {n} parameters (> {threshold}) -- consider a parameter object"))
    return out


def check_nesting_depth(added, mod, base, threshold):
    out = []
    for p in added + mod:
        touched = touched_lines(p, base)
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is None:
                continue
            for fn in py_funcs(tree):
                d = py_max_nesting(fn)
                if d > threshold and overlaps(touched, fn.lineno, fn.end_lineno or fn.lineno):
                    out.append((f"{p}:{fn.lineno}", f"`{fn.name}` nests {d} levels deep (> {threshold})"))
        elif is_js(p):
            text = read(p)
            if text is None:
                continue
            for fn in js_functions(text):
                d = js_max_nesting(fn["body"])
                if d > threshold and overlaps(touched, fn["start"], fn["end"]):
                    out.append((f"{p}:{fn['start']}", f"`{fn['name']}` nests {d} levels deep (> {threshold})"))
    return out


CALL_START = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
NOT_A_CALL_NAME = {"if", "for", "while", "switch", "catch", "function", "return", "def", "class",
                    "elif", "except", "with", "lambda", "print"}
BOOL_LITERAL = re.compile(r"^(True|False|true|false)$")


def find_calls(text):
    for m in CALL_START.finditer(text):
        name = m.group(1)
        if name in NOT_A_CALL_NAME:
            continue
        start, depth, i, n = m.end(), 1, m.end(), len(text)
        while i < n and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        args = text[start:i - 1]
        line_no = text.count("\n", 0, m.start()) + 1
        yield name, args, line_no


def check_boolean_flag_arg(added, mod, base):
    out = []
    for p in added + mod:
        if not p.endswith(CODE_EXT) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        seen_lines = set()
        for name, args, ln in find_calls(text):
            if ln in seen_lines or (touched is not None and ln not in touched):
                continue
            for part in split_top_level(args):
                if BOOL_LITERAL.match(part.strip()):
                    out.append((f"{p}:{ln}",
                                f"boolean literal passed positionally to `{name}(...)` -- "
                                f"name the parameter (keyword arg) or split into two calls"))
                    seen_lines.add(ln)
                    break
    return out


def check_bare_except(added, mod, base):
    out = []
    for p in added + mod:
        touched = touched_lines(p, base)
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if not overlaps(touched, node.lineno, node.lineno):
                    continue
                stmts = node.body
                has_raise = any(isinstance(s, ast.Raise) for s in ast.walk(node))
                if has_raise:
                    continue
                only_pass = len(stmts) == 1 and isinstance(stmts[0], ast.Pass)
                only_log = len(stmts) == 1 and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Call) \
                    and LOGGING_NAME_RX.search(ast.dump(stmts[0].value.func))
                if only_pass or only_log:
                    out.append((f"{p}:{node.lineno}", "except block swallows the error (no raise) -- "
                                                       "empty or log-only, same failure mode as bloat_check's assertionless test"))
        elif is_js(p):
            text = read(p)
            if text is None:
                continue
            for m in re.finditer(r"catch\s*(?:\([^)]*\))?\s*\{", text):
                open_idx = m.end() - 1
                close_idx = scan_matching_brace(text, open_idx)
                body = text[open_idx + 1:close_idx].strip()
                ln = text.count("\n", 0, m.start()) + 1
                if not overlaps(touched, ln, ln):
                    continue
                if "throw" in body:
                    continue
                stmts = [s for s in body.split(";") if s.strip()]
                is_empty = body == ""
                is_log_only = len(stmts) <= 1 and bool(LOGGING_NAME_RX.search(body)) and body != ""
                if is_empty or is_log_only:
                    out.append((f"{p}:{ln}", "catch block swallows the error (no throw) -- "
                                              "empty or log-only, same failure mode as bloat_check's assertionless test"))
    return out


def check_vague_names(added, mod, base):
    out = []
    for p in added + mod:
        touched = touched_lines(p, base)
        seen = set()
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is None:
                continue
            for node in ast.walk(tree):
                candidates = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    candidates.append((node.name, node.lineno, "function"))
                    for pname in py_param_names(node):
                        candidates.append((pname, node.lineno, "parameter"))
                elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    candidates.append((node.targets[0].id, node.lineno, "variable"))
                for name, ln, kind in candidates:
                    key = (ln, name)
                    if vague_match(name) and overlaps(touched, ln, ln) and key not in seen:
                        seen.add(key)
                        out.append((f"{p}:{ln}", f"{kind} named `{name}` -- reveal intent instead of a generic noun"))
        elif is_js(p):
            text = read(p)
            if text is None:
                continue
            for m in re.finditer(r"\b(?:const|let|var|function)\s+(\w+)", text):
                name = m.group(1)
                ln = text.count("\n", 0, m.start()) + 1
                key = (ln, name)
                if vague_match(name) and overlaps(touched, ln, ln) and key not in seen:
                    seen.add(key)
                    out.append((f"{p}:{ln}", f"declaration named `{name}` -- reveal intent instead of a generic noun"))
            for fn in js_functions(text):
                for raw in split_top_level(fn["params"]):
                    pname = re.split(r"[:=]", raw.strip())[0].strip().lstrip("...").strip()
                    key = (fn["start"], pname)
                    if vague_match(pname) and overlaps(touched, fn["start"], fn["start"]) and key not in seen:
                        seen.add(key)
                        out.append((f"{p}:{fn['start']}", f"parameter named `{pname}` in `{fn['name']}` -- reveal intent"))
    return out


def check_money_as_float(added, mod, base):
    out = []
    for p in added + mod:
        touched = touched_lines(p, base)
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                        if arg.annotation is not None and isinstance(arg.annotation, ast.Name) \
                           and arg.annotation.id == "float" and looks_like_money(arg.arg):
                            if overlaps(touched, node.lineno, node.lineno):
                                out.append((f"{p}:{node.lineno}",
                                            f"parameter `{arg.arg}` is typed `float` -- use an int minor-unit "
                                            f"(cents) or a Money type for currency"))
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                        and isinstance(node.annotation, ast.Name) and node.annotation.id == "float" \
                        and looks_like_money(node.target.id):
                    if overlaps(touched, node.lineno, node.lineno):
                        out.append((f"{p}:{node.lineno}",
                                    f"`{node.target.id}` is typed `float` -- use an int minor-unit or a Money type"))
        elif is_js(p):
            text = read(p)
            if text is None:
                continue
            for m in re.finditer(r"\b(\w+)\s*:\s*number\b", text):
                name = m.group(1)
                ln = text.count("\n", 0, m.start()) + 1
                if looks_like_money(name) and overlaps(touched, ln, ln):
                    out.append((f"{p}:{ln}", f"`{name}` is typed `number` -- use an integer minor-unit or a "
                                              f"Money type for currency"))
    return out


def check_demeter_chain(added, mod, base, min_dots):
    out = []
    rx = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){%d,}\(" % min_dots)
    for p in added + mod:
        if not p.endswith(CODE_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        seen_lines = set()
        for m in rx.finditer(text):
            ln = text.count("\n", 0, m.start()) + 1
            if ln in seen_lines or (touched is not None and ln not in touched):
                continue
            seen_lines.add(ln)
            chain = m.group(0)[:-1]
            out.append((f"{p}:{ln}", f"chain `{chain}(...)` reaches through {min_dots + 1} collaborators "
                                      f"-- Law of Demeter (advisory: could be a fluent builder)"))
    return out


BLOCKING = {"bare-except"}


def build_checks(args):
    return {
        "function-length": lambda a, m, b: check_function_length(a, m, b, args.func_len),
        "param-count": lambda a, m, b: check_param_count(a, m, b, args.params),
        "nesting-depth": lambda a, m, b: check_nesting_depth(a, m, b, args.depth),
        "boolean-flag-arg": check_boolean_flag_arg,
        "bare-except": check_bare_except,
        "vague-names": check_vague_names,
        "money-as-float": check_money_as_float,
        "demeter-chain": lambda a, m, b: check_demeter_chain(a, m, b, args.demeter_depth),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="compare against this ref (default: HEAD)")
    ap.add_argument("--only", default=None, help="comma-separated subset of checks")
    ap.add_argument("--strict", action="store_true", help="treat advisory checks as failures")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--func-len", type=int, default=DEFAULTS["func_len"])
    ap.add_argument("--params", type=int, default=DEFAULTS["params"])
    ap.add_argument("--depth", type=int, default=DEFAULTS["depth"])
    ap.add_argument("--demeter-depth", type=int, default=DEFAULTS["demeter"])
    args = ap.parse_args()

    checks = build_checks(args)
    if args.list:
        for k in checks:
            print(f"{k}{' (blocking)' if k in BLOCKING else ' (advisory)'}")
        return 0

    names = [n.strip() for n in args.only.split(",")] if args.only else list(checks)
    bad = [n for n in names if n not in checks]
    if bad:
        print(f"unknown check(s): {', '.join(bad)}", file=sys.stderr)
        return 2

    added, mod = changed(args.base)
    if not added and not mod:
        print("craft_check: no changes to inspect")
        return 0

    hard = advisory = 0
    for n in names:
        try:
            res = checks[n](added, mod, args.base)
        except Exception as e:
            print(f"  ! {n} errored: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if not res:
            continue
        adv = n not in BLOCKING and not args.strict
        print(f"\n[{'ADVISORY' if adv else 'FAIL'}] {n}")
        for loc, msg in res[:12]:
            print(f"  {loc}: {msg}")
        if len(res) > 12:
            print(f"  ... {len(res) - 12} more")
        if adv:
            advisory += len(res)
        else:
            hard += len(res)

    print(f"\ncraft_check: {len(added)} added, {len(mod)} modified | "
          f"{hard} blocking, {advisory} advisory")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
