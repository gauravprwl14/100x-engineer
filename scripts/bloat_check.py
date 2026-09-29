#!/usr/bin/env python3
"""Diff-scoped checks for AI-generated bloat that no existing tool catches.

Per research/23-findings-antibloat-enforcement.md, off-the-shelf tooling covers
dead code, cycles, unused deps, complexity and byte budgets. It does NOT cover the
specific shapes an LLM produces. This fills those gaps, scoped to the current diff
so it is runnable on a large existing codebase.

    bloat_check.py                 # check staged+unstaged vs HEAD
    bloat_check.py --base origin/main
    bloat_check.py --only assertionless,new-docs

Exit 1 if any enabled check finds a violation.
"""
import argparse, ast, os, re, subprocess, sys, pathlib, collections

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt", ".swift"}
TEST_RX = re.compile(r"(^|/)(tests?|__tests__|spec)/|[._](test|spec)\.[a-z]+$|_test\.(go|py)$|^test_", re.I)
DOC_OK = ("docs/", "doc/", ".github/", "research/", "skills/", "agents/", "commands/")
# Docs that ARE the deliverable, or are conventional at a repo root, are never bloat.
DOC_ALLOW_NAMES = {
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE.md",
    "AGENTS.md", "CLAUDE.md", "SKILL.md", "CODE_OF_CONDUCT.md", "GOVERNANCE.md",
    "MAINTAINERS.md", "ADOPTERS.md", "NOTICE.md", "SUPPORT.md",
}


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
    # include untracked files as "added" -- an agent's stray files are usually untracked
    for p in sh(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        if p and p not in added:
            added.append(p)
    return added, mod


def added_lines(path, base):
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--unified=0"] + rng + ["--", path])
    if not out:
        try:
            return pathlib.Path(path).read_text(errors="replace").splitlines()
        except OSError:
            return []
    return [l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]


# ---------------- checks ----------------

def check_new_docs(added, mod, base):
    bad = [p for p in added if p.endswith((".md", ".rst", ".adoc"))
           and not p.startswith(DOC_OK)
           and os.path.basename(p) not in DOC_ALLOW_NAMES]
    return [(p, "new doc file outside docs/ - was this asked for?") for p in bad]


def check_assertionless(added, mod, base):
    """A test that calls code but never asserts cannot fail. Real failure mode #10."""
    out = []
    ASSERT_RX = re.compile(
        r"\b(assert|expect|require\.|assert\.|should|t\.Error|t\.Fatal|t\.Fail|"
        r"assertEqual|assertTrue|toBe|toEqual|toThrow|verify|XCTAssert)\b")
    for p in added + mod:
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        try:
            src = pathlib.Path(p).read_text(errors="replace")
        except OSError:
            continue
        if p.endswith(".py"):
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                   node.name.startswith("test"):
                    body = ast.get_source_segment(src, node) or ""
                    if not ASSERT_RX.search(body) and "pytest.raises" not in body:
                        out.append((f"{p}:{node.lineno}",
                                    f"test `{node.name}` contains no assertion"))
        else:
            # Brace languages: bound each test block at the NEXT test declaration.
            # A fixed-size window bleeds into the following block, so an adjacent
            # passing assertion masks an empty test -- verified failure mode.
            decl = re.compile(
                r"^[ \t]*(?:async\s+)?(?:it|test)(?:\.\w+)?\s*\(\s*[\"'`]([^\"'`]{0,80})"
                r"|^func\s+(Test\w+)\s*\(", re.M)
            hits = list(decl.finditer(src))
            for i, m in enumerate(hits):
                end = hits[i + 1].start() if i + 1 < len(hits) else len(src)
                block = src[m.end():end]
                if not ASSERT_RX.search(block):
                    name = (m.group(1) or m.group(2) or "?").strip()
                    ln = src[:m.start()].count("\n") + 1
                    out.append((f"{p}:{ln}", f"test `{name}` contains no assertion"))
    return out


def check_commented_code(added, mod, base):
    """Commented-out code added in a diff is dead on arrival."""
    out = []
    CODE_LIKE = re.compile(
        r"^\s*(#|//)\s*(if|for|while|return|def |func |class |const |let |var |import |"
        r"from |print\(|console\.|await |async |try:|except|\w+\s*=\s*\w|\w+\([^)]*\)\s*;?)\s")
    for p in added + mod:
        if not p.endswith(tuple(CODE_EXT)):
            continue
        run = 0
        for i, line in enumerate(added_lines(p, base), 1):
            if CODE_LIKE.match(line):
                run += 1
                if run == 2:
                    out.append((p, "2+ consecutive commented-out code lines added"))
                    break
            else:
                run = 0
    return out


def check_bare_todo(added, mod, base):
    """A TODO with no issue reference is a note to nobody."""
    out = []
    RX = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b(?!.*(#\d+|[A-Z]{2,}-\d+|https?://))")
    for p in added + mod:
        if not p.endswith(tuple(CODE_EXT)):
            continue
        for line in added_lines(p, base):
            if RX.search(line):
                out.append((p, f"TODO/FIXME with no issue reference: {line.strip()[:60]}"))
                break
    return out


def check_single_use_abstraction(added, mod, base):
    """An interface/protocol/abstract class added with exactly one implementation.
    A signal, not a verdict -- research says this needs human judgement."""
    out = []
    for p in added:
        if not p.endswith((".ts", ".tsx", ".py", ".go")):
            continue
        try:
            src = pathlib.Path(p).read_text(errors="replace")
        except OSError:
            continue
        names = re.findall(r"^\s*(?:export\s+)?(?:interface|type)\s+(\w+)", src, re.M)
        names += re.findall(r"^\s*class\s+(\w+)\s*\(\s*(?:ABC|Protocol)\s*\)", src, re.M)
        names += re.findall(r"^\s*type\s+(\w+)\s+interface\s*\{", src, re.M)
        for n in names:
            uses = int(sh(["git", "grep", "-c", "-w", n]).count("\n")) if n else 0
            if uses <= 1:
                out.append((p, f"abstraction `{n}` appears in <=1 file - "
                               f"speculative or load-bearing? (review)"))
    return out


def check_file_creation_ratio(added, mod, base):
    """Many new files alongside few edits is the signature of an agent rebuilding
    rather than integrating."""
    a = [p for p in added if p.endswith(tuple(CODE_EXT)) and not TEST_RX.search(p)]
    m = [p for p in mod if p.endswith(tuple(CODE_EXT))]
    if len(a) >= 3 and len(a) > 2 * max(len(m), 1):
        return [("(diff)", f"{len(a)} new code files vs {len(m)} edited - "
                           f"prefer editing existing modules over creating new ones")]
    return []


def check_focused_tests(added, mod, base):
    """A focused test silently disables every other test in its file.

    `jest/no-focused-tests` and equivalents are the one near-universal real gate
    found in production repos (research/36-findings-antibloat-in-practice.md), so a
    diff-scoped version belongs here.
    """
    out = []
    FOCUS = re.compile(
        r"\b(fdescribe|fit|fcontext)\s*\(|"
        r"\b(describe|it|test|context|suite|bench)\.only\s*\(|"
        r"\.only\s*\(\s*[\"\'`]")
    SKIP = re.compile(
        r"\b(xdescribe|xit|xtest)\s*\(|"
        r"\b(describe|it|test)\.skip\s*\(|"
        r"@pytest\.mark\.skip\b(?!\s*\()|"
        r"\bt\.Skip\(\)")
    for p in added + mod:
        if not TEST_RX.search(p) or not p.endswith(tuple(CODE_EXT)):
            continue
        for i, line in enumerate(added_lines(p, base), 1):
            if FOCUS.search(line):
                out.append((p, f"focused test disables the rest of the file: "
                               f"{line.strip()[:60]}"))
                break
        for line in added_lines(p, base):
            if SKIP.search(line):
                out.append((p, f"skipped test with no stated reason: {line.strip()[:60]}"))
                break
    return out


CHECKS = {
    "new-docs": check_new_docs,
    "assertionless": check_assertionless,
    "commented-code": check_commented_code,
    "bare-todo": check_bare_todo,
    "single-use-abstraction": check_single_use_abstraction,
    "file-creation-ratio": check_file_creation_ratio,
    "focused-tests": check_focused_tests,
}
# checks that are signals needing judgement, not hard failures
ADVISORY = {"single-use-abstraction", "file-creation-ratio"}


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
        print("bloat_check: no changes to inspect")
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

    print(f"\nbloat_check: {len(added)} added, {len(mod)} modified | "
          f"{hard} blocking, {advisory} advisory")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
