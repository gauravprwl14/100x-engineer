#!/usr/bin/env python3
"""Stop / SubagentStop hook: one skeptical second pass on a substantive turn.

Blind A/B runs found that a second pass catches real defects the first answer missed
(skills/recheck/references/evidence.md), so when a turn edited files or ended in a long
answer, the stop is blocked once with the re-check prompt as the reason. The prompt is
read from skills/recheck/references/recheck-prompt.md, its single source.

It never loops: with stop_hook_active (any Stop hook already blocked this stop) it lets
the stop through. It reads only the tail of the transcript and the prompt file, writes
nothing and runs no subprocess. Fails open on any error, because a Stop hook that
crashes would wedge every session.

Mode: env HUNDREDX_RECHECK (auto|manual|off) overrides ~/.config/100x/recheck.json
{"mode": ..., "min_chars": ..., "subagents": ...}; defaults auto and 1500. manual and off
never block a Stop. SubagentStop is opt-in: "subagents" is "off" (default), "all", or a
list of agent types, overridden by env HUNDREDX_RECHECK_SUBAGENTS (off, all, or a comma
list); mode "off" disables it too.
"""
import json, os, pathlib, re, sys

MODES = ("auto", "manual", "off")
DEFAULT_MODE = "auto"
DEFAULT_MIN_CHARS = 1500
CONFIG_REL = (".config", "100x", "recheck.json")
# SubagentStop documents agent_type; the others are read defensively in case a host
# version names it differently.
AGENT_TYPE_KEYS = ("agent_type", "agentType", "subagent_type", "agent_name")
TAIL_BYTES = 2 * 1024 * 1024
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
# A Bash command that changes files counts as an edit too: in-place editors, tee, git
# commits, Python file writes, and output redirected to a path (not /dev/null or an fd).
BASH_WRITE = re.compile(
    r"\b(?:sed|perl)\s+-i|\btee\b|\bgit\s+(?:commit|apply|am)\b|\.write_text\(|"
    r"open\([^)]*['\"][wa]b?['\"]|(?<![0-9&])>>?\s*(?!&|/dev/null)[\w./~$\"'-]")
PROMPT_REL = ("skills", "recheck", "references", "recheck-prompt.md")
START, END = "<!-- recheck-prompt:start -->", "<!-- recheck-prompt:end -->"
# A turn that already asked for the re-check: the user typed the command (matched only in
# their own text, so another skill's body naming it does not count) or the prompt is present.
COMMAND = re.compile(r"/(?:100x:)?recheck\b", re.I)
PROMPT_MARK = re.compile(r"assume this answer still has at least one mistake", re.I)
DONE_LINE = re.compile(r"^[\s>*_`]*Re-check:", re.M)


def subagent_setting(value):
    """"off" | "all" | a set of agent types; None when the value is not understood."""
    if isinstance(value, str):
        v = value.strip()
        if v.lower() in ("off", "all"):
            return v.lower()
        value = v.split(",")
    if isinstance(value, list):
        names = {n.strip() for n in value if isinstance(n, str) and n.strip()}
        return names or "off"
    return None


def config():
    mode, min_chars, subagents = DEFAULT_MODE, DEFAULT_MIN_CHARS, "off"
    try:
        cfg = json.loads(pathlib.Path.home().joinpath(*CONFIG_REL).read_text())
    except (OSError, ValueError):
        cfg = {}
    if isinstance(cfg, dict):
        if cfg.get("mode") in MODES:
            mode = cfg["mode"]
        n = cfg.get("min_chars")
        if isinstance(n, int) and not isinstance(n, bool) and n > 0:
            min_chars = n
        subagents = subagent_setting(cfg.get("subagents")) or subagents
    env = os.environ.get("HUNDREDX_RECHECK", "").strip().lower()
    if env in MODES:
        mode = env
    env_sub = os.environ.get("HUNDREDX_RECHECK_SUBAGENTS")
    if env_sub and env_sub.strip():
        subagents = subagent_setting(env_sub) or subagents
    return mode, min_chars, subagents


def prompt_text():
    roots = [os.environ.get("CLAUDE_PLUGIN_ROOT"),
             str(pathlib.Path(__file__).resolve().parent.parent)]
    for root in filter(None, roots):
        try:
            text = pathlib.Path(root, *PROMPT_REL).read_text(encoding="utf-8")
        except OSError:
            continue
        if START in text and END in text:
            body = text.split(START, 1)[1].split(END, 1)[0]
            lines = [l for l in body.strip().splitlines() if not l.startswith("```")]
            if lines:
                return "\n".join(lines).strip()
    return None


def tail_entries(path, keep):
    """Transcript entries passing keep(), newest first, from the last TAIL_BYTES of the file."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read()
    lines = data.split(b"\n")
    if size > TAIL_BYTES:
        lines = lines[1:]            # the first line was cut mid-entry
    for raw in reversed(lines):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if isinstance(entry, dict) and keep(entry):
            yield entry


def blocks(entry):
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def current_turn(path, keep):
    """Entries after the last real user prompt (oldest first), and whether it asked to re-check.

    A real prompt is a user entry that carries no tool_result and is not isMeta (skill
    bodies, command caveats); those belong to the turn they appear in.
    """
    turn, asked = [], False
    for e in tail_entries(path, keep):
        if e.get("type") == "user":
            bs = blocks(e)
            text = "\n".join(b.get("text") or "" for b in bs if b.get("type") == "text")
            asked = asked or bool(PROMPT_MARK.search(text))
            if not e.get("isMeta") and not any(b.get("type") == "tool_result" for b in bs):
                return list(reversed(turn)), asked or bool(COMMAND.search(text))
        turn.append(e)
    return list(reversed(turn)), asked


def scan(turn):
    """(edited a file?, final assistant text, recheck skill already ran?) for the turn."""
    edited, final = False, []
    for e in turn:
        if e.get("type") == "user":
            final = []               # a tool result: the answer after it is the final one
            continue
        if e.get("type") != "assistant":
            continue
        for b in blocks(e):
            if b.get("type") == "tool_use":
                if b.get("name") == "Skill" and COMMAND.search(
                        "/" + str((b.get("input") or {}).get("skill", ""))):
                    return edited, "", True
                edited = edited or b.get("name") in EDIT_TOOLS or (
                    b.get("name") == "Bash" and bool(BASH_WRITE.search(
                        str((b.get("input") or {}).get("command", "")))))
                final = []
            elif b.get("type") == "text":
                final.append(b.get("text") or "")
    return edited, "\n".join(final), False


def is_file(p):
    return isinstance(p, str) and bool(p) and os.path.isfile(p)


def main_transcript(payload):
    """The main session's transcript; subagent (sidechain) entries are not its turn."""
    path = payload.get("transcript_path")
    return (path, lambda e: not e.get("isSidechain")) if is_file(path) else (None, None)


def subagent_transcript(payload):
    """The stopping subagent's transcript, and its agent type when one can be found.

    Order: agent_transcript_path if given; <session>/subagents/agent-<agent_id>.jsonl
    beside the main transcript (the on-disk layout Claude Code writes); else the main
    transcript, keeping only that agent's sidechain entries.
    """
    agent_id = payload.get("agent_id")
    agent_type = next((payload[k] for k in AGENT_TYPE_KEYS
                       if isinstance(payload.get(k), str) and payload[k]), None)
    main = payload.get("transcript_path")
    derived = None
    if is_file(main) and isinstance(agent_id, str) and re.fullmatch(r"[\w-]+", agent_id):
        derived = pathlib.Path(main).with_suffix("") / "subagents" / f"agent-{agent_id}.jsonl"
        if agent_type is None:
            try:
                meta = json.loads(derived.with_suffix(".meta.json").read_text())
                agent_type = meta.get("agentType") if isinstance(meta, dict) else None
            except (OSError, ValueError):
                pass
    if is_file(payload.get("agent_transcript_path")):
        return payload["agent_transcript_path"], (lambda e: True), agent_type
    if derived is not None and derived.is_file():
        return str(derived), (lambda e: True), agent_type
    if is_file(main):
        def mine(e):
            return bool(e.get("isSidechain")) and e.get("agentId") in (None, agent_id)
        return main, mine, agent_type
    return None, None, agent_type


def allowed(subagents, agent_type):
    if subagents == "all":
        return True
    if not isinstance(subagents, set) or not isinstance(agent_type, str):
        return False
    return agent_type in subagents or agent_type.split(":")[-1] in subagents


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return {}
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return {}
    mode, min_chars, subagents = config()
    if payload.get("hook_event_name") == "SubagentStop":
        if mode == "off" or subagents == "off":
            return {}
        path, keep, agent_type = subagent_transcript(payload)
        if not allowed(subagents, agent_type):
            return {}
    else:
        if mode != "auto":
            return {}
        path, keep = main_transcript(payload)
    if path is None:
        return {}
    turn, asked = current_turn(path, keep)
    if asked:
        return {}
    edited, final, ran = scan(turn)
    if ran:
        return {}
    # The transcript is written asynchronously and can lag the turn's last message; the
    # host passes that message directly, so it decides the length and Re-check: tests.
    last = payload.get("last_assistant_message")
    if isinstance(last, str) and last.strip():
        final = last
    if not (edited or len(final.strip()) >= min_chars) or DONE_LINE.search(final):
        return {}
    reason = prompt_text()
    return {"decision": "block", "reason": reason} if reason else {}


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception:  # fail-open: a Stop hook that crashes would wedge every session
        print(json.dumps({}))
    sys.exit(0)
