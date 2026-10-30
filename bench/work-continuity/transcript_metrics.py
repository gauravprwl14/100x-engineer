#!/usr/bin/env python3
"""Measure work-continuity metrics (PRD M1, M3, M4) from Claude Code session transcripts.

Reads one or more main-session transcripts (<session>.jsonl) and, when present, their
subagent transcripts (<session>/subagents/*.jsonl). Prints a markdown table, or JSON with
--json. Read-only; stdlib only.

    python3 transcript_metrics.py ~/.claude/projects/<proj>/<session>.jsonl [...] [--json]
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

# Prompt categories counted per 100 human prompts. Generic phrasings, overridable with --patterns.
DEFAULT_PATTERNS = {
    "restated_ownership": r"respective (branch|pr)|wrong branch|keep (them|it|the \w+) separate|integration worktree|this session is (focus|about)",
    "status_asks": r"what is the status|status \?|status\?|what is pending|is everything (fixed|pushed|done)",
    "confusion": r"(don'?t|do not|not able to) understand|explain it",
    "approval_only": r"^\s*(go ahead|go with your recommendations?|agreed|yes|ok(ay)?)\b[\s.!,]*$",
}
COMPACTION_MARK = "This session is being continued from a previous conversation"


def human_prompt(entry):
    """The text of a prompt the human typed, or None for tool results, meta and sidechains."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            return None
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(texts) if texts else None
    return None


def scan(path):
    """Token totals (deduplicated by message id), prompts, compactions and agent launches."""
    out = {"tokens": 0, "prompts": [], "compactions": 0, "agent_types": collections.Counter()}
    seen = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
                out["compactions"] += 1
            message = entry.get("message") or {}
            if entry.get("type") == "assistant" and message.get("id") not in seen:
                seen.add(message.get("id"))
                usage = message.get("usage") or {}
                out["tokens"] += sum(usage.get(k, 0) for k in (
                    "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if entry.get("type") == "assistant":
                for c in message.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in ("Agent", "Task"):
                        out["agent_types"][(c.get("input") or {}).get("subagent_type") or "default"] += 1
            text = human_prompt(entry)
            if text is None or text.startswith("<"):
                continue
            if not text.startswith(COMPACTION_MARK):  # the summary is injected as a user turn
                out["prompts"].append(text)
    return out


def subagent_tokens(session_path):
    """Tokens per subagent type, from <session>/subagents/*.jsonl and their .meta.json."""
    by_type = collections.Counter()
    folder = session_path.with_suffix("") / "subagents"
    for transcript in sorted(folder.glob("*.jsonl")):
        try:
            agent_type = json.loads(transcript.with_suffix(".meta.json").read_text()).get("agentType", "unknown")
        except (OSError, ValueError):
            agent_type = "unknown"
        by_type[agent_type] += scan(transcript)["tokens"]
    return by_type


def measure(session_path, patterns):
    main = scan(session_path)
    subs = subagent_tokens(session_path)
    prompts = main["prompts"]
    counts = {name: sum(1 for p in prompts if re.search(rx, p, re.I | re.M)) for name, rx in patterns.items()}
    total = main["tokens"] + sum(subs.values())
    per100 = lambda n: round(100 * n / len(prompts), 1) if prompts else 0.0
    return {
        "session": session_path.stem,
        "prompts": len(prompts),
        "compactions": main["compactions"],
        "tokens_main": main["tokens"],
        "tokens_subagents": sum(subs.values()),
        "fork_token_share": round(subs.get("fork", 0) / total, 3) if total else 0.0,
        "agents_launched": sum(main["agent_types"].values()),
        "counts": counts,
        "per_100_prompts": {k: per100(v) for k, v in counts.items()},
        # PRD M1: restated ownership + status asks per 100 prompts
        "m1_restated_per_100": per100(counts.get("restated_ownership", 0) + counts.get("status_asks", 0)),
    }


def table(rows):
    fmt = lambda n: f"{n / 1e9:.2f} B" if n >= 1e8 else f"{n / 1e6:.1f} M"
    lines = ["| session | prompts | compactions | tokens main / sub | fork share | M1 per 100 | confusion per 100 | approval-only per 100 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['session'][:8]} | {r['prompts']} | {r['compactions']} | {fmt(r['tokens_main'])} / "
                     f"{fmt(r['tokens_subagents'])} | {r['fork_token_share']:.0%} | {r['m1_restated_per_100']} | "
                     f"{r['per_100_prompts'].get('confusion', 0)} | {r['per_100_prompts'].get('approval_only', 0)} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("transcripts", nargs="+", type=Path)
    ap.add_argument("--patterns", type=Path, help="JSON object {category: regex} replacing the defaults")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    patterns = json.loads(args.patterns.read_text()) if args.patterns else DEFAULT_PATTERNS
    missing = [str(p) for p in args.transcripts if not p.is_file()]
    if missing:
        print("not found: " + ", ".join(missing), file=sys.stderr)
        return 2
    rows = [measure(p, patterns) for p in args.transcripts]
    print(json.dumps(rows, indent=2) if args.json else table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
