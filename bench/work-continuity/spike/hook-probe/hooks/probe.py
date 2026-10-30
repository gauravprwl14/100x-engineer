"""Phase 0 probe hook. `prompt` injects a marker as additional context; `end` records that
SessionEnd fired. Writes only to $WORK_PROBE_LOG (default: a file in the system temp dir)."""
import json, os, sys, tempfile, time

log = os.environ.get("WORK_PROBE_LOG") or os.path.join(tempfile.gettempdir(), "work-hook-probe.log")
payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
with open(log, "a") as f:
    f.write(json.dumps({"t": time.time(), "mode": sys.argv[1], "event": payload.get("hook_event_name"),
                        "reason": payload.get("reason")}) + "\n")
if sys.argv[1] == "prompt":
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": "work-probe marker: PROBE-7731"}}))
