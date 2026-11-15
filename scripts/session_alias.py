#!/usr/bin/env python3
"""Give the current Claude Code session a memorable name, list the names, and turn a
name back into the command that resumes that session.

The store is one JSON file, ~/.claude/session-aliases.json, in the format ecc's
`sessions` skill used (`{"version": "1.0", "aliases": {name: entry}}`), so names
created before this tool existed keep resolving. A new entry carries the full session
id and the folder the session ran in. An old ecc entry only points at a summary file
named `YYYY-MM-DD-<last 8 hex of the id>-session.tmp`; it resolves by finding the
transcript whose id ends in those 8 characters.

Transcripts are found under the same `projects` folders `session_find` searches
(~/.claude/projects and ~/.cc-1/projects, or --roots).

    session_alias.py set gaurav-pr-1720-reactions-backend
    session_alias.py list
    session_alias.py resolve gaurav-pr-1720-reactions-backend

Exit codes: 0 done; 1 the name is taken by another session, or does not resolve;
2 usage or environment error (bad name, no session id, no transcript).

Python stdlib only.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from session_find import resolve_roots

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")
LEGACY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-([0-9a-f]{8})-session\.tmp$")
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_store():
    return Path.home() / ".claude" / "session-aliases.json"


def load(store):
    try:
        data = json.loads(store.read_text())
    except FileNotFoundError:
        data = {}
    data.setdefault("version", "1.0")
    data.setdefault("aliases", {})
    return data


def save(store, data):
    data["metadata"] = {**data.get("metadata", {}), "totalCount": len(data["aliases"]), "lastUpdated": now()}
    store.parent.mkdir(parents=True, exist_ok=True)
    # Write then rename, so a crash mid-write never leaves a truncated store that
    # loses every other alias.
    tmp = store.with_name(store.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, store)


def transcripts(roots, id_suffix):
    hits = [p for root in roots for p in root.glob(f"*/*{id_suffix}.jsonl")]
    return sorted(hits, key=lambda p: p.stat().st_mtime, reverse=True)


def session_cwd(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and isinstance(record.get("cwd"), str) and record["cwd"]:
                return record["cwd"]
    return None


def resolve_entry(roots, entry):
    """Return (session_id, transcript) or (None, reason)."""
    sid = entry.get("sessionId")
    if not sid:
        m = LEGACY_RE.match(Path(entry.get("sessionPath") or "").name)
        if not m:
            return None, f"unrecognised sessionPath {entry.get('sessionPath')!r}"
        sid = m.group(1)
    hits = transcripts(roots, sid)
    if not hits:
        return None, f"no transcript ends in {sid}"
    return hits[0].stem, hits[0]


def cmd_set(store, roots, name):
    if not NAME_RE.match(name):
        print(f"session_alias: alias must be 2-80 lowercase letters, digits and dashes: {name!r}", file=sys.stderr)
        return 2
    sid = os.environ.get(SESSION_ENV)
    if not sid:
        print(f"session_alias: {SESSION_ENV} is not set in this environment", file=sys.stderr)
        return 2
    hits = transcripts(roots, sid)
    if not hits:
        print(f"session_alias: no transcript found for session {sid}", file=sys.stderr)
        return 2
    data = load(store)
    old = data["aliases"].get(name)
    if old:
        old_sid, _ = resolve_entry(roots, old)
        if old_sid == sid:
            print(f"Already aliased as: {name}")
            return 0
        print(f'COLLISION: "{name}" already points at a different session; pick another name (e.g. add -2)')
        return 1
    stamp = now()
    data["aliases"][name] = {
        "sessionPath": str(hits[0]),
        "sessionId": sid,
        "cwd": session_cwd(hits[0]),
        "createdAt": stamp,
        "updatedAt": stamp,
        "title": None,
    }
    save(store, data)
    print(f"Alias created: {name} -> {sid}")
    return 0


def cmd_list(store, roots):
    entries = load(store)["aliases"].items()
    for name, entry in sorted(entries, key=lambda kv: kv[1].get("updatedAt") or kv[1].get("createdAt") or "", reverse=True):
        sid, where = resolve_entry(roots, entry)
        print(f"{name:<55} {sid or f'UNRESOLVED ({where})'}")
    return 0


def cmd_resolve(store, roots, name):
    entry = load(store)["aliases"].get(name)
    if not entry:
        print(f"session_alias: no alias named {name!r}", file=sys.stderr)
        return 1
    sid, path = resolve_entry(roots, entry)
    if not sid:
        print(f"session_alias: {path}", file=sys.stderr)
        return 1
    cwd = entry.get("cwd") or session_cwd(path)
    # A session from any home other than ~/.claude only resumes with that home's
    # config dir; `claude --resume` alone would report "no conversation found".
    home = path.parent.parent.parent
    env = "" if home == Path.home() / ".claude" else f"CLAUDE_CONFIG_DIR={home} "
    print(f"session:    {sid}")
    print(f"transcript: {path}")
    print(f"resume:     cd {cwd} && {env}claude --resume {sid}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="session_alias", description="Name, list and resolve Claude Code sessions.")
    parser.add_argument("--store", help="alias file (default: ~/.claude/session-aliases.json)")
    parser.add_argument(
        "--roots",
        help="comma-separated 'projects' directories holding transcripts "
        "(default: ~/.claude/projects, ~/.cc-1/projects — whichever exist)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("set", help=f"alias the current session (${SESSION_ENV})").add_argument("name")
    sub.add_parser("list", help="every alias, newest first")
    sub.add_parser("resolve", help="print the folder and the claude --resume command").add_argument("name")
    args = parser.parse_args(argv)

    store = Path(args.store).expanduser() if args.store else default_store()
    roots = resolve_roots(args.roots)
    if not roots:
        print("session_alias: no session directory found", file=sys.stderr)
        return 2
    if args.command == "set":
        return cmd_set(store, roots, args.name)
    if args.command == "list":
        return cmd_list(store, roots)
    return cmd_resolve(store, roots, args.name)


if __name__ == "__main__":
    sys.exit(main())
