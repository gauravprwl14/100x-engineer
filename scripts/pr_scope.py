#!/usr/bin/env python3
"""Scope guard for a pull request, stacked PRs especially: does the diff hold only
what this PR is about?

Feature code leaking into the wrong stacked PR (a reactions PR that also carries the
tagging code) is invisible in a diff against main, because main is not the PR's base.
This lists the files changed since the merge-base with the PR's *own* base and warns
on three signals:

  out-of-scope     a changed file matching none of the declared scope globs
                   (--scope, a `scope:` line in the PR body, or a .100x-scope file)
  sibling-overlap  a changed file that a sibling branch -- one forked from the same
                   point -- also changes: the feature probably belongs to the sibling
  wide-diff        no scope declared, and the diff spans more than 3 unrelated
                   top-level areas

Scope leaks were reviewers' most frequent complaint.
SOURCE: original (private-repo PR survey: 105 human PRs, ~180 review comments).

Warn-only: exits 0 unless --strict, which exits 1 when anything is found. Also a
library: require_verification.py calls analyse() on `gh pr create`.

    100x pr_scope                               # base: upstream, else origin/main, else main
    100x pr_scope --base feature/tagging --scope 'app/reactions/**,spec/reactions/**'
    100x pr_scope --body-file pr.md --strict
"""
import argparse, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _globs import path_owned  # noqa: E402

SCOPE_FILE = ".100x-scope"
MAX_AREAS = 3
MAX_SIBLINGS = 50
# Areas that accompany any change (its tests, its docs), so they do not make a diff
# "span" another area.
COMPANION_AREAS = {"test", "tests", "spec", "specs", "__tests__", "docs", "doc"}
SCOPE_LINE = re.compile(r"^\s*(?:[-*]\s*)?\**scope\**\s*:\s*(.+?)\s*$", re.I | re.M)


def _git(args, cwd):
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                           timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def _lines(out):
    return [ln for ln in (out or "").splitlines() if ln.strip()]


def resolve_base(cwd, base=None):
    """The ref the PR merges into: an explicit one, else the branch's upstream, else
    origin/main, else main. None when none of them names a commit."""
    candidates = [base] if base else []
    if not base:
        up = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd)
        current = (_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) or "").strip()
        # A branch tracking its own remote twin (origin/feat for feat) says where it is
        # pushed, not what it merges into.
        if up and up.strip().split("/", 1)[-1] != current:
            candidates.append(up.strip())
        candidates += ["origin/main", "main"]
    for ref in candidates:
        if _git(["rev-parse", "--verify", "-q", ref + "^{commit}"], cwd):
            return ref
    return None


def changed_files(cwd, base):
    return _lines(_git(["diff", "--name-only", f"{base}...HEAD"], cwd))


def diff_lines(cwd, base):
    """Insertions plus deletions since the merge-base, or None when git cannot say."""
    out = _git(["diff", "--shortstat", f"{base}...HEAD"], cwd)
    if out is None:
        return None
    return sum(int(n) for n in re.findall(r"(\d+) (?:insertion|deletion)", out))


def parse_scope(text):
    """Globs from comma- or whitespace-separated text; `#` starts a comment."""
    globs = []
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0]
        globs += [g.strip().strip("`") for g in re.split(r"[,\s]+", line) if g.strip("` ")]
    return globs


def declared_scope(cwd, body=None):
    """(globs, source) from a `scope:` line in the PR body, else .100x-scope."""
    if body:
        m = SCOPE_LINE.search(body)
        if m and parse_scope(m.group(1)):
            return parse_scope(m.group(1)), "PR body"
    top = (_git(["rev-parse", "--show-toplevel"], cwd) or "").strip()
    path = pathlib.Path(top or cwd) / SCOPE_FILE
    if path.is_file():
        globs = parse_scope(path.read_text(errors="replace"))
        if globs:
            return globs, SCOPE_FILE
    return [], None


def area(path):
    return path.split("/", 1)[0] if "/" in path else "(root)"


def group_areas(files):
    groups = {}
    for f in files:
        groups.setdefault(area(f), []).append(f)
    return groups


def _siblings(cwd, base, fork):
    """{branch: changed files} for local branches forked from the same commit as
    this one, newest first."""
    head = (_git(["rev-parse", "HEAD"], cwd) or "").strip()
    current = (_git(["symbolic-ref", "-q", "--short", "HEAD"], cwd) or "").strip()
    base_sha = (_git(["rev-parse", "--verify", "-q", base + "^{commit}"], cwd) or "").strip()
    refs = _lines(_git(["for-each-ref", "--sort=-committerdate", f"--count={MAX_SIBLINGS}",
                        "--format=%(refname:short) %(objectname)", "refs/heads"], cwd))
    out = {}
    for row in refs:
        name, _, sha = row.rpartition(" ")
        if name in (current, base) or sha in (head, fork, base_sha):
            continue
        if (_git(["merge-base", base, sha], cwd) or "").strip() != fork:
            continue
        # A branch stacked on this one carries these files because it contains them.
        if _git(["merge-base", "--is-ancestor", "HEAD", sha], cwd) is not None:
            continue
        files = _lines(_git(["diff", "--name-only", f"{fork}..{sha}"], cwd))
        if files:
            out[name] = (sha, set(files))
    return out


def analyse(cwd, base=None, scope=None, body=None):
    """Return {"base", "files", "areas", "scope", "scope_source", "findings"}. Each
    finding is {"rule", "file", "message"}. A cwd outside a repo, or a base that
    names nothing, yields no findings rather than an error."""
    result = {"base": None, "files": [], "areas": {}, "scope": [], "scope_source": None,
              "findings": []}
    ref = resolve_base(cwd, base)
    if not ref:
        return result
    fork = (_git(["merge-base", ref, "HEAD"], cwd) or "").strip()
    files = changed_files(cwd, ref)
    result.update(base=ref, files=files, areas=group_areas(files))
    if not files or not fork:
        return result
    findings = result["findings"]

    globs, source = (scope, "--scope") if scope else declared_scope(cwd, body)
    result.update(scope=globs, scope_source=source)
    if globs:
        for f in files:
            if not path_owned(f, globs):
                findings.append({"rule": "out-of-scope", "file": f,
                                 "message": f"outside the declared scope ({source}: "
                                            f"{', '.join(globs)})"})
    else:
        spread = sorted(a for a in result["areas"]
                        if a != "(root)" and a not in COMPANION_AREAS)
        if len(spread) > MAX_AREAS:
            findings.append({"rule": "wide-diff", "file": "-",
                             "message": f"the diff spans {len(spread)} top-level areas "
                                        f"({', '.join(spread)}) with no declared scope; "
                                        f"split the PR or declare `scope:` in its body"})

    for name, (sha, theirs) in _siblings(cwd, ref, fork).items():
        stacked = _git(["merge-base", "--is-ancestor", sha, "HEAD"], cwd) is not None
        hint = (f"this branch contains `{name}`; if the PR is stacked on it, use "
                f"--base {name}") if stacked else \
            f"the change may belong to `{name}`, not this PR"
        for f in files:
            if f in theirs:
                findings.append({"rule": "sibling-overlap", "file": f,
                                 "message": f"also changed on sibling branch `{name}`: "
                                            f"{hint}"})
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", help="ref the PR merges into (default: upstream, else "
                                   "origin/main, else main)")
    ap.add_argument("--scope", help="comma-separated globs the PR may touch")
    ap.add_argument("--body-file", help="PR body to read a `scope:` line from")
    ap.add_argument("--strict", action="store_true", help="exit 1 when anything is found")
    a = ap.parse_args(argv)
    body = pathlib.Path(a.body_file).read_text(errors="replace") if a.body_file else None
    r = analyse(".", a.base, parse_scope(a.scope) if a.scope else None, body)
    if not r["base"]:
        print("pr_scope: no base ref found (pass --base)", file=sys.stderr)
        return 2
    print(f"pr_scope: {len(r['files'])} file(s) changed vs merge-base with {r['base']}")
    if not r["scope"]:
        for name, fs in sorted(r["areas"].items()):
            print(f"  {name}/: {len(fs)}" if name != "(root)" else f"  {name}: {len(fs)}")
    for f in r["findings"]:
        print(f"{f['file']}: [{f['rule']}] {f['message']}")
    if not r["findings"]:
        print("pr_scope: no scope warnings")
    return 1 if a.strict and r["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
