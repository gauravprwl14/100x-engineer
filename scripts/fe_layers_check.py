#!/usr/bin/env python3
"""Diff-scoped checks for the presentation / logic / business layer boundary in
React + TypeScript code (skills/frontend-architecture/SKILL.md).

TypeScript/TSX has no `ast` module available here, so every check is regex +
a hand-rolled brace scanner -- heuristic, no real parser, same caveat as
craft_check.py's JS/TS engine (which this file's brace scanner is copied
from, kept self-contained rather than imported so this script has no
in-repo dependency). A missed violation is cheap; a false positive is what
gets a layering gate turned off, so every check below is biased to require
tight, low-noise textual context before firing -- see each function's
docstring for the specific false-positive it was built to avoid.

The three layers, checkable:
  presentation  `*.tsx`/`*.jsx` components -- renders props/view state, no I/O,
                no money math, no validation, no direct storage access.
  logic         `use*.ts` hooks -- orchestration, fetching, caching, effects.
                Knows the business layer and the transport, never JSX.
  business      plain `.ts` modules (`domain/`, `lib/`, `core/`, `business/`),
                no React import, no DOM global -- pure, unit-testable.
Dependency direction: presentation -> logic -> business, never backwards.

    fe_layers_check.py                      # all checks vs HEAD
    fe_layers_check.py --base origin/main
    fe_layers_check.py --strict             # advisory findings also fail
    fe_layers_check.py --only presentation-io,hook-renders-jsx
    fe_layers_check.py --effect-lines 20 --file-lines 250 --hook-calls 4

Exit 1 if any BLOCKING check finds a violation (or any check, under --strict).
"""
import argparse, os, re, subprocess, sys, pathlib

TSX_EXT = (".tsx", ".jsx")
TS_EXT = (".ts", ".js")
CODE_EXT = TSX_EXT + TS_EXT
TEST_RX = re.compile(r"(^|/)(tests?|__tests__|spec)/|[._](test|spec)\.[a-z]+$|\.stories\.[a-z]+$", re.I)
DTS_RX = re.compile(r"\.d\.ts$")

MONEY_WORDS = ("price", "amount", "total", "tax", "discount", "fee")
MONEY_SAFE_HINTS = ("cent", "minor", "subunit", "micros", "milli")
BUSINESS_DIR_RX = re.compile(r"(^|/)(domain|lib|core|business)/")
HOOK_FILE_RX = re.compile(r"(^|/)use[A-Z]\w*\.tsx?$")

DEFAULTS = dict(effect_lines=15, file_lines=200, hook_calls=3)


# ---------------- shared helpers (diff plumbing, mirrors craft_check.py) ----------------

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
    whole file as touched' -- true for a brand-new/untracked file."""
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


def is_tsx(p):
    return p.endswith(TSX_EXT)


def is_ts(p):
    return p.endswith(TS_EXT) and not DTS_RX.search(p)


def scan_matching_brace(text, open_idx):
    """Index of the '}' matching the '{' at open_idx, skipping string/comment
    content on a best-effort basis (no real lexer). Copied from
    craft_check.py's engine -- kept local so this checker has no in-repo
    import dependency."""
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


def is_comment_line(line):
    s = line.strip()
    return s.startswith("//") or s.startswith("*") or s.startswith("/*") or s.startswith("{/*")


def looks_like_money(name):
    n = name.lower()
    if any(h in n for h in MONEY_SAFE_HINTS):
        return False
    return any(w in n for w in MONEY_WORDS)


def has_react_sibling_exemption(path):
    """A business module is '.ts with no .tsx sibling'. A same-stem .tsx next
    to it (component.ts + component.tsx co-location, rare but real) means
    this .ts is plausibly component-adjacent types, not a domain module --
    skip rather than risk a false positive on a legitimate pairing."""
    p = pathlib.Path(path)
    return (p.with_suffix(".tsx")).exists()


# ---------------- checks ----------------

# 1. presentation-io: fetch/axios/.then/API-client-call/raw URL string in a .tsx
IO_PATTERNS = [
    re.compile(r"\bfetch\s*\("),
    re.compile(r"\baxios\.[A-Za-z]+\s*\("),
    re.compile(r"\.then\s*\(\s*(?:\(|[A-Za-z_$])"),
    # Any identifier ending in Api/Client, called as a method -- deliberately
    # broad: `userApi.refresh()` in an event handler IS a direct client call
    # made from the presentation layer, whoever injected `userApi`. The
    # false-positive risk this raises is a plain callback prop
    # (`onTrack()`), which this pattern does not match (no Api/Client
    # suffix) -- see tests/test_fe_layers_check.sh for both cases.
    re.compile(r"\b[A-Za-z_$][\w$]*(?:Api|Client)\.[A-Za-z_$][\w$]*\s*\("),
]
RX_RAW_URL = re.compile(r"""['"`]https?://[^'"`]+['"`]""")
# A URL literal that IS a JSX attribute value (a link, an image, a form action)
# is ordinary markup, not I/O -- exempt it so a plain <a href> doesn't fire.
JSX_URL_ATTR_RX = re.compile(r"(href|src|action|poster|srcSet|icon)\s*=\s*$", re.I)


def check_presentation_io(added, mod, base):
    """A .tsx component calling fetch/axios/.then/an *Api./*Client. method, or
    embedding a raw URL literal outside a JSX link/image/action attribute --
    I/O belongs in a hook, not the component. Import-line paths
    (`from "./total/price"`) are skipped so a directory name never trips the
    URL/client patterns; `href=`/`src=`/`action=` URL literals are skipped
    so ordinary markup (a link, an image) isn't mistaken for a fetch target."""
    out = []
    for p in added + mod:
        if not is_tsx(p) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for ln, line in enumerate(text.splitlines(), 1):
            if is_comment_line(line) or re.match(r"\s*(import|export)\b.*\bfrom\b", line):
                continue
            if not overlaps(touched, ln, ln):
                continue
            found = None
            for rx in IO_PATTERNS:
                m = rx.search(line)
                if m:
                    found = m
                    break
            if not found:
                m = RX_RAW_URL.search(line)
                if m and not JSX_URL_ATTR_RX.search(line[:m.start()]):
                    found = m
            if found:
                out.append((f"{p}:{ln}",
                            f"presentation layer performing I/O: `{found.group(0).strip()}`"))
    return out


# 2. presentation-money-math: arithmetic on a money-ish identifier in a .tsx
TOKEN = r"(?:[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[[^\]]+\])*|\d+(?:\.\d+)?)"
RX_ARITH = re.compile(rf"(?P<lhs>{TOKEN})\s*(?P<op>[+\-*/])(?!=)\s*(?P<rhs>{TOKEN})")


def check_presentation_money_math(added, mod, base):
    """`total + tax`, `price * quantity` typed directly in JSX/component body.
    Requires an arithmetic operator with a real token contiguous (mod
    whitespace) on both sides, which is what keeps this off string
    concatenation like `"Total: " + total` -- the token pattern cannot start
    at a quote character, so a string literal on either side breaks the
    match rather than firing it."""
    out = []
    for p in added + mod:
        if not is_tsx(p) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for ln, line in enumerate(text.splitlines(), 1):
            if is_comment_line(line) or re.match(r"\s*(import|export)\b.*\bfrom\b", line):
                continue
            if not overlaps(touched, ln, ln):
                continue
            for m in RX_ARITH.finditer(line):
                lhs, op, rhs = m.group("lhs"), m.group("op"), m.group("rhs")
                if looks_like_money(lhs) or looks_like_money(rhs):
                    out.append((f"{p}:{ln}",
                                f"business rule in the presentation layer: `{m.group(0)}`"))
                    break
    return out


# 3. large-use-effect: useEffect body exceeding N lines
RX_USE_EFFECT = re.compile(r"\buseEffect\s*\(\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{")


def check_large_use_effect(added, mod, base):
    """A useEffect whose body is long is orchestration that outgrew the
    component -- advisory, since a long effect isn't always wrong (a
    subscription setup/teardown can legitimately run a dozen lines)."""
    out = []
    for p in added + mod:
        if not is_tsx(p) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for m in RX_USE_EFFECT.finditer(text):
            open_idx = m.end() - 1
            close_idx = scan_matching_brace(text, open_idx)
            start_ln = text.count("\n", 0, m.start()) + 1
            end_ln = text.count("\n", 0, close_idx) + 1
            length = end_ln - start_ln + 1
            if length > DEFAULTS["effect_lines"] and overlaps(touched, start_ln, end_ln):
                out.append((f"{p}:{start_ln}",
                            f"useEffect body is {length} lines (> {DEFAULTS['effect_lines']}) "
                            f"-- logic belongs in a hook"))
    return out


# 4. business-imports-react: a domain/lib/core/business .ts file importing react/next/DOM
RX_REACT_IMPORT = re.compile(
    r"""from\s+['"](react(?:-dom)?|next(?:/[\w-]+)?)['"]|require\(\s*['"](react(?:-dom)?|next(?:/[\w-]+)?)['"]\s*\)""")
RX_DOM_GLOBAL = re.compile(r"\b(document|window|localStorage|sessionStorage|navigator)\b\s*\.")


def check_business_imports_react(added, mod, base):
    """A `.ts` file under domain/lib/core/business (with no same-stem `.tsx`
    sibling, see has_react_sibling_exemption) importing react/next or
    touching a DOM global -- the dependency-direction rule made mechanical:
    presentation -> logic -> business, never backwards."""
    out = []
    for p in added + mod:
        if not is_ts(p) or is_tsx(p) or not BUSINESS_DIR_RX.search(p) or TEST_RX.search(p):
            continue
        if has_react_sibling_exemption(p):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for ln, line in enumerate(text.splitlines(), 1):
            if is_comment_line(line) or not overlaps(touched, ln, ln):
                continue
            m = RX_REACT_IMPORT.search(line)
            if m:
                out.append((f"{p}:{ln}",
                            f"dependency direction reversed: business module imports "
                            f"`{next(g for g in m.groups() if g)}`"))
                continue
            m2 = RX_DOM_GLOBAL.search(line)
            if m2:
                out.append((f"{p}:{ln}",
                            f"dependency direction reversed: business module touches "
                            f"DOM global `{m2.group(1)}`"))
    return out


# 5. container-presenter-fused: big component file with many use* calls
RX_USE_CALL = re.compile(r"\buse[A-Z]\w*\s*\(")
RX_JSX_RETURN = re.compile(r"return\s*\(?\s*<[A-Za-z]|<>|className=")


def check_container_presenter_fused(added, mod, base):
    """A component file that both renders JSX and racks up more than M `use*`
    calls, past a line-count floor -- signal that the container (data/state)
    and the presenter (markup) never got split. File-level, not diff-line
    scoped, because the smell is the file's total shape, not which lines
    just changed; still gated on the file being touched in this diff."""
    out = []
    for p in added + mod:
        if not is_tsx(p) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        n_lines = len(text.splitlines())
        if n_lines <= DEFAULTS["file_lines"]:
            continue
        if not RX_JSX_RETURN.search(text):
            continue
        n_hooks = len(RX_USE_CALL.findall(text))
        if n_hooks > DEFAULTS["hook_calls"]:
            out.append((p, f"{n_lines} lines with {n_hooks} `use*` calls and JSX -- "
                           f"container and presenter fused, split the data/state out into a hook"))
    return out


# 6. presentation-storage-access: localStorage/sessionStorage/document.cookie in a .tsx
RX_STORAGE = re.compile(r"\b(localStorage|sessionStorage)\b\s*\.|document\.cookie\b")


def check_presentation_storage_access(added, mod, base):
    """Direct browser-storage access in a component -- advisory: storage
    access belongs behind the logic layer (a hook), so it can be mocked/
    swapped without touching markup."""
    out = []
    for p in added + mod:
        if not is_tsx(p) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for ln, line in enumerate(text.splitlines(), 1):
            if is_comment_line(line) or not overlaps(touched, ln, ln):
                continue
            m = RX_STORAGE.search(line)
            if m:
                out.append((f"{p}:{ln}", f"storage access belongs behind the logic layer: "
                                          f"`{m.group(0).strip()}`"))
    return out


# 7. presentation-inline-validation: a .tsx importing zod/yup/joi and calling .parse/.validate
RX_VALIDATION_IMPORT = re.compile(r"""from\s+['"](zod|yup|joi)['"]""")
RX_VALIDATION_CALL = re.compile(r"\.(parse|parseAsync|validate|validateSync)\s*\(")


def check_presentation_inline_validation(added, mod, base):
    """A component that imports a validation library AND calls .parse()/
    .validate() itself -- the schema call belongs in the business layer, the
    component should only read the already-validated result or an error
    the logic layer produced."""
    out = []
    for p in added + mod:
        if not is_tsx(p) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        if not RX_VALIDATION_IMPORT.search(text):
            continue
        touched = touched_lines(p, base)
        for ln, line in enumerate(text.splitlines(), 1):
            if is_comment_line(line) or not overlaps(touched, ln, ln):
                continue
            m = RX_VALIDATION_CALL.search(line)
            if m:
                out.append((f"{p}:{ln}", f"validation belongs in the business layer: "
                                          f"`{m.group(0).strip()}` called in a component"))
    return out


# 8. hook-renders-jsx: a use*.ts (not .tsx) hook file that contains JSX
def check_hook_renders_jsx(added, mod, base):
    """A `use*.ts` file (logic layer, by this contract never `.tsx`) that
    contains JSX -- the hook is rendering, which is the presentation layer's
    job. Detected via the same JSX giveaways as check 5: a JSX return, a
    fragment, or a className prop."""
    out = []
    for p in added + mod:
        if not (p.endswith(".ts") and not DTS_RX.search(p)) or not HOOK_FILE_RX.search(p) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        m = RX_JSX_RETURN.search(text)
        if m:
            ln = text.count("\n", 0, m.start()) + 1
            touched = touched_lines(p, base)
            if overlaps(touched, ln, ln):
                out.append((f"{p}:{ln}", f"logic layer rendering: `{m.group(0).strip()}` in a hook file"))
    return out


BLOCKING = {"presentation-io", "presentation-money-math", "business-imports-react", "hook-renders-jsx"}


def build_checks():
    return {
        "presentation-io": check_presentation_io,
        "presentation-money-math": check_presentation_money_math,
        "large-use-effect": check_large_use_effect,
        "business-imports-react": check_business_imports_react,
        "container-presenter-fused": check_container_presenter_fused,
        "presentation-storage-access": check_presentation_storage_access,
        "presentation-inline-validation": check_presentation_inline_validation,
        "hook-renders-jsx": check_hook_renders_jsx,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="compare against this ref (default: HEAD)")
    ap.add_argument("--only", default=None, help="comma-separated subset of checks")
    ap.add_argument("--strict", action="store_true", help="treat advisory checks as failures")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--effect-lines", type=int, default=DEFAULTS["effect_lines"])
    ap.add_argument("--file-lines", type=int, default=DEFAULTS["file_lines"])
    ap.add_argument("--hook-calls", type=int, default=DEFAULTS["hook_calls"])
    args = ap.parse_args()
    DEFAULTS["effect_lines"] = args.effect_lines
    DEFAULTS["file_lines"] = args.file_lines
    DEFAULTS["hook_calls"] = args.hook_calls

    checks = build_checks()
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
        print("fe_layers_check: no changes to inspect")
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

    print(f"\nfe_layers_check: {len(added)} added, {len(mod)} modified | "
          f"{hard} blocking, {advisory} advisory")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
