#!/usr/bin/env python3
"""Content fingerprint of the working tree.

Shared by the receipt writer and the enforcing hooks. The fingerprint must change
whenever any content that could be committed changes, and must NOT change when only
git bookkeeping changes: staging a file, or committing it, moves no bytes, so a
receipt taken before `git add && git commit` has to survive into the following push.

The fingerprint is therefore a hash over (path, mode, blob id) of every file in the
working tree that git tracks or would pick up (tracked + untracked-not-ignored), with
blob ids computed the way `git add` would compute them. HEAD is deliberately absent.
"""
import hashlib, os, stat, subprocess, sys

# Derived state that must NOT be part of the content it attests to. Without this
# exclusion the receipt is self-referential: writing it changes the fingerprint it
# just recorded, so every receipt is instantly stale.
EXCLUDE = (
    ".claude/verification-receipt.json",   # derived: the attestation itself
    ".claude/verification-policy.json",    # config: re-read and enforced on every
                                           # check, so editing it must not invalidate
                                           # the checks it demands
)

# fsmonitor is a repo-configured program git would run on our behalf; the gate has no
# reason to execute repo-supplied code just to read file state.
_SAFE = ["-c", "core.fsmonitor=false"]


def _git(args, cwd=None, git_args=(), binary=False, stdin=None):
    try:
        r = subprocess.run(["git", *_SAFE, *git_args, *args], cwd=cwd,
                           capture_output=True, input=stdin)
    except (OSError, ValueError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout if binary else r.stdout.decode("utf-8", "surrogateescape")


def repo_root(cwd=None, git_args=()):
    out = _git(["rev-parse", "--show-toplevel"], cwd, git_args)
    return out.strip() if out and out.strip() else None


def _z(out):
    return [p for p in (out or "").split("\0") if p]


def _blob_id(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _hash_paths(root, git_args, paths):
    """Blob ids for worktree files, through git so clean filters and eol conversion
    match what `git add` would store."""
    result = {}
    batch = [p for p in paths if "\n" not in p]
    if batch:
        out = _git(["hash-object", "--stdin-paths"], root, git_args,
                   stdin=("\n".join(batch) + "\n").encode("utf-8", "surrogateescape"))
        ids = (out or "").split()
        if len(ids) == len(batch):
            result.update(zip(batch, ids))
    for p in paths:
        if p not in result:
            out = _git(["hash-object", "--", p], root, git_args)
            result[p] = out.strip() if out else "unreadable"
    return result


def snapshot(cwd=None, git_args=()):
    """Return {fingerprint, root, unstaged, untracked} or None outside a repo.

    `unstaged` lists tracked paths whose worktree content differs from the index;
    `untracked` lists files git would pick up but does not track. Both matter to a
    commit: verification ran with them present, the commit will not contain them.
    """
    root = repo_root(cwd, git_args)
    if not root:
        return None
    index = {}
    for rec in _z(_git(["ls-files", "-s", "-z"], root, git_args)):
        meta, _, path = rec.partition("\t")
        mode, sha, stage = (meta.split() + ["", "", ""])[:3]
        if stage == "0":
            index[path] = (mode, sha)
        else:
            index[path] = (mode, "conflict")
    changed = set(_z(_git(["diff-files", "--name-only", "-z"], root, git_args)))
    untracked = set(_z(_git(["ls-files", "-z", "--others", "--exclude-standard"],
                            root, git_args)))

    entries, to_hash = {}, []
    for path in sorted(set(index) | untracked):
        if path in EXCLUDE:
            continue
        full = os.path.join(root, path)
        try:
            st = os.lstat(full)
        except OSError:
            continue                    # deleted: absent content, staged or not
        imode, isha = index.get(path, (None, None))
        if path.endswith("/") or stat.S_ISDIR(st.st_mode):
            # A gitlink (submodule) or nested repository: its own HEAD is its content.
            # An uninitialised submodule is an empty directory, where rev-parse would
            # answer with the PARENT's HEAD and make the fingerprint commit-sensitive.
            if imode == "160000" and path not in changed:
                entries[path] = ["160000", isha]
                continue
            top = repo_root(full)
            own = top and os.path.realpath(top) == os.path.realpath(full.rstrip("/"))
            sub = (_git(["rev-parse", "HEAD"], full) or "") if own else ""
            entries[path] = ["160000", "sub:" + sub.strip()]
        elif stat.S_ISLNK(st.st_mode):
            target = os.fsencode(os.readlink(full))
            entries[path] = ["120000", _blob_id(target)]
        else:
            mode = "100755" if st.st_mode & 0o111 else "100644"
            if path in index and path not in changed and isha != "conflict":
                entries[path] = [mode, isha]
            else:
                entries[path] = [mode, None]
                to_hash.append(path)
    for path, blob in _hash_paths(root, git_args, to_hash).items():
        entries[path][1] = blob

    unstaged = sorted(p for p in changed if p in entries and p in index
                      and index[p][1] != entries[p][1])
    return {"fingerprint": _digest(entries), "root": root, "unstaged": unstaged,
            "untracked": sorted(p for p in untracked if p in entries)}


def _digest(entries):
    h = hashlib.sha256()
    for path in sorted(entries):
        mode, blob = entries[path]
        h.update(path.encode("utf-8", "surrogateescape") + b"\0" +
                 mode.encode() + b"\0" + (blob or "").encode() + b"\0")
    return h.hexdigest()


def tree_fingerprint(cwd=None, git_args=(), rev="HEAD"):
    """Fingerprint of a commit's tree in snapshot()'s format.

    A push sends commits, not the working tree, so the push gate needs to know whether
    the commit being sent holds exactly the content a receipt was taken against. Equal
    to fingerprint() precisely when `rev` contains the working tree's content, with the
    same exclusions. Returns None when `rev` does not name a commit.
    """
    root = repo_root(cwd, git_args)
    if not root:
        return None
    out = _git(["ls-tree", "-r", "-z", "--full-tree", rev], root, git_args)
    if out is None:
        return None
    entries = {}
    for rec in _z(out):
        meta, _, path = rec.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or path in EXCLUDE:
            continue
        entries[path] = [parts[0], parts[2]]
    return _digest(entries)


def fingerprint(cwd=None, git_args=()):
    snap = snapshot(cwd, git_args)
    return snap["fingerprint"] if snap else None


if __name__ == "__main__":
    fp = fingerprint()
    if not fp:
        print("not a git repository", file=sys.stderr)
        sys.exit(1)
    print(fp)
