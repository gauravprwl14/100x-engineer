"""File-ownership globs shared by plan_dag.py (do two tasks' files overlap?) and
agent_report.py (is a changed path inside a task's files?).

Not a standalone tool. One implementation, because the lint that admits a plan and
the lint that checks a finished task must agree on what a glob owns.

Syntax, deliberately small:

  - Paths split on "/"; "**" matches zero or more whole segments; "./" prefixes are
    ignored.
  - A trailing "/" means everything under the directory.
  - A bare final segment with no wildcard and no "." (`src/auth`, `Makefile`) is read
    as a directory too, `src/auth/**`. "**" also matches zero segments, so this still
    owns a file of that name: the reading is a superset, never a miss.
  - Inside a segment, fnmatch's `*`, `?` and `[...]`.
  - Brace sets `{a,b}` are NOT supported: fnmatch would compare them literally and a
    plan owning `src/{a,b}.ts` would silently own nothing. `has_brace` lets callers
    reject them.
"""
import fnmatch
from functools import lru_cache

WILD = set("*?[")


def has_brace(p):
    return "{" in p or "}" in p


def _is_glob(s):
    return any(c in WILD for c in s)


def segs(p, as_pattern=True):
    p = p.strip()
    while p.startswith("./"):
        p = p[2:]
    if p.endswith("/"):
        p += "**"
    out = tuple(s for s in p.strip("/").split("/") if s not in ("", "."))
    if as_pattern and out and out[-1] != "**" and not _is_glob(out[-1]) and "." not in out[-1]:
        out += ("**",)
    return out


def _lit_prefix(s):
    i = min((s.index(c) for c in WILD if c in s), default=len(s))
    return s[:i]


def _lit_suffix(s):
    i = max((s.rindex(c) for c in "*?]" if c in s), default=-1)
    return s[i + 1:]


def _seg_compat(x, y):
    """May two single segments match a common string? One-sided: glob vs glob is
    'overlapping' unless their literal prefixes or suffixes are incompatible, so
    `*.ts` vs `*.tsx` is disjoint but `*foo*` vs `*bar*` is reported as overlapping."""
    gx, gy = _is_glob(x), _is_glob(y)
    if not gx and not gy:
        return x == y
    if not gx:
        return fnmatch.fnmatchcase(x, y)
    if not gy:
        return fnmatch.fnmatchcase(y, x)
    px, py = _lit_prefix(x), _lit_prefix(y)
    sx, sy = _lit_suffix(x), _lit_suffix(y)
    return ((px.startswith(py) or py.startswith(px))
            and (sx.endswith(sy) or sy.endswith(sx)))


def _walk(A, B, seg_ok):
    @lru_cache(maxsize=None)
    def ov(i, j):
        if i == len(A) and j == len(B):
            return True
        if i < len(A) and A[i] == "**":
            if ov(i + 1, j) or (j < len(B) and ov(i, j + 1)):
                return True
        if j < len(B) and B[j] == "**":
            if ov(i, j + 1) or (i < len(A) and ov(i + 1, j)):
                return True
        if i == len(A) or j == len(B):
            return False
        if A[i] == "**" or B[j] == "**":
            return False
        return seg_ok(A[i], B[j]) and ov(i + 1, j + 1)
    return ov(0, 0)


def globs_overlap(a, b):
    """Can two ownership globs match a common path? May report an overlap that cannot
    happen, must never miss one that can: a false collision costs a reworded plan, a
    missed one two agents overwriting each other."""
    return _walk(segs(a), segs(b), _seg_compat)


def path_matches(path, pattern):
    """Does one concrete repo-relative path fall under an ownership glob? The path is
    taken literally: `src/x` changed is the file src/x, not a directory."""
    P = segs(path, as_pattern=False)
    return _walk(P, segs(pattern), lambda p, g: fnmatch.fnmatchcase(p, g))


def path_owned(path, patterns):
    return any(path_matches(path, p) for p in patterns)
