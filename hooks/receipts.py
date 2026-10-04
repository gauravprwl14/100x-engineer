"""Receipt signing, policy loading and receipt evaluation.

Shared by scripts/verified.py (writes receipts) and the PreToolUse and Stop hooks
(read them). Python stdlib only.

Threat model, stated so nobody over-trusts it: the signature stops a model from
satisfying the gate by writing JSON by hand, which an audit showed was enough to pass
the unsigned version. The key lives in the user's home directory and the agent runs as
the same user, so an agent that deliberately reads the key can still forge. Closing
that needs an OS-level boundary (a permission deny rule on the key path, or a sandbox),
not more code here.
"""
import datetime, hashlib, hmac, json, os, pathlib, secrets, shlex, stat

from verify_fingerprint import _git

# The receipt lives in the per-worktree git directory, never in the worktree: there it
# would show up as an untracked change (failing `agent_report lint`) and `git add -A`
# could commit it. `git rev-parse --git-path` keeps linked worktrees apart.
RECEIPT_GIT_PATH = "100x/verification-receipt.json"
RECEIPT = "$(git rev-parse --git-path " + RECEIPT_GIT_PATH + ")"
LEGACY_RECEIPT = ".claude/verification-receipt.json"
POLICY = ".claude/verification-policy.json"
RECEIPT_VERSION = 2
MODES = ("block", "off")
DEFAULT_KEY = pathlib.Path("~/.config/100x/receipt.key")


class GateError(Exception):
    """A condition the user must fix; the message says how."""


# ---------------------------------------------------------------- signing key

def key_path():
    return pathlib.Path(os.environ.get("HUNDREDX_KEY_FILE") or DEFAULT_KEY).expanduser()


def _create_key(path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return                          # another process won the race; read theirs
    with os.fdopen(fd, "w") as f:
        f.write(secrets.token_hex(32) + "\n")


def load_key(create=False):
    """Return the HMAC key bytes. Raises GateError with a fix-it message."""
    path = key_path()
    if create and not os.path.lexists(path):
        _create_key(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        raise GateError(f"no receipt signing key at {path}; `100x verified` creates it "
                        f"on first use")
    except OSError as e:
        raise GateError(f"receipt signing key {path} is unreadable or a symlink ({e})")
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        # A key others can read or replace signs nothing: anyone could mint receipts.
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() \
                or st.st_mode & 0o077:
            raise GateError(f"receipt signing key {path} must be a regular file owned "
                            f"by you with mode 0600 (fix: chmod 600 {path})")
        raw = f.read()
    try:
        key = bytes.fromhex(raw.decode("ascii").strip())
    except ValueError:              # includes UnicodeDecodeError: deny, never fail open
        key = b""
    if len(key) < 32:
        raise GateError(f"receipt signing key {path} is malformed; move it aside and "
                        f"re-run `100x verified` to create a new one")
    return key


def _canonical(label, entry):
    body = {k: v for k, v in entry.items() if k != "sig"}
    body["label"] = label        # signed, so an entry cannot be renamed to another label
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def sign(key, label, entry):
    return hmac.new(key, _canonical(label, entry), hashlib.sha256).hexdigest()


def signature_ok(key, label, entry):
    sig = entry.get("sig")
    return isinstance(sig, str) and hmac.compare_digest(sig, sign(key, label, entry))


# ---------------------------------------------------------------- policy

def normalize_command(value):
    """Policy and receipt commands compare as argv lists: a string is split the way
    a POSIX shell would split it, so `pytest -q` and ["pytest", "-q"] are equal."""
    if isinstance(value, str):
        return shlex.split(value)
    if isinstance(value, list) and all(isinstance(a, str) for a in value):
        return list(value)
    raise ValueError("a command must be a string or a list of strings")


def _read_policy_text(root, git_args):
    wt = pathlib.Path(root) / POLICY
    wt_text = wt.read_text() if wt.is_file() else None
    head_text = _git(["show", "HEAD:" + POLICY], root, git_args)
    if head_text is not None and wt_text != head_text:
        # The agent can edit any file in the worktree, including this one. Enforcing
        # the committed copy means weakening the policy (mode "off", fewer checks, or
        # deleting it) only takes effect after a commit that passed the old policy.
        return head_text, "HEAD", [
            f"{POLICY} differs from its committed version; the committed policy is "
            f"enforced until the change is committed"]
    return wt_text, "worktree", []


def load_policy(root, git_args=()):
    """Return a policy dict, or None when the repo has not configured one.

    {"mode", "required": {label: argv-or-None}, "legacy", "max_age", "notes"}
    Raises GateError when a policy exists but cannot be understood: the gate will not
    guess what a malformed policy meant.
    """
    text, source, notes = _read_policy_text(root, git_args)
    if text is None:
        return None
    try:
        pol = json.loads(text)
        if not isinstance(pol, dict):
            raise ValueError("top level must be an object")
        mode = pol.get("mode", "block")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        raw = pol.get("required_checks") or {}
        legacy = isinstance(raw, list)
        if legacy:
            if not all(isinstance(x, str) for x in raw):
                raise ValueError("required_checks list must contain labels")
            required = {label: None for label in raw}
            if raw:
                notes.append(
                    "policy uses the legacy list form, which checks labels but not "
                    "commands; bind each label to its command, e.g. "
                    '{"required_checks": {"test": "pytest -q"}}')
        elif isinstance(raw, dict):
            required = {str(k): normalize_command(v) for k, v in raw.items()}
        else:
            raise ValueError("required_checks must be an object or a list")
        max_age = pol.get("max_age_minutes")
        if max_age is not None and not isinstance(max_age, (int, float)):
            raise ValueError("max_age_minutes must be a number")
    except (ValueError, TypeError) as e:
        raise GateError(f"{POLICY} ({source}) is invalid: {e}. Fix it, or set "
                        f'{{"mode": "off"}} to disable the gate for this repo')
    return {"mode": mode, "required": required, "legacy": legacy,
            "max_age": max_age, "notes": notes, "source": source}


# ---------------------------------------------------------------- receipts

def receipt_path(root, git_args=()):
    """The receipt's absolute path in the per-worktree git directory.

    Raises GateError when git cannot name it, or when the `100x/` directory or the
    receipt is a symlink, or `100x/` does not sit directly in the resolved git
    directory: any of those could redirect a write or substitute a receipt.
    """
    out = _git(["rev-parse", "--absolute-git-dir", "--git-path", RECEIPT_GIT_PATH],
               root, git_args)
    lines = (out or "").splitlines()
    if len(lines) != 2:
        raise GateError(f"cannot locate the git directory of {root} for the receipt")
    gitdir, path = pathlib.Path(lines[0]), pathlib.Path(lines[1])
    if not path.is_absolute():          # --git-path answers relative to the cwd
        path = pathlib.Path(root) / path
    for p in (path.parent, path):
        if os.path.islink(p):
            raise GateError(f"{p} is a symlink; refusing to use it for the receipt. "
                            f"Replace it with a real directory or file")
    if os.path.realpath(path.parent.parent) != os.path.realpath(gitdir):
        raise GateError(f"{path} is not inside the git directory {gitdir}")
    return path


def legacy_note(root):
    """One line when a receipt from before the move is still in the worktree."""
    if os.path.lexists(pathlib.Path(root) / LEGACY_RECEIPT):
        return (f"{LEGACY_RECEIPT} is from an older version and is ignored (receipts "
                f"now live in the git directory); delete it")
    return None


def read_receipt(root, git_args=()):
    path = receipt_path(root, git_args)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    except OSError as e:
        raise GateError(f"{path} is unreadable ({e}); re-run `100x verified`")
    try:
        with os.fdopen(fd, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
        checks = data.get("checks")
        if not isinstance(checks, dict):
            raise ValueError("no checks object")
        return data
    except (ValueError, OSError, AttributeError) as e:
        raise GateError(f"{path} is unreadable ({e}); re-run `100x verified`, which "
                        f"replaces it")


def evaluate(root, policy, current_fp, key, git_args=()):
    """Judge the receipt against the current content and the policy.

    Returns {"problems": [str], "notes": [str], "fresh": {label: entry},
             "missing": [labels]}; an empty `problems` list means the gate passes.
    A forged or tampered entry is a problem even when other entries are valid: a
    receipt containing a forgery is not evidence of anything.
    """
    problems, notes = [], []
    legacy = legacy_note(root)
    if legacy:
        notes.append(legacy)
    data = read_receipt(root, git_args)
    if data is None:
        return {"problems": [f"no verification receipt at {RECEIPT}"], "notes": notes,
                "fresh": {}, "missing": sorted(policy["required"])}
    checks = data["checks"]
    if not checks:
        return {"problems": [f"{RECEIPT} contains no checks"], "notes": notes,
                "fresh": {}, "missing": sorted(policy["required"])}
    if data.get("version") != RECEIPT_VERSION:
        problems.append(f"{RECEIPT} is unsigned (version {data.get('version')!r}); "
                        f"receipts must be written by `100x verified`")
        return {"problems": problems, "notes": notes, "fresh": {},
                "missing": sorted(policy["required"])}
    forged = sorted(label for label, entry in checks.items()
                    if not isinstance(entry, dict) or not signature_ok(key, label, entry))
    if forged:
        problems.append(f"receipt entr{'y' if len(forged) == 1 else 'ies'} "
                        f"{', '.join(forged)} failed signature verification (forged, "
                        f"edited by hand, or signed with another key); only "
                        f"`100x verified` may write receipts")
        return {"problems": problems, "notes": notes, "fresh": {},
                "missing": sorted(policy["required"])}

    fresh = {n: c for n, c in checks.items() if c.get("fingerprint") == current_fp}
    stale = sorted(set(checks) - set(fresh))
    if stale:
        notes.append(f"ignored {len(stale)} stale receipt entr"
                     f"{'y' if len(stale) == 1 else 'ies'} ({', '.join(stale)})")
    if not fresh:
        problems.append(
            f"the code changed after verification: receipts on record "
            f"({', '.join(sorted(checks))}) were produced against different content. "
            f"A passing check from before an edit proves nothing about the edit")

    for n, c in sorted(fresh.items()):
        if c.get("exit_code") != 0:
            problems.append(f"check `{n}` FAILED: `{c.get('command')}` exited "
                            f"{c.get('exit_code')}")

    missing = []
    for label, argv in sorted(policy["required"].items()):
        entry = fresh.get(label)
        if entry is None:
            missing.append(label)
        elif argv is not None and entry.get("argv") != argv:
            problems.append(f"check `{label}` ran `{entry.get('command')}`, but the "
                            f"policy binds `{label}` to `{shlex.join(argv)}`")
    if missing and fresh:
        problems.append(f"required check(s) not run against the current content: "
                        f"{', '.join(missing)}")

    if policy.get("max_age"):
        now = datetime.datetime.now(datetime.timezone.utc)
        for n, c in sorted(fresh.items()):
            try:
                at = datetime.datetime.fromisoformat(c["at"])
            except (KeyError, TypeError, ValueError):
                problems.append(f"check `{n}` has no valid timestamp")
                continue
            if (now - at).total_seconds() / 60 > policy["max_age"]:
                problems.append(f"check `{n}` is older than {policy['max_age']} min")
    return {"problems": problems, "notes": notes, "fresh": fresh, "missing": missing}


def rerun_hint(policy):
    labels = sorted(policy["required"]) if policy else []
    if not labels:
        return "    100x verified --name test -- <your test command>"
    lines = []
    for label in labels:
        argv = policy["required"][label]
        lines.append(f"    100x verified --name {label}" +
                     ("" if argv is not None else " -- <its command>"))
    return "\n".join(lines)
