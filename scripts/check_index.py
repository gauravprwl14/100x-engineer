#!/usr/bin/env python3
"""Require a navigable index in documents people traverse to find information.

Two failures, both of which appear once a project has more than a handful of records:

  COLLECTION level -- hundreds of specs with no single file listing them. You cannot
  find the one you need without opening them.
  DOCUMENT level -- a 500-line findings file with 13 sections and no summary, so
  answering "is the answer in here?" costs a full read.

A book solves both: a shelf catalogue, and a table of contents in every volume. This
enforces the same thing, and only where it pays -- long documents you read to extract
information, never short ones or fixed-structure files like SKILL.md or a generated
spec.md / prd.md (recognised by the header table its generator writes).

    check_index.py                       # check the whole repo
    check_index.py research/             # one tree
    check_index.py --fix-stubs           # insert a Contents skeleton to fill in
    check_index.py --json
    check_index.py --gen-terms           # write TERMS.md, the back-of-book term index
    check_index.py --check-terms         # exit 1 if TERMS.md is stale
    check_index.py --register docs/engineering/architecture/auth.md
                                         # add/update its row in <records root>/INDEX.md

The term index (docs/OPERATING-MODEL.md section 8) maps each term to every file#anchor
where it is defined or used as a section title. A term is any of:
  - a bold term in definition position: `**term** —`, `**term**:`, `**term:**`,
    `**term** is ...`;
  - the first-column entry of a table under a heading containing "glossary",
    "terms" or "definitions";
  - a level-2 or level-3 heading.
Anchors follow GitHub's slug rule (lowercase, drop punctuation except `-` and `_`,
spaces to `-`, `-1`/`-2` suffixes for repeated headings), so every link resolves on
GitHub. Terms are deduplicated case-insensitively. Too-generic terms are dropped:
  - GENERIC_TERMS below (structural headings such as "Contents", "Rules", "Verify",
    "Sources", "Overview", "Next"), compared case-insensitively;
  - a heading that appears in more than MAX_HEADING_FILES files and is never
    bold-defined: it is document scaffolding (every SKILL.md has "Failure modes"),
    not vocabulary;
  - anything under 3 or over 60 characters, over 6 words (5 for a bold term), with
    no letter, starting with a digit, ending in "?" (a question is not a term), or
    containing code or reference punctuation (quotes, braces, `=`, `:`, `@`, `#`):
    those are examples and citations, not vocabulary.
A trailing parenthetical is dropped before comparison, so "Worklist (25/25 read)" and
"Worklist" are one term.

Exit 1 if a document that needs an index lacks one.
Python stdlib only.
"""
import argparse, json, os, pathlib, re, subprocess, sys
import _paths

MIN_LINES = 150          # below this, a reader just reads it
MIN_SECTIONS = 4         # fewer sections than this needs no map
CONTENTS_RX = re.compile(r"^##\s+(contents|table of contents|index|at a glance)\b",
                         re.I | re.M)
H2_RX = re.compile(r"^##\s+(.+?)\s*$", re.M)


def real_h2s(text):
    """Headings OUTSIDE fenced code blocks.

    A `## ` line inside a fence is sample content, not a section: it produces no
    anchor, so requiring a Contents row for it demands a link that cannot resolve.
    research/37 embeds a PR template containing `## What changed and why`, and
    research/20 quotes an "## The Iron Law" block -- both were being counted.
    """
    out, fence = [], False
    for l in text.splitlines():
        st = l.lstrip()
        if st.startswith("```") or st.startswith("~~~"):
            fence = not fence
            continue
        if fence:
            continue
        m = re.match(r"^##\s+(.+?)\s*$", l)
        if m:
            out.append(m.group(1))
    return out

# Directories whose documents are traversed for information.
INDEXED_DIRS = ("research", "docs", "reviewers", "specs", "prds", "rca", "reviews",
                "decisions", "evals")
# Fixed-structure or generated files: an index would be noise.
EXEMPT_NAMES = {"INDEX.md", "MAP.md", "SKILL.md", "ARCHIVE.md", "README.md",
                "CHANGELOG.md", "AGENTS.md", "CLAUDE.md", "LICENSE.md"}
EXEMPT_PREFIX = ("_TEMPLATE",)
# Records `plan_feature new` and `prd new` generate: <root>/specs/<name>/spec.md and
# <root>/prds/<name>/prd.md. Their sections are fixed by the template (AGENTS.md rule
# 17), so they are recognised by the template's header table, not by length: the
# `| field | value |` table right under the title, with the rows each template writes.
GENERATED_RECORDS = {"spec.md": ("specs", ("feature", "status")),
                     "prd.md": ("prds", ("linked spec", "status"))}
HEADER_ROW_RX = re.compile(r"^\|\s*([^|]+?)\s*\|")


def generated_record(path, text):
    """True for a spec.md / prd.md under a specs/ or prds/ collection that still carries
    its generator's header table. A hand-written long document in the same place, or a
    record whose header was removed, is not exempt."""
    want = GENERATED_RECORDS.get(path.name)
    if not want or len(path.parts) < 3 or path.parts[-3] != want[0]:
        return False
    lines = text.splitlines()
    i = next((n for n, l in enumerate(lines[:5]) if l.startswith("# ")), None)
    if i is None:
        return False
    rows = []
    for l in lines[i + 1:i + 16]:
        if not l.strip() and not rows:
            continue
        m = HEADER_ROW_RX.match(l)
        if not m:
            break
        rows.append(m.group(1).strip().lower())
    return bool(rows) and rows[0] == "field" and all(k in rows for k in want[1])
# Collections that should carry a listing file.
COLLECTIONS = {
    "research": "INDEX.md", "reviewers": "INDEX.md", "specs": "INDEX.md",
    "prds": "INDEX.md", "decisions": "INDEX.md", "rca": "INDEX.md",
    "skills": "INDEX.md",
}


def project_root():
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return pathlib.Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() \
        else pathlib.Path.cwd()


ROOT = project_root()


def write(path, text, origin):
    """Every write here goes through the containment check: a committed symlink
    (skills/, INDEX.md, a --terms-out target) must not carry it outside the repo."""
    return _paths.safe_write_text(path, text, ROOT, origin)


def needs_index(path, text):
    if path.name in EXEMPT_NAMES or path.name.startswith(EXEMPT_PREFIX):
        return False
    parts = path.relative_to(ROOT).parts if path.is_absolute() else path.parts
    if not parts or parts[0] not in INDEXED_DIRS:
        return False
    if len(text.splitlines()) < MIN_LINES:
        return False
    if generated_record(path, text):
        return False
    return len(real_h2s(text)) >= MIN_SECTIONS


def audit_doc(path):
    text = path.read_text(errors="replace")
    if not needs_index(path, text):
        return None
    sections = [s for s in real_h2s(text)
                if not re.match(r"(contents|table of contents|index|at a glance)$",
                                s, re.I)]
    has = bool(CONTENTS_RX.search(text))
    covered = 0
    if has:
        # the contents block runs until the next H2
        blk = text[CONTENTS_RX.search(text).end():]
        blk = re.split(r"\n## ", blk, maxsplit=1)[0]
        for s in sections:
            key = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
            words = [w for w in key.split() if len(w) > 3][:3]
            if words and all(w in blk.lower() for w in words):
                covered += 1
    return {"path": str(path.relative_to(ROOT) if path.is_absolute() else path),
            "lines": len(text.splitlines()), "sections": len(sections),
            "has_contents": has, "covered": covered,
            "missing": [] if not has else
                       [s for s in sections
                        if not all(w in (text[CONTENTS_RX.search(text).end():]
                                         .split("\n## ")[0].lower())
                                   for w in [w for w in re.sub(r"[^a-z0-9]+", " ",
                                             s.lower()).split() if len(w) > 3][:3])]}


STUB = """## Contents

| # | section | what it answers |
|---|---------|-----------------|
{rows}

"""


def insert_stub(path):
    text = path.read_text(errors="replace")
    if CONTENTS_RX.search(text):
        return False
    secs = real_h2s(text)
    rows = "\n".join(
        f"| {i} | [{s}](#{re.sub(r'[^a-z0-9 -]', '', s.lower()).replace(' ', '-')}) "
        f"| <!-- what this section answers --> |"
        for i, s in enumerate(secs, 1))
    lines = text.splitlines()
    # insert after the title and its lead paragraph, before the first H2
    at = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    out = lines[:at] + STUB.format(rows=rows).splitlines() + lines[at:]
    write(path, "\n".join(out) + "\n", "check_index --fix-stubs")
    return True


def first_para(text):
    """The document's own one-line statement of what it is."""
    for l in text.splitlines():
        t = l.strip()
        if not t or t.startswith(("#", "|", "```", ">", "<!--", "-", "*")):
            continue
        return re.sub(r"\s+", " ", t)[:150]
    return ""


def frontmatter_field(text, key):
    if not text.startswith("---"):
        return ""
    fm = text.split("---", 2)[1]
    lines = fm.splitlines()
    for i, l in enumerate(lines):
        if l.startswith(f"{key}:"):
            inline = l.split(":", 1)[1].strip()
            if inline and inline not in (">", "|", ">-", "|-"):
                return inline
            buf = []
            for nxt in lines[i + 1:]:
                if nxt and not nxt[0].isspace():
                    break
                buf.append(nxt.strip())
            return " ".join(x for x in buf if x)
    return ""


TERM_ROOTS = ("docs", "research", "reviewers", "skills")
TERMS_FILE = "TERMS.md"
MAX_HEADING_FILES = 8
GENERIC_TERMS = {
    "contents", "table of contents", "index", "at a glance", "overview", "summary",
    "introduction", "intro", "background", "context", "notes", "note", "examples",
    "example", "usage", "references", "see also", "sources", "source", "next",
    "next steps", "trigger", "rules", "verify", "failure modes", "scale", "why",
    "how", "what", "when", "method", "methods", "results", "findings", "status",
    "appendix", "changelog", "todo", "misc", "other", "details", "setup",
    "honest limitations", "limitations", "open questions", "glossary", "terms",
    "definitions", "the rule", "the problem", "the fix", "the gap", "conclusion",
    "description", "purpose", "scope", "goals", "non-goals", "options", "decision",
    "consequences", "what it does", "what this is", "how to use this", "faq",
    "applies when", "exact command", "why it works", "what it misses",
}
_FENCE = ("```", "~~~")


def strip_md(s):
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = s.replace("`", "")
    s = re.sub(r"(\*\*|__|\*)", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def gh_slug(heading):
    """GitHub's heading anchor: lowercase, keep word chars, '-' and ' ', spaces -> '-'."""
    s = strip_md(heading).lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def clean_term(raw):
    s = strip_md(raw)
    s = re.sub(r"^(§\s*)?\d+[a-z]?[.)]?\s+", "", s)       # "1. Roles", "§ 3 ..."
    s = re.sub(r"^[A-Z]\d+[.:]\s+", "", s)                # "R5. ...", "A1: ..."
    s = re.sub(r"\s*\([^()]*\)$", "", s)                  # "Worklist (25/25 read)"
    return s.strip(" .:;,—–-")


CODE_CHARS_RX = re.compile(r"[\"{}\[\]=<>|\\:@#]")


def generic(term, kind="heading"):
    k = term.casefold()
    return (len(term) < 3 or len(term) > 60
            or len(term.split()) > (6 if kind == "heading" else 5)
            or not re.search(r"[^\W\d_]", term) or term.endswith("?")
            or CODE_CHARS_RX.search(term) or re.match(r"^\d", term)
            or k in GENERIC_TERMS)


BOLD_DEF_RX = re.compile(
    r"\*\*([^*\n]{2,80}?)\*\*(?=\s*(?:—|–|:|\s-\s|is\b|are\b|means\b))"
    r"|\*\*([^*\n]{2,80}?)[:.]\*\*")
GLOSSARY_HEADING_RX = re.compile(r"glossary|terms|definitions", re.I)


def extract_terms(path, relname):
    """[(term, anchor, kind)] for one markdown file; kind is 'defined' or 'heading'."""
    out, seen_slugs = [], {}
    anchor, glossary, fence = "", False, False
    for line in path.read_text(errors="replace").splitlines():
        st = line.lstrip()
        if st.startswith(_FENCE):
            fence = not fence
            continue
        if fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            level, text = len(m.group(1)), m.group(2)
            base = gh_slug(text)
            n = seen_slugs.get(base, 0)
            seen_slugs[base] = n + 1
            anchor = base if n == 0 else f"{base}-{n}"
            if level in (2, 3):
                glossary = bool(GLOSSARY_HEADING_RX.search(text))
                out.append((clean_term(text), anchor, "heading"))
            continue
        for bm in BOLD_DEF_RX.finditer(line):
            out.append((clean_term(bm.group(1) or bm.group(2)), anchor, "defined"))
        if glossary and st.startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", st):
            cells = [c.strip() for c in st.strip("|").split("|")]
            if cells and cells[0]:
                out.append((clean_term(cells[0]), anchor, "defined"))
    return out


def gen_terms_text(roots=None, out_rel=TERMS_FILE):
    roots = [r for r in (roots or TERM_ROOTS) if (ROOT / r).exists()]
    out_path = ROOT / out_rel
    refs = {}            # casefold key -> {(file, anchor, kind)}
    forms = {}           # casefold key -> Counter of display forms (defined forms weigh more)
    heading_files = {}   # casefold key -> files where it is a heading
    defined = set()
    files = []
    for r in roots:
        for f in sorted((ROOT / r).rglob("*.md")):
            if f.name in ("INDEX.md", TERMS_FILE, "MAP.md") or \
                    any(x in f.parts for x in (".git", "node_modules", "raw")):
                continue
            files.append(f)
    for f in files:
        relname = f.relative_to(ROOT).as_posix()
        for term, anchor, kind in extract_terms(f, relname):
            if not term or generic(term, kind):
                continue
            k = term.casefold()
            refs.setdefault(k, set()).add((relname, anchor, kind))
            forms.setdefault(k, {})
            forms[k][term] = forms[k].get(term, 0) + (10 if kind == "defined" else 1)
            if kind == "defined":
                defined.add(k)
            else:
                heading_files.setdefault(k, set()).add(relname)
    keep = {k for k in refs
            if k in defined or len(heading_files.get(k, ())) <= MAX_HEADING_FILES}
    base_dir = out_path.parent

    def display(k):
        return sorted(forms[k].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    def letter(k):
        c = display(k)[0].upper()
        return c if "A" <= c <= "Z" else "#"

    groups = {}
    for k in sorted(keep, key=lambda k: (display(k).casefold(), display(k))):
        groups.setdefault(letter(k), []).append(k)
    order = sorted(groups, key=lambda g: (g != "#", g))
    name = {g: ("Symbols and numbers" if g == "#" else g) for g in order}
    o = ["# Terms", "",
         "Back-of-book index: every term defined in bold (`**term** —`), listed in a "
         "glossary table, or used as a level-2/3 heading, and each place it appears that "
         "way. Generated by `100x check_index --gen-terms`; do not edit by hand. "
         "`100x check_index --check-terms` fails when it is stale.", "",
         f"{len(keep)} terms from {len(files)} files under "
         + ", ".join(f"`{r}/`" for r in roots) + ". *defined* marks a definition; "
         f"other links are section headings. Generic and scaffolding headings are "
         f"filtered (see `scripts/check_index.py`).", "",
         " · ".join(f"[{name[g]}](#{gh_slug(name[g])})" for g in order), ""]
    for g in order:
        o += [f"## {name[g]}", ""]
        for k in groups[g]:
            items = sorted(refs[k], key=lambda x: (x[2] != "defined", x[0], x[1]))
            links = []
            for relname, anchor, kind in items:
                target = os.path.relpath(ROOT / relname, base_dir).replace(os.sep, "/")
                href = f"{target}#{anchor}" if anchor else target
                label = f"{relname}#{anchor}" if anchor else relname
                links.append(f"[{label}]({href})" + (" *defined*" if kind == "defined" else ""))
            o.append(f"- **{display(k)}** — " + ", ".join(links))
        o.append("")
    return "\n".join(o)


def register(note, index_rel):
    """Add or update the catalogue row for one durable note."""
    p = (ROOT / note) if not pathlib.Path(note).is_absolute() else pathlib.Path(note)
    if not p.is_file():
        print(f"check_index --register: no such file: {note}", file=sys.stderr)
        return 2
    # The note's title and first paragraph are copied into the catalogue, so a note
    # outside the repository would leak its contents into a committed file.
    p = _paths.contained(p, ROOT, "check_index --register (note)")
    idx = _paths.contained(ROOT / index_rel, ROOT, "check_index --register (index)")
    text = p.read_text(errors="replace")
    title = (re.search(r"^#\s+(.+)$", text, re.M) or [None, p.stem])[1].strip()
    href = os.path.relpath(p, idx.parent).replace(os.sep, "/")
    row = f"| [{title}]({href}) | {p.parent.name} | {first_para(text)[:120]} |"
    if idx.exists():
        lines = idx.read_text().splitlines()
    else:
        lines = ["# Engineering docs", "",
                 "Catalogue of the durable engineering notes under this directory. Rows "
                 "are added by `100x check_index --register <file>`.", "",
                 "| note | kind | what it covers |", "|---|---|---|"]
    hit = next((i for i, l in enumerate(lines) if f"]({href})" in l), None)
    if hit is not None:
        lines[hit] = row
    else:
        last = max((i for i, l in enumerate(lines) if l.startswith("|")), default=None)
        if last is None:
            lines += ["", "| note | kind | what it covers |", "|---|---|---|", row]
        else:
            lines.insert(last + 1, row)
    write(idx, "\n".join(lines) + "\n", "check_index --register")
    print(f"{'updated' if hit is not None else 'registered'} {href} in {index_rel}")
    return 0


def gen_collections():
    """Write the catalogue file for each collection that lacks one."""
    written = []

    # --- skills: name, trigger, and the pipeline phase it belongs to ---
    sk = ROOT / "skills"
    if sk.exists():
        PHASE = {
            "solution-architecture": "1 before code", "feature-planning": "1 before code",
            "approach-selection": "1 before code", "decision-records": "1 before code",
            "data-modeling": "1 before code", "api-contract": "1 before code",
            "code-craft": "2 while writing", "minimal-diff": "2 while writing",
            "frontend-architecture": "2 while writing",
            "dependency-vetting": "2 while writing",
            "stack-reviewer": "2 while writing", "language-verification": "2 while writing",
            "mobile-release-safety": "2 while writing", "test-design": "2 while writing",
            "distributed-correctness": "2 while writing",
            "performance-budgets": "2 while writing", "diagramming": "2 while writing",
            "accessibility": "2 while writing", "web-vitals": "2 while writing",
            "observability-design": "2 while writing", "legacy-change": "2 while writing",
            "verification-gate": "3 before shipping", "diff-review": "3 before shipping",
            "pr-review": "3 before shipping", "pr-description": "3 before shipping",
            "recheck": "3 before shipping", "prompt-bench": "6 meta",
            "review-gates": "3 before shipping",
            "security-baseline": "3 before shipping",
            "bug-fix": "4 when broken", "root-cause-analysis": "4 when broken",
            "codebase-comprehension": "5 understanding", "explain": "5 understanding",
            "agent-instructions": "6 meta",
            "untrusted-agent-config": "6 meta",
            "100x": "0 start here", "requirements-intake": "0 start here",
            "orchestrate": "0 start here",
            "scale-appropriateness": "1 before code",
            "ui-baseline": "2 while writing", "app-security": "2 while writing",
            "data-lifecycle": "2 while writing", "qa-strategy": "2 while writing",
            "release-rollout": "3 before shipping",
            "project-learning": "6 meta",
        }
        rows = []
        for f in sorted(sk.glob("*/SKILL.md")):
            t = f.read_text(errors="replace")
            n = f.parent.name
            d = frontmatter_field(t, "description")
            d = re.sub(r"^Use\s+(when|to|BEFORE|PROACTIVELY|this)\s*", "", d,
                       flags=re.I)
            rows.append((PHASE.get(n, "9 unclassified"), n, d[:150],
                         len(t.splitlines())))
        rows.sort()
        o = ["# Skill index", "",
             f"{len(rows)} skills, in pipeline order. Regenerated by "
             f"`100x check_index --gen-collections`.", "",
             "| phase | skill | fires when | lines |", "|---|---|---|--:|"]
        o += [f"| {ph} | [{n}]({n}/SKILL.md) | {d} | {ln} |" for ph, n, d, ln in rows]
        o += ["", "Phase order is the order work moves through them; see "
              "`docs/PLAYBOOK.md` for the command sequence per task.", ""]
        write(sk / "INDEX.md", "\n".join(o), "check_index --gen-collections")
        written.append("skills/INDEX.md")

    # --- reviewers: stack, and when it applies ---
    rv = ROOT / "reviewers"
    if rv.exists():
        rows = []
        for f in sorted(rv.glob("*.md")):
            if f.name in ("INDEX.md",) or f.name.startswith("_TEMPLATE"):
                continue
            t = f.read_text(errors="replace")
            m = re.search(r"^##\s+Applies when\s*\n+(.+?)$", t, re.M)
            when = re.sub(r"\s+", " ", m.group(1)).strip("<!- >")[:110] if m else first_para(t)[:110]
            title = (re.search(r"^#\s+(.+)$", t, re.M) or [None, f.stem])[1]
            rows.append((f.name.startswith("_"), f.name, title, when,
                         len(t.splitlines())))
        rows.sort()
        o = ["# Reviewer index", "",
             f"{len(rows)} reviewer files. Stack-specific failure modes, edge cases and "
             f"default architectural choices. Files prefixed `_` are shared references, "
             f"not stack reviewers.", "",
             "| file | covers | applies when | lines |", "|---|---|---|--:|"]
        o += [f"| [{n}]({n}) | {ti} | {wh} | {ln} |" for _, n, ti, wh, ln in rows]
        o += ["", "Read only the one matching the diff — see the `stack-reviewer` skill.", ""]
        write(rv / "INDEX.md", "\n".join(o), "check_index --gen-collections")
        written.append("reviewers/INDEX.md")

    # --- research: what each document answers ---
    rs = ROOT / "research"
    if rs.exists():
        rows = []
        for f in sorted(rs.glob("*.md")):
            if f.name == "INDEX.md":
                continue
            t = f.read_text(errors="replace")
            title = (re.search(r"^#\s+(.+)$", t, re.M) or [None, f.stem])[1]
            secs = len(real_h2s(t))
            rows.append((f.name, title, first_para(t)[:130], len(t.splitlines()), secs))
        o = ["# Research index", "",
             f"{len(rows)} documents, {sum(r[3] for r in rows):,} lines. The evidence "
             f"every skill cites. Regenerated by "
             f"`100x check_index --gen-collections`.", "",
             "| file | title | what it establishes | lines | sections |",
             "|---|---|---|--:|--:|"]
        o += [f"| [{n}]({n}) | {ti} | {p} | {ln} | {sc} |"
              for n, ti, p, ln, sc in rows]
        o += ["", "Numbering: `0x` contracts and corpus, `2x` ecosystem and tooling "
              "surveys, `3x` per-cluster deep reads. Each document carries its own "
              "`## Contents` table.", ""]
        write(rs / "INDEX.md", "\n".join(o), "check_index --gen-collections")
        written.append("research/INDEX.md")
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--fix-stubs", action="store_true",
                    help="insert a Contents skeleton into files that lack one "
                         "(rewrites files in place; needs --yes)")
    ap.add_argument("--yes", action="store_true",
                    help="confirm an in-place rewrite; without it --fix-stubs only "
                         "lists what it would touch")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gen-collections", action="store_true",
                    help="generate the catalogue file for each collection")
    ap.add_argument("--gen-terms", action="store_true",
                    help=f"write the back-of-book term index ({TERMS_FILE})")
    ap.add_argument("--check-terms", action="store_true",
                    help="exit 1 if the term index differs from a fresh regeneration")
    ap.add_argument("--terms-root", action="append", default=None,
                    help=f"directory to index for terms (repeatable; default: "
                         f"{', '.join(TERM_ROOTS)})")
    ap.add_argument("--terms-out", default=TERMS_FILE,
                    help=f"where the term index lives (default: {TERMS_FILE} at the root)")
    ap.add_argument("--register", metavar="FILE",
                    help="add or update FILE's row in the --index catalogue")
    ap.add_argument("--index", default=None,
                    help="catalogue that --register writes (default: INDEX.md at the "
                         "records root -- docs/engineering/ unless .100x.json or "
                         "HUNDREDX_ROOT_DIR says otherwise)")
    a = ap.parse_args()
    terms_rc = 0
    if a.register:
        if a.index is None:
            # Resolved here, not at import: only --register writes a record, and the
            # resolver can warn or refuse on a bad .100x.json, which must not break a
            # plain contents check.
            records, _ = _paths.resolve(ROOT)
            a.index = _paths.show(records / "INDEX.md", ROOT).as_posix()
        terms_rc = register(a.register, a.index)
        if terms_rc:
            return terms_rc
    if a.gen_collections:
        for w in gen_collections():
            print(f"wrote {w}")
    if a.gen_terms:
        _paths.contained(ROOT / a.terms_out, ROOT, "check_index --gen-terms")
        txt = gen_terms_text(a.terms_root, a.terms_out)
        write(ROOT / a.terms_out, txt, "check_index --gen-terms")
        print(f"wrote {a.terms_out} ({txt.count(chr(10) + '- **')} terms)")
    if a.check_terms:
        want = gen_terms_text(a.terms_root, a.terms_out)
        have_p = ROOT / a.terms_out
        have = have_p.read_text() if have_p.exists() else None
        if have != want:
            why = "missing" if have is None else "stale"
            print(f"check_index: {a.terms_out} is {why} — regenerate with "
                  f"`100x check_index --gen-terms`" + (
                      "".join(f" --terms-root {r}" for r in a.terms_root or [])) + (
                      f" --terms-out {a.terms_out}" if a.terms_out != TERMS_FILE else ""))
            terms_rc = 1
        else:
            print(f"check_index: {a.terms_out} is current")
    base = (ROOT / a.path) if not pathlib.Path(a.path).is_absolute() else pathlib.Path(a.path)

    docs, fixed, pending = [], 0, []
    for p in sorted(base.rglob("*.md")):
        if any(x in p.parts for x in (".git", "node_modules", "raw")):
            continue
        r = audit_doc(p)
        if r:
            if a.fix_stubs and not r["has_contents"]:
                if not a.yes:
                    pending.append(r["path"])
                elif insert_stub(p):
                    fixed += 1
                    r = audit_doc(p)
            docs.append(r)

    missing_coll = []
    for d, idx in COLLECTIONS.items():
        dd = ROOT / d
        if dd.exists() and any(dd.rglob("*.md")) and not (dd / idx).exists():
            missing_coll.append(f"{d}/{idx}")

    no_contents = [d for d in docs if not d["has_contents"]]
    partial = [d for d in docs if d["has_contents"] and d["missing"]]

    if a.json:
        print(json.dumps({"docs": docs, "missing_collection_indexes": missing_coll,
                          "without_contents": len(no_contents),
                          "partial": len(partial)}, indent=2))
        return 0 if not (no_contents or missing_coll or terms_rc) else 1

    print(f"check_index: {len(docs)} document(s) need an index "
          f"(>= {MIN_LINES} lines, >= {MIN_SECTIONS} sections, in {'/'.join(INDEXED_DIRS[:4])}/...)")
    if fixed:
        print(f"  inserted {fixed} Contents skeleton(s) — fill in the 'what it answers' cells")
    if pending:
        print(f"  --fix-stubs would REWRITE {len(pending)} file(s) in place. Nothing has "
              f"changed. Re-run with --yes to proceed:")
        for x in pending[:12]:
            print(f"      {x}")
    ok = [d for d in docs if d["has_contents"] and not d["missing"]]
    print(f"  complete index   : {len(ok)}")
    print(f"  partial index    : {len(partial)}")
    print(f"  no index at all  : {len(no_contents)}")
    for d in no_contents[:15]:
        print(f"    MISSING  {d['path']}  ({d['lines']} lines, {d['sections']} sections)")
    for d in partial[:10]:
        print(f"    PARTIAL  {d['path']}  — not listed: {', '.join(d['missing'][:4])}")
    if missing_coll:
        print(f"\n  collections with no listing file ({len(missing_coll)}):")
        for c in missing_coll:
            print(f"    {c}")
    if not no_contents and not missing_coll:
        print("\n  every traversable document is navigable")
    else:
        print("\n  A document you read to extract information needs a map at the top; "
              "a collection needs a catalogue. `--fix-stubs` scaffolds the former.")
    return 0 if not (no_contents or missing_coll or terms_rc) else 1


if __name__ == "__main__":
    sys.exit(main())
