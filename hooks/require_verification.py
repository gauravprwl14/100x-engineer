#!/usr/bin/env python3
"""PreToolUse gate: block completion-shaped actions without fresh verification.

Instructions asking a model to "verify before claiming done" are prose the model can
talk itself past. This is a gate it cannot: the receipt is signed and bound to a
content fingerprint, so editing a file after verifying invalidates the proof, and
hand-writing a receipt does not produce one.

hooks.json routes broadly (any command mentioning git, gh or a publisher) because its
`if` patterns cannot see past `git -C <path>` or `git -c k=v`; this script parses the
command and decides. Reads hook JSON on stdin, writes a decision on stdout.

Decisions: deny (gate failed), ask (an explicit [skip-verify] -- a human approves it,
the agent cannot), or no decision at all when the gate passes. A passing gate does not
emit "allow": that would also skip the user's own `ask` permission rules for the
command, and a verification gate has no business granting permissions.

Fails OPEN on internal error -- a broken gate must not brick the user's shell.
"""
import json, os, pathlib, re, shlex, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    from verify_fingerprint import _git, repo_root, snapshot
    from receipts import (POLICY, RECEIPT, GateError, evaluate, load_key, load_policy,
                          rerun_hint)
except Exception:                                   # fail open, see module docstring
    print(json.dumps({}))
    sys.exit(0)

SKIP_TOKEN = re.compile(r"\[skip-verify\]|\[no-verify\]")
SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", "\n", "|&", ";;"}
REDIRECT = re.compile(r"^[<>&]+$|^<<-?$")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
WRAPPERS = {"env", "command", "exec", "nohup", "time", "nice", "sudo", "builtin"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
NOT_ALIASES = {  # common git builtins; anything else may be an alias worth resolving
    "add", "am", "apply", "bisect", "blame", "branch", "cat-file", "cherry-pick",
    "clone", "commit", "config", "describe", "diff", "fetch", "grep", "init", "log",
    "ls-files", "merge", "mv", "pull", "push", "rebase", "reflog", "remote",
    "restore", "rev-parse", "revert", "show", "status", "switch", "tag", "worktree"}
GIT_OPT_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env",
               "--super-prefix", "--list-cmds"}
COMMIT_LONG_ARG = {"--message", "--file", "--reuse-message", "--reedit-message",
                   "--fixup", "--squash", "--author", "--date", "--cleanup",
                   "--template", "--trailer", "--pathspec-from-file", "--untracked-files"}
# Options that take a separate value, per tool, so the value is not mistaken for the
# subcommand (`-r` is a value-taking --repository for twine but a flag for pnpm).
OPT_ARG = {
    "npm": {"--registry", "--workspace", "-w", "--prefix", "--userconfig", "--cache",
            "--loglevel", "--otp", "--tag", "--access"},
    "pnpm": {"--registry", "-C", "--dir", "--filter", "-F", "--tag", "--access",
             "--otp", "--workspace-dir", "--loglevel"},
    "yarn": {"--cwd", "--registry", "--tag", "--access", "--otp"},
    "twine": {"-r", "--repository", "--repository-url", "-u", "--username",
              "--config-file", "-c", "--comment"},
    "uv": {"--directory", "--project", "--config-file", "--index", "--publish-url",
           "--cache-dir", "--python", "-p"},
    "gh": {"-R", "--repo"},
}


GIT_LABELS = {
    "commit": "git commit",
    "push": "git push",
    "tag": "git tag",
}


class Action:
    def __init__(self, label, cwd, git_args=(), evasion=None, commit_all=False):
        self.label, self.cwd, self.git_args = label, cwd, list(git_args)
        self.evasion, self.commit_all = evasion, commit_all


# ---------------------------------------------------------------- tokenising

def _strip_heredocs(cmd):
    """Drop heredoc bodies: their lines are data, not commands, and a body line that
    happens to start with a gated word must not be gated."""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = [m.group(2) for m in HEREDOC.finditer(line)]
        i += 1
        for d in delims:
            while i < len(lines) and lines[i].strip() != d:
                i += 1
            i += 1
    return "\n".join(out)


def segments(cmd):
    """Split a shell command into simple-command argv lists.

    Approximate by design: over-splitting only ever gates more, never less. Command
    substitutions are split out because `(` is a separator; backticks become one.
    """
    cmd = _strip_heredocs(cmd).replace("`", "\n")
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    segs, cur = [], []
    skip_next = False
    for tok in lx:
        if skip_next:
            skip_next = False
            continue
        if tok in SEPARATORS:
            if cur:
                segs.append(cur)
            cur = []
        elif REDIRECT.match(tok):
            if cur and cur[-1].isdigit():
                cur.pop()
            skip_next = True
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs


# ---------------------------------------------------------------- per-tool parsing

def _positionals(args, opt_arg):
    pos, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1:])
            break
        if a.startswith("-") and len(a) > 1:
            if a in opt_arg:
                i += 1
        else:
            pos.append(a)
        i += 1
    return pos


def _commit_flags(args):
    """Return (evasion, commit_all) from `git commit` arguments, skipping option
    values so `-m "-n"` is a message, not a flag."""
    evasion, all_ = None, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            break
        if a == "--no-verify":
            evasion = "--no-verify"
        elif a == "--all":
            all_ = True
        elif a.startswith("--"):
            if a in COMMIT_LONG_ARG:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:], 1):
                if ch == "n":
                    evasion = "-n (--no-verify)"
                elif ch == "a":
                    all_ = True
                elif ch in "mFCct":
                    if j == len(a) - 1:
                        i += 1          # the value is the next argument
                    break               # otherwise the rest of the cluster is the value
                elif ch in "Su":
                    break               # optional value, attached
        i += 1
    return evasion, all_


def _tag_creates(args):
    opts = {"-m", "-F", "-u", "--local-user", "--contains", "--no-contains",
            "--points-at", "--merged", "--no-merged", "--sort", "--format", "--cleanup",
            "--message", "--file"}
    for a in args:
        if a in ("-l", "--list", "-d", "--delete", "-v", "--verify"):
            return False
    if any(a in ("-a", "-s", "-f", "--annotate", "--sign", "--force") or
           a.startswith(("-m", "-F", "-u")) for a in args):
        return True
    return bool(_positionals(args, opts))


def _resolve_alias(name, cwd, git_args):
    out = _git(["config", "--get", "alias." + name], cwd, git_args)
    return out.strip() if out else None


def parse_git(args, cwd, env, depth):
    git_args, cfgs, raw_dirs, i = [], [], [], 0
    for var, opt in (("GIT_DIR", "--git-dir"), ("GIT_WORK_TREE", "--work-tree")):
        if var in env:
            raw_dirs.append((opt, env[var]))
    while i < len(args):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(args[i + 1])))
            i += 2
            continue
        if a == "-c" and i + 1 < len(args):
            cfgs.append(args[i + 1])
            i += 2
            continue
        if a.startswith(("--git-dir=", "--work-tree=")):
            opt, _, val = a.partition("=")
            raw_dirs.append((opt, val))
        elif a in ("--git-dir", "--work-tree") and i + 1 < len(args):
            raw_dirs.append((a, args[i + 1]))
            i += 1
        elif a in GIT_OPT_ARG and i + 1 < len(args):
            i += 1
        elif not a.startswith("-"):
            break
        i += 1
    # Relative --git-dir/--work-tree resolve against the directory after every -C.
    for opt, val in raw_dirs:
        git_args.append(f"{opt}={os.path.normpath(os.path.join(cwd, os.path.expanduser(val)))}")
    if i >= len(args):
        return []
    sub, rest = args[i], args[i + 1:]
    evasion = None
    for c in cfgs:
        if c.lower().startswith("core.hookspath="):
            evasion = f"-c {c} (disables git's own hooks)"

    if sub not in NOT_ALIASES and depth < 3:
        alias = _resolve_alias(sub, cwd, git_args)
        if alias:
            if alias.startswith("!"):
                return parse_command(alias[1:] + " " + shlex.join(rest), cwd, depth + 1)
            try:
                expanded = shlex.split(alias)
            except ValueError:
                expanded = []
            if expanded:
                carried = git_args + [x for c in cfgs for x in ("-c", c)]
                return parse_git(carried + expanded + rest, cwd, {}, depth + 1)

    if sub == "commit":
        ev, all_ = _commit_flags(rest)
        return [Action(GIT_LABELS[sub], cwd, git_args, evasion or ev, all_)]
    if sub == "push":
        if "-n" in rest or "--dry-run" in rest:
            return []
        ev = "--no-verify" if "--no-verify" in rest else None
        return [Action(GIT_LABELS[sub], cwd, git_args, evasion or ev)]
    if sub == "tag" and _tag_creates(rest):
        return [Action(GIT_LABELS[sub], cwd, git_args, evasion)]
    return []


def parse_segment(argv, cwd, depth):
    env = {}
    while argv and ENV_ASSIGN.match(argv[0]):
        k, _, v = argv[0].partition("=")
        env[k] = v
        argv = argv[1:]
    while argv and os.path.basename(argv[0].lstrip("\\")) in WRAPPERS:
        argv = argv[1:]
        while argv and (argv[0].startswith("-") or ENV_ASSIGN.match(argv[0])):
            if ENV_ASSIGN.match(argv[0]):
                k, _, v = argv[0].partition("=")
                env[k] = v
            argv = argv[1:]
    if not argv:
        return []
    prog = os.path.basename(argv[0].lstrip("\\"))
    args = argv[1:]
    if prog in SHELLS:
        for j, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
                if j + 1 < len(args) and depth < 3:
                    return parse_command(args[j + 1], cwd, depth + 1)
        return []
    if prog == "git":
        return parse_git(args, cwd, env, depth)
    if prog == "gh":
        pos = _positionals(args, OPT_ARG["gh"])
        if pos[:1] == ["pr"] and pos[1:2] and pos[1] in ("create", "merge", "ready"):
            return [Action(f"gh pr {pos[1]}", cwd)]
        if pos[:2] == ["release", "create"]:
            return [Action("gh release create", cwd)]
        return []
    if prog in ("npm", "pnpm", "yarn"):
        pos = _positionals(args, OPT_ARG[prog])
        if pos[:1] == ["publish"] or (prog == "yarn" and pos[:2] == ["npm", "publish"]):
            return [Action(f"{prog} publish", cwd)]
        return []
    if prog == "twine":
        return [Action("twine upload", cwd)] if _positionals(args, OPT_ARG["twine"])[:1] == \
            ["upload"] else []
    if re.fullmatch(r"python[0-9.]*", prog) and args[:2] == ["-m", "twine"]:
        return parse_segment(["twine"] + args[2:], cwd, depth)
    if prog == "uv":
        pos = _positionals(args, OPT_ARG["uv"])
        if pos[:1] == ["publish"]:
            return [Action("uv publish", cwd)]
        if pos[:3] == ["tool", "run", "twine"]:
            return parse_segment(["twine"] + pos[3:], cwd, depth)
        return []
    if prog == "uvx" and args:
        return parse_segment(args, cwd, depth)
    return []


def parse_command(cmd, cwd, depth=0):
    """Return the gated Actions a shell command would perform, in order."""
    actions = []
    for argv in segments(cmd):
        if argv[0] in ("cd", "pushd"):
            target = argv[1] if len(argv) > 1 and argv[1] != "-" else None
            if target is None and len(argv) == 1:
                target = os.path.expanduser("~")
            if target:
                cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
            continue
        actions.extend(parse_segment(argv, cwd, depth))
    return actions


def _fallback_actions(cmd, cwd):
    """Unparseable input (unbalanced quotes): gate on a plain word match rather than
    letting malformed syntax become a way around the gate."""
    if re.search(r"\bgit\b.*\b(commit|push|tag)\b|\bgh\s+(pr|release)\b|\bpublish\b|"
                 r"\btwine\b", cmd, re.S):
        return [Action("completion-shaped command", cwd)]
    return []


# ---------------------------------------------------------------- decisions

def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason},
            "systemMessage": "Verification gate: blocked."}


def ask(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "ask",
                                   "permissionDecisionReason": reason},
            "systemMessage": "Verification gate: a human must approve this bypass."}


def note(message):
    return {"systemMessage": message,
            "hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "additionalContext": message}}


NOT_CONFIGURED = (
    "Verification gate: not configured for this repository, so `{action}` was not "
    "checked. To enable it, create .claude/verification-policy.json, e.g.\n"
    '    {{"required_checks": {{"test": "<your test command>"}}}}\n'
    "then run `100x verified --name test` before shipping. To silence this notice "
    'without enabling the gate, use {{"mode": "off"}}.')


def judge(action, cmd):
    """Return (rank, output) for one action. rank: 0 pass, 1 note, 2 ask, 3 deny."""
    root = repo_root(action.cwd, action.git_args) if os.path.isdir(action.cwd) else None
    if not root:
        return 0, {}                    # not a repo: nothing to gate
    try:
        policy = load_policy(root, action.git_args)
    except GateError as e:
        return 3, deny(f"`{action.label}` blocked: {e}")
    if policy is None:
        return 1, note(NOT_CONFIGURED.format(action=action.label))
    if policy["mode"] == "off":
        return 0, {}
    notes = list(policy["notes"])

    skip = SKIP_TOKEN.search(cmd)
    if action.evasion and not skip:
        return 3, deny(
            f"`{action.label}` blocked: {action.evasion} skips git's own hooks "
            f"silently.\n\nIf the hooks are wrong, fix them. To ship without "
            f"verification deliberately, put [skip-verify] in the commit message: a "
            f"human is then asked to approve it, and the bypass is in the transcript.")
    if skip:
        why = f" It also uses {action.evasion}." if action.evasion else ""
        return 2, ask(
            f"`{action.label}` carries [skip-verify]: it asks to ship WITHOUT the "
            f"verification this repository requires ({POLICY}).{why} Approve only if "
            f"you intend that; deny to make the agent run `100x verified` first.")
    if os.environ.get("VERIFY_SKIP") == "1":
        return 1, note(f"Verification gate BYPASSED for `{action.label}`: VERIFY_SKIP=1 "
                       f"is set in the environment Claude Code was started from.")

    if not (pathlib.Path(root) / RECEIPT).exists():
        return 3, deny(f"`{action.label}` blocked: no verification receipt at {RECEIPT}."
                       f"\n\nRun the checks first:\n{rerun_hint(policy)}")
    try:
        key = load_key()
    except GateError as e:
        return 3, deny(f"`{action.label}` blocked: {e}.\n\nRun the checks first:\n"
                       f"{rerun_hint(policy)}")
    snap = snapshot(root, action.git_args)
    if not snap:
        return 0, {}
    try:
        result = evaluate(root, policy, snap["fingerprint"], key)
    except GateError as e:
        return 3, deny(f"`{action.label}` blocked: {e}")
    notes += result["notes"]
    if result["problems"]:
        body = "\n".join(f"  - {p}" for p in result["problems"])
        extra = ("\n\nNotes:\n" + "\n".join(f"  - {n}" for n in notes)) if notes else ""
        return 3, deny(f"`{action.label}` blocked:\n{body}\n\nRe-run verification "
                       f"against the current content, then retry:\n"
                       f"{rerun_hint(policy)}{extra}")

    if action.label == "git commit":
        left = [] if action.commit_all else snap["unstaged"]
        if left or snap["untracked"]:
            notes.append(
                "the commit will not contain everything that was verified "
                f"(unstaged: {', '.join(left[:5]) or 'none'}; untracked: "
                f"{', '.join(snap['untracked'][:5]) or 'none'}); the committed tree "
                "itself was never tested")
    passed = ", ".join(f"{n}(ok)" for n in sorted(result["fresh"]))
    msg = f"Verification gate PASSED for `{action.label}`: {passed}."
    if notes:
        msg += " " + " ".join(f"Note: {n}." for n in notes)
    return 0, {"systemMessage": msg}


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return {}
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return {}
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    base = payload.get("cwd")
    if not (isinstance(base, str) and os.path.isdir(base)):
        base = os.getcwd()
    try:
        actions = parse_command(cmd, base)
    except ValueError:
        actions = _fallback_actions(cmd, base)
    if not actions:
        return {}

    worst, outputs, seen = -1, [], set()
    for action in actions:
        key = (action.label, action.cwd, tuple(action.git_args), action.evasion)
        if key in seen:
            continue
        seen.add(key)
        rank, out = judge(action, cmd)
        if rank > worst:
            worst, outputs = rank, [out]
        elif rank == worst:
            outputs.append(out)
    if worst >= 2:
        return outputs[0]
    messages = [o["systemMessage"] for o in outputs if o.get("systemMessage")]
    if not messages:
        return {}
    joined = "\n".join(dict.fromkeys(messages))
    return note(joined) if worst == 1 else {"systemMessage": joined}


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception as e:
        print(json.dumps({"systemMessage": f"verification hook error (failing open): {e}"}))
    sys.exit(0)
