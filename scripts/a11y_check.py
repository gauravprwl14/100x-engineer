#!/usr/bin/env python3
"""Diff-scoped, per-component accessibility checks for JSX/TSX and HTML.

Companion to skills/accessibility/SKILL.md. Same plumbing shape as
scripts/craft_check.py and scripts/perf_check.py: diff-scoped (only lines the
current diff touched are reported), --base/--only/--strict, Python stdlib only.

Detection method, stated plainly per this project's convention (a heuristic that
hides its own shape is worse than none): **this is regex + a hand-rolled
angle-bracket/brace scanner, not a real JSX/HTML parser.** It cannot see runtime
state (whether a `role` prop is conditionally applied, whether an icon component
renders visible text, whether a CSS class actually removes the focus ring at
runtime). It reads source text only. A missed violation is cheap; a false
positive is what gets a checker like this disabled -- so every check below is
written to under-fire on ambiguous input, and every check has a paired clean
test in tests/test_a11y_check.sh proving it does not fire on correct code.

    a11y_check.py                       # all checks vs HEAD
    a11y_check.py --base origin/main
    a11y_check.py --only img-no-alt,control-no-accessible-name
    a11y_check.py --strict              # advisory findings also fail
    a11y_check.py --list

Blocking checks (fail even without --strict): onclick-non-interactive,
img-no-alt, form-field-no-label, control-no-accessible-name -- these are the
four defect classes that make a control invisible or unusable to assistive
tech, not a preference. Everything else is advisory: a real risk, but one this
heuristic cannot confirm without a human or a runtime tool (axe, a keyboard
pass).

Exit 1 if any BLOCKING check finds a violation (or any check, under --strict).
"""
import argparse, re, subprocess, sys, pathlib

JSX_EXT = (".tsx", ".jsx")
HTML_EXT = (".html", ".htm")
MARKUP_EXT = JSX_EXT + HTML_EXT
CSS_EXT = (".css", ".scss")
SCAN_EXT = MARKUP_EXT + CSS_EXT

# ---------------------------------------------------------------------------
# shared git diff plumbing -- same shape as scripts/craft_check.py
# ---------------------------------------------------------------------------

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


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


# ---------------------------------------------------------------------------
# JSX/HTML tag scanner -- angle-bracket + brace/quote depth aware, mirrors the
# brace-scanning approach craft_check.py uses for JS function bodies.
# ---------------------------------------------------------------------------

TAG_OPEN_RX = re.compile(r"<([A-Za-z][\w.]*)")


def scan_tag(text, start):
    """Given the index of a tag's leading '<', return (attrs_str, gt_idx,
    self_closing) for that opening tag, or None if it never closes."""
    m = TAG_OPEN_RX.match(text, start)
    if not m:
        return None
    i, n = m.end(), len(text)
    depth, quote, attr_start = 0, None, m.end()
    while i < n:
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in ("'", '"'):
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth <= 0:
            self_closing = i > 0 and text[i - 1] == "/"
            end = i - 1 if self_closing else i
            return text[attr_start:end], i, self_closing
        i += 1
    return None


def jsx_tags(text, names=None):
    """Yield (tag, attrs, gt_idx, self_closing, start_idx) for each matched
    opening tag; names=None matches every tag."""
    for m in TAG_OPEN_RX.finditer(text):
        tag = m.group(1)
        if names is not None and tag not in names:
            continue
        res = scan_tag(text, m.start())
        if res is None:
            continue
        attrs, gt_idx, self_closing = res
        yield tag, attrs, gt_idx, self_closing, m.start()


def has_attr(attrs, name):
    """Attribute present by name, bare or with a value."""
    return re.search(r"(?:^|\s)" + re.escape(name) + r"(?:\s*=|[\s/]|$)", attrs) is not None


def attr_value(attrs, name):
    m = re.search(
        r"(?:^|\s)" + re.escape(name) + r"\s*=\s*"
        r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\{(?:[^{}]|\{[^{}]*\})*\})",
        attrs)
    return m.group(1) if m else None


def scan_children(text, tag, after_gt_idx):
    """Text between an opening tag's '>' and its first matching '</tag>'."""
    close_rx = re.compile(r"</\s*" + re.escape(tag) + r"\s*>")
    mclose = close_rx.search(text, after_gt_idx + 1)
    if not mclose:
        return None
    return text[after_gt_idx + 1:mclose.start()]


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

NONINTERACTIVE_TAGS = {"div", "span", "li"}


def check_onclick_non_interactive(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for tag, attrs, _, _, start in jsx_tags(text, NONINTERACTIVE_TAGS):
            if not has_attr(attrs, "onClick") and not has_attr(attrs, "onclick"):
                continue
            if has_attr(attrs, "role") or has_attr(attrs, "tabIndex") or has_attr(attrs, "tabindex"):
                continue
            ln = line_of(text, start)
            if not overlaps(touched, ln, ln):
                continue
            out.append((f"{p}:{ln}",
                        f"<{tag}> has onClick with no role/tabIndex -- not focusable, "
                        f"not keyboard-operable, invisible to assistive tech; use <button>"))
    return out


IMG_TAGS = {"img", "Image"}


def check_img_no_alt(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for tag, attrs, _, _, start in jsx_tags(text, IMG_TAGS):
            ln = line_of(text, start)
            if not overlaps(touched, ln, ln):
                continue
            if not has_attr(attrs, "alt"):
                out.append((f"{p}:{ln}",
                            f"<{tag}> has no alt attribute -- add descriptive alt text, "
                            f'or alt="" if purely decorative (that is a decision, not an omission)'))
    return out


def check_img_no_dimensions(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for tag, attrs, _, _, start in jsx_tags(text, IMG_TAGS):
            ln = line_of(text, start)
            if not overlaps(touched, ln, ln):
                continue
            has_dims = has_attr(attrs, "width") and has_attr(attrs, "height")
            has_fill = has_attr(attrs, "fill")
            has_ar = has_attr(attrs, "aspectRatio") or "aspect-ratio" in attrs
            if not (has_dims or has_fill or has_ar):
                out.append((f"{p}:{ln}",
                            f"<{tag}> has no width/height, fill, or aspect-ratio -- "
                            f"CLS risk: the layout shifts once the image loads"))
    return out


FORM_TAGS = {"input", "select", "textarea"}


def check_form_field_no_label(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for tag, attrs, _, _, start in jsx_tags(text, FORM_TAGS):
            ln = line_of(text, start)
            if not overlaps(touched, ln, ln):
                continue
            typ = attr_value(attrs, "type")
            if typ and typ.strip("\"'{}").strip().lower() == "hidden":
                continue
            if has_attr(attrs, "aria-label") or has_attr(attrs, "aria-labelledby"):
                continue
            idv = attr_value(attrs, "id")
            labeled = False
            if idv:
                idv_clean = idv.strip("\"'{} ")
                if idv_clean and (
                    re.search(r"htmlFor\s*=\s*[\"'{]*\s*" + re.escape(idv_clean) + r"\b", text)
                    or re.search(r"\bfor\s*=\s*[\"']" + re.escape(idv_clean) + r"[\"']", text)
                ):
                    labeled = True
            if not labeled:
                out.append((f"{p}:{ln}",
                            f"<{tag}> has no accessible label -- pair `id` with a "
                            f"`label htmlFor`, or add aria-label/aria-labelledby"))
    return out


CONTROL_TAGS = {"button", "a"}


def is_icon_only_children(children):
    """True if `children` is empty, a null/false expression, or exactly one
    capitalized component / svg element and nothing else -- i.e. no text node
    that could serve as an accessible name."""
    stripped = re.sub(r"\{/\*.*?\*/\}", "", children, flags=re.S).strip()
    if not stripped:
        return True
    if re.fullmatch(r"\{\s*(null|false|undefined)?\s*\}", stripped):
        return True
    m = re.match(r"^<([A-Za-z][\w.]*)\b[^>]*?(/?)>", stripped, re.S)
    if not m:
        return False
    tagname, selfclose = m.group(1), m.group(2)
    if not (tagname[0].isupper() or tagname == "svg"):
        return False
    if selfclose == "/":
        return stripped[m.end():].strip() == ""
    close_rx = re.compile(r"</\s*" + re.escape(tagname) + r"\s*>\s*$", re.S)
    return bool(close_rx.search(stripped))


def check_control_no_accessible_name(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for tag, attrs, gt_idx, self_closing, start in jsx_tags(text, CONTROL_TAGS):
            ln = line_of(text, start)
            if not overlaps(touched, ln, ln):
                continue
            if has_attr(attrs, "aria-label") or has_attr(attrs, "aria-labelledby") or has_attr(attrs, "title"):
                continue
            if self_closing:
                continue
            children = scan_children(text, tag, gt_idx)
            if children is None:
                continue
            if is_icon_only_children(children):
                out.append((f"{p}:{ln}",
                            f"<{tag}> has no accessible name -- icon-only or empty "
                            f"content with no aria-label; an icon-only control is unusable"))
    return out


OUTLINE_NONE_RX = re.compile(r"outline\s*:\s*(?:none|0)\b")
FOCUS_VISIBLE_RX = re.compile(r":focus-visible")


def check_outline_none(files, base):
    out = []
    for p in files:
        if not p.endswith(SCAN_EXT):
            continue
        text = read(p)
        if text is None or FOCUS_VISIBLE_RX.search(text):
            continue
        touched = touched_lines(p, base)
        for m in OUTLINE_NONE_RX.finditer(text):
            ln = line_of(text, m.start())
            if not overlaps(touched, ln, ln):
                continue
            out.append((f"{p}:{ln}",
                        "outline removed (outline: none/0) with no :focus-visible "
                        "rule in this file -- keyboard users lose the focus indicator"))
    return out


TABINDEX_RX = re.compile(r"tab[Ii]ndex\s*=\s*[\"'{]?\s*(-?\d+)\s*[\"'}]?")


def check_positive_tabindex(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for m in TABINDEX_RX.finditer(text):
            n = int(m.group(1))
            if n <= 0:
                continue
            ln = line_of(text, m.start())
            if not overlaps(touched, ln, ln):
                continue
            out.append((f"{p}:{ln}",
                        f"tabIndex={{{n}}} is positive -- breaks natural focus order; use 0 or -1"))
    return out


def check_anchor_no_href(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for tag, attrs, _, _, start in jsx_tags(text, {"a"}):
            if not (has_attr(attrs, "onClick") or has_attr(attrs, "onclick")):
                continue
            if has_attr(attrs, "href"):
                continue
            ln = line_of(text, start)
            if not overlaps(touched, ln, ln):
                continue
            out.append((f"{p}:{ln}",
                        "<a> with onClick and no href -- used as a button; "
                        "use <button> or add a real href"))
    return out


# WAI-ARIA 1.3 states and properties -- w3c/aria@main:index.html (full attribute
# index). Kept lowercase for case-insensitive comparison.
KNOWN_ARIA = {
    "aria-activedescendant", "aria-atomic", "aria-autocomplete", "aria-braillelabel",
    "aria-brailleroledescription", "aria-busy", "aria-checked", "aria-colcount",
    "aria-colindex", "aria-colindextext", "aria-colspan", "aria-controls",
    "aria-current", "aria-describedby", "aria-description", "aria-details",
    "aria-disabled", "aria-dropeffect", "aria-errormessage", "aria-expanded",
    "aria-flowto", "aria-grabbed", "aria-haspopup", "aria-hidden", "aria-invalid",
    "aria-keyshortcuts", "aria-label", "aria-labelledby", "aria-level", "aria-live",
    "aria-modal", "aria-multiline", "aria-multiselectable", "aria-notify",
    "aria-orientation", "aria-owns", "aria-placeholder", "aria-posinset",
    "aria-pressed", "aria-readonly", "aria-relevant", "aria-required",
    "aria-roledescription", "aria-rowcount", "aria-rowindex", "aria-rowindextext",
    "aria-rowspan", "aria-selected", "aria-setsize", "aria-sort", "aria-valuemax",
    "aria-valuemin", "aria-valuenow", "aria-valuetext",
}
ARIA_ATTR_RX = re.compile(r"(?:^|\s)(aria-[\w-]+)\s*=")


def check_unknown_aria(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        seen = set()
        for m in ARIA_ATTR_RX.finditer(text):
            name = m.group(1)
            if name.lower() in KNOWN_ARIA:
                continue
            ln = line_of(text, m.start())
            key = (ln, name)
            if key in seen or not overlaps(touched, ln, ln):
                continue
            seen.add(key)
            out.append((f"{p}:{ln}", f"`{name}` is not a known ARIA attribute -- possible typo"))
    return out


AUTOFOCUS_RX = re.compile(r"(?:^|\s)autoFocus\b")


def check_autofocus(files, base):
    out = []
    for p in files:
        if not p.endswith(MARKUP_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        for m in AUTOFOCUS_RX.finditer(text):
            ln = line_of(text, m.start())
            if not overlaps(touched, ln, ln):
                continue
            out.append((f"{p}:{ln}",
                        "autoFocus -- moves focus without the user's initiation; "
                        "confusing for screen-reader users, review whether it's needed"))
    return out


DURATION_RX = re.compile(
    r"(?:animation|transition)(?:-duration|Duration)?\s*:\s*[^;{}\n]*?(\d*\.?\d+)(m?s)\b")
REDUCED_MOTION_RX = re.compile(r"prefers-reduced-motion")


def check_animation_no_reduced_motion(files, base):
    out = []
    for p in files:
        if not p.endswith(SCAN_EXT):
            continue
        text = read(p)
        if text is None or REDUCED_MOTION_RX.search(text):
            continue
        touched = touched_lines(p, base)
        seen = set()
        for m in DURATION_RX.finditer(text):
            dur = float(m.group(1))
            if dur <= 0:
                continue
            ln = line_of(text, m.start())
            if ln in seen or not overlaps(touched, ln, ln):
                continue
            seen.add(ln)
            out.append((f"{p}:{ln}",
                        "animation/transition with a positive duration and no "
                        "prefers-reduced-motion guard anywhere in this file"))
    return out


BLOCKING = {"onclick-non-interactive", "img-no-alt", "form-field-no-label",
            "control-no-accessible-name"}


def build_checks():
    return {
        "onclick-non-interactive": check_onclick_non_interactive,
        "img-no-alt": check_img_no_alt,
        "img-no-dimensions": check_img_no_dimensions,
        "form-field-no-label": check_form_field_no_label,
        "control-no-accessible-name": check_control_no_accessible_name,
        "outline-none-no-focus-visible": check_outline_none,
        "positive-tabindex": check_positive_tabindex,
        "anchor-no-href": check_anchor_no_href,
        "unknown-aria-attribute": check_unknown_aria,
        "autofocus": check_autofocus,
        "animation-no-reduced-motion": check_animation_no_reduced_motion,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="compare against this ref (default: HEAD)")
    ap.add_argument("--only", default=None, help="comma-separated subset of checks")
    ap.add_argument("--strict", action="store_true", help="treat advisory checks as failures")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

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
    files = added + mod
    if not files:
        print("a11y_check: no changes to inspect")
        return 0

    hard = advisory = 0
    for n in names:
        try:
            res = checks[n](files, args.base)
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

    print(f"\na11y_check: {len(files)} file(s) touched | {hard} blocking, {advisory} advisory")
    print("heuristic tool: regex + tag scanning, no runtime state -- pair with a "
          "keyboard-only pass and a screen-reader pass (see skills/accessibility/SKILL.md)")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
