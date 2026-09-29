#!/usr/bin/env python3
"""Content fingerprint of the working tree.

Shared by the receipt writer and the enforcing hook. The fingerprint must change
whenever ANY code that would be committed changes -- that is what makes a
verification receipt impossible to reuse after an edit.
"""
import hashlib, subprocess, sys, os

# Derived state that must NOT be part of the content it attests to. Without this
# exclusion the receipt is self-referential: writing it changes the fingerprint it
# just recorded, so every receipt is instantly stale.
EXCLUDE = (
    ".claude/verification-receipt.json",   # derived: the attestation itself
    ".claude/verification-policy.json",    # config: declares WHICH checks are required,
                                           # so it must not invalidate the checks it demands
)


def _run(args, cwd=None, binary=False):
    r = subprocess.run(args, cwd=cwd, capture_output=True)
    if r.returncode != 0:
        return b"" if binary else ""
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def repo_root(cwd=None):
    out = _run(["git", "rev-parse", "--show-toplevel"], cwd).strip()
    return out or None


def fingerprint(cwd=None):
    """sha256 over: HEAD + all tracked modifications + all untracked file contents."""
    root = repo_root(cwd)
    if not root:
        return None
    h = hashlib.sha256()
    h.update(_run(["git", "rev-parse", "HEAD"], root).strip().encode())
    h.update(b"\x00tracked\x00")
    # staged + unstaged changes vs HEAD, including binary
    diff_args = ["git", "diff", "HEAD", "--binary", "--"] + \
        [":(exclude)" + e for e in EXCLUDE]
    h.update(_run(diff_args, root, binary=True))
    h.update(b"\x00untracked\x00")
    others = sorted(
        p for p in _run(["git", "ls-files", "--others", "--exclude-standard"], root).split("\n")
        if p and p not in EXCLUDE
    )
    for p in others:
        h.update(p.encode())
        fp = os.path.join(root, p)
        try:
            if os.path.isfile(fp) and os.path.getsize(fp) < 8 * 1024 * 1024:
                with open(fp, "rb") as f:
                    h.update(hashlib.sha256(f.read()).digest())
            else:
                h.update(str(os.path.getsize(fp)).encode())
        except OSError:
            h.update(b"?")
    return h.hexdigest()


if __name__ == "__main__":
    fp = fingerprint()
    if not fp:
        print("not a git repository", file=sys.stderr)
        sys.exit(1)
    print(fp)
