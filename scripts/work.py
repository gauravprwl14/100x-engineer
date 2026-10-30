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
    100x work doctor

Without --ws, the workstream is the one whose repos and PR branches match the current
directory's `origin` remote and branch.

Environment: HUNDREDX_WORK_DIR (record dir, default ~/.config/100x/work),
HUNDREDX_WORK=off (disable every command and hook), HUNDREDX_WORK_BACKUP_HINT (a file
naming the record dir when a backup covers it; default: claude-setup's mirrors.txt).

Exit codes: 0 ok, 1 refused or not found (nothing written), 2 usage error.
Python stdlib only.
"""
import argparse, datetime, json, os, pathlib, re, secrets, subprocess, sys
import urllib.parse

SCHEMA = 1
EVENT_TYPES = ("set", "note", "decision", "hold", "release-hold", "handoff")
DIR_MODE = 0o700
FILE_MODE = 0o600
DEFAULT_DIR_REL = (".config", "100x", "work")
# Default backup hint: the owner's claude-setup lists mirrored folders here (ADR-0006 A2).
# Anyone else points HUNDREDX_WORK_BACKUP_HINT at their own tool's list.
DEFAULT_BACKUP_HINT_REL = ("Sites", "projects", "rnd", "claude-setup", "mirrors.txt")
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
    notes = view["notes"][-BRIEF_RECENT:]
    decisions = list(view["decisions"].values())
    dropped = len(view["notes"]) - len(notes)
    while True:
        text = brief_text(view, notes, decisions, dropped, newer)
        if len(text) / CHARS_PER_TOKEN <= max_tokens:
            return text
        if notes:
            notes = notes[1:]
            dropped += 1
        elif decisions:
            decisions = decisions[1:]
        else:
            return text


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
    env = os.environ.get("HUNDREDX_WORK_BACKUP_HINT")
    return pathlib.Path(env).expanduser() if env else \
        pathlib.Path.home().joinpath(*DEFAULT_BACKUP_HINT_REL)


def backup_line(root):
    """(hint file, line) when a line of the hint file starts with the record dir, given
    home-relative or absolute; None otherwise."""
    hint = backup_hint()
    names = {str(root)}
    home = pathlib.Path.home()
    if home in root.parents:
        names.add(str(root.relative_to(home)))
    try:
        lines = hint.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        words = line.split()
        if words and words[0].rstrip("/") in names:
            return hint, line.strip()
    return None


def cmd_doctor(_args):
    root = record_dir()
    print(f"record dir: {root}")
    if disabled():
        print("HUNDREDX_WORK=off: every command and hook is disabled")
    if not root.is_dir():
        print("  not created yet (`100x work start` creates it)")
    else:
        mode = root.stat().st_mode & 0o777
        print(f"  mode {mode:o}" + ("" if mode & 0o077 == 0 else
                                    "  WARNING: readable by other users; chmod 700 it"))
        for ws in workstreams():
            events, unreadable, newer = read_events(ws)
            extra = "".join([f", {unreadable} unreadable" if unreadable else "",
                             f", {newer} newer-schema" if newer else ""])
            print(f"  {ws}: {len(events)} events{extra}")
    found = backup_line(root)
    if found:
        print(f"backup: {found[0]} names it ({found[1]})")
    else:
        print(f"WARNING not backed up: {backup_hint()} does not name {root}. Losing this "
              "machine loses the record; set HUNDREDX_WORK_BACKUP_HINT to your backup's "
              "folder list once one covers it.")


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
    sub.add_parser("doctor", help="record dir, counts, backup status").set_defaults(func=cmd_doctor)
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
        args.func(args)
    except WorkError as err:
        print(f"100x work: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
