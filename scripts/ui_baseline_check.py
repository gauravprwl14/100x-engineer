#!/usr/bin/env python3
"""Diff-scoped checks for the always-on UI defaults in skills/ui-baseline/SKILL.md.

Same plumbing shape as scripts/a11y_check.py: only lines the current diff touched
are reported, --base/--only/--strict/--list, Python stdlib only.

Detection is regex plus a small brace-depth CSS walker, not a CSS or JSX parser.
It reads source text, so it cannot see a computed layout: a width set by a class
built at runtime, or an overflow masked by a parent, is invisible to it. Every
check under-fires on ambiguous input; tests/test_ui_baseline_check.sh pairs each
detection with a clean file that must not be flagged.

    ui_baseline_check.py                  # all checks vs HEAD
    ui_baseline_check.py --base origin/main
    ui_baseline_check.py --only fixed-width,viewport-zoom
    ui_baseline_check.py --strict         # advisory findings also fail
    ui_baseline_check.py --list

Blocking: fixed-width, viewport-zoom, and raw-color when the repo has a token or
theme file. Advisory: raw-color without one, fetch-no-states, overflow-x-hidden.
Exit 1 on a blocking finding (any finding under --strict); exit 2 outside a git
repository or with a --base that does not resolve.
"""
import argparse, re, subprocess, sys, pathlib

from _mutation_guard import enter_git_root

JSX_EXT = (".tsx", ".jsx")
HTML_EXT = (".html", ".htm")
CSS_EXT = (".css", ".scss")
VUE_EXT = (".vue",)
MARKUP_EXT = JSX_EXT + HTML_EXT + VUE_EXT
TEST_RX = re.compile(r"(?:^|/)(?:__tests__|__mocks__|tests?|fixtures|e2e)/|\.(?:test|spec|stories)\.[jt]sx?$")

# Rule ids match the numbered rules in skills/ui-baseline/SKILL.md.
RULE = {
    "fixed-width": "rule 1, WCAG 2.2 SC 1.4.10 Reflow (320 CSS px, no 2-D scroll)",
    "viewport-zoom": "rule 1, WCAG 2.2 SC 1.4.4 Resize Text; ACT rule b4f0c3",
    "raw-color": "rule 7, design tokens over raw values",
    "fetch-no-states": "rule 4, loading/empty/error states per view",
    "overflow-x-hidden": "rule 1, overflow masked instead of fixed",
}


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed(base):
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--name-status", "--diff-filter=AM"] + rng)
    files = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            files.append(parts[-1])
    for p in sh(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        if p and p not in files:
            files.append(p)
    return files


def touched_lines(path, base):
    """New-file line numbers this diff added; None means the whole file."""
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


def overlaps(touched, start, end=None):
    if touched is None:
        return True
    return any(ln in touched for ln in range(start, (end or start) + 1))


def read(path):
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except OSError:
        return None


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def strip_css_comments(text):
    """Blank out /* */ comments, keeping offsets so line numbers stay true."""
    return re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def css_declarations(text):
    """Yield (start_idx, declaration, headers, block_text) for every declaration.

    headers is the stack of enclosing selectors/at-rules, innermost last;
    block_text is the full body of the innermost block, for sibling lookups.
    """
    text = strip_css_comments(text)
    stack, seg_start, i, n = [], 0, 0, len(text)
    opens = []
    while i < n:
        c = text[i]
        if c == "{":
            stack.append(text[seg_start:i].strip())
            opens.append(i)
            seg_start = i + 1
        elif c in ";}":
            seg = text[seg_start:i]
            if stack and ":" in seg and seg.strip():
                body_end = text.find("}", i) if c == ";" else i
                body = text[opens[-1] + 1:body_end if body_end != -1 else n]
                lead = len(seg) - len(seg.lstrip())
                yield seg_start + lead, seg.strip(), list(stack), body
            if c == "}" and stack:
                stack.pop()
                opens.pop()
            seg_start = i + 1
        i += 1


# --- fixed-width -----------------------------------------------------------
# 400px leaves headroom over the 320 CSS px reflow width: a value between 320
# and 400 can still overflow, but is as often a deliberate card or dialog size,
# and a false positive is what gets a checker disabled.
MIN_PX = 400
CSS_WIDTH_RX = re.compile(r"^(min-width|width)\s*:\s*(\d+(?:\.\d+)?)px\b", re.I)
JSX_WIDTH_RX = re.compile(r"(?<![\w-])(minWidth|width)\s*:\s*['\"](\d+(?:\.\d+)?)px['\"]")
TW_WIDTH_RX = re.compile(r"^(min-w|w)-\[(\d+(?:\.\d+)?)px\]$")
BREAKPOINT_PREFIX_RX = re.compile(r"^(?:sm|md|lg|xl|2xl|min-\[[^\]]+\]|@\w+):")
CLASS_ATTR_RX = re.compile(
    r"\bclass(?:Name)?\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|\{\s*`([^`]*)`\s*\}|\{\s*\"([^\"]*)\"\s*\})")
FLUID_CAP_RX = re.compile(r"max-width\s*:\s*(?:100%|\d+(?:\.\d+)?(?:vw|%)|none\b|min\()", re.I)


def class_lists(text):
    for m in CLASS_ATTR_RX.finditer(text):
        val = next(g for g in m.groups() if g is not None)
        yield m.start(), val.split()


def tag_before(text, idx):
    """Name of the tag whose attributes contain idx, if any."""
    lt = text.rfind("<", 0, idx)
    if lt == -1 or text.find(">", lt, idx) != -1:
        return None
    m = re.match(r"<([A-Za-z][\w.]*)", text[lt:])
    return m.group(1) if m else None


def check_fixed_width(files, base):
    out = []
    for p in files:
        if TEST_RX.search(p) or not p.endswith(CSS_EXT + MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        if p.endswith(CSS_EXT):
            for start, decl, headers, body in css_declarations(text):
                m = CSS_WIDTH_RX.match(decl)
                if not m or float(m.group(2)) < MIN_PX:
                    continue
                if any(h.startswith("@media") and re.search(r"min-width|print", h) for h in headers) \
                        or any(h.startswith("@container") for h in headers):
                    continue
                selector = headers[-1] if headers else ""
                # Data tables are WCAG 1.4.10's own exception (two-dimensional layout).
                if re.search(r"\btable\b|\bth\b|\btd\b", selector) or FLUID_CAP_RX.search(body):
                    continue
                ln = line_of(text, start)
                if overlaps(touched, ln):
                    out.append((f"{p}:{ln}", f"`{decl}` fixes a width wider than a 320px "
                                f"viewport with no min-width media query or fluid max-width "
                                f"-- forces horizontal scroll [{RULE['fixed-width']}]"))
            continue
        for start, toks in class_lists(text):
            if tag_before(text, start) == "table":
                continue
            for t in toks:
                m = TW_WIDTH_RX.match(t)
                if not m or float(m.group(2)) < MIN_PX or BREAKPOINT_PREFIX_RX.match(t):
                    continue
                if any(re.match(r"^max-w-(?:full|screen|\[\d+(?:vw|%)\])$", o) for o in toks):
                    continue
                ln = line_of(text, start)
                if overlaps(touched, ln):
                    out.append((f"{p}:{ln}", f"`{t}` applies at every viewport, mobile "
                                f"first -- prefix it (md:{t}) or use a fluid width "
                                f"[{RULE['fixed-width']}]"))
        for m in JSX_WIDTH_RX.finditer(text):
            if float(m.group(2)) < MIN_PX:
                continue
            window = text[m.start():m.start() + 200]
            if re.search(r"maxWidth\s*:\s*['\"](?:100%|\d+vw)", window):
                continue
            ln = line_of(text, m.start())
            if overlaps(touched, ln):
                out.append((f"{p}:{ln}", f"inline style {m.group(1)}: {m.group(2)}px cannot "
                            f"respond to the viewport [{RULE['fixed-width']}]"))
    return out


# --- viewport-zoom ---------------------------------------------------------
META_VIEWPORT_RX = re.compile(r"<meta\b[^>]*\bname\s*=\s*[\"']viewport[\"'][^>]*>", re.I | re.S)


def check_viewport_zoom(files, base):
    out = []
    for p in files:
        if not p.endswith(HTML_EXT) or TEST_RX.search(p):
            continue
        text = read(p)
        if text is None:
            continue
        head = re.search(r"<head\b[^>]*>(.*?)</head>", text, re.I | re.S)
        if not head:
            continue
        touched = touched_lines(p, base)
        meta = META_VIEWPORT_RX.search(text)
        if not meta:
            hs, he = line_of(text, head.start()), line_of(text, head.end())
            if overlaps(touched, hs, he):
                out.append((f"{p}:{hs}", "<head> has no <meta name=\"viewport\"> -- mobile "
                            "browsers render at ~980px and shrink the page "
                            f"[{RULE['viewport-zoom']}]"))
            continue
        content = (re.search(r"content\s*=\s*[\"']([^\"']*)[\"']", meta.group(0), re.I) or [None, ""])[1]
        problems = []
        if re.search(r"user-scalable\s*=\s*(?:no|0)\b", content, re.I):
            problems.append("user-scalable=no")
        ms = re.search(r"maximum-scale\s*=\s*([\d.]+)", content, re.I)
        if ms and float(ms.group(1)) < 2:
            problems.append(f"maximum-scale={ms.group(1)} (< 2)")
        ln = line_of(text, meta.start())
        if problems and overlaps(touched, ln, line_of(text, meta.end())):
            out.append((f"{p}:{ln}", f"viewport meta blocks zoom ({', '.join(problems)}) "
                        f"[{RULE['viewport-zoom']}]"))
    return out


# --- raw-color -------------------------------------------------------------
TOKEN_FILE_RX = re.compile(
    r"(?:^|/)(?:design-tokens?|tokens)(?:/|\.(?:json|ya?ml|[cm]?[jt]s|s?css)$)"
    r"|(?:^|/)theme\.(?:[cm]?[jt]sx?|json|s?css)$"
    r"|(?:^|/)tailwind\.config\.(?:[cm]?js|ts)$"
    r"|(?:^|/)_?(?:variables|colou?rs|palette)\.(?:s?css|[cm]?[jt]s|json)$", re.I)
CSS_COLOR_RX = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(\s*\d")
JSX_COLOR_RX = re.compile(
    r"(?<![\w=])[\"'`]#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})[\"'`]"
    r"|\[#[0-9a-fA-F]{3,8}\]"
    r"|[\"'`](?:rgba?|hsla?)\(\s*\d")
NON_COLOR_ATTR_RX = re.compile(r"(?:href|to|id|xlinkHref|htmlFor|key)\s*=\s*\{?\s*$")


def token_files():
    return [p for p in sh(["git", "ls-files"]).splitlines() if TOKEN_FILE_RX.search(p)]


def check_raw_color(files, base, tokens):
    out = []
    for p in files:
        if TEST_RX.search(p) or TOKEN_FILE_RX.search(p) or not p.endswith(CSS_EXT + JSX_EXT + VUE_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        if p.endswith(CSS_EXT):
            for start, decl, _, _ in css_declarations(text):
                # A custom-property definition IS a token, wherever it lives.
                if decl.startswith("--") or decl.startswith("$"):
                    continue
                m = CSS_COLOR_RX.search(decl.split(":", 1)[1])
                if not m:
                    continue
                ln = line_of(text, start)
                if overlaps(touched, ln):
                    out.append((f"{p}:{ln}", f"raw color in `{decl}` -- use a token "
                                f"[{RULE['raw-color']}]"))
            continue
        for m in JSX_COLOR_RX.finditer(text):
            if NON_COLOR_ATTR_RX.search(text[max(0, m.start() - 20):m.start()]):
                continue
            ln = line_of(text, m.start())
            if overlaps(touched, ln):
                out.append((f"{p}:{ln}", f"raw color {m.group(0).strip(chr(34) + chr(39) + '`')} "
                            f"-- use a token [{RULE['raw-color']}]"))
    note = (f"tokens found: {', '.join(tokens[:3])}" if tokens
            else "no token/theme file found -- advisory")
    return [(loc, f"{msg} ({note})") for loc, msg in out]


# --- fetch-no-states -------------------------------------------------------
FETCH_RX = re.compile(r"\b(?:useQuery|useInfiniteQuery|useSWR|useSWRInfinite|fetch)\s*\(")
STATE_RX = re.compile(
    r"\b(?:isLoading|isPending|isFetching|loading|isError|error|status\s*===?|"
    r"Suspense|ErrorBoundary|useSuspenseQuery|useSuspenseInfiniteQuery)\b")
USE_CLIENT_RX = re.compile(r"""^\s*(['"])use client\1""", re.M)


def check_fetch_no_states(files, base):
    out = []
    for p in files:
        if TEST_RX.search(p) or not p.endswith(JSX_EXT + VUE_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        # A server component under app/ gets loading.tsx/error.tsx from the router.
        if re.search(r"(?:^|/)app/", p) and not USE_CLIENT_RX.search(text):
            continue
        m = FETCH_RX.search(text)
        if not m or STATE_RX.search(text):
            continue
        ln = line_of(text, m.start())
        if overlaps(touched_lines(p, base), ln):
            out.append((f"{p}:{ln}", "fetches data but never branches on loading or error "
                        f"-- the view has a blank or broken state [{RULE['fetch-no-states']}]"))
    return out


# --- overflow-x-hidden -----------------------------------------------------
ROOT_SEL_RX = re.compile(r"(?:^|[\s,>])(?:html|body|:root)(?=$|[\s,.:#\[>{])")


def check_overflow_x_hidden(files, base):
    out = []
    for p in files:
        if TEST_RX.search(p) or not p.endswith(CSS_EXT + MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        if p.endswith(CSS_EXT):
            for start, decl, headers, _ in css_declarations(text):
                if not re.match(r"overflow-x\s*:\s*(?:hidden|clip)\b", decl, re.I):
                    continue
                if not headers or not ROOT_SEL_RX.search(headers[-1]):
                    continue
                ln = line_of(text, start)
                if overlaps(touched, ln):
                    out.append((f"{p}:{ln}", f"`{decl}` on {headers[-1]} hides horizontal "
                                f"overflow instead of fixing it [{RULE['overflow-x-hidden']}]"))
            continue
        for start, toks in class_lists(text):
            if "overflow-x-hidden" not in toks or tag_before(text, start) not in ("body", "html"):
                continue
            ln = line_of(text, start)
            if overlaps(touched, ln):
                out.append((f"{p}:{ln}", "overflow-x-hidden on <body>/<html> hides horizontal "
                            f"overflow instead of fixing it [{RULE['overflow-x-hidden']}]"))
    return out


CHECKS = ["fixed-width", "viewport-zoom", "raw-color", "fetch-no-states", "overflow-x-hidden"]
ALWAYS_BLOCKING = {"fixed-width", "viewport-zoom"}


def main():
    ap = argparse.ArgumentParser(description="Diff-scoped UI baseline checks.")
    ap.add_argument("--base", default=None, help="compare against this ref (default: HEAD)")
    ap.add_argument("--only", default=None, help="comma-separated subset of checks")
    ap.add_argument("--strict", action="store_true", help="advisory findings also fail")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for k in CHECKS:
            sev = ("blocking" if k in ALWAYS_BLOCKING
                   else "blocking with a token file, else advisory" if k == "raw-color"
                   else "advisory")
            print(f"{k} ({sev}) -- {RULE[k]}")
        return 0
    names = [n.strip() for n in args.only.split(",")] if args.only else CHECKS
    bad = [n for n in names if n not in CHECKS]
    if bad:
        print(f"unknown check(s): {', '.join(bad)}", file=sys.stderr)
        return 2
    if enter_git_root("ui_baseline_check", args.base) is None:
        return 2
    files = changed(args.base)
    if not files:
        print("ui_baseline_check: no changes to inspect")
        return 0

    tokens = token_files()
    run = {
        "fixed-width": lambda: check_fixed_width(files, args.base),
        "viewport-zoom": lambda: check_viewport_zoom(files, args.base),
        "raw-color": lambda: check_raw_color(files, args.base, tokens),
        "fetch-no-states": lambda: check_fetch_no_states(files, args.base),
        "overflow-x-hidden": lambda: check_overflow_x_hidden(files, args.base),
    }
    hard = advisory = 0
    for n in names:
        res = run[n]()
        if not res:
            continue
        blocking = n in ALWAYS_BLOCKING or (n == "raw-color" and tokens)
        print(f"\n[{'FAIL' if blocking else 'ADVISORY'}] {n}")
        for loc, msg in res[:12]:
            print(f"  {loc}: {msg}")
        if len(res) > 12:
            print(f"  ... {len(res) - 12} more")
        if blocking:
            hard += len(res)
        else:
            advisory += len(res)
    print(f"\nui_baseline_check: {len(files)} file(s) touched | {hard} blocking, {advisory} advisory"
          + (" (--strict: advisory findings fail)" if args.strict and advisory else ""))
    print("heuristic tool: source text only -- confirm reflow at 320px and the "
          "loading/empty/error states in a browser (see skills/ui-baseline/SKILL.md)")
    return 1 if hard or (args.strict and advisory) else 0


if __name__ == "__main__":
    sys.exit(main())
