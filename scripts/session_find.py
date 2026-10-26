#!/usr/bin/env python3
"""Find which past Claude Code session touched a topic, so it can be resumed
instead of redone.

Work on one feature is routinely split across several sessions and worktrees
(design, backend PR, frontend PR, integration test, review pass), and weeks
later there is no way to find which session(s) did it short of grepping raw
transcripts by hand. This searches every session transcript under one or more
Claude Code home directories (by default ~/.claude and ~/.cc-1, the two home
directories this user actually runs) and ranks the sessions that mention a
topic by how recently they were touched.

A session is one `<uuid>.jsonl` file under `<home>/projects/<project-dir>/`.
Each line is a JSON record; only `user` and `assistant` turns are searched —
hook output, mode/permission records and other bookkeeping lines are skipped
so a tool name or path that happens to appear in plumbing never counts as a
hit (SKILL.md Failure modes, "hook noise" case). Matching is a cheap raw
substring check before any JSON parsing, so scanning stays fast even across
a large, long-lived `~/.claude/projects` corpus.

    session_find.py "tagging module"
    session_find.py "PR 1471" --limit 5
    session_find.py refund --json
    session_find.py refund --roots /tmp/fixture-a/projects,/tmp/fixture-b/projects

Python stdlib only.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOME_DIRS = (".claude", ".cc-1")
SEARCHABLE_TYPES = {"user", "assistant"}


def extract_text(message):
    """Pull the human-readable text out of a user/assistant `message` field.

    `content` is a plain string for a typed user turn, or a list of blocks
    (text/thinking/tool_use/tool_result/image) for an assistant turn or a
    pasted/tool-result user turn. Only `text` blocks are read; thinking and
    tool_use blocks are not prose and would just add JSON noise to a snippet.
    """
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts)
    return ""


def make_snippet(text, query, width=140):
    text = " ".join(text.split())
    if not text:
        return ""
    idx = text.lower().find(query.lower())
    if idx == -1:
        return text[:width]
    start = max(0, idx - 40)
    end = min(len(text), idx + len(query) + 80)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def search_session(path, root_label, query, case_sensitive):
    """Return a match record for one session file, or None if it has no hit.

    Malformed lines and unreadable files are skipped rather than raised —
    a corrupt or half-written transcript must not abort the whole search.
    """
    needle = query if case_sensitive else query.lower()
    hits = 0
    cwd = None
    snippet = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                haystack = line if case_sensitive else line.lower()
                if needle not in haystack:
                    continue
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(record, dict) or record.get("type") not in SEARCHABLE_TYPES:
                    continue
                hits += 1
                record_cwd = record.get("cwd")
                if isinstance(record_cwd, str) and record_cwd:
                    cwd = record_cwd
                if snippet is None:
                    text = extract_text(record.get("message") or {})
                    snippet = make_snippet(text, query)
    except OSError:
        return None
    if hits == 0:
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return {
        "session_id": path.stem,
        "root": root_label,
        "project_dir": path.parent.name,
        "cwd": cwd,
        "hits": hits,
        "mtime": mtime,
        "last_activity": datetime.fromtimestamp(mtime, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "path": str(path),
        "snippet": snippet or "",
    }


def iter_sessions(root):
    for project_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for session_file in sorted(project_dir.glob("*.jsonl")):
            yield session_file


def resolve_roots(roots_arg):
    if roots_arg:
        candidates = [Path(r).expanduser() for r in roots_arg.split(",") if r.strip()]
    else:
        candidates = [Path.home() / home_dir / "projects" for home_dir in DEFAULT_HOME_DIRS]
    return [r for r in candidates if r.is_dir()]


def run(query, roots_arg, limit, case_sensitive):
    roots = resolve_roots(roots_arg)
    if not roots:
        return None, "no session directory found (checked: {})".format(
            roots_arg or ", ".join(f"~/{d}/projects" for d in DEFAULT_HOME_DIRS)
        )
    results = []
    for root in roots:
        root_label = root.parent.name or root.name
        for session_file in iter_sessions(root):
            record = search_session(session_file, root_label, query, case_sensitive)
            if record:
                results.append(record)
    results.sort(key=lambda r: r["mtime"], reverse=True)
    if limit:
        results = results[:limit]
    return results, None


def print_table(results):
    if not results:
        print("No sessions found.")
        return
    for record in results:
        scope = record["cwd"] or record["project_dir"]
        print(
            f"{record['session_id']}  [{record['root']}]  {scope}  "
            f"last={record['last_activity']}  hits={record['hits']}"
        )
        if record["snippet"]:
            print(f"    {record['snippet']}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="session_find",
        description="Search past Claude Code session transcripts by keyword; rank matches by recency.",
    )
    parser.add_argument("query", help="keyword or phrase to search for (case-insensitive by default)")
    parser.add_argument(
        "--roots",
        help="comma-separated 'projects' directories to search "
        "(default: ~/.claude/projects, ~/.cc-1/projects — whichever exist)",
    )
    parser.add_argument("--limit", type=int, default=20, help="max sessions to return (default: 20, 0 = no limit)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--case-sensitive", action="store_true")
    args = parser.parse_args(argv)

    if not args.query.strip():
        parser.error("query must not be empty")

    results, error = run(args.query, args.roots, args.limit, args.case_sensitive)
    if error:
        print(f"session_find: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_table(results)

    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
