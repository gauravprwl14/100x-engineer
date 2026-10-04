#!/usr/bin/env python3
"""Run a verification command and write a signed, content-bound receipt."""
import datetime, hashlib, json, os, pathlib, shlex, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "hooks"))
from verify_fingerprint import fingerprint, repo_root
from receipts import (POLICY, RECEIPT, RECEIPT_VERSION, GateError, load_key,
                      load_policy, sign, signature_ok)
from _paths import safe_write_text

# Variables that change what a check runs without changing its command line, each able
# to turn a real suite into a passing no-op: PYTEST_ADDOPTS (`--collect-only`,
# `-k nothing`), PYTEST_PLUGINS (a plugin that skips everything), NODE_OPTIONS
# (`--require` a preload that exits 0), GOFLAGS (`-run=^$`), and the two dynamic-loader
# preloads. The receipt records the command, so a run shaped by any of these would
# attest to something the command does not say.
RUNNER_ENV = ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "NODE_OPTIONS", "GOFLAGS",
              "LD_PRELOAD", "DYLD_INSERT_LIBRARIES")

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

Refuses (exit 2) when a variable that can turn a check into a no-op is set
(PYTEST_ADDOPTS, PYTEST_PLUGINS, NODE_OPTIONS, GOFLAGS, LD_PRELOAD,
DYLD_INSERT_LIBRARIES), when the command's program would come from a PATH entry inside
the repository or a temp directory, or when .claude/ or the receipt is a symlink.

Exits with the wrapped command's exit code (2 on a usage or policy refusal)."""


class Refusal(Exception):
    """A reason not to record a receipt; the message says how to fix it."""


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _temp_roots():
    roots = [tempfile.gettempdir(), "/tmp", "/var/tmp", "/dev/shm"]
    # macOS gives each user a private temp dir under /var/folders that TMPDIR usually
    # names; when TMPDIR is unset or redirected, gettempdir() no longer returns it.
    if sys.platform == "darwin":
        r = subprocess.run(["getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True)
        if r.returncode == 0:
            roots.append(r.stdout.strip())
    return {os.path.realpath(p) for p in roots if p and os.path.isdir(p)}


def _tool_managed(directory):
    """A virtualenv's or node_modules' bin directory: on PATH inside the repository on
    purpose, written by the package manager rather than committed."""
    d = pathlib.Path(directory)
    return (d.parent / "pyvenv.cfg").is_file() or \
        (d.name == ".bin" and d.parent.name == "node_modules")


def resolve_executable(name, root):
    """(path to run, its real path) for argv[0], or raise Refusal.

    A program found first in a PATH entry inside the repository or a temp directory
    shadows the real tool: a committed `bin/pytest` or a planted `/tmp/x/npm` that
    exits 0 would make any receipt pass. A symlink there to a system binary is fine,
    so the check is on the real path of what would run.
    """
    if os.sep in name:
        path = os.path.join(root, name)
        return path, os.path.realpath(path)
    temps = _temp_roots()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        directory = os.path.join(root, entry or ".")
        cand = os.path.join(directory, name)
        if not (os.path.isfile(cand) and os.access(cand, os.X_OK)):
            continue
        real = os.path.realpath(cand)
        where = "the repository" if _inside(real, root) else next(
            (t for t in temps if _inside(real, t)), None)
        if where and not _tool_managed(directory):
            raise Refusal(f"`{name}` resolves to {real}, inside {where}, ahead of the "
                          f"system's copy on PATH; a program there can fake a pass. "
                          f"Remove {entry or '.'} from PATH, or name the program by "
                          f"its path in the policy")
        return cand, real
    raise Refusal(f"`{name}` was not found on PATH")


def _check_receipt_path(root):
    """The receipt goes under .claude/ at the git root. A committed symlink there
    (`.claude -> ~/somewhere`, or the receipt itself pointing at a file) would redirect
    the write, so both are refused before anything is written."""
    claude = pathlib.Path(root) / ".claude"
    for p in (claude, pathlib.Path(root) / RECEIPT):
        if os.path.islink(p):
            raise Refusal(f"{p} is a symlink; refusing to write the receipt through "
                          f"it. Replace it with a real directory or file")
    if claude.exists() and not _inside(claude, root):
        raise Refusal(f"{claude} resolves outside the repository")


def _display_path(path):
    """The executable's real path, with the home directory written as `~`: receipts
    must not carry a username or home layout (tests/test_safety.sh), and `~/x` still
    names exactly one file for the person reading it."""
    home = os.path.realpath(os.path.expanduser("~"))
    if _inside(path, home):
        return "~" + path[len(home):]
    return path


def _policy_sha(root):
    path = pathlib.Path(root) / POLICY
    if not path.is_file():
        return "absent"
    return hashlib.sha256(path.read_text().encode()).hexdigest()


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

    try:
        set_vars = [v for v in RUNNER_ENV if os.environ.get(v)]
        if set_vars:
            raise Refusal(f"{', '.join(set_vars)} is set; it can change what "
                          f"`{shlex.join(cmd)}` runs without changing the command the "
                          f"receipt records. Unset it and re-run")
        _check_receipt_path(root)
        exe, exe_real = resolve_executable(cmd[0], root)
    except Refusal as e:
        print(f"verified: refusing to record `{name}`: {e}", file=sys.stderr)
        return 2

    before = fingerprint()
    t0 = time.time()
    try:
        rc = subprocess.run(cmd, cwd=root, executable=exe).returncode
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
        "fingerprint": after, "duration_s": dur, "exe": _display_path(exe_real),
        "policy_sha": _policy_sha(root),
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    entry["sig"] = sign(key, name, entry)
    checks[name] = entry
    try:
        _check_receipt_path(root)       # again: the check itself may have planted one
    except Refusal as e:
        print(f"verified: refusing to record `{name}`: {e}", file=sys.stderr)
        return 2
    safe_write_text(path, json.dumps({"version": RECEIPT_VERSION, "checks": checks},
                                     indent=2) + "\n", root, origin="verified")
    status = "PASS" if rc == 0 else f"FAIL(rc={rc})"
    print(f"verified: {name} {status} in {dur}s -> {RECEIPT}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
