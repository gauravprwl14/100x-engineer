#!/usr/bin/env bash
# Skill discoverability: the trigger eval's realism modes (truncate, name-only, distractors,
# list-valued expect, pre-merge aliases) and the description rules in lint_skills.py. Each
# check asserts both that a bad catalogue is caught and that a good one is not.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRIG="$ROOT/scripts/skill_triggers.py"
LINT="$ROOT/scripts/lint_skills.py"
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }

# skill <root> <name> <description>: the smallest SKILL.md the trigger scorer reads.
skill() { mkdir -p "$1/skills/$2"; printf -- '---\nname: %s\ndescription: >\n  %s\n---\n' "$2" "$3" > "$1/skills/$2/SKILL.md"; }

mk_catalogue() {
  local d="$1"; mkdir -p "$d/evals"
  skill "$d" alpha-skill "Webhook retries and duplicate events: idempotency keys and the outbox pattern."
  skill "$d" beta-skill  "Responsive page layout: mobile breakpoints, loading and empty states."
  skill "$d" gamma-skill "Postmortem for an outage: timeline, hypotheses, five whys, action items."
  # the trigger noun sits past char 100, so only a full-length listing can route to it
  skill "$d" delta-skill "A careful, thorough, end-to-end, senior-engineer-grade practice applied to everyday engineering - for flamegraph profiling."
  skill "$d" epsilon-skill "Database schema design: tables, columns, indexes and migrations."
  # neighbours that share a generic word with the profiling prompt, so a truncated delta loses
  skill "$d" zeta-skill "Read build log output and summarise the failure."
  skill "$d" eta-skill "Read command output and format it as a table."
  cat > "$d/evals/triggers.json" <<'JSON'
{"cases": [
 {"prompt": "the webhook fired twice, add idempotency", "expect": "alpha-skill"},
 {"prompt": "make this page responsive on mobile", "expect": "beta-skill"},
 {"prompt": "write the postmortem for last night's outage", "expect": "gamma-skill"},
 {"prompt": "read this flamegraph profiling output", "expect": "delta-skill"},
 {"prompt": "design the schema tables and indexes", "expect": ["epsilon-skill", "alpha-skill"]}
]}
JSON
  cat > "$d/evals/distractors.json" <<'JSON'
{"_doc": "synthetic", "skills": [
 {"name": "other:layout", "description": "Responsive page layout, mobile breakpoints, responsive page grid, mobile page."}
]}
JSON
}

run() { python3 "$TRIG" --root "$1" "${@:2}" >"$OUT/run.out" 2>&1; }

echo "=== skill_triggers.py: the real catalogue ==="
python3 "$TRIG" --all-modes >"$OUT/real.out" 2>&1 \
  && ok "the plugin's own catalogue passes both gates" \
  || { bad "the plugin's own catalogue fails a gate"; sed 's/^/     /' "$OUT/real.out"; }

echo "=== skill_triggers.py: no false positive on a clean catalogue ==="
C="$OUT/clean"; mk_catalogue "$C"
run "$C" && ok "full mode passes a discriminating catalogue" \
  || { bad "clean catalogue flagged"; sed 's/^/     /' "$OUT/run.out"; }
run "$C" --json && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d["top3"]==1.0 else 1)' "$OUT/run.out" \
  && ok "a list-valued expect counts any listed skill as a hit" || bad "list-valued expect not honoured"

echo "=== skill_triggers.py: detection ==="
run "$C" --truncate 100 --json; rc=$?
if [ "$rc" -ne 0 ] && grep -q '"delta-skill"' "$OUT/run.out" && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); r=[c for c in d["cases"] if c["expect"]=="delta-skill"][0]; sys.exit(0 if not r["top3_hit"] else 1)' "$OUT/run.out"; then
  ok "--truncate 100 misses a skill whose trigger noun sits past char 100"
else bad "--truncate did not cut the description (rc=$rc)"; fi
run "$C" --name-only --json; rc=$?
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d["top3"] < 1.0 else 1)' "$OUT/run.out" \
  && ok "--name-only drops descriptions (recall falls)" || bad "--name-only still scored descriptions (rc=$rc)"
run "$C" --distractors "$C/evals/distractors.json" --json
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); r=[c for c in d["cases"] if c["expect"]=="beta-skill"][0]; sys.exit(0 if r["top3"][0]=="other:layout" and d["distractor_top1"]>=1 else 1)' "$OUT/run.out" \
  && ok "a distractor that out-scores a skill takes first place and is counted" \
  || { bad "distractor not ranked"; sed 's/^/     /' "$OUT/run.out" | head -20; }
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if "other:layout" not in d["never_wins"] else 1)' "$OUT/run.out" \
  && ok "a distractor is never reported as an unshortlisted plugin skill" || bad "distractor leaked into never_wins"
python3 "$TRIG" --root "$C" --all-modes --distractors "$C/evals/distractors.json" >"$OUT/all.out" 2>&1; rc=$?
[ "$rc" -ne 0 ] && grep -q "truncate100+distractors" "$OUT/all.out" && grep -q "FAIL" "$OUT/all.out" \
  && ok "--all-modes fails when truncate-with-distractors misses the floor" \
  || { bad "--all-modes passed a catalogue that fails truncation (rc=$rc)"; sed 's/^/     /' "$OUT/all.out"; }

# --from-git collapses merged skills into the name they became.
G="$OUT/git"; mk_catalogue "$G"
mv "$G/skills/beta-skill" "$G/skills/scoped-review"; sed -i.bak 's/^name: beta-skill/name: scoped-review/' "$G/skills/scoped-review/SKILL.md"; rm -f "$G/skills/scoped-review/SKILL.md.bak"
sed -i.bak 's/"beta-skill"/"diff-review"/' "$G/evals/triggers.json"; rm -f "$G/evals/triggers.json.bak"
( cd "$G" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm fixture )
python3 "$TRIG" --root "$G" --from-git HEAD --json >"$OUT/git.out" 2>&1
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); r=[c for c in d["cases"] if c["expect"]=="diff-review"][0]; sys.exit(0 if r["top3_hit"] else 1)' "$OUT/git.out" \
  && ok "--from-git scores a pre-merge skill under its merged name" \
  || { bad "alias not applied"; sed 's/^/     /' "$OUT/git.out" | head; }

echo "=== lint_skills.py: description rules ==="
L="$OUT/lint"; mkdir -p "$L/skills"; cp -R "$ROOT/skills/bug-fix" "$L/skills/"
python3 "$LINT" --root "$L" >"$OUT/l.out" 2>&1 && ! grep -q WARN "$OUT/l.out" \
  && ok "a real skill passes with no warning" || { bad "real skill flagged"; cat "$OUT/l.out"; }
setdesc() { python3 - "$L/skills/bug-fix/SKILL.md" "$1" <<'PY'
import re,sys,pathlib
p=pathlib.Path(sys.argv[1]); t=p.read_text()
t=re.sub(r"description: >\n(  .*\n)+", "description: >\n  "+sys.argv[2]+"\n", t, count=1); p.write_text(t)
PY
}
setdesc "$(printf 'Crash, regression, failing test: reproduce first. %.0s' $(seq 1 7))"
python3 "$LINT" --root "$L" >"$OUT/l.out" 2>&1; rc=$?
[ "$rc" -ne 0 ] && grep -q "over the 300 cap" "$OUT/l.out" && ok "a description over 300 chars is an error" \
  || { bad "long description not rejected (rc=$rc)"; cat "$OUT/l.out"; }
setdesc "Use when you want a careful and thorough senior-engineer-grade practice applied to everyday engineering situations: crash, regression, failing test."
python3 "$LINT" --root "$L" >"$OUT/l.out" 2>&1; rc=$?
[ "$rc" -eq 0 ] && grep -q "share no noun with" "$OUT/l.out" && ok "trigger nouns only after char 100 warn without failing" \
  || { bad "late trigger nouns not warned (rc=$rc)"; cat "$OUT/l.out"; }
setdesc "Crash, regression, wrong output or failing test: reproduce first, commit the failing test, fix the narrowest thing. Not for an outage (→ root-cause-analysis)."
python3 "$LINT" --root "$L" >"$OUT/l.out" 2>&1 && ! grep -q WARN "$OUT/l.out" \
  && ok "a front-loaded description under 250 chars passes clean" || { bad "good description flagged"; cat "$OUT/l.out"; }

echo
echo "skill_triggers: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
