#!/usr/bin/env python3
"""Pin and export the trees a PR review reads: head, merge-base, diff, default branch.

    pr_snapshot.py --repo CLONE --pr N [--pr N ...] --dest DIR [--base REF] [--remote NAME] [--url PR_URL]

Read-only on the clone: the only git call that changes anything is `git fetch`, which
updates remote-tracking refs and FETCH_HEAD. Never checks out, never writes the working
tree. Everything else lands under --dest:

    <dest>/<default-branch>/   tree of the remote's default branch
    <dest>/<n>/                tree at the PR head          (what the review links to)
    <dest>/base-<n>/           tree at the merge-base       (the diff's "before")
    <dest>/<n>.diff            <base>...<head>
    <dest>/PINS.md             one row per PR: base, head SHA, merge-base, commits, files, behind

The PR head is fetched from `pull/<n>/head` on the remote (GitHub and GitHub Enterprise
publish it for every PR, forks included), so no gh call is needed. Remote: --remote, else
the remote whose URL matches --url, else the only remote, else `upstream`, else `origin`.
Base: --base, else the remote's default branch.
Exit codes: 0 ok, 1 git failure (named), 2 usage. Python stdlib only.
"""
import argparse, datetime, io, pathlib, re, subprocess, sys, tarfile

PULL_REF = "pull/{n}/head"
FALLBACK_DEFAULTS = ("main", "master")


class GitError(Exception):
    pass


def git(repo, *args, binary=False):
    p = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True)
    if p.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {p.stderr.decode(errors='replace').strip()}")
    return p.stdout if binary else p.stdout.decode(errors="replace").strip()


def git_ok(repo, *args):
    try:
        return git(repo, *args)
    except GitError:
        return None


def norm_url(u):
    """Comparable form of a remote or PR URL: host/owner/repo, lower case."""
    u = u.strip().split("/pull/")[0]
    u = re.sub(r"^[a-z+]+://", "", u, flags=re.I)
    u = re.sub(r"^[^@/]+@", "", u)
    u = re.sub(r"\.git/?$", "", u.rstrip("/"))
    u = re.sub(r"^([^/:]+)(:\d+)?[:/]", r"\1/", u)
    return u.lower()


def pick_remote(repo, want, url):
    names = (git_ok(repo, "remote") or "").split()
    if not names: raise GitError(f"{repo} has no git remote")
    if want:
        if want not in names: raise GitError(f"no remote named '{want}' (have: {', '.join(names)})")
        return want
    if url:
        target = norm_url(url)
        for n in names:
            if norm_url(git_ok(repo, "remote", "get-url", n) or "") == target: return n
        raise GitError(f"no remote of {repo} points at {target} (have: {', '.join(names)})")
    if len(names) == 1: return names[0]
    for n in ("upstream", "origin"):
        if n in names: return n
    return names[0]


def default_branch(repo, remote):
    ref = git_ok(repo, "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
    if ref: return ref.split("/", 1)[1]
    out = git_ok(repo, "ls-remote", "--symref", remote, "HEAD") or ""
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", out, re.M)
    if m: return m.group(1)
    for b in FALLBACK_DEFAULTS:
        if git_ok(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{b}"): return b
    raise GitError(f"cannot tell the default branch of '{remote}' -- pass --base")


def export(repo, rev, dest):
    """git archive <rev> into dest, refusing members that would escape it."""
    data = git(repo, "archive", "--format=tar", rev, binary=True)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            target = (dest / m.name).resolve()
            if root != target and root not in target.parents:
                raise GitError(f"archive member escapes {dest}: {m.name}")
            if m.issym() or m.islnk():
                link = (target.parent / m.linkname).resolve()
                if root != link and root not in link.parents:
                    raise GitError(f"archive link escapes {dest}: {m.name} -> {m.linkname}")
        tf.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


def snapshot(a):
    repo = pathlib.Path(a.repo).resolve()
    if git_ok(repo, "rev-parse", "--git-dir") is None: raise GitError(f"{repo} is not a git repository")
    remote = pick_remote(repo, a.remote, a.url)
    git(repo, "fetch", "--quiet", remote)
    default = default_branch(repo, remote)
    base = a.base or default
    dest = pathlib.Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    def_ref = f"{remote}/{default}"
    export(repo, def_ref, dest / default)
    repo_url = git_ok(repo, "remote", "get-url", remote) or remote
    rows = []
    for n in a.pr:
        git(repo, "fetch", "--quiet", remote, PULL_REF.format(n=n))
        sha = git(repo, "rev-parse", "FETCH_HEAD^{commit}")
        base_ref = f"{remote}/{base}" if git_ok(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{base}") else base
        git(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
        mb = git(repo, "merge-base", base_ref, sha)
        commits = git(repo, "rev-list", "--count", f"{base_ref}..{sha}")
        files = len([x for x in git(repo, "diff", "--name-only", f"{base_ref}...{sha}").splitlines() if x])
        behind = git(repo, "rev-list", "--count", f"{sha}..{base_ref}")
        export(repo, sha, dest / str(n))
        export(repo, mb, dest / f"base-{n}")
        (dest / f"{n}.diff").write_bytes(git(repo, "diff", f"{base_ref}...{sha}", binary=True))
        rows.append(f"| {n} | `{base}` | `{PULL_REF.format(n=n)}` | `{sha}` | `{mb[:10]}` | {commits} | {files} | {behind} |")
    pins = ["# Pins", "",
            f"> **In 10 seconds:** {len(rows)} PR(s) pinned on {datetime.date.today().isoformat()}; every permalink in this review points at a head SHA below.", "",
            f"Repo: {repo_url} · `{def_ref}` @ `{git(repo, 'rev-parse', def_ref)}`", "",
            "| PR | Base | Head | Head SHA | Merge-base | Commits | Files | Behind base |",
            "|---|---|---|---|---|---|---|---|"] + rows
    text = "\n".join(pins) + "\n"
    (dest / "PINS.md").write_text(text, encoding="utf-8")
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pr_snapshot.py", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="local clone (a worktree is fine)")
    ap.add_argument("--pr", required=True, action="append", type=int, help="PR number; repeat for several")
    ap.add_argument("--dest", required=True, help="snapshot directory to write")
    ap.add_argument("--base", help="base branch (default: the remote's default branch)")
    ap.add_argument("--remote", help="remote name (default: detected)")
    ap.add_argument("--url", help="PR or repo URL; picks the remote that points at it")
    a = ap.parse_args(argv)
    try:
        print(snapshot(a), end="")
    except GitError as e:
        print(f"pr_snapshot: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
