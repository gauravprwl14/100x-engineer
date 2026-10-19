"""Markdown record helpers shared by prd.py, plan_feature.py, testplan.py and plan_dag.py.

Not a standalone tool. Three things every record tool needs and must not disagree on:

  - tables and sections: `rows_of`, `kv_table`, `find_section`, `section_by_rx`;
  - acceptance criteria: `parse_criteria` / `parse_acs`, the ONE parser for `AC-<n>`
    definitions, so four tools cannot disagree about which criteria a spec defines;
  - record arguments: `find_record`, so `audit specs/login`, `audit login` and
    `audit docs/engineering/specs/login` all reach the same file.

An acceptance criterion is a line that STARTS with its id. When the document has an
"Acceptance criteria" section (a spec's `## 2b. Acceptance criteria`), only that
section defines criteria: a verification-table row or a prose line elsewhere ("AC-4
was dropped") is a mention. Without such a section (a PRD, a hand-written doc) the
whole document is read. The canonical line is the one `plan_feature new` writes:

    AC-1: A member can tag up to 10 people on a photo. (R1, S1)

and two older shapes are still read: `- **AC-1** text` and `| AC-2 | text |`. A bare
`AC-4 was dropped` -- no separator, no bold, no table pipe -- is never a definition.
"""
import pathlib
import re

TABLE_RX = re.compile(r"^\|(.+)\|\s*$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")

# A definition needs a marker after the id: a separator, the closing ** of a bold id,
# or the cell pipe of a table row. Without one, "AC-4 was dropped" would define AC-4.
AC_DEF = re.compile(
    r"^\s*(?:[-*+]\s+|\d+\.\s+)?"
    r"(?:\|\s*(?P<t>AC-(?P<tn>\d+))\s*\|"
    r"|(?:\*\*|__)\[?(?P<b>AC-(?P<bn>\d+))\]?(?:\*\*|__)\s*[:.)—–-]*"
    r"|\[?(?P<p>AC-(?P<pn>\d+))\]?\s*[:.)—–-]+)"
    r"\s*(?P<body>.*)$")
AC_TAG = re.compile(r"(?<![A-Za-z0-9])@?AC-(\d+)(?![0-9])")
# Trailing "(R1, S2)" on a definition: the PRD requirements and in-scope rows it traces to.
# AC_LINKS is kept for importers; parse_criteria does not use it, because `.search` on
# a long line of spaces backtracks quadratically (40 KB took 5 s). `_trailing_links`
# finds the same parenthesis with one rfind and a linear fullmatch.
AC_LINKS = re.compile(r"\s*\(\s*((?:[RS]\d+)(?:\s*[,;]\s*[RS]\d+)*)\s*\)\s*$")
LINKS_INNER = re.compile(r"\s*[RS]\d+(?:\s*[,;]\s*[RS]\d+)*\s*")
AC_SECTION_RX = re.compile(r"^(#{2,6})\s+(?:§\s*)?(?:\d+[a-z]?\.\s+)?Acceptance criteria\b.*$",
                           re.I)


def cells(inner):
    r"""Split a markdown table row on unescaped pipes; a cell may legitimately
    contain an escaped pipe, e.g. an options list 'a \| b \| c'."""
    return [c.strip().replace("\\|", "|") for c in CELL_SPLIT.split(inner)]


def is_separator(cs):
    return set("".join(cs)) <= set("-: ")


def rows_of(text, header_contains):
    """Data rows of the markdown table whose header line contains a marker."""
    out, in_tbl = [], False
    for line in text.splitlines():
        m = TABLE_RX.match(line)
        if not m:
            in_tbl = False
            continue
        cs = cells(m.group(1))
        if header_contains in line:
            in_tbl = True
            continue
        if in_tbl and not is_separator(cs):
            out.append(cs)
    return out


def kv_table(sec_text):
    """A two-column `| field | value |` table as a dict keyed by lower-cased field."""
    d = {}
    for line in sec_text.splitlines():
        m = TABLE_RX.match(line)
        if not m:
            continue
        cs = cells(m.group(1))
        if len(cs) != 2 or is_separator(cs):
            continue
        if cs[0].strip().lower() in ("field", "constraint"):
            continue
        d[cs[0].strip().lower()] = cs[1].strip()
    return d


def header_field(text, name):
    """Value of a `| name | value |` row anywhere in the document, '' when absent."""
    m = re.search(rf"^\|\s*{re.escape(name)}\s*\|\s*(.+?)\s*\|\s*$", text, re.I | re.M)
    return m.group(1).strip() if m else ""


def status_field(text):
    """The record's `| status |` header value reduced to its leading word, lower-cased:
    `**draft — not ready to implement**` -> 'draft', `**ready**` -> 'ready'; '' when
    the header has no status row."""
    m = re.match(r"[\s*_`]*([A-Za-z][A-Za-z-]*)", header_field(text, "status"))
    return m.group(1).lower() if m else ""


def section_by_rx(text, rx):
    """(1-based first body line, body) of the first '## ' section whose heading
    matches rx; (None, None) when absent. The body ends at the next '## '."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if rx.match(line.strip()):
            body = []
            for m in lines[i + 1:]:
                if m.startswith("## "):
                    break
                body.append(m)
            return i + 2, "\n".join(body)
    return None, None


def find_section(text, name):
    """Body of '## [N. ]<name>' (number-agnostic, case-insensitive), or None."""
    rx = re.compile(rf"^##\s+(?:\d+[a-z]?\.\s+)?{re.escape(name)}\s*$", re.I)
    return section_by_rx(text, rx)[1]


def section_body(text, heading):
    """Body of exactly '## <heading>', stripped, or None."""
    body = section_by_rx(text, re.compile(rf"^## {re.escape(heading)}$"))[1]
    return None if body is None else body.strip()


# ---------------------------------------------------------------- acceptance criteria

FENCE_RX = re.compile(r"^ {0,3}(`{3,}|~{3,})")


class _Fences:
    """Fenced-code-block state, fed one line at a time. A fence opens on a line
    starting (after up to three spaces) with ``` or ~~~ and closes only on a run of
    the SAME character at least as long, so a ``` inside a ~~~ block stays content.
    `step(line)` is True when the line is a fence delimiter or inside a block."""

    def __init__(self):
        self.open = None

    def step(self, line):
        m = FENCE_RX.match(line)
        if self.open is None:
            if m:
                self.open = m.group(1)
                return True
            return False
        if m and m.group(1)[0] == self.open[0] and len(m.group(1)) >= len(self.open) \
                and not line.strip().lstrip(self.open[0]):
            self.open = None
        return True


def ac_section(text):
    """(offset, body) of the acceptance-criteria section, ends at the next heading of
    the same or a higher level; (None, None) when the document has none.

    Fenced code blocks are content, never structure: a heading inside a fence neither
    opens the section (a quoted `## Acceptance criteria` example) nor ends it (a
    `# create a tag` comment in a ```bash block)."""
    lines = text.splitlines()
    fences = _Fences()
    for i, line in enumerate(lines):
        if fences.step(line):
            continue
        m = AC_SECTION_RX.match(line.strip())
        if not m:
            continue
        level, body, inner = len(m.group(1)), [], _Fences()
        for nxt in lines[i + 1:]:
            if not inner.step(nxt):
                h = re.match(r"^(#{1,6})\s", nxt)
                if h and len(h.group(1)) <= level:
                    break
            body.append(nxt)
        return i + 1, "\n".join(body)
    return None, None


def _trailing_links(body):
    """(body without its trailing "(R1, S2)", [link ids]); the body unchanged and []
    when it does not end in a link parenthesis. Linear in the line length."""
    s = body.rstrip()
    i = s.rfind("(")
    if not s.endswith(")") or i < 0 or not LINKS_INNER.fullmatch(s, i + 1, len(s) - 1):
        return body, []
    return s[:i].rstrip(), re.findall(r"[RS]\d+", s[i + 1:-1])


def parse_criteria(text, scoped=True):
    """Every AC definition line in document order, duplicates included:
    [{"id", "num", "text", "links", "line", "raw"}].

    scoped=True reads only the acceptance-criteria section when the document has one.
    `text` has the trailing link parenthesis removed (so "(R1)" never reads as a
    boundary number); `links` lists the R/S ids it named. A fenced code block is an
    example, not a criterion."""
    offset = 0
    if scoped:
        off, body = ac_section(text)
        if body is not None:
            offset, text = off, body
    out, fences = [], _Fences()
    for n, line in enumerate(text.splitlines(), 1):
        if fences.step(line):
            continue
        m = AC_DEF.match(line)
        if not m:
            continue
        acid = m.group("t") or m.group("b") or m.group("p")
        num = m.group("tn") or m.group("bn") or m.group("pn")
        body = m.group("body").strip().rstrip("|").strip()
        # split/join, not re.sub(r"\s*\|\s*"): the regex is quadratic on long blank runs
        body = " — ".join(part.strip() for part in body.split("|")).strip(" —")
        body, links = _trailing_links(body)
        out.append({"id": acid, "num": int(num), "text": body, "links": links,
                    "line": n + offset, "raw": line})
    return out


def parse_acs(text):
    """Ordered {id: text}; the first defining line of an id wins."""
    acs = {}
    for c in parse_criteria(text):
        acs.setdefault(c["id"], c["text"] or "(no text)")
    return dict(sorted(acs.items(), key=lambda kv: int(kv[0][3:])))


def ac_key(s):
    m = re.search(r"(\d+)$", s)
    return (int(m.group(1)) if m else 0, s)


# ---------------------------------------------------------------- record arguments

def find_record(arg, collection, filename, repo, records):
    """Resolve a record argument to its file, or None.

    `arg` may be the file, its directory, or a bare name. Tried in order: as given
    (relative to the cwd), relative to the git root, relative to the records root
    (`specs/login` -> <root>/specs/login), and as a bare name (<root>/<collection>/
    login). The records root is where `plan_feature new` and `prd new` write; a user
    or agent copying `specs/<name>` from a message must not get exit 2 because the
    path was resolved against the repo top level instead."""
    raw = pathlib.Path(arg)
    cands = [raw] if raw.is_absolute() else [
        pathlib.Path.cwd() / raw, pathlib.Path(repo) / raw, pathlib.Path(records) / raw,
        pathlib.Path(records) / collection / raw]
    for c in cands:
        if c.is_file() and (c.name == filename or c.suffix == ".md"):
            return c
        if c.is_dir() and (c / filename).is_file():
            return c / filename
    return None


def not_found(arg, collection, filename, records, show):
    return (f"no {filename} for {arg!r} — tried it as given, relative to the git root, "
            f"under the records root ({show(records)}), and as "
            f"{show(pathlib.Path(records) / collection / arg)}")
