#!/usr/bin/env python3
"""Prove that the tests changed on a branch fail when the fix is taken away.

A test that passes whatever the code does guards nothing, and review keeps finding
them: an assertion that is always true, a test that never imports the changed
function, a mock that returns the expected value. This tool runs the tests twice in a throwaway worktree:

  1. on HEAD, where they must pass (otherwise the comparison says nothing);
  2. with every NON-test file changed since the merge-base with --base put back to
     its base version, where they must fail.

    100x fails_without_fix --base origin/main --test-cmd "python3 -m unittest"
    100x fails_without_fix --base main --test-cmd "npm test" --tests "src/**/*.spec.ts"
    100x fails_without_fix --base main --test-cmd "pytest -q" --include-uncommitted
    100x fails_without_fix --base main --test-cmd "npx jest" --link-deps

The user's working tree, index and stash are never touched: everything happens in a
`git worktree add --detach` under a temp dir, removed afterwards. By default only
committed HEAD is checked; --include-uncommitted copies tracked edits and untracked
files into the worktree first. A fresh worktree has no gitignored dependency dirs
(node_modules, .venv, vendor/bundle); --link-deps symlinks the user's into it.

Warn-only: exit 0 unless --strict, which exits 1 on any warning. Setup errors exit 2.
"""
import argparse
import fnmatch
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile

DEFAULT_TESTS = ("tests/", "test/", "spec/", "__tests__/",
                 "*_test.*", "*.test.*", "*.spec.*", "test_*.py")
DEFAULT_TIMEOUT = 600
DEP_DIRS = ("node_modules", ".venv", "vendor/bundle")
OUTPUT_TAIL = 15


class SetupError(Exception):
    pass


def git(args, cwd, check=True):
    # --no-optional-locks stops read commands such as `git diff` from refreshing the
    # user's index as a side effect; this tool promises never to write it.
    r = subprocess.run(["git", "--no-optional-locks", *args], cwd=cwd,
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SetupError(f"git {' '.join(args)}: {r.stderr.strip() or r.returncode}")
    return r.stdout


def is_test_path(path, patterns):
    """A trailing "/" matches a directory of that name at any depth; a pattern with
    a "/" matches the whole path; anything else matches the file name."""
    parts = path.split("/")
    for pat in patterns:
        if pat.endswith("/"):
            if pat.rstrip("/") in parts[:-1]:
                return True
        elif "/" in pat:
            if fnmatch.fnmatch(path, pat):
                return True
        elif fnmatch.fnmatch(parts[-1], pat):
            return True
    return False


def changed_paths(repo, merge_base, include_uncommitted):
    if include_uncommitted:
        diff = git(["diff", "--name-only", "--no-renames", merge_base], repo)
        diff += git(["ls-files", "--others", "--exclude-standard"], repo)
    else:
        diff = git(["diff", "--name-only", "--no-renames", merge_base, "HEAD"], repo)
    return sorted({p for p in diff.splitlines() if p})


def copy_uncommitted(repo, worktree):
    patch = git(["diff", "--binary", "HEAD"], repo)
    if patch:
        r = subprocess.run(["git", "apply", "--whitespace=nowarn"], cwd=worktree,
                           input=patch, capture_output=True, text=True)
        if r.returncode != 0:
            raise SetupError(f"could not copy uncommitted changes: {r.stderr.strip()}")
    for rel in git(["ls-files", "--others", "--exclude-standard"], repo).splitlines():
        dest = pathlib.Path(worktree, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pathlib.Path(repo, rel), dest)


def revert_to_base(worktree, merge_base, paths, hooks):
    """Put each path back as it was at the merge-base; a file the branch added is
    deleted, because at the base it did not exist."""
    existed = [p for p in paths
               if subprocess.run(["git", "cat-file", "-e", f"{merge_base}:{p}"],
                                 cwd=worktree, capture_output=True).returncode == 0]
    if existed:
        # A path checkout runs post-checkout too; the user's hook must not fire.
        git(["-c", f"core.hooksPath={hooks}", "checkout", merge_base, "--", *existed], worktree)
    for p in set(paths) - set(existed):
        pathlib.Path(worktree, p).unlink(missing_ok=True)


def run_tests(argv, worktree, timeout):
    """(exit code, output). argv is a list and never goes through a shell, the same
    way verified.py runs a recorded command."""
    # The reverted file can have the same size and mtime second as the fixed one, and
    # Python then trusts the stale .pyc and runs the fix anyway.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    # os.walk does not descend into a --link-deps symlink, so the user's own .venv
    # keeps its caches.
    for root, dirs, _ in os.walk(worktree):
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")
            shutil.rmtree(os.path.join(root, "__pycache__"), ignore_errors=True)
    try:
        r = subprocess.run(argv, cwd=worktree, env=env, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SetupError(f"`{shlex.join(argv)}` timed out after {timeout}s")
    except OSError as e:
        raise SetupError(f"cannot run `{shlex.join(argv)}`: {e}")
    return r.returncode, r.stdout + r.stderr


def tail(output):
    lines = output.rstrip().splitlines()[-OUTPUT_TAIL:]
    return "\n".join("    " + line for line in lines)


def hooks_dir(parent):
    # An empty hooks dir: a post-checkout hook in the user's repo must not run
    # against, or outside of, the throwaway checkout.
    return os.path.join(parent, "no-hooks")


def make_worktree(repo, parent):
    worktree = os.path.join(parent, "wt")
    hooks = hooks_dir(parent)
    os.mkdir(hooks)
    git(["-c", f"core.hooksPath={hooks}", "worktree", "add", "--detach", worktree, "HEAD"],
        repo)
    return worktree


def missing_deps(repo, worktree):
    """Gitignored dependency dirs the user's repo has and the fresh worktree lacks."""
    return [d for d in DEP_DIRS
            if os.path.isdir(os.path.join(repo, d))
            and not os.path.lexists(os.path.join(worktree, d))
            and subprocess.run(["git", "check-ignore", "-q", d], cwd=repo,
                               capture_output=True).returncode == 0]


def link_deps(repo, worktree):
    # Symlinks, not copies: rmtree and `git worktree remove` unlink a symlink and never
    # descend into it, so the user's node_modules survives the cleanup.
    for d in missing_deps(repo, worktree):
        dest = os.path.join(worktree, d)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.symlink(os.path.join(repo, d), dest)


def remove_worktree(repo, worktree, parent):
    # No `git worktree prune`: it would also drop the user's other stale worktrees.
    git(["worktree", "remove", "--force", worktree], repo, check=False)
    shutil.rmtree(parent, ignore_errors=True)


def compare(args, repo, merge_base, source_files):
    """The two runs, in a worktree that exists only inside this function."""
    argv = shlex.split(args.test_cmd)
    parent = tempfile.mkdtemp(prefix="100x-fails-without-fix-")
    worktree = None
    try:
        worktree = make_worktree(repo, parent)
        if args.include_uncommitted:
            copy_uncommitted(repo, worktree)
        if args.link_deps:
            link_deps(repo, worktree)
        code, output = run_tests(argv, worktree, args.timeout)
        if code != 0:
            absent = missing_deps(repo, worktree)
            if absent:
                return ("warning", f"tests fail on HEAD in a fresh worktree (exit {code}) — "
                        f"{', '.join(absent)} is gitignored and not present there; rerun "
                        f"with --link-deps to symlink it in\n{tail(output)}")
            return ("warning", f"tests fail on HEAD (exit {code}) with the fix in place, "
                    f"so reverting it proves nothing; fix them first\n{tail(output)}")
        revert_to_base(worktree, merge_base, source_files, hooks_dir(parent))
        code, output = run_tests(argv, worktree, args.timeout)
        if code != 0:
            return "ok", f"tests fail without the fix (exit {code})"
        return ("warning", "tests still pass with the fix reverted — they may not test "
                f"the change (reverted: {', '.join(source_files)})")
    finally:
        if worktree:
            remove_worktree(repo, worktree, parent)
        else:
            shutil.rmtree(parent, ignore_errors=True)


def check(args):
    """(level, message), level one of ok / warning."""
    repo = git(["rev-parse", "--show-toplevel"], os.getcwd()).strip()
    merge_base = git(["merge-base", args.base, "HEAD"], repo).strip()
    patterns = [p.strip() for p in args.tests.split(",") if p.strip()] if args.tests \
        else list(DEFAULT_TESTS)
    changed = changed_paths(repo, merge_base, args.include_uncommitted)
    test_files = [p for p in changed if is_test_path(p, patterns)]
    source_files = [p for p in changed if not is_test_path(p, patterns)]
    if not test_files:
        return "warning", "no test files changed"
    if not source_files:
        return "warning", "no non-test files changed, so there is no fix to revert"
    return compare(args, repo, merge_base, source_files)


def parse_args(argv):
    ap = argparse.ArgumentParser(
        prog="100x fails_without_fix",
        description="Check that changed tests fail with the non-test changes reverted.")
    ap.add_argument("--base", required=True, help="ref whose merge-base with HEAD is 'before the fix'")
    ap.add_argument("--test-cmd", required=True, help="test command, split with shlex, no shell")
    ap.add_argument("--tests", help="comma-separated test-file globs (default: %s)"
                    % ",".join(DEFAULT_TESTS))
    ap.add_argument("--include-uncommitted", action="store_true",
                    help="also check uncommitted and untracked changes (default: HEAD only)")
    ap.add_argument("--link-deps", action="store_true",
                    help="symlink the repo's gitignored %s into the worktree" % ", ".join(DEP_DIRS))
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help="seconds per test run (default: %(default)s)")
    ap.add_argument("--strict", action="store_true", help="exit 1 on a warning")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not shlex.split(args.test_cmd):
        print("error: --test-cmd is empty", file=sys.stderr)
        return 2
    try:
        level, message = check(args)
    except SetupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{level}: {message}")
    return 1 if level == "warning" and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
