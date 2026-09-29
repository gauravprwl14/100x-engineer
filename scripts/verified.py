#!/usr/bin/env python3
"""Run a verification command and write a content-bound receipt.

    verified.py -- npm test
    verified.py --name typecheck -- npx tsc --noEmit

Writes .claude/verification-receipt.json binding the command's exit code to a
fingerprint of the exact working-tree content that was verified. The receipt
becomes invalid the moment any file changes.
"""
import json, os, subprocess, sys, time, datetime, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "hooks"))
from verify_fingerprint import fingerprint, repo_root

RECEIPT = ".claude/verification-receipt.json"


USAGE = """verified.py -- run a check and write a content-bound receipt

    verified.py [--name LABEL] -- COMMAND [ARGS...]

    --name LABEL   label for this check (default: "verify"); the receipt records one
                   entry per label, so `test`, `typecheck` and `lint` coexist

Writes .claude/verification-receipt.json binding the command's exit code to a
fingerprint of the exact working-tree content that was verified. The receipt becomes
invalid the moment any tracked, staged or untracked file changes, which is what stops
a passing result being reused after an edit.

Examples:
    verified.py --name test      -- npm test
    verified.py --name typecheck -- npx tsc --noEmit
    verified.py -- pytest -q

Exits with the wrapped command's exit code."""


def main(argv):
    if not argv or any(a in ("--help", "-h") for a in argv):
        print(USAGE)
        return 0
    name = "verify"
    if "--name" in argv:
        i = argv.index("--name"); name = argv[i + 1]; del argv[i:i + 2]
    if "--" in argv:
        cmd = argv[argv.index("--") + 1:]
    else:
        cmd = argv
    if not cmd:
        print("usage: verified.py [--name LABEL] -- COMMAND ...", file=sys.stderr)
        return 2

    root = repo_root()
    if not root:
        print("verified: not a git repository; running command without a receipt", file=sys.stderr)
        return subprocess.run(cmd).returncode

    before = fingerprint()
    t0 = time.time()
    rc = subprocess.run(cmd, cwd=root).returncode
    dur = round(time.time() - t0, 2)
    after = fingerprint()

    if before != after:
        # the command itself mutated the tree (codegen, formatter, snapshot write).
        # Bind to the POST state, since that is what would be committed.
        print(f"verified: tree changed during '{name}' -- receipt bound to post-run state",
              file=sys.stderr)

    path = pathlib.Path(root) / RECEIPT
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            existing = {}
    checks = {k: v for k, v in (existing.get("checks") or {}).items()
              if v.get("fingerprint") == after}     # drop receipts for stale content
    checks[name] = {
        "command": " ".join(cmd), "exit_code": rc, "fingerprint": after,
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "duration_s": dur,
    }
    path.write_text(json.dumps({"version": 1, "checks": checks}, indent=2) + "\n")
    status = "PASS" if rc == 0 else f"FAIL(rc={rc})"
    print(f"verified: {name} {status} in {dur}s -> {RECEIPT}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
