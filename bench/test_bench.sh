#!/usr/bin/env bash
# Offline self-test for the bench: every scaffold builds, every case parses for
# `claude plugin eval`, and every deterministic grader passes a hand-written good result and
# fails a hand-written bad one (bench/samples/<case>/{good,bad}.sh). No model is called.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fails=0

# Static check of the case files against the schema `claude plugin eval` 2.1.287 enforces
# (allowed prompt.md keys, grader types and per-type keys), so a typo fails here and not
# halfway through a paid run.
python3 - "$here/cases" <<'PY' || fails=$((fails + 1))
import re, sys
from pathlib import Path
PROMPT_KEYS = {"schema_version", "name", "description", "tags", "plugins", "runs", "expected_outcome",
               "model", "max_turns", "timeout_seconds", "allowed_tools", "artifact_publish",
               "growthbook_overrides", "append_system_prompt", "env"}
GRADER_KEYS = {"regex": {"target", "pattern", "flags", "match"}, "tool_used": {"tool", "input_match", "min", "max"},
               "tool_order": {"before", "after"}, "file_exists": {"path", "exists"},
               "llm": {"focus"}, "baseline": {"baseline_file"}}
def keys(path):
    head = path.read_text().split("---")[1]
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^(\w+):\s*(.*)$", head, re.M)}
bad = []
for case in sorted(p for p in Path(sys.argv[1]).iterdir() if p.is_dir()):
    extra = set(keys(case / "prompt.md")) - PROMPT_KEYS
    if extra: bad.append(f"{case.name}/prompt.md: {extra}")
    if not re.search(r"scaffold_script:\s*scaffold.sh", (case / "case.yaml").read_text()):
        bad.append(f"{case.name}/case.yaml: no scaffold_script")
    for grader in sorted((case / "graders").glob("*.md")):
        found = keys(grader)
        kind = found.pop("type", None)
        allowed = GRADER_KEYS.get(kind, set()) | {"name", "weight", "arm"}
        if kind not in GRADER_KEYS or set(found) - allowed:
            bad.append(f"{case.name}/graders/{grader.name}: type={kind} extra={set(found) - allowed}")
print("\n".join(bad) or "case files: ok")
sys.exit(1 if bad else 0)
PY

for case_dir in "$here"/cases/[0-9]*/; do
  case_name="$(basename "$case_dir")"
  for kind in good bad; do
    ws="$work/$case_name-$kind"
    mkdir -p "$ws"
    (cd "$ws" && bash "$case_dir/scaffold.sh")
    text="$work/$case_name-$kind.txt"
    : > "$text"
    (cd "$ws" && BENCH_TEXT="$text" bash "$here/samples/$case_name/$kind.sh")
    result="$(python3 "$here/checks.py" score "$case_name" "$ws" --text "$text")"
    verdict="$(KIND="$kind" python3 -c '
import json, os, sys
r = json.load(sys.stdin)
failed = [k for k, v in r["checks"].items() if not v]
ok = not failed and not r["error"] if os.environ["KIND"] == "good" else bool(failed)
print(("ok" if ok else "FAIL") + "  failed=" + ",".join(failed) + ("  error=" + r["error"] if r["error"] else ""))
' <<<"$result")"
    printf '%-24s %-4s %s\n' "$case_name" "$kind" "$verdict"
    [[ "$verdict" == ok* ]] || fails=$((fails + 1))
  done
done

# compare.py end to end on fake eval output: kept dirs laid out like the harness's
# (<root>/sealed/home/cwd + <root>/out/trace.jsonl), NEW given the good samples, OLD and
# no-plugin the bad ones. NEW must win both scenarios.
fake="$work/fake"
python3 - "$work" "$fake" <<'PY'
import json, shutil, sys
from pathlib import Path
work, fake = Path(sys.argv[1]), Path(sys.argv[2])
docs = {"new": {"cases": []}, "old": {"cases": []}}
for case in ("10-explain-module", "12-over-building"):
    arms = {"new": {"with": [], "without": []}, "old": {"with": []}}
    for doc, key, kind, loaded in (("new", "with", "good", True), ("new", "without", "bad", False),
                                   ("old", "with", "bad", True)):
        root = fake / f"{case}-{doc}-{key}"
        shutil.copytree(work / f"{case}-{kind}", root / "sealed/home/cwd", symlinks=True)
        (root / "out").mkdir()
        init = {"type": "system", "subtype": "init",
                "slash_commands": ["100x:100x"] if loaded else ["simplify"]}
        result = {"type": "result", "result": (work / f"{case}-{kind}.txt").read_text()}
        (root / "out/trace.jsonl").write_text(json.dumps(init) + "\n" + json.dumps(result) + "\n")
        grader = {"name": "g", "passed": kind == "good", "weight": 1, "scored": True}
        arms[doc][key].append({"tracePath": str(root / "out/trace.jsonl"), "costUsd": 0.5,
                               "error": None, "graders": [grader]})
    for doc in docs:
        docs[doc]["cases"].append({"name": case, "arms": arms[doc]})
for doc, body in docs.items():
    (fake / f"{doc}.json").write_text(json.dumps(body))
PY
summary="$(python3 "$here/compare.py" --new "$fake/new.json" --old "$fake/old.json")"
echo "$summary"
if grep -q "new vs old: new better in 2, worse in 0" <<<"$summary" \
   && grep -q "plugin-load mismatches 0" <<<"$summary" \
   && ! grep -q WARNING <<<"$summary"; then
  echo "compare.py: ok"
else
  echo "compare.py: FAIL"; fails=$((fails + 1))
fi

if [[ $fails -gt 0 ]]; then
  echo "test_bench: $fails failure(s)"
  exit 1
fi
echo "test_bench: all graders discriminate"
