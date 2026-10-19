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
                      Waiver: a handler that must swallow on purpose (a hook
                      that fails open so it never blocks the session) carries
                      `# fail-open: <reason>` (`// fail-open: <reason>` in JS)
                      on its except/catch line or the first line of its body.
                      The reason is required; a bare `# fail-open:` waives
                      nothing.
  short-names, abbreviations, boolean-predicate, function-verb, method-names,
  magic-number        advisory  -- google/styleguide pyguide.md 3.16 (naming,
                      "descriptiveness should be proportional to the name's
                      scope", avoid abbreviations) and airbnb/javascript
                      README section 23 (naming conventions). Lists and
                      thresholds (1-2 chars over more than 5 lines, the
                      abbreviation and verb lists, the magic-number
                      allowlist) are SOURCE: original. A repo exempts its
                      own domain names with `"craft_allow_names": [...]` in
                      .100x.json.

Files in languages these checks do not parse (.rb .go .kt .swift .dart .java)
are counted and named on stdout, never silently passed.

    craft_check.py                          # all checks vs HEAD
    craft_check.py --base origin/main
    craft_check.py --only vague-names,bare-except
    craft_check.py --strict                 # advisory findings also fail
    craft_check.py --func-len 80 --params 6 --depth 5 --demeter-depth 4

Exit 1 if any BLOCKING check finds a violation (or any check, under --strict).
"""
import argparse, ast, functools, json, os, re, subprocess, sys, pathlib

from _mutation_guard import changed_files, diff_rev, enter_git_root, path_args, unreadable
from _paths import CONFIG_NAME

PY_EXT = (".py",)
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
CODE_EXT = PY_EXT + JS_EXT
UNSUPPORTED_EXT = (".rb", ".go", ".kt", ".swift", ".dart", ".java")
UI_FILE_RX = re.compile(r"\.(tsx|jsx|vue)$|(^|/)components?/")
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
    """(added, modified) paths in the diff; see _mutation_guard.changed_files."""
    return changed_files(base, "craft_check")


@functools.lru_cache(maxsize=None)
def touched_lines(path, base):
    """Line numbers (new-file numbering) this diff added. None means 'treat the
    whole file as touched' -- true for a brand-new/untracked file, and the safe
    default if git can't produce a diff at all."""
    rng = [diff_rev(base)]
    out = sh(["git", "diff", "--unified=0"] + rng + path_args(path))
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
        kind = "function"
        if m:
            name, params = m.group(1), m.group(2)
        else:
            m2 = RX_METHOD.match(line)
            first_word = re.match(r"[A-Za-z_$][\w$]*", stripped)
            if m2 and m2.group(1) not in JS_CONTROL_WORDS and not (first_word and first_word.group(0) in JS_CONTROL_WORDS):
                m, name, params, kind = m2, m2.group(1), m2.group(2), "method"
        if not m or name is None:
            continue
        brace_pos = m.group(0).rfind("{")
        if brace_pos == -1:
            continue
        open_idx = offsets[ln - 1] + brace_pos
        close_idx = scan_matching_brace(text, open_idx)
        end_line = text.count("\n", 0, close_idx) + 1
        out.append(dict(name=name, params=params or "", start=ln, end=end_line, kind=kind, line=line,
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


FAIL_OPEN_RX = re.compile(r"(?:#|//)\s*fail-open:\s*\S")


def fail_open_waived(lines, ln):
    """An explicit `fail-open: <reason>` comment on line ln or the line after it."""
    return any(FAIL_OPEN_RX.search(lines[i]) for i in (ln - 1, ln) if 0 <= i < len(lines))


def check_bare_except(added, mod, base):
    out = []
    for p in added + mod:
        touched = touched_lines(p, base)
        if is_py(p):
            src_lines = (read(p) or "").splitlines()
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
                if (only_pass or only_log) and not fail_open_waived(src_lines, node.lineno):
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
                if (is_empty or is_log_only) and not fail_open_waived(text.splitlines(), ln):
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


# ---------------- naming by scope, predicates, verbs, magic numbers ----------------

SHORT_NAME_MAX = 2
SHORT_NAME_SPAN = 5  # a name used across more lines than this needs to say what it holds
SHORT_OK = {"i", "j", "k", "n", "x", "y", "z", "id", "db", "ok", "err", "e", "ex", "ctx", "_"}
ABBREV_WORDS = {"tmp", "cfg", "usr", "mgr", "calc", "proc", "cnt", "idx", "btn", "arr"}
ABBREV_WHOLE = {"str", "num", "obj"}
PREDICATE_RX = re.compile(r"^_*(is|has|should|can|was|did|needs)(_|[A-Z])")
CONSTANT_RX = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
VERBS = set("""
accept activate add analyse analyze allow append apply approve archive assert assign attach audit authenticate
authorize bill build bump cache calculate call cancel capture charge check choose classify clean clear clone
close collect combine commit compare compile compose compute configure confirm connect consume
convert copy count create debounce decode decorate decrypt default define delete deny deploy
deserialize destroy detach detect diff disable discard dispatch display do download drop dump
emit enable encode encrypt end enqueue ensure enter escape estimate evaluate exec execute exit
expand expect explain export extend extract fail fetch fill filter find finish fix flag flatten
flush fold format forward from gather generate get give go group guard handle hash hide hydrate
import increment infer init initialize inject insert install invalidate invoke is join keep
label leave limit link lint list listen load lock log login logout lookup make map mark match
measure merge migrate mount move mutate negotiate normalize notify observe on open pad
paginate parse patch pause persist pick ping place plan play poll pop populate post prefetch
prepare prepend preview print process produce prompt protect provide prune publish pull
push put query queue quote raise rank read rebuild receive recompute record redact redirect
reduce refresh refund register reject release reload remove rename render reorder repeat replace reply
report request require rerun reset resolve respond restore resume retry return reuse revert
revoke rewrite rollback rotate round route run sanitize save scan schedule score search seed
select send serialize serve set setup shift ship should show shuffle sign skip sleep slice sort spawn
split stamp start stop store stream strip stub submit subscribe summarize swap sync tag take
test throttle throw tick to toggle track transform translate traverse trigger trim truncate try
unlink unlock unmount unpack unregister unsubscribe unwrap update upgrade upload upsert use
validate verify visit wait walk warn watch wrap write yield as can has was did needs with
""".split())
JS_LIFECYCLE = {"constructor", "render", "componentDidMount", "componentDidUpdate",
                "componentWillUnmount", "componentDidCatch", "getSnapshotBeforeUpdate",
                "getDerivedStateFromProps", "main"}
PY_EXEMPT_FUNCS = {"main", "setUp", "tearDown", "setUpClass", "tearDownClass", "setUpModule",
                   "tearDownModule"}
PY_GETTER_DECORATORS = {"property", "cached_property", "setter", "getter", "deleter", "fixture"}
MAGIC_OK = {-1.0, 0.0, 1.0, 2.0, 100.0, 1000.0}
TIMEOUT_KW_RX = re.compile(r"timeout|delay|interval|ttl", re.I)
NUMBER_PATTERN = r"-?\d[\d_]*(?:\.\d+)?"


def allowed_names():
    """Names a repo has declared legitimate (domain abbreviations, an established
    short name) under `craft_allow_names` in .100x.json at the git root."""
    try:
        config = json.loads(pathlib.Path(CONFIG_NAME).read_text())
    except (OSError, ValueError):
        return frozenset()
    names = config.get("craft_allow_names", []) if isinstance(config, dict) else []
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        print(f"craft_check: {CONFIG_NAME}: \"craft_allow_names\" must be a list of strings; ignored",
              file=sys.stderr)
        return frozenset()
    return frozenset(names)


ALLOWED = None


def is_allowed(name):
    global ALLOWED
    if ALLOWED is None:
        ALLOWED = allowed_names()
    return name in ALLOWED


def name_words(name):
    return [w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


def js_code_only(text):
    """`text` with comment and string-literal content blanked, newlines kept, so a
    word inside a string is not read as a use of a variable."""
    out, i, n, state = [], 0, len(text), None
    while i < n:
        char, pair = text[i], text[i:i + 2]
        if state is None and pair in ("//", "/*"):
            state, step, kept = pair, 2, "  "
        elif state is None:
            state = char if char in ("'", '"', "`") else None
            step, kept = 1, char
        elif state == "//":
            state = None if char == "\n" else state
            step, kept = 1, char if char == "\n" else " "
        elif state == "/*" and pair == "*/":
            state, step, kept = None, 2, "  "
        elif state != "/*" and char == "\\":
            step, kept = 2, "  "
        elif state != "/*" and char == state:
            state, step, kept = None, 1, char
        else:
            step, kept = 1, char if char == "\n" else " "
        out.append(kept)
        i += step
    return "".join(out)


def walk_scope(node):
    """Descendants of `node` that belong to its own scope: nested defs and classes
    are yielded but not entered."""
    for child in ast.iter_child_nodes(node):
        yield child
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            yield from walk_scope(child)


def target_names(target):
    if isinstance(target, ast.Name):
        return [target]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in target_names(elt)]
    if isinstance(target, ast.Starred):
        return target_names(target.value)
    return []


def bound_targets(node):
    """(Name nodes `node` binds, whether they are loop targets)."""
    if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
        return target_names(node.target), True
    if isinstance(node, ast.Assign):
        return [t for tgt in node.targets for t in target_names(tgt)], False
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return target_names(node.target), False
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return target_names(node.optional_vars), False
    return [], False


def py_bindings(scope):
    """{name: (first binding line, is_loop_target, is_param)} for one scope."""
    found = {}
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = scope.args
        for arg in a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
            if arg.arg not in PY_KEYWORD_SKIP:
                found.setdefault(arg.arg, (arg.lineno, False, True))
    for node in walk_scope(scope):
        if isinstance(node, ast.ExceptHandler) and node.name:
            found.setdefault(node.name, (node.lineno, False, False))
        targets, loop = bound_targets(node)
        for t in targets:
            found.setdefault(t.id, (t.lineno, loop, False))
    return found


def short_name_ok(name, loop, param, in_test):
    if len(name) > SHORT_NAME_MAX or name in SHORT_OK or loop or is_allowed(name):
        return True
    return (name == "t" and in_test) or (name == "fn" and param)


def py_short_names(path, tree, touched, in_test):
    out = []
    scopes = [tree] + py_funcs(tree)
    for scope in scopes:
        uses = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Name):
                uses.setdefault(node.id, []).append(node.lineno)
        for name, (ln, loop, param) in py_bindings(scope).items():
            if short_name_ok(name, loop, param, in_test) or not overlaps(touched, ln, ln):
                continue
            span = max(uses.get(name, [ln]) + [ln]) - ln
            if span > SHORT_NAME_SPAN:
                out.append((f"{path}:{ln}", f"`{name}` is {len(name)} char(s) but lives {span} lines -- "
                                            f"a name's length should grow with its scope"))
    return out


def js_scope_end(fns, ln, default):
    inner = [f for f in fns if f["start"] <= ln <= f["end"]]
    return min(inner, key=lambda f: f["end"] - f["start"])["end"] if inner else default


def js_last_use(code_lines, name, start, end):
    rx = re.compile(r"(?<![\w$.])" + re.escape(name) + r"(?![\w$])")
    last = start
    for ln in range(start, min(end, len(code_lines)) + 1):
        if rx.search(code_lines[ln - 1]):
            last = ln
    return last


def js_param_names(params):
    names = []
    for raw in split_top_level(params):
        token = raw.strip()
        if token.startswith(("{", "[")):
            continue
        names.append(re.split(r"[:=?]", token.lstrip("."))[0].strip())
    return [n for n in names if n]


def js_short_names(path, text, touched, in_test):
    out, seen = [], set()
    code = js_code_only(text)
    code_lines = code.splitlines()
    fns = js_functions(text)
    total = len(code_lines)
    candidates = []
    for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]?)(?![\w$])", code):
        line_no = code.count("\n", 0, m.start()) + 1
        line_head = code_lines[line_no - 1][:m.start() - (code.rfind("\n", 0, m.start()) + 1)]
        loop = bool(re.search(r"\bfor\s*\(\s*$", line_head))
        candidates.append((m.group(1), line_no, loop, False, js_scope_end(fns, line_no, total)))
    for fn in fns:
        for name in js_param_names(fn["params"]):
            candidates.append((name, fn["start"], False, True, fn["end"]))
    for name, line_no, loop, param, end in candidates:
        if (name, line_no) in seen or short_name_ok(name, loop, param, in_test) or not overlaps(touched, line_no, line_no):
            continue
        seen.add((name, line_no))
        span = js_last_use(code_lines, name, line_no + (0 if param else 1), end) - line_no
        if span > SHORT_NAME_SPAN:
            out.append((f"{path}:{line_no}", f"`{name}` is {len(name)} char(s) but lives {span} lines -- "
                                              f"a name's length should grow with its scope"))
    return out


def check_short_names(added, mod, base):
    out = []
    for p in added + mod:
        touched = touched_lines(p, base)
        in_test = bool(TEST_RX.search(p))
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is not None:
                out += py_short_names(p, tree, touched, in_test)
        elif is_js(p):
            text = read(p)
            if text is not None:
                out += js_short_names(p, text, touched, in_test)
    return out


def abbreviation(name, loop, ui_file):
    """The abbreviation `name` uses, or None."""
    if is_allowed(name):
        return None
    if name.lower() in ABBREV_WHOLE:
        return name
    for w in name_words(name):
        if w not in ABBREV_WORDS or (w == "idx" and loop) or (w == "btn" and ui_file):
            continue
        return w
    return None


def py_named_things(tree):
    """(name, line, kind, is_loop_target) for every function, parameter and variable."""
    for scope in [tree] + py_funcs(tree):
        if scope is not tree:
            yield scope.name, scope.lineno, "function", False
        for name, (ln, loop, param) in py_bindings(scope).items():
            yield name, ln, "parameter" if param else "variable", loop


def js_named_things(text):
    code = js_code_only(text)
    for m in re.finditer(r"\b(const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", code):
        ln = code.count("\n", 0, m.start()) + 1
        head = code[code.rfind("\n", 0, m.start()) + 1:m.start()]
        yield m.group(2), ln, "declaration", bool(re.search(r"\bfor\s*\(\s*$", head))
    for fn in js_functions(text):
        if fn["kind"] == "method":
            yield fn["name"], fn["start"], "method", False
        for pname in js_param_names(fn["params"]):
            yield pname, fn["start"], "parameter", False


def check_abbreviations(added, mod, base):
    out = []
    for p in added + mod:
        if is_py(p):
            tree, _ = parse_py(p)
            things = py_named_things(tree) if tree is not None else []
        elif is_js(p):
            text = read(p)
            things = js_named_things(text) if text is not None else []
        else:
            continue
        touched = touched_lines(p, base)
        ui_file = bool(UI_FILE_RX.search(p))
        seen = set()
        for name, ln, kind, loop in things:
            abbr = abbreviation(name, loop, ui_file)
            if abbr and (name, ln) not in seen and overlaps(touched, ln, ln):
                seen.add((name, ln))
                out.append((f"{p}:{ln}", f"{kind} `{name}` abbreviates (`{abbr}`) -- spell the word out"))
    return out


def predicate_ok(name):
    return bool(PREDICATE_RX.match(name)) or bool(CONSTANT_RX.match(name)) or name == "ok" \
        or is_allowed(name)


def is_bool_literal(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, bool)


def check_boolean_predicate(added, mod, base):
    out = []
    msg = "boolean `{}` does not read as a predicate -- prefix is_/has_/should_/can_/was_/did_/needs_"
    for p in added + mod:
        touched = touched_lines(p, base)
        flagged = set()
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is None:
                continue
            # A class-body field (dataclass, pydantic, ORM column) names stored state
            # whose schema or API often fixes the name; only variables are checked.
            fields = {id(stmt) for cls in ast.walk(tree) if isinstance(cls, ast.ClassDef)
                      for stmt in cls.body}
            for node in ast.walk(tree):
                hits = []
                if id(node) in fields:
                    continue
                if isinstance(node, ast.Assign) and is_bool_literal(node.value):
                    hits = [t for tgt in node.targets for t in target_names(tgt)]
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and (
                        (isinstance(node.annotation, ast.Name) and node.annotation.id == "bool")
                        or (node.value is not None and is_bool_literal(node.value))):
                    hits = [node.target]
                for t in hits:
                    if t.id not in flagged and not predicate_ok(t.id) and overlaps(touched, t.lineno, t.lineno):
                        flagged.add(t.id)
                        out.append((f"{p}:{t.lineno}", msg.format(t.id)))
        elif is_js(p):
            text = read(p)
            if text is None:
                continue
            code = js_code_only(text)
            rx = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*"
                            r"(?::\s*boolean\b[^=;\n]*(?:=|;|$)|=\s*(?:true|false)\b)", re.M)
            for m in rx.finditer(code):
                name = m.group(1)
                ln = code.count("\n", 0, m.start()) + 1
                if name not in flagged and not predicate_ok(name) and overlaps(touched, ln, ln):
                    flagged.add(name)
                    out.append((f"{p}:{ln}", msg.format(name)))
    return out


def starts_with_verb(name):
    words = name_words(name.lstrip("_$"))
    if not words:
        return False
    first = words[0]
    return first in VERBS or (first.endswith("s") and first[:-1] in VERBS)


NOUN_NAME_MAX_LINES = 10


def noun_name_ok(length):
    # A short noun (`total()`, `median()`, `changed_files()`) reads as the value it
    # returns; a long body behind a noun hides what the function does.
    return length <= NOUN_NAME_MAX_LINES


def py_decorator_names(fn):
    names = set()
    for d in fn.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
        elif isinstance(target, ast.Name):
            names.add(target.id)
    return names


def check_function_verb(added, mod, base):
    out = []
    for p in added + mod:
        if TEST_RX.search(p):
            continue
        touched = touched_lines(p, base)
        if is_py(p):
            tree, _ = parse_py(p)
            if tree is None:
                continue
            for fn in py_funcs(tree):
                name = fn.name
                if (name.startswith("__") and name.endswith("__")) or name.startswith("test") \
                        or name in PY_EXEMPT_FUNCS or py_decorator_names(fn) & PY_GETTER_DECORATORS \
                        or is_allowed(name) or starts_with_verb(name) \
                        or noun_name_ok((fn.end_lineno or fn.lineno) - fn.lineno + 1):
                    continue
                if overlaps(touched, fn.lineno, fn.lineno):
                    out.append((f"{p}:{fn.lineno}", f"function `{name}` does not start with a verb -- "
                                                     f"name what it does (`get_`, `build_`, `parse_`...)"))
        elif is_js(p):
            text = read(p)
            if text is None:
                continue
            component_file = p.endswith((".tsx", ".jsx"))
            for fn in js_functions(text):
                name = fn["name"]
                if name in JS_LIFECYCLE or re.match(r"ng[A-Z]", name) or is_allowed(name) \
                        or (component_file and name[:1].isupper()) \
                        or re.search(r"\bget\s+" + re.escape(name) + r"\s*\(", fn["line"]) \
                        or starts_with_verb(name) or noun_name_ok(fn["end"] - fn["start"] + 1):
                    continue
                if overlaps(touched, fn["start"], fn["start"]):
                    out.append((f"{p}:{fn['start']}", f"{fn['kind']} `{name}` does not start with a verb -- "
                                                       f"name what it does (`get`, `build`, `parse`...)"))
    return out


def check_method_names(added, mod, base):
    out = []
    for p in added + mod:
        if not is_js(p):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for fn in js_functions(text):
            if fn["kind"] == "method" and vague_match(fn["name"]) and overlaps(touched, fn["start"], fn["start"]):
                out.append((f"{p}:{fn['start']}", f"method named `{fn['name']}` -- reveal intent instead of a generic noun"))
    return out


def magic_value(literal):
    try:
        return float(literal.replace("_", "")) not in MAGIC_OK
    except ValueError:
        return False


def py_number(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = py_number(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    return None


STATUS_NAME_RX = re.compile(r"status|code", re.I)


def is_http_status(value):
    return isinstance(value, int) and 100 <= value <= 599


def py_operand_name(node):
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ""


def py_magic(tree, src_lines):
    """(line, literal) for each numeric literal compared against or passed as a timeout."""
    for node in ast.walk(tree):
        operands = []
        if isinstance(node, ast.Compare):
            operands = [node.left] + node.comparators
            # `resp.status_code == 404` already names the number: HTTP defines it.
            if any(STATUS_NAME_RX.search(py_operand_name(o)) for o in operands):
                operands = [o for o in operands if not is_http_status(py_number(o))]
        elif isinstance(node, ast.Call):
            operands = [k.value for k in node.keywords if k.arg and TIMEOUT_KW_RX.search(k.arg)]
            func = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if func == "sleep" and node.args:
                operands.append(node.args[0])
        for op in operands:
            value = py_number(op)
            if value is not None and float(value) not in MAGIC_OK:
                ln = op.lineno
                if not re.match(r"^\s*_*[A-Z][A-Z0-9_]*\s*(?::[^=]+)?=", src_lines[ln - 1]):
                    yield ln, str(value)


JS_CONST_DECL = re.compile(r"^\s*(?:export\s+)?(?:(?:const|let|var|static|readonly|private|public|protected)\s+)*"
                           r"_*[A-Z][A-Z0-9_]*\s*(?::[^=]+)?=")
JS_CMP = r"(?:===?|!==?|(?<![<>=])<=?(?![<=])|(?<![<>=])>=?(?![>=]))"
JS_MAGIC_RX = [
    re.compile(r"(?<![\w$.\])])(" + NUMBER_PATTERN + r")\s*" + JS_CMP),
    re.compile(JS_CMP + r"\s*(" + NUMBER_PATTERN + r")(?![\w.\[])"),
    re.compile(r"\b(?:setTimeout|setInterval)\s*\(.*,\s*(" + NUMBER_PATTERN + r")\s*\)"),
    re.compile(r"\b\w*(?:[Tt]imeout|[Dd]elay|[Ii]nterval|[Tt]tl)\w*\s*:\s*(" + NUMBER_PATTERN + r")\b"),
]


JS_STATUS_BEFORE = re.compile(r"[\w$]*(?:[Ss]tatus|[Cc]ode)[\w$]*\s*" + JS_CMP + r"\s*$")
JS_STATUS_AFTER = re.compile(r"^\s*" + JS_CMP + r"\s*[\w$.]*(?:[Ss]tatus|[Cc]ode)")


def js_status_compare(line, m):
    """True when the literal is an HTTP status compared with a status/code name."""
    literal = m.group(1)
    if not literal.isdigit() or not is_http_status(int(literal)):
        return False
    return bool(JS_STATUS_BEFORE.search(line[:m.start(1)])
                or JS_STATUS_AFTER.match(line[m.end(1):]))


def js_magic(text):
    for ln, line in enumerate(js_code_only(text).splitlines(), 1):
        if JS_CONST_DECL.match(line):
            continue
        for rx in JS_MAGIC_RX:
            for m in rx.finditer(line):
                if not js_status_compare(line, m):
                    yield ln, m.group(1)


def check_magic_number(added, mod, base):
    out = []
    for p in added + mod:
        if TEST_RX.search(p):
            continue
        touched = touched_lines(p, base)
        if is_py(p):
            tree, src = parse_py(p)
            hits = py_magic(tree, src.splitlines()) if tree is not None else []
        elif is_js(p):
            text = read(p)
            hits = js_magic(text) if text is not None else []
        else:
            continue
        seen = set()
        for ln, literal in hits:
            if magic_value(literal) and (ln, literal) not in seen and overlaps(touched, ln, ln):
                seen.add((ln, literal))
                out.append((f"{p}:{ln}", f"magic number {literal} -- name it as a constant or read it from config"))
    return out


def report_unsupported(paths):
    counts = {}
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext in UNSUPPORTED_EXT:
            counts[ext] = counts.get(ext, 0) + 1
    for ext, n in sorted(counts.items()):
        print(f"craft_check: {n} {ext} files not checked (unsupported language)")


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
        "short-names": check_short_names,
        "abbreviations": check_abbreviations,
        "boolean-predicate": check_boolean_predicate,
        "function-verb": check_function_verb,
        "method-names": check_method_names,
        "magic-number": check_magic_number,
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

    if enter_git_root("craft_check", args.base) is None:
        return 2
    added, mod = changed(args.base)
    if unreadable(added + mod, "craft_check"):
        return 2
    if not added and not mod:
        print("craft_check: no changes to inspect")
        return 0
    report_unsupported(added + mod)

    hard = advisory = 0
    for n in names:
        try:
            res = checks[n](added, mod, args.base)
        except Exception as e:
            print(f"  ! {n} errored: {type(e).__name__}: {e}", file=sys.stderr)
            hard += 1
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
