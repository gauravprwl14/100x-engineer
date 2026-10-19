#!/usr/bin/env python3
"""PreToolUse gate: block completion-shaped actions without fresh verification.

Instructions asking a model to "verify before claiming done" are prose the model can
talk itself past. This is a gate it cannot casually step around: the receipt is signed
and bound to a content fingerprint, so editing a file after verifying invalidates the
proof, and hand-writing a receipt does not produce one.

What it is, and is not: an integrity aid against a confused agent and against casual
evasion -- every natural way of phrasing a commit, push, PR or publish is meant to be
caught. It is not a boundary against an agent deliberately setting out to defeat it
(see docs/SAFETY.md, "Residual bypass classes"). Where the parser cannot tell what a
command does, it gates rather than guesses.

hooks.json routes broadly (any command mentioning git, gh, commit, push or a
publisher) because its `if` patterns see only text; this script parses the command and
decides, and returns fast when nothing is gated. Reads hook JSON on stdin, writes a
decision on stdout.

Decisions: deny (gate failed), ask (an explicit [skip-verify] -- a human approves it,
the agent cannot), or no decision at all when the gate passes. A passing gate does not
emit "allow": that would also skip the user's own `ask` permission rules for the
command, and a verification gate has no business granting permissions.

Fails OPEN on internal error -- a broken gate must not brick the user's shell.
"""
import hashlib, json, os, pathlib, re, shlex, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    from verify_fingerprint import EXCLUDE, _git, repo_root, snapshot, tree_fingerprint
    from receipts import (POLICY, RECEIPT, GateError, evaluate, legacy_note, load_key,
                          load_policy, receipt_path, rerun_hint)
except Exception:  # fail-open: a gate that cannot import its helpers must not brick the shell
    print(json.dumps({}))
    sys.exit(0)

SKIP_TOKEN = re.compile(r"\[skip-verify\]|\[no-verify\]")
SEPARATORS = {"&&", "||", ";", "|", "&", "\n", "|&", ";;", ";&", ";;&"}
PUNCT_PIECES = sorted([";;&", ";;", ";&", "&&", "||", "|&", "&>>", "&>", ">>", ">&", "<&",
                       "<<<", "<<-", "<<", ">|", "<>", ";", "&", "|", "(", ")", "<",
                       ">", "\n"], key=len, reverse=True)
REDIRECT = re.compile(r"^(?:[<>&]+|>\||<<-?)$")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
# A heredoc whose command is a shell: its body is a script, so it is parsed as commands.
SHELL_FED = re.compile(r"(?:^|[;&|(\s])(?:sh|bash|zsh|dash|ksh)\b[^;&|]*$")
METACHARS = " \t\n;&|()<>"
VAR_RX = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
SUB = "$__100x_sub{}__"
SUB_RX = re.compile(r"\$__100x_sub(\d+)__")
MAX_DEPTH = 4

# Reserved words at command position. They separate commands rather than being
# programs, so `{ git push; }` and `if x; then git push; fi` are parsed as `git push`.
KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while",
            "until", "esac"}
LIST_HEADS = {"for", "select", "case"}       # `for x in a b`: the words are data
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# Programs that run another command, with the options of each that consume a value,
# and how many positionals precede the command (timeout's duration).
WRAPPERS = {
    "env": ({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}, 0),
    "command": (set(), 0), "exec": ({"-a"}, 0), "nohup": (set(), 0),
    "time": ({"-f", "--format", "-o", "--output"}, 0), "builtin": (set(), 0),
    "nice": ({"-n", "--adjustment"}, 0),
    "sudo": ({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T", "--user",
              "--group", "--host", "--prompt", "--close-from", "--chdir", "--role",
              "--type", "--other-user", "--command-timeout"}, 0),
    "doas": ({"-u", "-C"}, 0),
    "timeout": ({"-s", "--signal", "-k", "--kill-after"}, 1),
    "stdbuf": ({"-i", "-o", "-e", "--input", "--output", "--error"}, 0),
    "xargs": ({"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "--arg-file",
               "--delimiter", "--max-args", "--max-procs", "--max-chars", "--max-lines",
               "--eof", "--process-slot-var"}, 0),
    "watch": ({"-n", "--interval", "-q", "--equexit"}, 0),
    "eval": (set(), 0), "setsid": (set(), 0), "chronic": (set(), 0),
    "unbuffer": (set(), 0), "caffeinate": ({"-t", "-w"}, 0),
    "ionice": ({"-c", "-n", "-p", "--class", "--classdata"}, 0),
}
CHDIR_OPTS = {"-C", "--chdir", "-D"}         # env -C, sudo -D/--chdir
# An unrecognised program may still run its arguments (`find -exec`, `docker run`),
# so its argv is scanned for these; programs that only display text are not scanned.
SCAN_PROGS = {"git", "gh", "npm", "pnpm", "yarn", "twine", "uv", "uvx"} | SHELLS
NO_EXEC = {"echo", "printf", "grep", "egrep", "fgrep", "rg", "ag", "ack", "cat", "less",
           "more", "head", "tail", "wc", "ls", "man", "which", "type", "whereis",
           "whatis", "apropos", "info", "help", "tldr", "test", "[", "true", "false",
           ":", "sed", "awk", "jq", "yq", "diff", "cmp", "sort", "uniq", "cut", "tr",
           "tee", "file", "stat", "basename", "dirname", "realpath", "readlink",
           "touch", "mkdir", "cp", "mv", "ln", "chmod"}
# Words that, after a program name the parser cannot resolve, mean "gate this".
GATE_WORDS = {"commit", "push", "tag", "merge", "publish", "upload", "send-pack",
              "commit-tree", "update-ref", "pr", "release"}
# Segments that cannot change file content, so they may precede a gated action in the
# same command line without opening a window between the check and the action.
READ_ONLY = {"cd", "pushd", "popd", "pwd", "ls", "cat", "echo", "printf", "true",
             "false", ":", "test", "[", "head", "tail", "wc", "grep", "which", "type",
             "date"}
READ_ONLY_GIT = {"status", "diff", "log", "show", "add", "rev-parse", "ls-files"}
# Gated actions that move no content, so a later action in the same line may follow
# them: each is judged on its own.
SAFE_EARLIER = {"commit", "tag", "push", "pr"}
NOT_ALIASES = {  # git builtins: git never lets an alias shadow one
    "add", "am", "apply", "bisect", "blame", "branch", "cat-file", "cherry-pick",
    "clone", "commit", "commit-tree", "config", "describe", "diff", "fetch", "grep",
    "init", "log", "ls-files", "ls-tree", "merge", "mv", "pull", "push", "rebase",
    "reflog", "remote", "restore", "rev-parse", "revert", "send-pack", "show",
    "status", "switch", "tag", "update-ref", "worktree"}
GIT_OPT_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env",
               "--super-prefix", "--list-cmds", "--exec-path"}
COMMIT_LONG_ARG = {"--message", "--file", "--reuse-message", "--reedit-message",
                   "--fixup", "--squash", "--author", "--date", "--cleanup",
                   "--template", "--trailer", "--pathspec-from-file", "--untracked-files"}
PUSH_OPT_ARG = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
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
    "poetry": {"-C", "--directory", "-P", "--project", "-r", "--repository", "-u",
               "--username", "-p", "--password", "--cert", "--client-cert"},
    "hatch": {"-e", "--env", "-p", "--project", "--data-dir", "--cache-dir", "--config",
              "-r", "--repo", "-u", "--user", "-a", "--auth"},
    "cargo": {"--manifest-path", "-Z", "--config", "--token", "--registry", "--index",
              "-p", "--package", "-j", "--jobs", "--target", "--target-dir", "-F",
              "--features", "--color"},
    "gem": {"--host", "-k", "--key", "--otp"},
}
# Publishers beyond npm/pnpm/yarn/twine/uv: (program, the subcommand that ships).
PUBLISHERS = {"poetry": "publish", "hatch": "publish", "cargo": "publish", "gem": "push"}
# Package-manager subcommands that run an arbitrary program: their argv is scanned.
RUNNER_SUBCOMMANDS = {"exec", "dlx", "x", "run"}
# Shell options that consume the next argument (`bash -o pipefail -c '…'`).
SHELL_OPT_ARG = {"--rcfile", "--init-file"}
# macOS filesystems are case-insensitive by default: `GIT commit` runs git.
FOLD_CASE = sys.platform == "darwin"


class Action:
    """One gated action. kind: commit | merge | push | tag | plumbing | publish | pr |
    generic. srcs (push only): refs it sends; [] means the default (HEAD), None means
    the parser could not tell."""

    def __init__(self, label, kind, state, git_args=(), evasion=None, commit_all=False,
                 pathspec=False, srcs=(), push_mode=None):
        self.label, self.kind = label, kind
        self.cwd, self.base = state.cwd, state.base
        self.git_args = list(git_args)
        self.evasion, self.commit_all, self.pathspec = evasion, commit_all, pathspec
        self.srcs = None if srcs is None else list(srcs)
        self.push_mode = push_mode
        self.after_write = state.dirty_by
        self.prior_commits = [a for a in state.actions if a.kind == "commit"]
        self.added = state.added

    def key(self):
        return (self.label, self.kind, self.cwd, tuple(self.git_args), self.evasion,
                self.after_write, None if self.srcs is None else tuple(self.srcs),
                self.push_mode, self.commit_all)


class State:
    """What one shell would know while running the command line, in order."""

    def __init__(self, cwd, raw):
        self.cwd = self.base = cwd
        self.raw = raw
        self.vars, self.exported = {}, {}
        self.dirty_by = None          # first earlier segment that may change files
        self.added = False            # an earlier `git add` in this command line
        self.aliases = {}             # `git config alias.X …` earlier in this line
        self.actions, self.stack, self.dirstack = [], [], []

    def emit(self, action):
        self.actions.append(action)

    def push_scope(self):
        self.stack.append((self.cwd, dict(self.vars), dict(self.exported)))

    def pop_scope(self):
        if self.stack:
            self.cwd, self.vars, self.exported = self.stack.pop()


class Seg:
    def __init__(self, argv, redirected):
        self.argv, self.redirected = argv, redirected


# ---------------------------------------------------------------- tokenising

def _match_paren(cmd, k):
    """Index of the `)` closing the `(` at k, honouring quotes; len(cmd) if none."""
    depth, q, i = 0, None, k
    while i < len(cmd):
        c = cmd[i]
        if q == "'":
            if c == "'":
                q = None
        elif c == "\\":
            i += 1
        elif c == '"':
            q = None if q == '"' else '"'
        elif c == "'" and q is None:
            q = "'"
        elif q is None and c == "(":
            depth += 1
        elif q is None and c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(cmd)


def _extract_substitutions(cmd, quotes=True):
    """Replace $(...), `...`, <(...) and >(...) with placeholders.

    Returns (text, inners). A substitution is a command the shell runs before the one
    containing it, so its text is parsed separately; the placeholder keeps a `$`, which
    marks a program name produced by substitution as unresolvable.
    """
    out, inners, i, n, q = [], [], 0, len(cmd), None
    while i < n:
        c = cmd[i]
        if quotes and q == "'":
            out.append(c)
            q = None if c == "'" else q
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(cmd[i:i + 2])
            i += 2
            continue
        if quotes and c == "'" and q is None:
            q = "'"
        elif quotes and c == '"':
            q = None if q == '"' else '"'
        elif cmd.startswith("(", i + 1) and (c == "$" or (c in "<>" and q is None)):
            j = _match_paren(cmd, i + 1)
            inners.append(cmd[i + 2:j])
            out.append(SUB.format(len(inners) - 1))
            i = j + 1
            continue
        elif c == "`":
            j = i + 1
            while j < n and cmd[j] != "`":
                j += 2 if cmd[j] == "\\" else 1
            inners.append(cmd[i + 1:j])
            out.append(SUB.format(len(inners) - 1))
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out), inners


def _heredoc_word(cmd, k):
    """(delimiter, quoted, end) for the heredoc word starting at k: the whole shell
    word, so `<<EOF-X` ends at `EOF-X`, not `EOF`. Any quoting disables expansion of
    the body. delimiter is "" when there is no word."""
    while k < len(cmd) and cmd[k] in " \t":
        k += 1
    word, quoted, q = [], False, None
    while k < len(cmd):
        c = cmd[k]
        if q:
            if c == q:
                q = None
            else:
                word.append(c)
        elif c in "'\"":
            q, quoted = c, True
        elif c == "\\" and k + 1 < len(cmd):
            quoted = True
            word.append(cmd[k + 1])
            k += 1
        elif c in METACHARS:
            break
        else:
            word.append(c)
        k += 1
    return "".join(word), quoted, k


def _body_lines(cmd, i, delim, strip_tabs):
    """(body, index after the terminator line), or None when no line terminates it."""
    body = []
    while i <= len(cmd):
        j = cmd.find("\n", i)
        line = cmd[i:] if j < 0 else cmd[i:j]
        if (line.lstrip("\t") if strip_tabs else line) == delim:
            return body, (len(cmd) if j < 0 else j + 1)
        if j < 0:
            return None
        body.append(line)
        i = j + 1
    return None


def prelex(cmd):
    """Normalise shell text before it is split into words, the way the shell would:

    - a backslash-newline outside single quotes joins two lines into one command;
    - `#` starts a comment only at the start of a word, outside quotes, so `issue#12`,
      `${#PATH}`, `$#` and `page#top` are words, not the start of a comment;
    - heredoc bodies are dropped: their lines are data. `<<` counts only unquoted and
      outside `(( ))` arithmetic, and the delimiter is the whole word. Two exceptions
      run code: a body fed to a shell is kept as commands, and substitutions in an
      unquoted body are kept as subshells. A heredoc with no terminator line drops
      nothing, so a misread `<<` can only make the parser gate more.

    Public: tools that need to parse a command line the way the gate does (plan_dag,
    agent_report) go through parse_command, which calls this first.
    """
    out, pending, i, n, q, arith = [], [], 0, len(cmd), None, 0

    def prev():
        return out[-1][-1] if out and out[-1] else ""

    while i < n:
        c = cmd[i]
        if q == "'":
            out.append(c)
            q = None if c == "'" else q
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            if cmd[i + 1] != "\n":
                out.append(cmd[i:i + 2])
            i += 2
            continue
        if q == '"':
            out.append(c)
            q = None if c == '"' else q
            i += 1
            continue
        if c in "'\"":
            q = c
        elif c == "#" and prev() in ("",) + tuple(METACHARS):
            j = cmd.find("\n", i)
            i = n if j < 0 else j
            continue
        elif cmd.startswith("((", i):
            arith += 1
            out.append("((")
            i += 2
            continue
        elif arith and cmd.startswith("))", i):
            arith -= 1
            out.append("))")
            i += 2
            continue
        elif not arith and cmd.startswith("<<", i) and not cmd.startswith("<<<", i) \
                and prev() != "<":
            k = i + 2
            strip = cmd.startswith("-", k)
            delim, quoted, end = _heredoc_word(cmd, k + strip)
            if delim:
                line = "".join(out).rsplit("\n", 1)[-1]
                pending.append((delim, quoted, strip, bool(SHELL_FED.search(line))))
                out.append(cmd[i:end])
                i = end
                continue
        elif c == "\n" and pending:
            out.append(c)
            i += 1
            for delim, quoted, strip, shell_fed in pending:
                found = _body_lines(cmd, i, delim, strip)
                if found is None:
                    break               # unterminated: lex the rest as commands
                body, i = found
                if shell_fed:
                    out.append(prelex("\n".join(body)) + "\n")
                elif not quoted:
                    _, inners = _extract_substitutions("\n".join(body), quotes=False)
                    out.extend("( " + inner.replace("\n", " ; ") + " )\n"
                               for inner in inners)
            pending = []
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _split_punct(tok):
    pieces, i = [], 0
    while i < len(tok):
        for p in PUNCT_PIECES:
            if tok.startswith(p, i):
                pieces.append(p)
                i += len(p)
                break
        else:
            return [tok]
    return pieces


def segments(text):
    """Split shell text into Seg items and "(" / ")" subshell markers.

    Approximate by design: over-splitting only ever gates more, never less.
    """
    lx = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>\n")
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    # prelex already removed real comments. shlex's default would also end a word at a
    # `#` inside it (`issue#12 && git commit` lost the commit), so it must see none.
    lx.commenters = ""
    items, cur, state = [], [], {"redir": False, "target": None}

    def flush():
        if cur:
            items.append(Seg(list(cur), state["redir"]))
        del cur[:]
        state["redir"] = False

    raw = list(lx)
    toks = []
    for tok in raw:
        toks.extend(_split_punct(tok) if tok and set(tok) <= set(";&|()<>\n") else [tok])
    for tok in toks:
        if state["target"] is not None:
            if state["target"] == "write" and tok not in ("/dev/null", "-") \
                    and not tok.isdigit():
                state["redir"] = True
            state["target"] = None
            continue
        if tok in ("(", ")"):
            flush()
            items.append(tok)
        elif tok in SEPARATORS:
            flush()
        elif REDIRECT.match(tok):
            if cur and cur[-1].isdigit():
                cur.pop()
            state["target"] = "write" if ">" in tok else "read"
        else:
            cur.append(tok)
    flush()
    return items


def expand(tok, state):
    """Expand $NAME / ${NAME} from what the command line itself assigned, then from
    the hook's environment; an unknown name stays literal (and so keeps its `$`)."""
    if "$" not in tok:
        return tok

    def sub(m):
        name = m.group(1) or m.group(2)
        if name.startswith("__100x_sub"):
            return m.group(0)
        if name == "PWD":
            return state.cwd
        if name in state.vars:
            return state.vars[name]
        return os.environ.get(name, m.group(0))
    return VAR_RX.sub(sub, tok)


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


def _is_no_verify(a):
    # git accepts any unambiguous prefix of a long option: `--no-veri` is --no-verify.
    return len(a) >= 9 and "--no-verify".startswith(a)


def _commit_flags(args):
    """Return (evasion, commit_all, pathspec) from `git commit` arguments, skipping
    option values so `-m "-n"` is a message, not a flag."""
    evasion, all_, paths = None, False, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            paths = paths or i + 1 < len(args)
            break
        if _is_no_verify(a):
            evasion = "--no-verify"
        elif a in ("--all", "--include", "--only"):
            all_ = all_ or a == "--all"
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
        else:
            paths = True
        i += 1
    return evasion, all_, paths


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


def _push_refs(args):
    """(srcs, mode) for `git push` arguments: the local refs whose commits it sends.
    [] means the default, the current branch. mode: all | mirror | tags | None."""
    pos, mode, delete, i = [], None, False, 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1:])
            break
        if a in PUSH_OPT_ARG:
            i += 2
            continue
        if a in ("--all", "--branches"):
            mode = "all"
        elif a == "--mirror":
            mode = "mirror"
        elif a == "--tags":
            mode = mode or "tags"
        elif a in ("-d", "--delete"):
            delete = True
        elif not a.startswith("-"):
            pos.append(a)
        i += 1
    if delete:
        return [], None                 # deleting a remote ref sends no content
    srcs, specs, j = [], pos[1:], 0
    while j < len(specs):
        r = specs[j].lstrip("+")
        if r == "tag" and j + 1 < len(specs):
            srcs.append("refs/tags/" + specs[j + 1])
            j += 2
            continue
        if r == ":":                    # matching: every branch with a remote twin
            mode = "all"
        elif not r.startswith(":"):     # `:dst` deletes dst
            src = r.split(":", 1)[0]
            if src:
                srcs.append(src)
        j += 1
    return srcs, mode


def _config_overlay(env, cfgs):
    """Config git would see from the environment and -c, lowercased keys. Later
    entries win, as in git: GIT_CONFIG_PARAMETERS, then GIT_CONFIG_COUNT pairs, then
    each -c on the command line."""
    overlay = {}
    params = env.get("GIT_CONFIG_PARAMETERS", "")
    try:
        for item in shlex.split(params):
            k, _, v = item.partition("=")
            overlay[k.lower()] = v
    except ValueError:  # fail-open: unbalanced quotes make git itself reject GIT_CONFIG_PARAMETERS
        pass
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        count = 0
    for n in range(min(count, 100)):
        k = env.get(f"GIT_CONFIG_KEY_{n}")
        if k:
            overlay[k.lower()] = env.get(f"GIT_CONFIG_VALUE_{n}", "")
    for c in cfgs:
        k, eq, v = c.partition("=")
        overlay[k.lower()] = v if eq else "true"
    return overlay


def _resolve_alias(name, cwd, git_args, overlay, env):
    key = "alias." + name.lower()
    if key in overlay:
        return overlay[key].strip() or None
    for var in ("GIT_CONFIG", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
        if env.get(var) and "$" not in env[var]:
            path = os.path.join(cwd, os.path.expanduser(env[var]))
            out = _git(["config", "--file", path, "--get", key], cwd if os.path.isdir(cwd)
                       else None)
            if out and out.strip():
                return out.strip()
    if not os.path.isdir(cwd):
        return None
    out = _git(["config", "--get", key], cwd, git_args)
    return out.strip() if out else None


def parse_git(args, state, env, depth):
    git_args, cfgs, raw_dirs, i, cwd = [], [], [], 0, state.cwd
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
        if a.startswith("--config-env="):
            k, _, var = a[len("--config-env="):].partition("=")
            cfgs.append(f"{k}={env.get(var, os.environ.get(var, ''))}")
        elif a.startswith(("--git-dir=", "--work-tree=")):
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
    # Relative --git-dir/--work-tree resolve against the directory after every -C. A
    # value the parser cannot resolve is dropped: the payload cwd's repo is judged
    # instead (see judge), rather than a nonexistent path that is "not a repo".
    for opt, val in raw_dirs:
        path = os.path.normpath(os.path.join(cwd, os.path.expanduser(val)))
        if "$" not in val and os.path.exists(path):
            git_args.append(f"{opt}={path}")
    if i >= len(args):
        return
    sub, rest = args[i], args[i + 1:]
    if "$" in sub:
        # `git ${C:-commit}`, `git $'commit'`, `git "$(…)"`: what runs is unknown.
        state.emit(Action(f"git {sub} (subcommand not resolvable)", "push", state,
                          git_args, srcs=None))
        return
    overlay = _config_overlay(env, cfgs)
    evasion = None
    if overlay.get("core.hookspath") is not None:
        evasion = "core.hooksPath set on the command line or in GIT_CONFIG_* " \
                  "(disables git's own hooks)"

    if sub not in NOT_ALIASES and depth < MAX_DEPTH:
        alias = state.aliases.get(sub.lower()) or \
            _resolve_alias(sub, cwd, git_args, overlay, env)
        if alias:
            saved = state.cwd
            state.cwd = cwd
            try:
                if alias.startswith("!"):
                    parse_command(alias[1:] + " " + shlex.join(rest), state, depth + 1)
                    return
                try:
                    expanded = shlex.split(alias)
                except ValueError:
                    expanded = []
                if expanded:
                    carried = git_args + [x for c in cfgs for x in ("-c", c)]
                    parse_git(carried + expanded + rest, state,
                              {k: v for k, v in env.items()
                               if k not in ("GIT_DIR", "GIT_WORK_TREE")}, depth + 1)
                    return
            finally:
                state.cwd = saved

    saved = state.cwd
    state.cwd = cwd
    try:
        _git_subcommand(sub, rest, state, git_args, evasion, overlay)
    finally:
        state.cwd = saved


def _push_config(rest, cwd, git_args, overlay):
    """What config makes a push send beyond its refspecs: "mirror", "all" (matching),
    "unknown" (remote.<name>.push refspecs), or None. -c on the command line wins."""
    pos = _positionals(rest, PUSH_OPT_ARG)
    remote = pos[0] if pos else None

    def get(key):
        if key in overlay:
            return overlay[key]
        if not os.path.isdir(cwd):
            return None
        out = _git(["config", "--get", key], cwd, git_args)
        return out.strip() if out is not None else None

    names = [remote] if remote else None
    if names is None:
        out = _git(["config", "--name-only", "--get-regexp", r"^remote\..*\.url$"], cwd,
                   git_args) if os.path.isdir(cwd) else ""
        names = [k[len("remote."):-len(".url")] for k in (out or "").split()]
        names += [k.split(".")[1] for k in overlay if k.startswith("remote.")
                  and k.count(".") >= 2]
    for name in dict.fromkeys(names):
        if (get(f"remote.{name}.mirror") or "").lower() in ("true", "yes", "on", "1"):
            return "mirror"
        if get(f"remote.{name}.push") and len(pos) < 2:
            return "unknown"
    if len(pos) < 2 and (get("push.default") or "").lower() == "matching":
        return "all"
    return None


def _git_subcommand(sub, rest, state, git_args, evasion, overlay=None):
    label = "git " + sub
    overlay = overlay or {}
    if sub == "add":
        state.added = True
    elif sub == "config":
        pos = _positionals(rest, {"-f", "--file", "--blob", "--type", "--default",
                                  "--comment", "--value"})
        if pos[:1] == ["set"]:
            pos = pos[1:]
        if len(pos) >= 2 and pos[0].lower().startswith("alias."):
            state.aliases[pos[0][len("alias."):].lower()] = pos[1]
    elif sub == "commit":
        ev, all_, paths = _commit_flags(rest)
        state.emit(Action(label, "commit", state, git_args, evasion or ev, all_, paths))
    elif sub == "push":
        if "-n" in rest or "--dry-run" in rest:
            return
        ev = "--no-verify" if any(_is_no_verify(a) for a in rest) else None
        srcs, mode = _push_refs(rest)
        widened = _push_config(rest, state.cwd, git_args, overlay)
        if widened == "unknown":
            srcs = None
        elif widened and mode != "mirror":
            mode = widened
        state.emit(Action(label, "push", state, git_args, evasion or ev, srcs=srcs,
                          push_mode=mode))
    elif sub == "send-pack":
        pos = _positionals(rest, {"--receive-pack", "--exec"})
        mode = "all" if "--all" in rest or "--mirror" in rest else None
        state.emit(Action(label, "push", state, git_args, evasion,
                          srcs=[r.lstrip("+").split(":", 1)[0] for r in pos[1:]
                                if not r.startswith(":")], push_mode=mode))
    elif sub == "tag" and _tag_creates(rest):
        state.emit(Action(label, "tag", state, git_args, evasion))
    elif sub == "merge" and not any(a in ("--abort", "--quit") for a in rest):
        ev = "--no-verify" if any(_is_no_verify(a) for a in rest) else None
        state.emit(Action(label, "merge", state, git_args, evasion or ev))
    elif sub in ("commit-tree", "update-ref") and "-d" not in rest:
        state.emit(Action(label, "plumbing", state, git_args, evasion))


def _parse_gh(args, state):
    pos = _positionals(args, OPT_ARG["gh"] | {"-H", "--head", "-B", "--base", "-t",
                                              "--title", "-b", "--body", "-F",
                                              "--body-file", "-f", "--field", "-X",
                                              "--method", "--jq", "-q"})
    if pos[:2] == ["pr", "create"]:
        head = None
        for k, a in enumerate(args):
            if a in ("-H", "--head") and k + 1 < len(args):
                head = args[k + 1]
            elif a.startswith("--head="):
                head = a.split("=", 1)[1]
        srcs = [head.split(":", 1)[-1]] if head else []
        state.emit(Action("gh pr create", "push", state, srcs=srcs))
    elif pos[:1] == ["pr"] and pos[1:2] and pos[1] in ("merge", "ready"):
        state.emit(Action(f"gh pr {pos[1]}", "pr", state))
    elif pos[:2] == ["release", "create"]:
        state.emit(Action("gh release create", "publish", state))
    elif pos[:1] == ["api"] and (any(re.search(r"/merges?(?:$|[/?])", p) for p in pos[1:])
                                 or any("mergePullRequest" in a for a in args)):
        state.emit(Action("gh api (merge)", "pr", state))


def _word_match(argv, state):
    """A program name the parser cannot resolve (`$G commit`, `$(echo git) push`):
    gate on the words that follow rather than let indirection pass silently."""
    words = argv[1:]
    hit = [w for w in words if w in GATE_WORDS]
    if not hit:
        return
    label = f"{argv[0]} {hit[0]} (program name not resolvable)"
    if hit[0] in ("push", "send-pack"):
        srcs, mode = _push_refs(words[words.index(hit[0]) + 1:])
        state.emit(Action(label, "push", state, srcs=srcs, push_mode=mode))
    else:
        state.emit(Action(label, "generic", state))


def _unwrap(prog, args, state, depth, env):
    opts, npos = WRAPPERS[prog]
    i, chdir, split, exec_mode = 0, None, None, False
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if prog == "env" and ENV_ASSIGN.match(a):
            k, _, v = a.partition("=")
            env[k.rstrip("+")] = v
            i += 1
            continue
        if not a.startswith("-") or a == "-" or prog == "eval":
            break
        name, eq, val = a.partition("=")
        if a in opts:
            opt, val, step = a, (args[i + 1] if i + 1 < len(args) else ""), 2
        elif eq and name in opts:
            opt, step = name, 1
        elif not a.startswith("--") and len(a) > 2 and a[:2] in opts:
            opt, val, step = a[:2], a[2:], 1
        else:
            if prog == "command" and a in ("-v", "-V"):
                return                  # `command -v git` only asks where git is
            exec_mode = exec_mode or (prog == "watch" and a in ("-x", "--exec"))
            i += 1
            continue
        if prog == "env" and opt in ("-u", "--unset"):
            env.pop(val, None)
        elif opt in CHDIR_OPTS and (prog == "env" or (prog == "sudo" and opt != "-C")):
            chdir = val
        elif prog == "env" and opt in ("-S", "--split-string"):
            split = val
        i += step
    rest = args[i + npos:]
    if split is not None:
        rest = shlex.split(split) + rest
    saved = state.cwd
    if chdir:
        state.cwd = os.path.normpath(os.path.join(state.cwd, os.path.expanduser(chdir)))
    try:
        if prog == "eval" or (prog == "watch" and not exec_mode):
            # eval (and watch without -x) joins its arguments and re-parses them.
            parse_command(" ".join(rest), state, depth + 1)
        else:
            parse_argv(rest, state, depth, env)
    finally:
        state.cwd = saved


def parse_argv(argv, state, depth, env=None):
    """Emit the gated Actions one simple command performs."""
    env = dict(state.exported) if env is None else env
    while argv and ENV_ASSIGN.match(argv[0]):
        k, _, v = argv[0].partition("=")
        env[k.rstrip("+")] = v
        argv = argv[1:]
    if not argv:
        return
    prog = prog_name(argv[0])
    args = argv[1:]
    if "$" in argv[0]:
        _word_match(argv, state)
    elif prog in WRAPPERS:
        _unwrap(prog, args, state, depth, env)
    elif prog in SHELLS:
        kind, script = _shell_invocation(args)
        if kind == "command":
            state.push_scope()          # a child shell: its `cd` does not leak out
            try:
                parse_command(script, state, depth + 1)
            finally:
                state.pop_scope()
        elif kind == "file" and not SUB_RX.search(script):
            return                      # a script file: not parsed (docs/SAFETY.md)
        elif kind != "none":
            # stdin (`echo ... | bash`) or a process substitution (`bash <(…)`): the
            # parser cannot see the script, so the whole line is word-matched.
            _emit_fallback(state)
    elif prog in ("source", "."):
        if any(SUB_RX.search(a) for a in args):
            _emit_fallback(state)       # `source <(…)` runs generated text
    elif prog == "git":
        parse_git(args, state, env, depth)
    elif prog == "gh":
        _parse_gh(args, state)
    elif prog in ("npm", "pnpm", "yarn"):
        pos = _positionals(args, OPT_ARG[prog])
        if pos[:1] == ["publish"] or (prog == "yarn" and pos[:2] == ["npm", "publish"]):
            state.emit(Action(f"{prog} publish", "publish", state))
        elif pos[:1] and pos[0] in RUNNER_SUBCOMMANDS:
            _scan_argv(args, state, depth, env)
    elif prog in PUBLISHERS:
        pos = [a for a in _positionals(args, OPT_ARG[prog]) if not a.startswith("+")]
        if pos[:1] == [PUBLISHERS[prog]]:
            state.emit(Action(f"{prog} {PUBLISHERS[prog]}", "publish", state))
    elif prog == "twine":
        if _positionals(args, OPT_ARG["twine"])[:1] == ["upload"]:
            state.emit(Action("twine upload", "publish", state))
    elif re.fullmatch(r"python[0-9.]*", prog) and args[:2] == ["-m", "twine"]:
        parse_argv(["twine"] + args[2:], state, depth, env)
    elif prog == "uv":
        pos = _positionals(args, OPT_ARG["uv"])
        if pos[:1] == ["publish"]:
            state.emit(Action("uv publish", "publish", state))
        elif pos[:3] == ["tool", "run", "twine"]:
            parse_argv(["twine"] + pos[3:], state, depth, env)
        elif pos[:1] and pos[0] in RUNNER_SUBCOMMANDS:
            _scan_argv(args, state, depth, env)
    elif prog == "uvx" and args:
        parse_argv(args, state, depth, env)
    elif prog not in NO_EXEC:
        if args[:1] == ["publish"]:     # `<tool> publish`: assume it ships
            state.emit(Action(f"{prog} publish", "publish", state))
        _scan_argv(args, state, depth, env)


def _scan_argv(args, state, depth, env):
    """An unrecognised program may run its arguments (`find -exec`, `docker run`,
    `pnpm exec`): parse from the first word that names a gated program."""
    for j, a in enumerate(args):
        if prog_name(a) in SCAN_PROGS:
            parse_argv(args[j:], state, depth, env)
            return


def prog_name(word):
    name = os.path.basename(word.lstrip("\\"))
    return name.lower() if FOLD_CASE else name


def _shell_invocation(args):
    """(kind, script) for `sh [options] …`: kind is command (`-c SCRIPT`), file, stdin
    or none (`-c` with nothing after it). -o/+o/-O/+O take a value, also at the end of
    a cluster (`-euo pipefail`), so the value is never read as a script file."""
    has_c, i = False, 0
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if a in SHELL_OPT_ARG:
            i += 2
            continue
        if a.startswith("--") or a in ("-", "+"):
            i += 1
            continue
        if a[:1] in "-+" and len(a) > 1:
            has_c = has_c or (a[0] == "-" and "c" in a[1:])
            i += 1 + sum(1 for ch in a[1:] if ch in "oO")
            continue
        break
    rest = args[i:]
    if has_c:
        return ("command", rest[0]) if rest else ("none", None)
    return ("file", rest[0]) if rest else ("stdin", None)


def _emit_fallback(state):
    for action in _fallback_actions(state.raw, state):
        state.emit(action)


def _is_read_only(argv, redirected):
    if redirected:
        return False
    prog = prog_name(argv[0])
    if prog in READ_ONLY:
        return True
    if prog == "git":
        i = 1
        while i < len(argv) and argv[i].startswith("-"):
            if argv[i] in ("-c", "--config-env") or argv[i].startswith("--config-env="):
                return False            # config can name a program git runs (a filter)
            i += 2 if argv[i] in GIT_OPT_ARG else 1
        # diff/log/show write a file with --output=<file>
        return i < len(argv) and argv[i] in READ_ONLY_GIT and \
            not any(a.startswith("--output") for a in argv[i + 1:])
    return False


def _segment(seg, state, depth):
    argv = [expand(t, state) for t in seg.argv]
    while argv and argv[0] in KEYWORDS:
        argv = argv[1:]
    if not argv or argv[0] in LIST_HEADS:
        return
    head = argv[0]
    if all(ENV_ASSIGN.match(a) for a in argv):
        for a in argv:
            k, _, v = a.partition("=")
            k = k.rstrip("+")
            state.vars[k] = v
            if k in state.exported:
                state.exported[k] = v
        return
    if head in ("export", "declare", "typeset", "local", "readonly"):
        exporting = head == "export" or any(a.startswith("-") and "x" in a
                                            for a in argv[1:])
        for a in argv[1:]:
            if a.startswith("-"):
                continue
            k, eq, v = a.partition("=")
            if eq:
                state.vars[k] = v
            if exporting and k in state.vars:
                state.exported[k] = state.vars[k]
        return
    if head == "unset":
        for a in argv[1:]:
            state.vars.pop(a, None)
            state.exported.pop(a, None)
        return
    if head in ("cd", "pushd", "popd"):
        if head == "popd":
            if state.dirstack:
                state.cwd = state.dirstack.pop()
            return
        target = next((a for a in argv[1:] if not a.startswith("-")), None)
        if target is None and len(argv) == 1:
            target = os.path.expanduser("~")
        if head == "pushd":
            state.dirstack.append(state.cwd)
        if target == "-":
            target = state.vars.get("OLDPWD")
        if target:
            state.vars["OLDPWD"] = state.cwd
            state.cwd = os.path.normpath(os.path.join(state.cwd,
                                                      os.path.expanduser(target)))
        return
    before = len(state.actions)
    parse_argv(argv, state, depth)
    new = state.actions[before:]
    if state.dirty_by is None and not _is_read_only(argv, seg.redirected) and \
            not (new and all(a.kind in SAFE_EARLIER for a in new)):
        state.dirty_by = " ".join(seg.argv)[:80]


def parse_command(cmd, state, depth=0):
    """Emit, into state.actions, the gated Actions a shell command would perform."""
    if depth > MAX_DEPTH:
        raise ValueError("nested deeper than the parser follows")
    text, inners = _extract_substitutions(prelex(cmd))
    done = set()
    for item in segments(text):
        if item == "(":
            state.push_scope()
            continue
        if item == ")":
            state.pop_scope()
            continue
        for tok in item.argv:
            for m in SUB_RX.finditer(tok):
                idx = int(m.group(1))
                if idx < len(inners) and idx not in done:
                    done.add(idx)
                    state.push_scope()  # a substitution runs in a subshell
                    try:
                        parse_command(inners[idx], state, depth + 1)
                    finally:
                        state.pop_scope()
        _segment(item, state, depth)
    return state.actions


def _fallback_actions(cmd, state):
    """Input the parser cannot follow: gate on a plain word match rather than let
    malformed syntax or a bare shell become a way around the gate."""
    m = re.search(r"\bgit\b.*\b(commit|push|tag|merge|send-pack|commit-tree|update-ref)"
                  r"\b|\bgh\b.*\b(pr|release|api)\b|\b(publish)\b|\b(twine)\b", cmd, re.S)
    if not m:
        return []
    word = next(g for g in m.groups() if g)
    if word in ("push", "send-pack"):
        return [Action("completion-shaped command", "push", state, srcs=None)]
    return [Action("completion-shaped command", "generic", state)]


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


def _where(action):
    """(cwd, git_args) to judge. A cwd the parser could not resolve (`cd "$X"`, a
    failed substitution) falls back to the payload cwd's repository instead of
    becoming "not a repository, nothing to gate"."""
    if os.path.isdir(action.cwd):
        return action.cwd, action.git_args
    return action.base, []


def _policy_sha(text):
    return "absent" if text is None else hashlib.sha256(text.encode()).hexdigest()


def _policy_problems(action, root, git_args, policy, fresh):
    """The policy file is excluded from the fingerprint so editing it does not
    invalidate the checks it demands -- which would let a commit weakening it ride a
    receipt taken before the edit. A commit that changes it needs a receipt recorded
    with the policy being committed."""
    head = _git(["show", "HEAD:" + POLICY], root, git_args)
    index = _git(["show", ":" + POLICY], root, git_args)
    wt_path = pathlib.Path(root) / POLICY
    wt = wt_path.read_text() if wt_path.is_file() else None
    # After `-a`, a pathspec, or an earlier `git add` in the same line, the working
    # copy is what gets committed; the index read now predates that add.
    committed = wt if (action.commit_all or action.pathspec or action.added) and \
        index is not None else index
    if committed == head:
        return []
    want = _policy_sha(committed)
    labels = sorted(policy["required"]) or sorted(fresh)
    stale = [n for n in labels if n in fresh and fresh[n].get("policy_sha") != want]
    if not stale:
        return []
    return [f"this commit changes {POLICY}, and the receipt for "
            f"{', '.join(stale)} was not recorded with that policy in place (stage the "
            f"policy edit, then re-run `100x verified`)"]


def _changed_paths(root, git_args):
    out = _git(["status", "--porcelain", "-z", "--untracked-files=all"], root, git_args)
    return [r[3:] for r in (out or "").split("\0") if len(r) > 3 and r[3:] not in EXCLUDE]


def _push_problems(action, root, git_args, snap):
    """A push sends commits, not the working tree the receipt describes. Every ref
    it sends must be the checked-out commit, and that commit's tree must be exactly
    the verified content."""
    if action.srcs is None:
        return [f"cannot tell which refs `{action.label}` would send, so they cannot be "
                f"checked against the receipt; push a named branch directly, as its "
                f"own command"]
    head = (_git(["rev-parse", "--verify", "-q", "HEAD"], root, git_args) or "").strip()
    if not head:
        return ["HEAD has no commit to send"]
    refs = list(action.srcs)
    if action.push_mode in ("all", "mirror"):
        refs += _z_refs(root, git_args, "refs/heads")
    if action.push_mode in ("tags", "mirror"):
        refs += _z_refs(root, git_args, "refs/tags")
    problems = []
    for ref in dict.fromkeys(refs):
        sha = (_git(["rev-parse", "--verify", "-q", ref + "^{commit}"], root, git_args)
               or "").strip()
        if not sha:
            problems.append(f"`{ref}` does not name a local commit, so what it sends "
                            f"cannot be checked against the receipt")
        elif sha != head:
            problems.append(f"`{ref}` is not the checked-out commit; the receipt covers "
                            f"the working tree at HEAD, not `{ref}`. Check it out, "
                            f"verify it there, then push it")
    if any(repo_root(*_where(c)) == root for c in action.prior_commits):
        # The commit has not happened when the gate judges, so what it will put in
        # HEAD cannot be checked: a pathspec, GIT_INDEX_FILE or a hook can all make it
        # differ from the verified tree.
        problems.append(
            "a commit earlier in this command has not happened yet, so the tree this "
            "push sends cannot be checked against the receipt. Commit, then push in a "
            "separate command")
    elif tree_fingerprint(root, git_args, "HEAD") != snap["fingerprint"]:
        changed = _changed_paths(root, git_args)
        problems.append(
            "HEAD's committed tree is not the verified content: there are uncommitted "
            f"changes ({', '.join(changed[:5]) or 'see git status'}). Commit the "
            "verified content first, then push in a separate command")
    return problems


def _z_refs(root, git_args, prefix):
    out = _git(["for-each-ref", "--format=%(refname)", prefix], root, git_args)
    return [r for r in (out or "").splitlines() if r]


def judge(action, cmd):
    """Return (rank, output) for one action. rank: 0 pass, 1 note, 2 ask, 3 deny."""
    cwd, git_args = _where(action)
    root = repo_root(cwd, git_args)
    if not root and git_args:
        root, git_args = repo_root(action.base), []
    if not root:
        return 0, {}                    # not a repo: nothing to gate
    try:
        policy = load_policy(root, git_args)
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
    if action.after_write:
        return 3, deny(
            f"`{action.label}` blocked: an earlier part of this command "
            f"(`{action.after_write}`) can change files after the gate has checked them, "
            f"so the receipt would not describe what ships. Run edits and verification "
            f"first, then commit in a separate command.")

    try:
        have_receipt = os.path.lexists(receipt_path(root, git_args))
    except GateError as e:
        return 3, deny(f"`{action.label}` blocked: {e}")
    if not have_receipt:
        legacy = legacy_note(root)
        return 3, deny(f"`{action.label}` blocked: no verification receipt at {RECEIPT}."
                       f"\n\nRun the checks first:\n{rerun_hint(policy)}"
                       + (f"\n\nNote: {legacy}." if legacy else ""))
    try:
        key = load_key()
    except GateError as e:
        return 3, deny(f"`{action.label}` blocked: {e}.\n\nRun the checks first:\n"
                       f"{rerun_hint(policy)}")
    snap = snapshot(root, git_args)
    if not snap:
        return 0, {}
    try:
        result = evaluate(root, policy, snap["fingerprint"], key, git_args)
    except GateError as e:
        return 3, deny(f"`{action.label}` blocked: {e}")
    notes += result["notes"]
    problems = list(result["problems"])
    if not problems and action.kind in ("commit", "merge"):
        problems += _policy_problems(action, root, git_args, policy, result["fresh"])
    if not problems and action.kind == "push":
        problems += _push_problems(action, root, git_args, snap)
    if problems:
        body = "\n".join(f"  - {p}" for p in problems)
        extra = ("\n\nNotes:\n" + "\n".join(f"  - {n}" for n in notes)) if notes else ""
        return 3, deny(f"`{action.label}` blocked:\n{body}\n\nRe-run verification "
                       f"against the current content, then retry:\n"
                       f"{rerun_hint(policy)}{extra}")

    if action.kind == "commit":
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


# ---------------------------------------------------------------- text warnings
# PR bodies and commit messages are checked for prose problems, and `gh pr create` for
# scope leaks. Advisory only: it is appended to the output after the gate has decided
# and never changes the decision, and a deny or ask is emitted exactly as before.

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
MAX_FINDINGS = 8
HEREDOC_SUB = re.compile(r"^\$\(\s*cat\s+<<-?\s*(['\"]?)(\w+)\1[ \t]*\n(.*?)\n[ \t]*\2\s*\)\s*$",
                         re.S)
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n[ \t]*\2[ \t]*(?:\n|$)", re.S)


def _option_values(args, names, prefixes=()):
    vals, i = [], 0
    while i < len(args):
        a = args[i]
        if a in names and i + 1 < len(args):
            vals.append(args[i + 1])
            i += 2
            continue
        for p in prefixes:
            if a.startswith(p) and len(a) > len(p):
                vals.append(a[len(p):])
        i += 1
    return vals


def _literal(value, raw):
    """The text an argument carries: `$(cat <<'EOF' … EOF)` is unwrapped; any other
    substitution or variable is unknown, so None."""
    m = HEREDOC_SUB.match(value)
    if m:
        return m.group(3)
    return None if "$" in value or "`" in value else value


def _read_body(path, cwd, raw):
    if path == "-":
        m = HEREDOC.search(raw)
        return m.group(3) if m else None
    p = pathlib.Path(cwd, os.path.expanduser(path))
    try:
        return p.read_text(errors="replace") if p.is_file() else None
    except OSError:
        return None


def _texts(cmd, cwd):
    """[(kind, text, cwd, pr_base, is_create)] for each PR body or commit message the
    command passes literally."""
    found = []
    try:
        items = segments(prelex(cmd))
    except ValueError:
        return found
    for item in items:
        if not isinstance(item, Seg):
            continue
        argv = list(item.argv)
        while argv and (argv[0] in KEYWORDS or ENV_ASSIGN.match(argv[0])):
            argv = argv[1:]
        if not argv:
            continue
        prog = prog_name(argv[0])
        if prog == "cd" and len(argv) > 1 and "$" not in argv[1]:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(argv[1])))
        elif prog == "gh":
            pos = _positionals(argv[1:], OPT_ARG["gh"] | {"-H", "--head", "-B", "--base",
                                                          "-t", "--title", "-b", "--body",
                                                          "-F", "--body-file"})
            if pos[:2] not in (["pr", "create"], ["pr", "edit"]):
                continue
            args = argv[1:]
            bodies = [_literal(v, cmd) for v in
                      _option_values(args, {"-b", "--body"}, ("--body=",))]
            bodies += [_read_body(v, cwd, cmd) for v in
                       _option_values(args, {"-F", "--body-file"}, ("--body-file=",))]
            base = (_option_values(args, {"-B", "--base"}, ("--base=",)) or [None])[-1]
            for text in bodies:
                if text and text.strip():
                    found.append(("pr", text, cwd, base, pos[1] == "create"))
        elif prog == "git":
            args, work_dir = argv[1:], cwd
            while args and args[0].startswith("-"):
                if args[0] == "-C" and len(args) > 1:
                    work_dir = os.path.normpath(os.path.join(work_dir, os.path.expanduser(args[1])))
                args = args[2:] if args[0] in GIT_OPT_ARG else args[1:]
            if args[:1] != ["commit"]:
                continue
            # `-am msg`: a cluster ending in m or F takes the next word as its value.
            args = [x for a in args[1:] for x in
                    ([a[:-1], "-" + a[-1]] if re.fullmatch(r"-[a-zA-Z]+[mF]", a) else [a])]
            msgs = [_literal(v, cmd) for v in
                    _option_values(args, {"-m", "--message"}, ("--message=", "-m"))]
            msgs += [_read_body(v, work_dir, cmd) for v in
                     _option_values(args, {"-F", "--file"}, ("--file=", "-F"))]
            if msgs and all(m is not None for m in msgs):
                text = "\n\n".join(msgs)
                if text.strip():
                    found.append(("commit", text, work_dir, None, False))
    return found


def _import(name):
    if str(SCRIPTS) not in sys.path:
        sys.path.append(str(SCRIPTS))
    try:
        return __import__(name)
    except ImportError:  # fail-open: the checker is optional; without it there is nothing to add
        return None


def text_findings(cmd, cwd):
    """Lines of advisory findings for the command's PR bodies and commit messages."""
    texts = _texts(cmd, cwd)
    if not texts:
        return []
    prose, scope = _import("prose_check"), _import("pr_scope")
    lines = []
    for kind, text, wd, pr_base, is_create in texts:
        base = scope.resolve_base(wd, pr_base) if scope and kind == "pr" else None
        if prose and hasattr(prose, "check_text"):
            n = scope.diff_lines(wd, base) if base else None
            for f in prose.check_text(text, kind=kind, diff_lines=n):
                lines.append(f"[{f.get('rule')}] {kind} line {f.get('line')}: "
                             f"{f.get('message')}")
        if scope and is_create:
            for f in scope.analyse(wd, pr_base, body=text)["findings"]:
                lines.append(f"[{f['rule']}] {f['file']}: {f['message']}")
    return lines


def _with_findings(out, lines):
    """Attach advisory lines to a non-blocking output as context the agent reads."""
    if not lines:
        return out
    shown = lines[:MAX_FINDINGS]
    more = len(lines) - len(shown)
    block = ("Writing and scope check (warn-only, does not block): fix these before "
             "shipping.\n" + "\n".join(f"  - {s}" for s in shown)
             + (f"\n  (+{more} more: run `100x prose_check` / `100x pr_scope`)"
                if more else ""))
    msg = out.get("systemMessage")
    return note(f"{msg}\n{block}" if msg else block)


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
    out = decide(cmd, base)
    if (out.get("hookSpecificOutput") or {}).get("permissionDecision"):
        return out
    try:
        lines = text_findings(cmd, base)
    except Exception:  # fail-open: an advisory check must never turn into a gate failure
        lines = []
    return _with_findings(out, lines)


def decide(cmd, base):
    state = State(base, cmd)
    try:
        actions = parse_command(cmd, state)
    except ValueError:
        actions = _fallback_actions(cmd, State(base, cmd))
    if not actions:
        return {}

    worst, outputs, seen = -1, [], set()
    for action in actions:
        if action.key() in seen:
            continue
        seen.add(action.key())
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
    except Exception as e:  # fail-open: an internal error must not brick the shell; it is reported
        print(json.dumps({"systemMessage": f"verification hook error (failing open): {e}"}))
    sys.exit(0)
