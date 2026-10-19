#!/usr/bin/env python3
"""Advisory lint for human-facing text: PR bodies, commits, review comments, replies, docs.

The rules are docs/WRITING.md's; each finding names the rule id that section cites. In
the survey the best and worst PR bodies used the same links, tables and code blocks; what
separated them was length relative to the diff and proof next to each claim. So most
checks here measure proportion and evidence, not style.
SOURCE: original (private-repo PR communication survey: 120 human PRs, 251 inline review comments)

Heuristic by construction: it reads markdown line by line, skips fenced code, tables,
quotes and HTML comments, and will miss a claim phrased oddly. Warn-only by default.

    prose_check.py --kind pr --diff-lines 40 body.md
    gh pr view 12 --json body -q .body | prose_check.py --kind pr --diff-lines 40 -
    prose_check.py --kind review-comment --strict comment.md

Prints `<file>:<line>: [<rule>] <message>` and a count line. Exit 0, or 1 with --strict
when anything was found; 2 when an input cannot be read. Python stdlib only.
"""
import argparse
import re
import sys

from check_claims import CITE_RX

KINDS = ("doc", "pr", "commit", "review-comment", "reply", "code-comment", "chat")

# Thresholds from the survey: best bodies had no paragraph over 300 chars, best bullets
# ran p90 144 chars, and history sections appeared only in the worst bodies.
PARA_LINES, PARA_CHARS = 3, 300
BULLET_CHARS = 160
HISTORY_DIFF, HEADING_DIFF, MAX_HEADINGS = 200, 100, 4
BUDGET_FLOOR, BUDGET_PER_LINE = 600, 8
HEADING_WALL = 3        # headings stacked before any text
ISSUE_LINK_LINES = 3    # where a reader looks for what the PR closes
MAX_ASK_BULLETS = 3

FENCE_RX = re.compile(r"^\s*(```|~~~)")
HEADING_RX = re.compile(r"^\s{0,3}#{1,6}\s+\S")
BULLET_RX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TICKED_RX = re.compile(r"^\s*[-*+]\s+\[[xX]\]")
CHECKBOX_RX = re.compile(r"^\s*[-*+]\s+\[[ xX]\]")
BACKLINK_RX = re.compile(r"^\s*\[[^\]]*\]\([^)]*\)\s*$")
CODE_SPAN_RX = re.compile(r"`[^`]+`")
URL_RX = re.compile(r"https?://\S+")
SHA_RX = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
LINK_RX = re.compile(r"https?://|\]\([^)]+\)|(?<![\w&])#\d+\b")

# Only claim phrasing: "values are passed by reference" or "confirmed by email" is an
# ordinary verb, not a statement that something was run.
CLAIM_RX = re.compile(
    r"\b(?:tests?|specs?|checks?|build|CI|suite)\s+(?:all\s+)?(?:passed|pass(?:es|ing)?)\b"
    r"|\bverified\b(?!\s+by\b|-)"
    r"|\b(?:I|we)(?:\s+have|'ve)?\s+tested\b"
    r"|\btested\s+(?:locally|on|in|against)\b"
    r"|\bconfirmed\s+(?:that|it\s+works|working|locally)\b"
    r"|\b100\s?%\s+(?:test\s+)?coverage\b", re.I)
NEGATED_RX = re.compile(r"(\bnot|\bnever|n't|\bnothing)\s+(been\s+|yet\s+)?$", re.I)
FILLER_RX = re.compile(r"\b(This PR|Successfully|I have|I've|As requested|In conclusion|"
                       r"It's worth noting|It is worth noting)\b", re.I)
HISTORY_RX = re.compile(r"^\s{0,3}#{1,6}\s+(History|Timeline|Background[\s/&-]*(and\s+)?history)\b",
                        re.I)
ISSUE_RX = re.compile(r"\b(closes|closed|fixes|fixed|resolves|resolved|part of|refs?)\b\s*:?\s*"
                      r"(\S*#\d+|[A-Z][A-Z0-9]+-\d+)|https?://\S+/(issues|pull)/\d+", re.I)
SEVERITY_RX = re.compile(r"^[\s*_]*(\[(MUST|SHOULD|NIT|ASK|IMO)\]|(issue|suggestion|nitpick|nit|"
                         r"question|praise|thought|todo|chore|note|blocking|should-fix|optional)"
                         r"\b[^:\n]{0,30}:)", re.I)
STRONG_RX = re.compile(r"^[\s*_]*(\[(MUST|SHOULD)\]|(issue|blocking|should-fix)\b)", re.I)
SCENARIO_RX = re.compile(r"→|->|=>|\b\w+(Error|Exception)\b|\b[45]\d\d\b")
FIXED_RX = re.compile(r"(?:^|[.!?;:]\s+)[\s>*_`-]*(done|fixed|addressed)\b", re.I | re.M)
COMMENT_MARK_RX = re.compile(r"^\s*(#+|//+|/\*+|\*+/?|--|\"\"\"|''')\s*")
# What-narration names a mechanic ("This function loops..."); "This function is pure;
# callers rely on that" states a contract, which is the why a comment is for.
NARRATION_RX = re.compile(r"^(This (function|method|code)|Here,? we|Now we)\s+"
                          r"(takes?|returns?|loops?|iterates?|calls?|gets?|sets?|creates?|"
                          r"checks?|does|do|will)\b", re.I)


class Doc:
    """The text split into classified lines and blocks, so every rule skips the same things."""

    def __init__(self, text, kind, diff_lines):
        self.text, self.kind, self.diff_lines = text, kind, diff_lines
        self.lines = text.splitlines()
        self.classes = classify(self.lines)
        self.blocks = group_blocks(self.lines, self.classes)

    def list_prose(self):
        """(line number, text with code spans removed) for lines a reader reads as prose."""
        return [(i, CODE_SPAN_RX.sub("", line))
                for i, (line, cls) in enumerate(zip(self.lines, self.classes), 1)
                if cls in ("text", "bullet", "check")]


def classify_line(line):
    """The class of one line outside fences and HTML comments."""
    stripped = line.strip()
    if not stripped:
        return "blank"
    if HEADING_RX.match(line):
        return "heading"
    if stripped.startswith("|"):
        return "table"
    if stripped.startswith(">"):
        return "quote"
    if CHECKBOX_RX.match(line):
        return "check"
    if BULLET_RX.match(line):
        return "bullet"
    return "text"


def classify(lines):
    classes, fence, html = [], False, False
    for line in lines:
        if FENCE_RX.match(line):
            fence = not fence
            classes.append("fence")
            continue
        if fence:
            classes.append("code")
            continue
        if html or line.strip().startswith("<!--"):
            html = "-->" not in line
            classes.append("comment")
            continue
        classes.append(classify_line(line))
    return classes


def group_blocks(lines, classes):
    """[(kind, first line number, [lines])] for paragraphs and bullets (with continuations)."""
    blocks = []
    for i, (line, cls) in enumerate(zip(lines, classes), 1):
        prev = blocks[-1] if blocks else None
        joined = prev and prev[1] + len(prev[2]) == i
        if cls == "text" and joined and prev[0] in ("paragraph", "bullet") \
                and (prev[0] == "paragraph" or line[:1].isspace()):
            prev[2].append(line)
        elif cls == "text":
            blocks.append(("paragraph", i, [line]))
        elif cls in ("bullet", "check"):
            blocks.append(("bullet", i, [line]))
    return blocks


def flag(rule, line, message):
    return {"rule": rule, "line": line, "message": message}


def is_too_long(block_lines):
    return len(block_lines) > PARA_LINES or len(" ".join(l.strip() for l in block_lines)) > PARA_CHARS


def has_evidence(line):
    return bool(CODE_SPAN_RX.search(line) or SHA_RX.search(line) or LINK_RX.search(line)
                or CITE_RX.search(line))


def find_next_content(doc, i):
    """The class and text of the first non-blank line after line number i."""
    for j in range(i, len(doc.lines)):
        if doc.classes[j] != "blank":
            return doc.classes[j], doc.lines[j]
    return None, ""


def check_budget(doc):
    if doc.diff_lines is None:
        return []
    body = re.sub(r"<!--.*?-->", "", doc.text, flags=re.S).strip()
    limit = max(BUDGET_FLOOR, BUDGET_PER_LINE * doc.diff_lines)
    if len(body) <= limit:
        return []
    return [flag("body-budget", 1, f"body is {len(body)} chars; a {doc.diff_lines}-line diff gets "
                 f"at most {limit} (max(600, 8 x diff lines)); cut history and diff restating")]


def check_paragraphs(doc):
    out = []
    paragraphs = [b for b in doc.blocks if b[0] == "paragraph"]
    if doc.kind == "doc" and paragraphs:
        paragraphs = paragraphs[1:]  # the opening paragraph is summary-first's to report
    for _, line, block in paragraphs:
        if is_too_long(block):
            size = len(" ".join(l.strip() for l in block))
            out.append(flag("long-paragraph", line, f"paragraph is {len(block)} lines, {size} chars; "
                            f"keep it to {PARA_LINES} lines and {PARA_CHARS} chars, or use bullets"))
    return out


def check_claim_evidence(doc):
    out = []
    for i, line in doc.list_prose():
        match = CLAIM_RX.search(line)
        if not match or NEGATED_RX.search(line[:match.start()]):
            continue
        next_cls, next_line = find_next_content(doc, i)
        if has_evidence(doc.lines[i - 1]) or next_cls == "fence" or has_evidence(next_line):
            continue
        out.append(flag("claim-without-evidence", i, f"'{match.group(0)}' with no command and "
                        "output, sha, link or file:line on this or the next line"))
    return out


def check_filler(doc):
    out = []
    for i, line in doc.list_prose():
        phrases = [m.group(1) for m in FILLER_RX.finditer(line)]
        if phrases:
            out.append(flag("filler-phrase", i, f"{', '.join(map(repr, phrases))}: filler; "
                            "start with the change or the answer"))
    return out


def check_bullets(doc):
    out = []
    for kind, line, block in doc.blocks:
        size = len(" ".join(l.strip() for l in block))
        if kind == "bullet" and size > BULLET_CHARS:
            out.append(flag("long-bullet", line, f"bullet is {size} chars; keep it under "
                            f"{BULLET_CHARS} or split it"))
    return out


def check_ticked(doc):
    return [flag("self-ticked-box", i, "ticked box in a PR body; put the command and its output "
                 "under Verified instead")
            for i, line in enumerate(doc.lines, 1)
            if doc.classes[i - 1] == "check" and TICKED_RX.match(line)]


def list_headings(doc):
    return [(i, l) for i, (l, c) in enumerate(zip(doc.lines, doc.classes), 1) if c == "heading"]


def check_history(doc):
    if doc.diff_lines is None or doc.diff_lines >= HISTORY_DIFF:
        return []
    return [flag("history-section", i, f"history/timeline section for a {doc.diff_lines}-line "
                 "diff; link the decision instead")
            for i, heading in list_headings(doc) if HISTORY_RX.match(heading)]


def check_heading_count(doc):
    found = list_headings(doc)
    if doc.diff_lines is None or doc.diff_lines >= HEADING_DIFF or len(found) <= MAX_HEADINGS:
        return []
    return [flag("heading-overload", found[MAX_HEADINGS][0], f"{len(found)} headings for a "
                 f"{doc.diff_lines}-line diff; {MAX_HEADINGS} is plenty")]


def check_issue_link(doc):
    content = [l for l, c in zip(doc.lines, doc.classes) if c not in ("blank", "comment")]
    if any(ISSUE_RX.search(l) for l in content[:ISSUE_LINK_LINES]):
        return []
    return [flag("missing-issue-link", 1, "no 'closes #N', 'part of #N' or issue URL in the "
                 "first 3 lines (warning)")]


def find_first_content(doc):
    for i, (line, cls) in enumerate(zip(doc.lines, doc.classes), 1):
        if cls not in ("blank", "comment"):
            return i, line
    return 1, ""


def check_review_comment(doc):
    out = []
    line_no, first = find_first_content(doc)
    if not SEVERITY_RX.match(first):
        out.append(flag("review-comment-no-severity", line_no, "start with [MUST], [SHOULD], "
                        "[NIT] or [ASK] so the author knows whether to act"))
    asks = sum(URL_RX.sub("", text).count("?") for _, text in doc.list_prose())
    bullets = sum(1 for b in doc.blocks if b[0] == "bullet")
    if asks > 1 or bullets > MAX_ASK_BULLETS:
        out.append(flag("review-comment-multi-ask", line_no, f"{asks} questions, {bullets} "
                        "bullets; one ask per comment, split the rest"))
    if STRONG_RX.match(first) and not SCENARIO_RX.search(doc.text) and "fence" not in doc.classes:
        out.append(flag("review-comment-no-scenario", line_no, "MUST/SHOULD with no failure "
                        "scenario: give input → failure, the error, the status code or a code block"))
    return out


def check_reply(doc):
    match = FIXED_RX.search(doc.text)
    if not match or SHA_RX.search(doc.text):
        return []
    line = doc.text.count("\n", 0, match.start(1)) + 1
    return [flag("reply-fixed-no-sha", line, f"'{match.group(1)}' with no commit sha; write "
                 "'Done in <sha>: <what changed>'")]


def check_summary_first(doc):
    stack = 0
    for i, (line, cls) in enumerate(zip(doc.lines, doc.classes), 1):
        if cls in ("blank", "comment") or (stack == 0 and BACKLINK_RX.match(line)):
            continue
        if cls == "heading":
            stack += 1
            continue
        if stack >= HEADING_WALL:
            return [flag("summary-first", i, f"{stack} headings before any text; open with the "
                         "answer in 2-5 lines")]
        block = next((b for b in doc.blocks if b[1] == i), None)
        if block and block[0] == "paragraph" and is_too_long(block[2]):
            return [flag("summary-first", i, "opening paragraph is over 3 lines; put the answer "
                         "first in 2-5 short lines or a summary table")]
        return []
    return []


def check_narration(doc):
    out = []
    for i, line in enumerate(doc.lines, 1):
        if NARRATION_RX.match(COMMENT_MARK_RX.sub("", line, count=1)):
            out.append(flag("code-comment-narration", i, "comment restates the code; say why, "
                            "or link the issue or decision"))
    return out


COMMON = (check_paragraphs, check_claim_evidence, check_filler, check_bullets)
BY_KIND = {
    "doc": COMMON + (check_summary_first, check_history, check_heading_count),
    "pr": COMMON + (check_budget, check_ticked, check_history, check_heading_count, check_issue_link),
    "commit": COMMON,
    "chat": COMMON,
    "review-comment": COMMON + (check_review_comment,),
    "reply": COMMON + (check_reply,),
    "code-comment": (check_narration,),
}


def check_text(text: str, kind: str = "doc", diff_lines: "int | None" = None) -> list:
    """Every finding for `text` read as `kind`, as {"rule", "line", "message"} dicts by line."""
    if kind not in BY_KIND:
        raise ValueError(f"unknown kind {kind!r}; one of {', '.join(KINDS)}")
    doc = Doc(text, kind, diff_lines)
    found = [f for rule in BY_KIND[kind] for f in rule(doc)]
    return sorted(found, key=lambda f: (f["line"], f["rule"]))


def read_input(name):
    if name == "-":
        return sys.stdin.read()
    with open(name, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Advisory lint for human-facing text "
                                                 "(docs/WRITING.md).")
    parser.add_argument("--kind", choices=KINDS, default="doc")
    parser.add_argument("--diff-lines", type=int, default=None,
                        help="changed lines in the diff; enables body-budget, history and "
                             "heading checks")
    parser.add_argument("--strict", action="store_true", help="exit 1 when anything is found")
    parser.add_argument("files", nargs="*", default=["-"], help="files to check, or - for stdin")
    args = parser.parse_args(argv)
    if args.kind == "pr" and args.diff_lines is None:
        print("prose_check: body-budget skipped; pass --diff-lines N", file=sys.stderr)
    total = 0
    for name in args.files:
        try:
            text = read_input(name)
        except OSError as e:
            print(f"prose_check: cannot read {name}: {e.strerror}", file=sys.stderr)
            return 2
        for f in check_text(text, args.kind, args.diff_lines):
            print(f"{name}:{f['line']}: [{f['rule']}] {f['message']}")
            total += 1
    print(f"prose_check: {total} finding(s) in {len(args.files)} input(s)"
          + ("" if args.strict else ", advisory"))
    return 1 if args.strict and total else 0


if __name__ == "__main__":
    sys.exit(main())
