#!/usr/bin/env python3
"""Run a verification command and write a signed, content-bound receipt."""
import datetime, json, os, pathlib, shlex, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "hooks"))
from verify_fingerprint import fingerprint, repo_root
from receipts import (RECEIPT, RECEIPT_VERSION, GateError, load_key, load_policy,
                      sign, signature_ok)

USAGE = """100x verified -- run a check and write a signed, content-bound receipt

    100x verified [--name LABEL] -- COMMAND [ARGS...]
    100x verified --name LABEL            run the command the policy binds to LABEL

    --name LABEL   label for this check (default: "verify"); the receipt records one
                   entry per label, so `test`, `typecheck` and `lint` coexist

Writes .claude/verification-receipt.json binding the command, its exit code and a
fingerprint of the exact file content that was verified, signed with HMAC-SHA256.
The key is ~/.config/100x/receipt.key (created 0600 on first use; HUNDREDX_KEY_FILE
overrides it). Any content change -- tracked, staged or a new untracked file --
invalidates the receipt; staging or committing does not, because no content moves.

When .claude/verification-policy.json binds LABEL to a command, only that exact
command may be recorded under LABEL; anything else is refused, so `--name test -- true`
cannot stand in for the real suite.

Examples:
    100x verified --name test      -- npm test
    100x verified --name typecheck -- npx tsc --noEmit
    100x verified --name test                 # uses the policy's command for `test`

Exits with the wrapped command's exit code (2 on a usage or policy refusal)."""


def parse(argv):
    argv = list(argv)
    name, cmd = "verify", None
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    if "--name" in argv:
        i = argv.index("--name")
        if i + 1 >= len(argv):
            raise SystemExit("verified: --name needs a label")
        name = argv[i + 1]
        del argv[i:i + 2]
    if cmd is None:
        cmd = argv
    elif argv:
        raise SystemExit(f"verified: unexpected arguments before `--`: {' '.join(argv)}")
    return name, cmd


def main(argv):
    own = argv[:argv.index("--")] if "--" in argv else argv
    if not argv or any(a in ("--help", "-h") for a in own):
        print(USAGE)
        return 0
    try:
        name, cmd = parse(argv)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    root = repo_root()
    if not root:
        if not cmd:
            print("verified: no command given", file=sys.stderr)
            return 2
        print("verified: not a git repository; running command without a receipt",
              file=sys.stderr)
        return subprocess.run(cmd).returncode

    try:
        policy = load_policy(root)
        key = load_key(create=True)
    except GateError as e:
        print(f"verified: {e}", file=sys.stderr)
        return 2
    for note in (policy or {}).get("notes", []):
        print(f"verified: warning: {note}", file=sys.stderr)

    bound = (policy or {}).get("required", {}).get(name)
    if not cmd:
        if bound is None:
            print(f"verified: no command given and the policy binds no command to "
                  f"`{name}`\n\n{USAGE}", file=sys.stderr)
            return 2
        cmd = bound
    elif bound is not None and cmd != bound:
        print(f"verified: refusing to record `{shlex.join(cmd)}` as `{name}`: the policy "
              f"binds `{name}` to `{shlex.join(bound)}`.\nRun `100x verified --name "
              f"{name}` to use the policy's command, or record this under another label.",
              file=sys.stderr)
        return 2

    before = fingerprint()
    t0 = time.time()
    try:
        rc = subprocess.run(cmd, cwd=root).returncode
    except OSError as e:
        print(f"verified: cannot run `{shlex.join(cmd)}`: {e}", file=sys.stderr)
        rc = 127
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
    try:
        existing = json.loads(path.read_text()) if path.exists() else {}
    except (ValueError, OSError):
        existing = {}
    old = existing.get("checks") if isinstance(existing, dict) else None
    # Carry forward only entries this key signed for this exact content; a stale or
    # foreign entry would otherwise ride along under a fresh signature's file.
    checks = {k: v for k, v in (old or {}).items()
              if isinstance(v, dict) and v.get("fingerprint") == after
              and signature_ok(key, k, v)}
    entry = {
        "argv": list(cmd), "command": shlex.join(cmd), "exit_code": rc,
        "fingerprint": after, "duration_s": dur,
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    entry["sig"] = sign(key, name, entry)
    checks[name] = entry
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"version": RECEIPT_VERSION, "checks": checks},
                              indent=2) + "\n")
    os.replace(tmp, path)
    status = "PASS" if rc == 0 else f"FAIL(rc={rc})"
    print(f"verified: {name} {status} in {dur}s -> {RECEIPT}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
