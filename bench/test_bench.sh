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

# Besides good.sh and bad.sh, a sample may declare what it must score in its first lines:
# `# expect: pass`, or `# expect: fail=a,b` (exactly those checks fail). Review fixes add
# one for each input that was once mis-scored.
for case_dir in "$here"/cases/[0-9]*/; do
  case_name="$(basename "$case_dir")"
  extras=()
  for sample in "$here/samples/$case_name"/*.sh; do
    [[ "$(basename "$sample" .sh)" == good || "$(basename "$sample" .sh)" == bad ]] || extras+=("$(basename "$sample" .sh)")
  done
  for kind in good bad ${extras[@]+"${extras[@]}"}; do
    ws="$work/$case_name-$kind"
    mkdir -p "$ws"
    (cd "$ws" && bash "$case_dir/scaffold.sh")
    # screen-patterns/AC-10: the screen cases (13-15) need no git, inside or outside the agent.
    if [[ "$case_name" == 1[3-5]-* ]] && { [[ -e "$ws/.git" ]] \
        || grep -vE '^\s*#' "$case_dir/scaffold.sh" | grep -qE '\bgit\b|git_init|commit_all'; }; then
      echo "$case_name: scaffold uses git"; fails=$((fails + 1))
    fi
    text="$work/$case_name-$kind.txt"
    : > "$text"
    (cd "$ws" && BENCH_TEXT="$text" bash "$here/samples/$case_name/$kind.sh")
    result="$(python3 "$here/checks.py" score "$case_name" "$ws" --text "$text")"
    expect="$(sed -n 's/^# expect: //p' "$here/samples/$case_name/$kind.sh" | head -1)"
    verdict="$(KIND="$kind" EXPECT="$expect" python3 -c '
import json, os, sys
r = json.load(sys.stdin)
failed = [k for k, v in r["checks"].items() if not v]
kind, expect = os.environ["KIND"], os.environ["EXPECT"]
if expect == "pass" or kind == "good":
    ok = not failed and not r["error"]
elif expect.startswith("fail="):
    ok = not r["error"] and sorted(failed) == sorted(expect[5:].split(","))
else:
    ok = bool(failed)
print(("ok" if ok else "FAIL") + "  failed=" + ",".join(failed) + ("  error=" + r["error"] if r["error"] else ""))
' <<<"$result")"
    printf '%-24s %-4s %s\n' "$case_name" "$kind" "$verdict"
    [[ "$verdict" == ok* ]] || fails=$((fails + 1))
  done
done

# screen-patterns/AC-10: case 15's PR.diff turns case 13's fixture (the PR base) into the
# head files case 15 puts on disk, so the agent reads a diff that matches the code.
pr="$work/pr-base"
cp -R "$here/cases/13-settings-screen-build/fixture" "$pr"
if (cd "$pr" && patch -p1 -s < "$here/cases/15-review-settings-diff/fixture/PR.diff") \
   && diff -r -x __pycache__ -x PR.diff -x PR.md -x REVIEW.md "$pr" "$work/15-review-settings-diff-good" >/dev/null; then
  echo "15 PR.diff: ok"
else
  echo "15 PR.diff: FAIL (does not match the head files)"; fails=$((fails + 1))
fi

# screen-patterns/AC-11: --old-ref is resolved before the cost warning and before any session.
old_main="$(git -C "$here/.." rev-parse --verify --quiet 'main^{commit}' || true)"
ref=main; [[ -n "$old_main" ]] || { ref=HEAD; old_main="$(git -C "$here/.." rev-parse HEAD)"; }
set +e
named="$(bash "$here/run.sh" --old-ref "$ref" 2>&1)"; named_exit=$?
unknown="$(bash "$here/run.sh" --old-ref no-such-ref-xyz 2>&1)"; unknown_exit=$?
default="$(bash "$here/run.sh" 2>&1)"
set -e
if [[ $named_exit -eq 2 ]] && grep -q "OLD plugin = $ref ($old_main)" <<<"$named" \
   && grep -q "Re-run with --yes" <<<"$named" \
   && [[ $unknown_exit -eq 2 ]] && grep -q "no-such-ref-xyz' is not a commit" <<<"$unknown" \
   && ! grep -q "COST WARNING" <<<"$unknown" \
   && grep -q "OLD plugin = 4c1cd93 (4c1cd93" <<<"$default"; then
  echo "run.sh --old-ref: ok"
else
  echo "run.sh --old-ref: FAIL"; printf '%s\n---\n%s\n---\n%s\n' "$named" "$unknown" "$default"
  fails=$((fails + 1))
fi

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
        # Only the NEW arm runs the checklist. OLD's `plan_feature new` and a grep for the
        # name are not checklist use.
        command = ("100x plan_feature cases --kind settings" if doc == "new" and loaded
                   else "100x plan_feature new x --kind payment" if doc == "old"
                   else "grep -rn plan_feature scripts")
        tool = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": command}}]}}
        result = {"type": "result", "result": (work / f"{case}-{kind}.txt").read_text()}
        (root / "out/trace.jsonl").write_text("\n".join(map(json.dumps, (init, tool, result))) + "\n")
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
# screen-patterns/AC-10: the footer counts, per arm, the runs that used the checklist.
if grep -q "new vs old: new better in 2, worse in 0" <<<"$summary" \
   && grep -q "plugin-load mismatches 0" <<<"$summary" \
   && grep -qE "^new .*checklist calls 2/2" <<<"$summary" \
   && grep -qE "^none .*checklist calls 0/2" <<<"$summary" \
   && grep -qE "^old .*checklist calls 0/2" <<<"$summary" \
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
