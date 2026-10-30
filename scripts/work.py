#!/usr/bin/env python3
"""Private work record: the state of a feature family that outlives any one session.

A long-running piece of work (several PRs, days or weeks, many sessions) loses its
facts every time a session is summarised or abandoned, and the human restates them.
This keeps those facts in plain files on the owner's machine, outside every project
repository (decisions/ADR-0006): nothing here writes to a repo, pushes, or uses the
network. Any local session, in any worktree, resumes from `100x work brief`.

Each write is one new file, created with O_CREAT|O_EXCL and never edited, moved or
deleted, so concurrent sessions and a second laptop's synced files never conflict;
the workstream view is derived in memory from the events.

    100x work start <ws> --repo <url-or-host/owner/repo> --pr <n>:<branch>:<role> ...
                    [--goal TEXT] [--merge-order 1,2,3] [--convention TEXT ...]
    100x work note TEXT            [--ws WS]
    100x work decide TEXT [--id D1] [--ws WS]
    100x work hold <pr> --reason TEXT [--ws WS]
    100x work release-hold <pr>    [--ws WS]
    100x work handoff TEXT         [--ws WS]
    100x work brief [--ws WS] [--max-tokens 3000]
    100x work list
    100x work doctor [--json] [--cwd DIR]

Without --ws, the workstream is the one whose repos and PR branches match the current
directory's `origin` remote and branch.

Environment: HUNDREDX_WORK_DIR (record dir, default ~/.config/100x/work),
HUNDREDX_WORK=off (disable every command and hook), HUNDREDX_WORK_BACKUP_HINT (a file
naming the record dir when a backup covers it; else "backup_hint" in ~/.config/100x/work.json;
unset means doctor reports the record as not backed up), HUNDREDX_CONFIG_DIRS (extra
Claude config dirs, colon-separated, whose installed plugin doctor inspects).

`doctor` is read-only: one finding per problem (id, severity, what, cause, fix), exit 1 when
any is an error or warning.

Exit codes: 0 ok, 1 refused or not found (nothing written) or doctor found a problem,
2 usage error.
Python stdlib only.
"""
import argparse, datetime, json, os, pathlib, re, secrets, shlex, subprocess, sys, time
import urllib.parse

SCHEMA = 1
EVENT_TYPES = ("set", "note", "decision", "hold", "release-hold", "handoff")
DIR_MODE = 0o700
FILE_MODE = 0o600
DEFAULT_DIR_REL = (".config", "100x", "work")
# User-level config, shared with hooks/work_fork_guard.py. No backup tool is assumed: a user
# names their own backup's file list here ("backup_hint"), which doctor greps for the record dir.
CONFIG_REL = (".config", "100x", "work.json")
DEFAULT_MAX_TOKENS = 3000
CHARS_PER_TOKEN = 4
BRIEF_RECENT = 10          # notes and handoffs shown before the token budget trims them
MAX_TEXT = 2000            # one note is a few sentences; a pasted log is not a note
GIT_TIMEOUT_S = 3          # the SessionStart hook that calls this is killed at 10 s
NAME_ATTEMPTS = 5
PR_FIELDS = 3              # <number>:<branch>:<role>; git branch names cannot hold ':'
WS_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ID_RX = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
SESSION_RX = re.compile(r"[^A-Za-z0-9-]")
EVENT_NAME_RX = re.compile(r"^\d{8}T\d{12}Z-[A-Za-z0-9-]+-[0-9a-f]{6}\.json$")
PRIVACY = "Private to you: never quote this brief in commits, PR text or review comments."
LIVE_STATE = ("PR state (CI, reviews, merged) is not stored here: read it live "
              "before acting.")

# Copied from claude-setup tools/sync.py (SECRET): the owner's backup refuses to commit a
# file matching these, so an event holding one would silently never be backed up. Email
# addresses are added because the record leaves the machine through that backup.
SECRET = re.compile(
    r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}"
    r"|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|xox[abpr]-[A-Za-z0-9-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|(?i:(?:password|passwd|secret|api[_-]?key|auth[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9/+_.-]{12,})"
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)


class WorkError(Exception):
    """A refusal the user can act on: printed, exit 1, nothing written."""


# ---------------------------------------------------------------- paths and config

def disabled():
    return os.environ.get("HUNDREDX_WORK", "").strip().lower() == "off"


def record_dir():
    env = os.environ.get("HUNDREDX_WORK_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path.home().joinpath(*DEFAULT_DIR_REL)


def session_label():
    raw = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    label = SESSION_RX.sub("", raw)[:36]
    return label or "cli"


def check_ws_name(ws):
    if not WS_RX.match(ws or "") or ".." in ws:
        raise WorkError(f"invalid workstream name {ws!r}: letters, digits, '.', '_', '-'")
    return ws


# ---------------------------------------------------------------- repo identity

def normalise_repo(text):
    """host/owner/repo from any remote form; credentials, scheme, port and .git dropped,
    because a stored URL can carry a token into the backup."""
    raw = (text or "").strip()
    scp = re.match(r"^(?:[^@/\s]+@)?([^:/\s]+):(?!//)(.+)$", raw)
    if "://" in raw:
        parts = urllib.parse.urlsplit(raw)
        host, path = parts.hostname or "", parts.path
    elif scp:
        host, path = scp.group(1), scp.group(2)
    else:
        host, _, path = raw.partition("/")
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-len(".git")]
    segments = [s for s in path.split("/") if s]
    if not host or len(segments) < 2 or any(s in (".", "..") for s in segments):
        raise WorkError(f"cannot read a host/owner/repo from {redact(raw)!r}")
    return "/".join([host] + segments).lower()


def redact(text):
    """The input with any userinfo removed, so an error message never echoes a token."""
    return re.sub(r"//[^/@\s]*@", "//", text)


def git_out(cwd, *args):
    try:
        done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                              text=True, timeout=GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def cwd_identity(cwd):
    """(repo, branch) for a directory, or None outside a repo, without origin, or detached."""
    url = git_out(cwd, "remote", "get-url", "origin")
    branch = git_out(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if not url or not branch or branch == "HEAD":
        return None
    try:
        return normalise_repo(url), branch
    except WorkError:
        return None


# ---------------------------------------------------------------- events

def refuse_secrets(event):
    for key, value in walk_strings(event):
        if SECRET.search(value):
            raise WorkError(f"refused: {key} looks like a secret or an email address; "
                            "nothing written (the backup would skip this file)")


def walk_strings(value, key="event"):
    if isinstance(value, str):
        yield key, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from walk_strings(v, k)
    elif isinstance(value, list):
        for v in value:
            yield from walk_strings(v, key)


def check_text(label, text):
    text = (text or "").strip()
    if not text:
        raise WorkError(f"{label} is empty")
    if len(text) > MAX_TEXT:
        raise WorkError(f"{label} is {len(text)} characters; the limit is {MAX_TEXT}")
    return text


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def ensure_dir(path):
    path.mkdir(mode=DIR_MODE, parents=False, exist_ok=True)


def create_exclusive(path, text):
    """Write a new file; FileExistsError if anything (even a symlink) is already there."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                 FILE_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def write_event(ws, kind, fields):
    if disabled():
        raise WorkError("disabled (HUNDREDX_WORK=off); nothing written")
    check_ws_name(ws)
    session = session_label()
    event = {"schema": SCHEMA, "type": kind, "ws": ws, "session": session, **fields}
    refuse_secrets(event)
    root = record_dir()
    root.parent.mkdir(parents=True, exist_ok=True)
    ensure_dir(root)
    ensure_dir(root / ws)
    events = root / ws / "events"
    ensure_dir(events)
    for _ in range(NAME_ATTEMPTS):
        now = utc_now()
        event["at"] = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
        name = f"{now.strftime('%Y%m%dT%H%M%S%f')}Z-{session}-{secrets.token_hex(3)}.json"
        try:
            create_exclusive(events / name, json.dumps(event, indent=1, sort_keys=True) + "\n")
            return events / name
        except FileExistsError:
            continue
    raise WorkError(f"could not create a unique event file in {events}")


def read_events(ws):
    """(events in file-name order, count of unreadable files, count of newer-schema events)."""
    folder = record_dir() / ws / "events"
    events, unreadable, newer = [], 0, 0
    try:
        names = sorted(p.name for p in folder.iterdir() if EVENT_NAME_RX.match(p.name))
    except OSError:
        return events, unreadable, newer
    for name in names:
        try:
            event = json.loads((folder / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable += 1
            continue
        if not isinstance(event, dict):
            unreadable += 1
        elif event.get("schema") != SCHEMA:
            newer += 1
        elif event.get("type") in EVENT_TYPES:
            event["_file"] = name
            events.append(event)
    return events, unreadable, newer


def workstreams():
    try:
        return sorted(p.name for p in record_dir().iterdir()
                      if p.is_dir() and WS_RX.match(p.name))
    except OSError:
        return []


# ---------------------------------------------------------------- derived view

def derive(ws, events):
    view = {"ws": ws, "goal": "", "repos": [], "prs": {}, "merge_order": [],
            "conventions": [], "decisions": {}, "holds": {}, "notes": []}
    for event in events:
        apply_event(view, event)
    return view


def apply_event(view, event):
    kind = event["type"]
    if kind == "set":
        merge_set(view, event)
    elif kind == "decision":
        key = event.get("id") or event["_file"]
        view["decisions"].pop(key, None)    # a re-decided id moves to the end
        view["decisions"][key] = event
    elif kind == "hold":
        view["holds"][event.get("pr")] = event
    elif kind == "release-hold":
        view["holds"].pop(event.get("pr"), None)
    elif kind in ("note", "handoff"):
        view["notes"].append(event)


def merge_set(view, event):
    """A later set wins field by field: goal and merge order replace, repos and conventions
    accumulate, a PR number's branch and role are replaced."""
    if event.get("goal"):
        view["goal"] = event["goal"]
    for repo in event.get("repos") or []:
        if repo not in view["repos"]:
            view["repos"].append(repo)
    for pr in event.get("prs") or []:
        view["prs"][pr["number"]] = pr
    if event.get("merge_order"):
        view["merge_order"] = list(event["merge_order"])
    for convention in event.get("conventions") or []:
        if convention not in view["conventions"]:
            view["conventions"].append(convention)


def load_view(ws):
    events, _, _ = read_events(ws)
    return derive(ws, events)


def lookup(cwd):
    """Workstreams whose repos include cwd's origin and whose PRs include its branch."""
    ident = cwd_identity(cwd)
    if not ident:
        return []
    repo, branch = ident
    found = []
    for ws in workstreams():
        view = load_view(ws)
        if repo in view["repos"] and any(p["branch"] == branch for p in view["prs"].values()):
            found.append(ws)
    return found


def resolve_ws(explicit, cwd=None):
    if explicit:
        check_ws_name(explicit)
        if not (record_dir() / explicit).is_dir():
            raise WorkError(f"no workstream {explicit!r} (`100x work list`)")
        return explicit
    matches = lookup(cwd or os.getcwd())
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise WorkError(f"this branch belongs to several workstreams ({', '.join(matches)}); "
                        "pass --ws")
    raise WorkError("no workstream matches this directory's origin remote and branch; "
                    "pass --ws, or `100x work start` one")


# ---------------------------------------------------------------- brief

def render_brief(view, newer=0, max_tokens=DEFAULT_MAX_TOKENS):
    """Markdown under max_tokens (len/4): oldest notes go first, then oldest decisions.
    Holds, PRs and the privacy line always stay."""
    return trim_brief(view, newer, max_tokens)["text"]


def trim_brief(view, newer, max_tokens):
    """The brief plus what the budget cut, so doctor can say what a session will not see."""
    notes = view["notes"][-BRIEF_RECENT:]
    decisions = list(view["decisions"].values())
    dropped = len(view["notes"]) - len(notes)
    cut = {"notes": 0, "decisions": 0}
    while True:
        text = brief_text(view, notes, decisions, dropped, newer)
        fits = len(text) / CHARS_PER_TOKEN <= max_tokens
        if fits or not (notes or decisions):
            return {"text": text, "fits": fits, **cut}
        if notes:
            notes = notes[1:]
            dropped += 1
            cut["notes"] += 1
        else:
            decisions = decisions[1:]
            cut["decisions"] += 1


def brief_text(view, notes, decisions, dropped, newer):
    lines = [f"# Workstream {view['ws']}", "", PRIVACY, LIVE_STATE, ""]
    if view["goal"]:
        lines += [f"**Goal:** {view['goal']}", ""]
    if view["repos"]:
        lines += ["**Repos:** " + ", ".join(f"`{r}`" for r in view["repos"]), ""]
    lines += ["| PR | branch | role |", "|---|---|---|"]
    for number in sorted(view["prs"]):
        pr = view["prs"][number]
        lines.append(f"| #{number} | `{pr['branch']}` | {pr['role']} |")
    lines.append("")
    if view["merge_order"]:
        lines += ["**Merge order:** " + " → ".join(f"#{n}" for n in view["merge_order"]), ""]
    lines.append("## Holds")
    lines += [f"- #{pr}: {h.get('reason', '')} (since {h.get('at', '?')})"
              for pr, h in sorted(view["holds"].items())] or ["- none"]
    lines += ["", "## Decisions"]
    lines += [f"- {fmt_decision(d)}" for d in decisions] or ["- none"]
    if view["conventions"]:
        lines += ["", "## Conventions"] + [f"- {c}" for c in view["conventions"]]
    lines += ["", "## Recent notes and handoffs"]
    if dropped:
        lines.append(f"- ({dropped} older not shown)")
    lines += [f"- {n.get('at', '?')[:16]} {n['type']}: {n.get('text', '')}" for n in notes] \
        or ["- none"]
    if newer:
        lines += ["", f"{newer} event(s) use a newer schema: upgrade the plugin to read them."]
    return "\n".join(lines) + "\n"


def fmt_decision(event):
    prefix = f"{event['id']}: " if event.get("id") else ""
    return prefix + event.get("text", "")


def brief_for(ws, max_tokens=DEFAULT_MAX_TOKENS):
    events, _, newer = read_events(ws)
    return render_brief(derive(ws, events), newer, max_tokens)


# ---------------------------------------------------------------- commands

def parse_pr(spec):
    parts = spec.split(":", PR_FIELDS - 1)
    if len(parts) != PR_FIELDS or not parts[0].isdigit() or int(parts[0]) < 1 \
            or not parts[1].strip() or not parts[2].strip():
        raise WorkError(f"--pr {spec!r}: expected <number>:<branch>:<role>")
    return {"number": int(parts[0]), "branch": parts[1].strip(),
            "role": check_text("PR role", parts[2])}


def parse_merge_order(text):
    try:
        order = [int(n) for n in text.split(",") if n.strip()]
    except ValueError:
        raise WorkError(f"--merge-order {text!r}: expected PR numbers like 1,2,3")
    if not order:
        raise WorkError("--merge-order is empty")
    return order


def cmd_start(args):
    ws = check_ws_name(args.ws)
    exists = (record_dir() / ws).is_dir()
    if not exists and not args.repo:
        raise WorkError("a new workstream needs at least one --repo")
    fields = {"repos": [normalise_repo(r) for r in args.repo or []],
              "prs": [parse_pr(p) for p in args.pr or []]}
    if args.goal is not None:
        fields["goal"] = check_text("--goal", args.goal)
    if args.convention:
        fields["conventions"] = [check_text("--convention", c) for c in args.convention]
    if args.merge_order:
        fields["merge_order"] = parse_merge_order(args.merge_order)
        known = set(load_view(ws)["prs"]) | {p["number"] for p in fields["prs"]}
        unknown = [n for n in fields["merge_order"] if n not in known]
        if unknown:
            raise WorkError(f"--merge-order names PRs not in the workstream: {unknown}")
    path = write_event(ws, "set", fields)
    print(f"{'updated' if exists else 'started'} {ws}: {path}")


def known_pr(ws, number):
    if number not in load_view(ws)["prs"]:
        raise WorkError(f"PR #{number} is not in workstream {ws} (`100x work brief`)")
    return number


def cmd_text_event(kind, label):
    def run(args):
        ws = resolve_ws(args.ws)
        fields = {"text": check_text(label, args.text)}
        if getattr(args, "id", None):
            if not ID_RX.match(args.id):
                raise WorkError(f"--id {args.id!r}: letters, digits, '_' or '-', up to 32")
            fields["id"] = args.id
        print(f"{kind} recorded in {ws}: {write_event(ws, kind, fields)}")
    return run


def cmd_hold(args):
    ws = resolve_ws(args.ws)
    fields = {"pr": known_pr(ws, args.pr), "reason": check_text("--reason", args.reason)}
    print(f"hold on #{args.pr} in {ws}: {write_event(ws, 'hold', fields)}")


def cmd_release_hold(args):
    ws = resolve_ws(args.ws)
    if args.pr not in load_view(ws)["holds"]:
        raise WorkError(f"PR #{args.pr} has no active hold in {ws}")
    print(f"hold released on #{args.pr} in {ws}: "
          f"{write_event(ws, 'release-hold', {'pr': args.pr})}")


def cmd_brief(args):
    if args.max_tokens < 1:
        raise WorkError("--max-tokens must be positive")
    sys.stdout.write(brief_for(resolve_ws(args.ws), args.max_tokens))


def cmd_list(_args):
    names = workstreams()
    if not names:
        print(f"no workstreams in {record_dir()}")
    for ws in names:
        events, _, _ = read_events(ws)
        view = derive(ws, events)
        print(f"{ws}\t{len(events)} events\t{len(view['prs'])} PRs\t"
              f"{', '.join(view['repos'])}\t{view['goal'][:60]}")


def backup_hint():
    """The backup's file list to grep, or None when none is configured."""
    env = os.environ.get("HUNDREDX_WORK_BACKUP_HINT")
    if env:
        return pathlib.Path(env).expanduser()
    try:
        hint = json.loads(pathlib.Path.home().joinpath(*CONFIG_REL).read_text()).get("backup_hint")
    except (OSError, ValueError, AttributeError):
        return None
    return pathlib.Path(hint).expanduser() if isinstance(hint, str) and hint else None


def hint_entry(hint, root):
    """The line of the hint file that starts with the record dir (home-relative or absolute),
    or None. OSError when the hint file cannot be read."""
    names = {str(root)}
    home = pathlib.Path.home()
    if home in root.parents:
        names.add(str(root.relative_to(home)))
    for line in hint.read_text(encoding="utf-8", errors="replace").splitlines():
        words = line.split()
        if words and words[0].rstrip("/") in names:
            return line.strip()
    return None


def home_relative(path):
    home = pathlib.Path.home()
    return str(path.relative_to(home)) if home in path.parents else str(path)


# ---------------------------------------------------------------- doctor
#
# Read-only diagnosis: every check reads files, git refs and one dry run of the SessionStart
# hook, and returns findings. Nothing here writes, fetches or calls gh. Adding a check is one
# function decorated with @check(<id>).

SEVERITIES = ("error", "warn", "info")
FAILING = ("error", "warn")
HOLD_STALE_DAYS = 14
HANDOFF_LAG_DAYS = 7
UNPUSHED_HOURS = 24
# Optional convention, not a dependency on any one backup tool: a backup that rebases before
# it pushes can leave this file at its repository's root when the rebase stops, with the
# reason in its first lines. When present, the backup is stuck until someone resolves it.
SYNC_FAILED_REL = (".state", "remote-sync-failed")
SYNC_FAILED_SHOWN = 5
PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN_NAME = "100x"
WORK_HOOKS = (("SessionStart", "work_brief.py"), ("PreToolUse", "work_fork_guard.py"))
BRIEF_HOOK = "work_brief.py"
HOOK_TIMEOUT_S = 10        # used when hooks.json does not state the hook's own timeout
HOOK_SLOW_FRACTION = 0.5   # a dry run past half the timeout is one bad day from being killed
CONFIG_DIRS_ENV = "HUNDREDX_CONFIG_DIRS"
CONFIG_DIRS_SEP = ":"
DEFAULT_CONFIG_DIR = ".claude"
PLACEHOLDER_MARKET = "<marketplace>"

CHECKS = []


def check(check_id):
    def register(fn):
        CHECKS.append((check_id, fn))
        return fn
    return register


def finding(fid, severity, what, cause, fix):
    return {"id": fid, "severity": severity, "what": what, "cause": cause, "fix": fix}


def q(path):
    return shlex.quote(str(path))


def parse_at(text):
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def age_days(then, now):
    return (now - then).total_seconds() / 86400


@check("D-record")
def check_record(ctx):
    out, root = [], ctx["root"]
    if disabled():
        out.append(finding("D-record.off", "warn", "HUNDREDX_WORK=off: every work command "
                           "and hook is disabled, so no session gets a brief",
                           "the variable is set in this shell or its profile",
                           "unset HUNDREDX_WORK"))
    if not root.exists():
        out.append(finding("D-record.missing", "info", f"no work record yet at {root}",
                           "no workstream has been started on this machine (or "
                           "HUNDREDX_WORK_DIR points elsewhere)",
                           "100x work start <name> --repo <host/owner/repo> "
                           "--pr <number>:<branch>:<role>"))
    elif not root.is_dir():
        out.append(finding("D-record.not-dir", "error", f"{root} exists but is not a directory",
                           "something else was created at the record path",
                           f"move {q(root)} aside by hand, or set HUNDREDX_WORK_DIR"))
    else:
        mode = root.stat().st_mode & 0o777
        if mode & 0o077:
            out.append(finding("D-record.mode", "warn",
                               f"record dir is mode {mode:o}: other users can read it",
                               "it was created or copied by something other than `100x work` "
                               "(a restore or a sync keeps the source mode)",
                               f"chmod 700 {q(root)}"))
    return out


def classify_event_files(ws):
    """(unreadable, newer-schema, stray) file names in one workstream's events folder."""
    folder = record_dir() / ws / "events"
    unreadable, newer, stray = [], [], []
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return unreadable, newer, stray
    for path in entries:
        if not EVENT_NAME_RX.match(path.name):
            stray.append(path.name)
            continue
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable.append(path.name)
            continue
        if not isinstance(event, dict):
            unreadable.append(path.name)
        elif event.get("schema") != SCHEMA:
            newer.append(path.name)
    return unreadable, newer, stray


def listed(names, limit=3):
    more = f" and {len(names) - limit} more" if len(names) > limit else ""
    return ", ".join(names[:limit]) + more


@check("D-events")
def check_events(ctx):
    out = []
    for ws in workstreams():
        unreadable, newer, stray = classify_event_files(ws)
        folder = record_dir() / ws / "events"
        if unreadable:
            aside = record_dir() / ws / "set-aside"
            out.append(finding("D-events.unreadable", "warn",
                               f"{ws}: {len(unreadable)} event file(s) are not readable JSON "
                               f"({listed(unreadable)}); the brief skips them",
                               "a crash or an interrupted sync truncated the file, or it was "
                               "edited by hand",
                               f"compare with your backup copy, then mkdir -p {q(aside)} && "
                               f"mv {q(folder / unreadable[0])} {q(aside)}/"))
        if newer:
            out.append(finding("D-events.newer-schema", "warn",
                               f"{ws}: {len(newer)} event(s) use a schema newer than {SCHEMA} "
                               "and are ignored here",
                               "another session or laptop runs a newer 100x plugin",
                               "upgrade the plugin here: " + reinstall_cmd(None, None)))
        if stray:
            out.append(finding("D-events.stray", "info",
                               f"{ws}: {len(stray)} file(s) in events/ are not named like an "
                               f"event and are ignored ({listed(stray)})",
                               "a file was copied in by hand or by a sync tool's conflict copy",
                               f"move them out of {q(folder)} if they are not needed"))
    return out


@check("D-lookup")
def check_lookup(ctx):
    cwd = ctx["cwd"]
    if git_out(cwd, "rev-parse", "--show-toplevel") is None:
        return [finding("D-lookup.not-repo", "info", f"{cwd} is not inside a git repository, "
                        "so no workstream can match it",
                        "the hooks match a session on its origin remote and branch",
                        "run doctor with --cwd <a worktree of the workstream>, or pass "
                        "--ws to work commands")]
    url = git_out(cwd, "remote", "get-url", "origin")
    if not url:
        return [finding("D-lookup.no-origin", "warn", f"{cwd} has no origin remote",
                        "workstreams match on origin; this repo has none (or names it "
                        "differently)", f"git -C {q(cwd)} remote add origin <url>, or pass "
                        "--ws to work commands")]
    if ctx["ident"] is None:
        branch = git_out(cwd, "rev-parse", "--abbrev-ref", "HEAD")
        if branch == "HEAD":
            return [finding("D-lookup.detached", "info", f"{cwd} is on a detached HEAD",
                            "workstreams match on a branch name", f"git -C {q(cwd)} switch "
                            "<branch>, or pass --ws to work commands")]
        return [finding("D-lookup.bad-origin", "warn", f"origin {redact(url)!r} does not read "
                        "as host/owner/repo", "an unusual remote form",
                        "pass --ws to work commands")]
    repo, branch = ctx["ident"]
    matches = ctx["matches"]
    if len(matches) > 1:
        return [finding("D-lookup.several", "warn",
                        f"{repo} {branch} matches {len(matches)} workstreams: "
                        f"{', '.join(matches)}; hooks and commands refuse to guess",
                        "the same repo and branch were added to more than one workstream",
                        f"pass --ws, or move the branch in one of them: 100x work start "
                        f"{matches[-1]} --pr <number>:<other-branch>:<role>")]
    if matches:
        return []
    same_repo = [ws for ws in workstreams() if repo in load_view(ws)["repos"]]
    near = (f"; {', '.join(same_repo)} has this repo but not this branch"
            if same_repo else "")
    target = same_repo[0] if len(same_repo) == 1 else "<name>"
    repo_arg = "" if same_repo else f" --repo {repo}"
    return [finding("D-lookup.none", "info", f"{repo} {branch} matches no workstream{near}",
                    "no `100x work start` has named this repo and branch",
                    f"100x work start {target}{repo_arg} --pr <number>:{shlex.quote(branch)}"
                    ":<role>")]


def hooks_config(plugin_root):
    """hooks.json's "hooks" object, or None when it is missing or unreadable."""
    try:
        config = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    hooks = config.get("hooks") if isinstance(config, dict) else None
    return hooks if isinstance(hooks, dict) else None


def hook_commands(hooks, event):
    for group in hooks.get(event) or []:
        for entry in (group.get("hooks") or []) if isinstance(group, dict) else []:
            if isinstance(entry, dict) and isinstance(entry.get("command"), str):
                yield entry


def missing_hooks(hooks):
    if hooks is None:
        return [name for _, name in WORK_HOOKS]
    return [name for event, name in WORK_HOOKS
            if not any(f"/hooks/{name}" in e["command"] for e in hook_commands(hooks, event))]


def brief_hook_timeout():
    hooks = hooks_config(PLUGIN_ROOT) or {}
    for entry in hook_commands(hooks, "SessionStart"):
        if BRIEF_HOOK in entry["command"] and isinstance(entry.get("timeout"), (int, float)):
            return entry["timeout"]
    return HOOK_TIMEOUT_S


def run_brief_hook_dry(cwd):
    """Feed hooks/work_brief.py the payload a SessionStart in cwd would send.
    (brief text or None, seconds, error text or None)."""
    payload = json.dumps({"hook_event_name": "SessionStart", "source": "startup",
                          "cwd": str(cwd), "session_id": "doctor-dry-run"})
    # No bytecode: a dry run must not leave __pycache__ in the plugin install either.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    try:
        done = subprocess.run([sys.executable, str(PLUGIN_ROOT / "hooks" / BRIEF_HOOK)],
                              input=payload, capture_output=True, text=True, env=env,
                              timeout=brief_hook_timeout())
    except subprocess.TimeoutExpired:
        return None, time.monotonic() - started, "timed out; Claude Code would kill it"
    except OSError as err:
        return None, time.monotonic() - started, str(err)
    took = time.monotonic() - started
    if not done.stdout.strip():
        return None, took, (done.stderr.strip().splitlines() or [None])[0]
    try:
        context = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return None, took, "printed something that is not SessionStart hook output"
    return context, took, None


@check("D-brief")
def check_brief(ctx):
    out, matches = [], ctx["matches"]
    brief, took, err = run_brief_hook_dry(ctx["cwd"])
    ctx["brief_hook"] = {"gets_brief": bool(brief), "seconds": round(took, 2)}
    limit = brief_hook_timeout()
    if took > limit * HOOK_SLOW_FRACTION:
        out.append(finding("D-brief.slow", "warn", f"the SessionStart hook took {took:.1f} s "
                           f"of its {limit} s timeout", "a large record or a slow git call",
                           "check `100x work list` for very large workstreams"))
    if len(matches) == 1 and not disabled() and not brief:
        out.append(finding("D-brief.hook-silent", "error",
                           f"{ctx['cwd']} matches {matches[0]}, but the SessionStart hook "
                           "would print no brief", f"the hook failed open ({err or 'no output'})",
                           f"100x work brief --ws {matches[0]} shows the error"))
    if len(matches) != 1:
        return out
    events, _, newer = read_events(matches[0])
    trimmed = trim_brief(derive(matches[0], events), newer, DEFAULT_MAX_TOKENS)
    if trimmed["decisions"] or not trimmed["fits"]:
        out.append(finding("D-brief.budget", "warn",
                           f"{matches[0]}'s brief is over its {DEFAULT_MAX_TOKENS}-token budget: "
                           f"{trimmed['decisions']} oldest decision(s) and {trimmed['notes']} "
                           "note(s) are cut" + ("" if trimmed["fits"] else
                                                ", and it still does not fit"),
                           "many or long decisions; each new --id adds one",
                           "re-decide superseded decisions under their old id "
                           f"(100x work decide TEXT --id <id> --ws {matches[0]}) so they "
                           "replace rather than accumulate"))
    elif trimmed["notes"]:
        out.append(finding("D-brief.notes-cut", "info",
                           f"{matches[0]}'s brief cuts {trimmed['notes']} recent note(s) to fit "
                           f"{DEFAULT_MAX_TOKENS} tokens", "long notes",
                           f"leave a short handoff that restates the state: 100x work "
                           f"handoff TEXT --ws {matches[0]}"))
    return out


def list_config_dirs():
    """Claude config dirs to inspect, in order, without duplicates."""
    raw = [os.environ.get("CLAUDE_CONFIG_DIR") or "",
           str(pathlib.Path.home() / DEFAULT_CONFIG_DIR)]
    raw += (os.environ.get(CONFIG_DIRS_ENV) or "").split(CONFIG_DIRS_SEP)
    seen, out = set(), []
    for text in raw:
        if not text.strip():
            continue
        path = pathlib.Path(text).expanduser()
        key = path.resolve() if path.exists() else path
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def version_key(path):
    parts = re.findall(r"\d+", path.name)
    return tuple(int(p) for p in parts), path.stat().st_mtime


def installed_copy(config_dir):
    """(plugin version dir, marketplace) of the newest installed 100x, or None."""
    found = [p.parent.parent for p in
             config_dir.glob(f"plugins/cache/*/{PLUGIN_NAME}/*/hooks/hooks.json")]
    if not found:
        return None
    newest = max(found, key=version_key)
    return newest, newest.parent.parent.name


def reinstall_cmd(config_dir, market):
    market = market or PLACEHOLDER_MARKET
    prefix = f"CLAUDE_CONFIG_DIR={q(config_dir)} " if config_dir else ""
    plugin = f"{PLUGIN_NAME}@{market}"
    return (f"{prefix}claude plugin uninstall {plugin} && {prefix}claude plugin marketplace "
            f"update {market} && {prefix}claude plugin install {plugin}")


@check("D-hooks")
def check_hooks(ctx):
    out = []
    missing = missing_hooks(hooks_config(PLUGIN_ROOT))
    if missing:
        out.append(finding("D-hooks.plugin", "error", f"this plugin ({PLUGIN_ROOT}) does not "
                           f"register {', '.join(missing)} in hooks/hooks.json",
                           "hooks/hooks.json was edited or is from a partial copy",
                           f"git -C {q(PLUGIN_ROOT)} diff hooks/hooks.json, and restore the "
                           "work hook entries"))
    for config_dir in list_config_dirs():
        if not config_dir.is_dir():
            continue
        copy = installed_copy(config_dir)
        if copy is None:
            out.append(finding("D-hooks.not-installed", "info",
                               f"no installed {PLUGIN_NAME} plugin under {config_dir}",
                               "the plugin is not installed for this config dir, or is loaded "
                               "with --plugin-dir", f"CLAUDE_CONFIG_DIR={q(config_dir)} claude "
                               f"plugin install {PLUGIN_NAME}@{PLACEHOLDER_MARKET}"))
            continue
        version_dir, market = copy
        gone = missing_hooks(hooks_config(version_dir))
        if gone:
            out.append(finding("D-hooks.installed-old", "warn",
                               f"the installed copy in {config_dir} ({version_dir.name}) is "
                               f"older than this plugin: it does not register {', '.join(gone)}",
                               "the plugin cache is a snapshot taken at install time; sessions "
                               "using this config dir run the old hooks",
                               reinstall_cmd(config_dir, market) + "; then restart sessions"))
    return out


def scan_backup_repo(hint):
    """Findings about the git repo holding the hint file, from local refs only."""
    top = git_out(hint.parent, "rev-parse", "--show-toplevel")
    if top is None:
        return []
    out, top = [], pathlib.Path(top)
    marker = top.joinpath(*SYNC_FAILED_REL)
    if marker.is_file():
        try:
            head = marker.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            head = []
        shown = " | ".join(line.strip() for line in head[:SYNC_FAILED_SHOWN] if line.strip())
        out.append(finding("D-backup.sync-failed", "error",
                           f"the backup repo's last sync stopped: {marker} says: "
                           f"{shown or '(empty)'}",
                           "its rebase hit a conflict, so nothing new leaves this machine",
                           f"resolve the rebase by hand in {top} (git -C {q(top)} status), "
                           "then let the backup tool clear its marker"))
    upstream = git_out(top, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not upstream:
        out.append(finding("D-backup.no-upstream", "info",
                           f"the backup repo {top} has no upstream branch",
                           "it was never set up to track a remote, so it may never leave this "
                           "machine", f"git -C {q(top)} branch --set-upstream-to <remote>/<branch>"))
        return out
    ahead = git_out(top, "rev-list", "--count", "@{u}..HEAD")
    last = git_out(top, "log", "-1", "--format=%ct")
    if not (ahead and ahead.isdigit() and last and last.isdigit()) or int(ahead) == 0:
        return out
    hours = (time.time() - int(last)) / 3600
    if hours > UNPUSHED_HOURS:
        out.append(finding("D-backup.unpushed", "warn",
                           f"backup not pushed: {top} is {ahead} commit(s) ahead of "
                           f"{upstream}, and its newest commit is {hours:.0f} h old",
                           "the backup's push has not run or keeps failing (counted from local "
                           "refs; nothing was fetched)",
                           f"run your backup tool's sync, or push {top} by hand"))
    return out


@check("D-backup")
def check_backup(ctx):
    root, hint = ctx["root"], backup_hint()
    if hint is None:
        return [finding("D-backup.none", "warn", "the work record is not backed up: no "
                        "backup_hint is configured", "losing this machine loses the record",
                        "once a backup covers the record dir, set \"backup_hint\" in "
                        "~/.config/100x/work.json (or HUNDREDX_WORK_BACKUP_HINT) to that "
                        "backup's file list")]
    try:
        line = hint_entry(hint, root)
    except OSError:
        return [finding("D-backup.hint-missing", "error",
                        f"the backup hint file {hint} does not exist or cannot be read",
                        "backup_hint points at a moved or deleted file",
                        "point backup_hint in ~/.config/100x/work.json (or "
                        "HUNDREDX_WORK_BACKUP_HINT) at your backup's real file list")]
    out = scan_backup_repo(hint)
    if line is None:
        out.insert(0, finding("D-backup.not-named", "warn",
                              f"{hint} does not name the record dir {root}",
                              "the backup was set up before the record existed, or names a "
                              "different path", f"add this line to {hint}: {home_relative(root)}"
                              " (plus any mode word your backup's other lines use)"))
    else:
        ctx["backup"] = f"{hint}: {line}"
    return out


@check("D-holds")
def check_holds(ctx):
    out, now = [], utc_now()
    for ws in workstreams():
        events, _, _ = read_events(ws)
        view = derive(ws, events)
        for pr, hold in sorted(view["holds"].items()):
            since = parse_at(hold.get("at"))
            if since and age_days(since, now) > HOLD_STALE_DAYS:
                out.append(finding("D-holds.stale", "info",
                                   f"{ws}: #{pr} has been on hold for "
                                   f"{age_days(since, now):.0f} days ({hold.get('reason', '')}); "
                                   "still on hold?", f"held over {HOLD_STALE_DAYS} days ago",
                                   f"if not: 100x work release-hold {pr} --ws {ws}"))
        stamps = [t for t in (parse_at(e.get("at")) for e in events) if t]
        handoffs = [t for t in (parse_at(n.get("at")) for n in view["notes"]
                                if n["type"] == "handoff") if t]
        if not stamps:
            continue
        since = max(handoffs) if handoffs else min(stamps)
        lag = age_days(since, max(stamps))
        if lag > HANDOFF_LAG_DAYS:
            out.append(finding("D-holds.handoff", "info",
                               f"{ws}: the last handoff is {lag:.0f} days older than its newest "
                               "event" if handoffs else
                               f"{ws}: {lag:.0f} days of events and no handoff",
                               "sessions recorded work without leaving a handoff for the next one",
                               f"100x work handoff TEXT --ws {ws}"))
    return out


def run_doctor(cwd):
    ident = cwd_identity(cwd)
    ctx = {"root": record_dir(), "cwd": cwd, "ident": ident,
           "matches": lookup(cwd) if ident else []}
    findings, checks = [], []
    for check_id, fn in CHECKS:
        found = fn(ctx)
        findings += found
        worst = next((s for s in SEVERITIES if any(f["severity"] == s for f in found)), "ok")
        checks.append({"id": check_id, "status": worst})
    findings.sort(key=lambda f: SEVERITIES.index(f["severity"]))
    ok = not any(f["severity"] in FAILING for f in findings)
    return {"ok": ok, "findings": findings, "checks": checks}, ctx


def print_doctor(result, ctx):
    hook = ctx.get("brief_hook") or {}
    matches = ctx["matches"]
    where = (matches[0] if len(matches) == 1 else
             f"{len(matches)} workstreams" if matches else "no workstream")
    gets = "yes" if hook.get("gets_brief") else "no"
    print("100x work doctor (read-only: nothing is written, no network)")
    print(f"  record dir:   {ctx['root']}")
    print(f"  plugin root:  {PLUGIN_ROOT}")
    print(f"  cwd:          {ctx['cwd']} -> {where}")
    print(f"  session brief here: {gets} (hook dry run, {hook.get('seconds', 0)} s)")
    if ctx.get("backup"):
        print(f"  backup:       {ctx['backup']}")
    for f in result["findings"]:
        print(f"\n{f['severity'].upper():5} {f['id']}: {f['what']}")
        print(f"      cause: {f['cause']}")
        print(f"      fix:   {f['fix']}")
    counts = {s: sum(f["severity"] == s for f in result["findings"]) for s in SEVERITIES}
    print("\nchecks: " + ", ".join(f"{c['id']} {c['status']}" for c in result["checks"]))
    print("doctor: " + ("no problems found" if not result["findings"] else
                        ", ".join(f"{n} {s}" for s, n in counts.items() if n)))


def cmd_doctor(args):
    cwd = os.path.abspath(args.cwd or os.getcwd())
    if not os.path.isdir(cwd):
        print(f"100x work doctor: --cwd {cwd!r} is not a directory", file=sys.stderr)
        return 2
    result, ctx = run_doctor(cwd)
    if args.json:
        result["checks"] = [dict(c, **({"gets_brief": ctx["brief_hook"]["gets_brief"]}
                                       if c["id"] == "D-brief" else {}))
                            for c in result["checks"]]
        print(json.dumps(result, indent=1))
    else:
        print_doctor(result, ctx)
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------- CLI

def build_parser():
    ap = argparse.ArgumentParser(prog="100x work", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Nothing is written to any repository; no network.")
    sub = ap.add_subparsers(dest="cmd", metavar="<command>")
    p = sub.add_parser("start", help="create or update a workstream (appends a set event)")
    p.add_argument("ws")
    p.add_argument("--repo", action="append", help="remote URL or host/owner/repo")
    p.add_argument("--pr", action="append", metavar="N:BRANCH:ROLE")
    p.add_argument("--goal")
    p.add_argument("--merge-order", metavar="1,2,3")
    p.add_argument("--convention", action="append")
    p.set_defaults(func=cmd_start)
    for name, kind, label, help_text in (
            ("note", "note", "note", "append a note"),
            ("decide", "decision", "decision", "record a decision"),
            ("handoff", "handoff", "handoff", "leave a handoff for the next session")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("text")
        p.add_argument("--ws")
        if name == "decide":
            p.add_argument("--id")
        p.set_defaults(func=cmd_text_event(kind, label))
    p = sub.add_parser("hold", help="hold a PR (do not push or merge it)")
    p.add_argument("pr", type=int)
    p.add_argument("--reason", required=True)
    p.add_argument("--ws")
    p.set_defaults(func=cmd_hold)
    p = sub.add_parser("release-hold", help="release a PR's hold")
    p.add_argument("pr", type=int)
    p.add_argument("--ws")
    p.set_defaults(func=cmd_release_hold)
    p = sub.add_parser("brief", help="print the workstream brief (markdown)")
    p.add_argument("--ws")
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p.set_defaults(func=cmd_brief)
    sub.add_parser("list", help="list workstreams").set_defaults(func=cmd_list)
    p = sub.add_parser("doctor", help="diagnose the record, lookup, brief hook, installed "
                       "hooks, backup and holds (read-only)")
    p.add_argument("--json", action="store_true", help="print {ok, findings, checks}")
    p.add_argument("--cwd", help="diagnose as if a session started here (default: cwd)")
    p.set_defaults(func=cmd_doctor)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_usage(sys.stderr)
        return 2
    if disabled() and args.cmd != "doctor":
        print("100x work: disabled (HUNDREDX_WORK=off)", file=sys.stderr)
        return 0
    try:
        code = args.func(args)
    except WorkError as err:
        print(f"100x work: {err}", file=sys.stderr)
        return 1
    return code if isinstance(code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
