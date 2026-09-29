#!/usr/bin/env python3
"""Require a navigable index in documents people traverse to find information.

Two failures, both of which appear once a project has more than a handful of records:

  COLLECTION level -- hundreds of specs with no single file listing them. You cannot
  find the one you need without opening them.
  DOCUMENT level -- a 500-line findings file with 13 sections and no summary, so
  answering "is the answer in here?" costs a full read.

A book solves both: a shelf catalogue, and a table of contents in every volume. This
enforces the same thing, and only where it pays -- long documents you read to extract
information, never short ones or fixed-structure files like SKILL.md.

    check_index.py                       # check the whole repo
    check_index.py research/             # one tree
    check_index.py --fix-stubs           # insert a Contents skeleton to fill in
    check_index.py --json

Exit 1 if a document that needs an index lacks one.
Python stdlib only.
"""
import argparse, json, pathlib, re, subprocess, sys

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


def needs_index(path, text):
    if path.name in EXEMPT_NAMES or path.name.startswith(EXEMPT_PREFIX):
        return False
    parts = path.relative_to(ROOT).parts if path.is_absolute() else path.parts
    if not parts or parts[0] not in INDEXED_DIRS:
        return False
    if len(text.splitlines()) < MIN_LINES:
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
    path.write_text("\n".join(out) + "\n")
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


def gen_collections():
    """Write the catalogue file for each collection that lacks one."""
    written = []

    # --- skills: name, trigger, and the pipeline phase it belongs to ---
    sk = ROOT / "skills"
    if sk.exists():
        PHASE = {
            "solution-architecture": "1 before code", "feature-planning": "1 before code",
            "approach-selection": "1 before code", "decision-log": "1 before code",
            "data-modeling": "1 before code", "api-contract": "1 before code",
            "code-craft": "2 while writing", "minimal-diff": "2 while writing",
            "frontend-architecture": "2 while writing",
            "dependency-vetting": "2 while writing",
            "stack-reviewer": "2 while writing", "typescript-verification": "2 while writing",
            "python-verification": "2 while writing", "go-verification": "2 while writing",
            "mobile-release-safety": "2 while writing", "test-design": "2 while writing",
            "distributed-correctness": "2 while writing",
            "performance-budgets": "2 while writing", "diagramming": "2 while writing",
            "observability-design": "2 while writing", "legacy-change": "2 while writing",
            "verification-gate": "3 before shipping", "scoped-review": "3 before shipping",
            "reviewing-others-code": "3 before shipping", "review-gates": "3 before shipping",
            "security-baseline": "3 before shipping",
            "bug-fix": "4 when broken", "root-cause-analysis": "4 when broken",
            "codebase-comprehension": "5 understanding",
            "engineering-ledger": "6 meta", "agent-instructions": "6 meta",
            "untrusted-agent-config": "6 meta",
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
             f"`python3 scripts/check_index.py --gen-collections`.", "",
             "| phase | skill | fires when | lines |", "|---|---|---|--:|"]
        o += [f"| {ph} | [{n}]({n}/SKILL.md) | {d} | {ln} |" for ph, n, d, ln in rows]
        o += ["", "Phase order is the order work moves through them; see "
              "`docs/PLAYBOOK.md` for the command sequence per task.", ""]
        (sk / "INDEX.md").write_text("\n".join(o))
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
        (rv / "INDEX.md").write_text("\n".join(o))
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
             f"`python3 scripts/check_index.py --gen-collections`.", "",
             "| file | title | what it establishes | lines | sections |",
             "|---|---|---|--:|--:|"]
        o += [f"| [{n}]({n}) | {ti} | {p} | {ln} | {sc} |"
              for n, ti, p, ln, sc in rows]
        o += ["", "Numbering: `0x` contracts and corpus, `2x` ecosystem and tooling "
              "surveys, `3x` per-cluster deep reads. Each document carries its own "
              "`## Contents` table.", ""]
        (rs / "INDEX.md").write_text("\n".join(o))
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
    a = ap.parse_args()
    if a.gen_collections:
        for w in gen_collections():
            print(f"wrote {w}")
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
        return 0 if not (no_contents or missing_coll) else 1

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
    return 0 if not (no_contents or missing_coll) else 1


if __name__ == "__main__":
    sys.exit(main())
