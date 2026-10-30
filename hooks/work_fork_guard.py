#!/usr/bin/env python3
"""PreToolUse (Agent|Task): steer away from forking a session that has been summarised.

A fork copies the parent's whole conversation into each helper. After a compaction that
copy is a lossy summary plus everything since, and in one measured session forks took
about 46% of all tokens (prds/work-continuity/prd.md §1). A fresh agent given
`100x work brief` and a task card starts smaller and from the recorded facts instead.

Acts only when tool_input.subagent_type is "fork" and the transcript holds a compaction
boundary. Policy: env HUNDREDX_FORK_POLICY, else ~/.config/100x/work.json "fork_policy",
else warn. allow: nothing. warn: the fork runs, with context telling the agent to brief
a fresh agent next time. refuse: exit 2 with the message on stderr, which blocks the
call. Any other payload, HUNDREDX_WORK=off, or any error: allow silently.
Reads the transcript and the config file only; writes nothing, runs no subprocess.
"""
import json, os, pathlib, re, sys

POLICIES = ("allow", "warn", "refuse")
DEFAULT_POLICY = "warn"
CONFIG_REL = (".config", "100x", "work.json")
AGENT_TOOLS = {"Agent", "Task"}
COMPACT = re.compile(rb'"subtype"\s*:\s*"compact_boundary"')
CHUNK = 1 << 20
OVERLAP = 64               # longer than the marker, so a match split across chunks is seen
MESSAGE = ("100x work: this session has been summarised (compacted), so a fork would copy "
           "a lossy summary of it into the helper. Start a fresh agent instead and brief it "
           "with `100x work brief` plus a task card (goal, owned files, worktree, verify "
           "commands). Set fork_policy in ~/.config/100x/work.json to allow, warn or refuse.")


def policy():
    env = (os.environ.get("HUNDREDX_FORK_POLICY") or "").strip().lower()
    if env in POLICIES:
        return env
    try:
        conf = json.loads(pathlib.Path.home().joinpath(*CONFIG_REL).read_text())
        value = str(conf.get("fork_policy", "")).strip().lower()
    except (OSError, ValueError, AttributeError):
        return DEFAULT_POLICY
    return value if value in POLICIES else DEFAULT_POLICY


def compacted(transcript):
    """True once the transcript contains a compaction boundary; stops at the first one."""
    tail = b""
    with open(transcript, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                return False
            if COMPACT.search(tail + chunk):
                return True
            tail = chunk[-OVERLAP:]


def evaluate_fork(payload):
    """(exit code, stdout object or None, stderr text or None)."""
    if os.environ.get("HUNDREDX_WORK", "").strip().lower() == "off":
        return 0, None, None
    if not isinstance(payload, dict) or payload.get("tool_name") not in AGENT_TOOLS:
        return 0, None, None
    tool_input = payload.get("tool_input")
    transcript = payload.get("transcript_path")
    if not isinstance(tool_input, dict) or tool_input.get("subagent_type") != "fork" \
            or not isinstance(transcript, str) or not compacted(transcript):
        return 0, None, None
    mode = policy()
    if mode == "refuse":
        return 2, None, MESSAGE
    if mode == "warn":
        return 0, {"systemMessage": MESSAGE,
                   "hookSpecificOutput": {"hookEventName": "PreToolUse",
                                          "additionalContext": MESSAGE}}, None
    return 0, None, None


if __name__ == "__main__":
    try:
        code, out, err = evaluate_fork(json.loads(sys.stdin.read()))
    except Exception:  # fail-open: a broken guard must never stop the agent tool
        code, out, err = 0, None, None
    if out:
        print(json.dumps(out))
    if err:
        print(err, file=sys.stderr)
    sys.exit(code)
