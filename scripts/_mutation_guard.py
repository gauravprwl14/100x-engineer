"""Shared helpers for the record-writing tools' safety surface.

Not a standalone tool -- imported by plan_feature.py, prd.py, decide.py, rca.py,
ledger.py and check_index.py, and (for `enter_git_root` and `changed_files`) by
the diff checkers, all of which live in this same directory, so a plain
`import _mutation_guard` resolves without any sys.path surgery (Python puts the
running script's own directory on sys.path[0]).

Three concerns live here because all six tools share them and drift between six
copies is how a safety guarantee quietly stops being true:

  1. Refusing to write when the current directory is not inside a git repository.
     `git rev-parse --show-toplevel` failing means ROOT falls back to `Path.cwd()`
     -- and cwd could be $HOME, or wherever the shell happened to be. A tool whose
     entire job is to create files has no business guessing that that is the right
     place. Read-only commands are unaffected; only the write path is gated.
  2. A safe record name: reject path separators and `..` so `new <name>` cannot be
     steered outside the records directory it is meant to create inside.
  3. `--dry-run` plumbing: a unified diff for in-place edits, and a plain
     "would create/write" line for new files, with nothing touching disk.
  4. `enter_git_root` for the read-only diff checkers. `git diff --name-status`
     prints repo-root-relative paths while file reads and `git diff -- <path>`
     resolve against cwd, so run from a monorepo subfolder every changed file was
     silently unreadable and the checker passed a diff it never saw.
  5. `changed_files` / `diff_rev` / `path_args`: the one definition of "which files
     did this diff touch". Each checker used to carry its own copy, and every copy
     dropped renamed files (`--diff-filter=AM`), mangled non-ASCII paths (no `-z`,
     so git C-quoted them) and failed on an unborn HEAD -- all three reported "no
     changes" and passed.
"""
import difflib
import os
import re
import subprocess
import sys

# name segments accepted for a record's own directory/file (feature name, decision
# title-slug are already regex-sanitised by their callers). This one guards the raw
# argument before it is ever joined onto a path.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def safe_record_name(name, tool):
    """Reject a record name that could escape the records directory.

    Returns None (write refused, caller should print + exit non-zero) or the name
    unchanged. Deliberately conservative: no `/`, no leading `.`, no `..` segment,
    not absolute -- a feature/PRD name has no legitimate reason to contain any of
    those, and pathlib silently honours all of them when joined with `/`.
    """
    if not name or not _SAFE_NAME.match(name) or ".." in name.split("."):
        print(f"{tool}: refusing name {name!r} -- record names may contain only "
              f"letters, digits, '.', '_', '-', and cannot start with '.' or contain "
              f"a path separator. This blocks a crafted name (e.g. '../../etc') from "
              f"writing outside the records directory.", file=sys.stderr)
        return None
    return name


def require_git_root(in_git_repo, tool, cwd):
    """Refuse a write when cwd is not inside a git repo. Returns True if refused."""
    if in_git_repo:
        return False
    print(f"{tool}: refusing to write -- {cwd} is not inside a git repository.\n"
          f"  Records are written relative to the git root so they land inside your "
          f"project and travel with it. Outside a repo the only honest fallback is "
          f"the current directory, which may be $HOME or anywhere else the shell "
          f"happened to be -- too easy to litter by accident. Run `git init`, or cd "
          f"into your project, and retry.", file=sys.stderr)
    return True


def diff_preview(old_text, new_text, label):
    """Unified diff for an in-place edit. Empty string if nothing would change."""
    if old_text == new_text:
        return ""
    return "".join(difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{label}", tofile=f"b/{label}"))


def print_diff_or_noop(old_text, new_text, label):
    """For --dry-run on an in-place edit: print the diff, or say nothing would change."""
    d = diff_preview(old_text, new_text, label)
    if d:
        print(f"--- would rewrite {label} ---")
        sys.stdout.write(d)
    else:
        print(f"no change: {label}")
    return bool(d)


def enter_git_root(tool, base=None):
    """chdir to the repository root so diff paths and file reads agree.

    Returns the root, or None after printing why (caller exits 2). Outside a git
    repo, or with a --base that does not resolve, the diff would come back empty
    and the checker would report "no changes" -- a pass on input it never read.
    """
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        print(f"{tool}: {os.getcwd()} is not inside a git repository -- there is no "
              f"diff to inspect, so nothing was checked.", file=sys.stderr)
        return None
    root = r.stdout.strip()
    os.chdir(root)
    if base is not None:
        v = subprocess.run(["git", "rev-parse", "--verify", "--quiet",
                            f"{base}^{{commit}}"], capture_output=True, text=True)
        if v.returncode != 0:
            print(f"{tool}: --base {base!r} does not resolve to a commit -- nothing "
                  f"was checked.", file=sys.stderr)
            return None
    return root


# git's well-known empty tree. Diffing against it is how a repository with no commit
# yet (unborn HEAD) still shows its staged files as added.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# destination -> source for renames seen by the last changed_files() call
_RENAMED = {}


_HEAD_REV = []


def diff_rev(base):
    """The revision a checker diffs against: --base, else HEAD, else the empty tree."""
    if base:
        return base
    if not _HEAD_REV:
        r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
                           capture_output=True, text=True)
        _HEAD_REV.append("HEAD" if r.returncode == 0 else EMPTY_TREE)
    return _HEAD_REV[0]


def _git_z(args, tool):
    r = subprocess.run(["git"] + args, capture_output=True)
    if r.returncode != 0:
        print(f"{tool}: `git {' '.join(args)}` failed -- nothing was checked.\n"
              f"  {r.stderr.decode('utf-8', 'replace').strip()}", file=sys.stderr)
        sys.exit(2)
    return [t for t in r.stdout.decode("utf-8", "surrogateescape").split("\0")]


def changed_files(base, tool):
    """(added, modified) repo-relative paths in the diff, untracked files counted as added.

    A rename (with or without edits) is reported under its destination path in
    `modified`; `path_args` then diffs it against its source so only the lines the
    rename changed count as added. A git failure exits 2: a checker that could not
    list its input must not report a clean pass.
    """
    _RENAMED.clear()
    toks = _git_z(["diff", "-z", "--name-status", "-M", "--diff-filter=AMR",
                   diff_rev(base)], tool)
    added, mod = [], []
    i = 0
    while i < len(toks):
        status = toks[i]
        if not status:
            i += 1
            continue
        if status[0] == "R":
            if i + 2 >= len(toks):
                break
            src, dst = toks[i + 1], toks[i + 2]
            _RENAMED[dst] = src
            mod.append(dst)
            i += 3
            continue
        if i + 1 >= len(toks):
            break
        (added if status[0] == "A" else mod).append(toks[i + 1])
        i += 2
    seen = set(added) | set(mod)
    for p in _git_z(["ls-files", "-z", "--others", "--exclude-standard"], tool):
        if p and p not in seen:
            added.append(p)
            seen.add(p)
    return added, mod


def path_args(path):
    """Trailing `git diff` arguments selecting `path`, paired with its rename source."""
    src = _RENAMED.get(path)
    return ["-M", "--", src, path] if src else ["--", path]


def unreadable(paths, tool):
    """Print and return the changed paths whose content cannot be read.

    A checker that skipped them would pass a diff it never saw, so callers exit 2
    on a non-empty result. A directory (a submodule's gitlink) and a dangling
    symlink carry no content to inspect and are not counted.
    """
    bad = []
    for p in paths:
        if os.path.isdir(p) or (os.path.islink(p) and not os.path.exists(p)):
            continue
        try:
            with open(p, "rb") as fh:
                fh.read(1)
        except OSError as e:
            bad.append(p)
            print(f"{tool}: cannot read changed file {p}: {e.strerror or e} -- it was "
                  f"not checked.", file=sys.stderr)
    return bad
