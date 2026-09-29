"""Shared helpers for the record-writing tools' safety surface.

Not a standalone tool -- imported by plan_feature.py, prd.py, decide.py, rca.py,
ledger.py and check_index.py, all of which live in this same directory, so a plain
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
"""
import difflib
import re
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
