#!/usr/bin/env bash
# Regression suite for scripts/plan_dag.py: every lint rule has a failing fixture, the
# valid plan passes, waves and next order tasks correctly.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EX="$ROOT/examples/orchestration"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
P="$ROOT/scripts/plan_dag.py"
O="$TMP/pd.out"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; [ -s "$O" ] && sed 's/^/       /' "$O" | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" "$O" && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -qF -- "$1" "$O" && bad "false positive: $1" || ok "absent: $1"; }

# --- the valid plan is clean, with the spec ---
python3 "$P" lint "$EX/plan.json" --spec "$EX/spec.md" >"$O" 2>&1; rc_is 0 $? "lint: valid plan passes with --spec"
no "WARN"; no "1."

# --- each rule: a fixture that must fail, and the message that names it ---
lint_fails() { # lint_fails <fixture> <expected substring> [extra args]
  local f="$1" msg="$2"; shift 2
  python3 "$P" lint "$EX/invalid/$f.json" "$@" >"$O" 2>&1
  rc_is 1 $? "lint: $f exits 1"; has "$msg"
}
lint_fails cycle                  "dependency cycle T0 -> T3 -> T1 -> T0"
no "does not depend on it"        # a cycle must not cascade into false consumer errors
lint_fails unknown-owner          "owner 'ux-wizard' is not a known agent"
lint_fails missing-fields         "T1: \"verify\" must be a non-empty list"
has "T2: \"files\" must be a non-empty list"
has "T3: \"acceptance\" must be a non-empty list"
lint_fails overlap-exact          "T1 and T2 can run in parallel but both own files"
lint_fails overlap-glob           "'backend/src/tagging/services/**' overlaps 'backend/src/**'"
lint_fails consumer-no-dep        "T2: consumes T0 but does not depend on it"
lint_fails consumer-owns-contract "T1: consumer owns contract T0's files"
lint_fails consumes-non-contract  "T3: consumes T1, which is not a contract task"
lint_fails missing-ac             "AC-4 in $EX/spec.md is covered by no task" --spec "$EX/spec.md"
grep -qE '^  1\. ' "$O" && ok "lint: messages are numbered" || bad "lint: messages not numbered"

# only DEFINED criteria count: a verification row or prose that mentions AC-9 is not one
cp "$EX/spec.md" "$TMP/mention.md"
printf '\n| V1 | unit | npm test | pre-PR | AC-9 |\nSee AC-9 in the follow-up, not this spec.\n' >> "$TMP/mention.md"
python3 "$P" lint "$EX/plan.json" --spec "$TMP/mention.md" >"$O" 2>&1
rc_is 0 $? "lint --spec: a mentioned-but-undefined id is not required (no false positive)"
no "AC-9"
# the canonical plan_feature line, with its requirement links, is parsed the same way
printf '# s\n\n## 2b. Acceptance criteria\n\nAC-1: one (R1, S1)\nAC-2: two (R2, S1)\nAC-3: three (R1)\nAC-4: four (S2)\nAC-5: five (R3, S2)\n' > "$TMP/canon.md"
python3 "$P" lint "$EX/plan.json" --spec "$TMP/canon.md" >"$O" 2>&1
rc_is 1 $? "lint --spec: canonical AC lines are parsed (AC-5 uncovered)"
has "AC-5 in $TMP/canon.md is covered by no task"
printf '# s\n\nNo criteria here.\n' > "$TMP/noac.md"
python3 "$P" lint "$EX/plan.json" --spec "$TMP/noac.md" >"$O" 2>&1
rc_is 1 $? "lint --spec: a spec defining no AC fails instead of checking nothing"
has "defines no acceptance criteria"

# without --spec the same plan has nothing to check AC coverage against
python3 "$P" lint "$EX/invalid/missing-ac.json" >"$O" 2>&1; rc_is 0 $? "lint: AC coverage only checked with --spec"

# --- unknown fields are errors, with a did-you-mean ---
lint_fails unknown-field          "T3: unknown field 'depend_on' — did you mean 'depends_on'?"
has "unknown top-level field 'owner_team'"; has "T1: unknown field 'priority'"
no "WARN"

# --- top level: feature required, tier from scale_tiers.json, schema ---
top() { # top <python expr mutating d> -> lint of the mutated valid plan
  python3 - "$EX/plan.json" "$TMP/top.json" "$1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); exec(sys.argv[3]); json.dump(d, open(sys.argv[2], "w"))
PY
  python3 "$P" lint "$TMP/top.json" >"$O" 2>&1
}
top 'del d["feature"]';        rc_is 1 $? "lint: a plan with no feature fails"; has 'missing top-level "feature"'
top 'd["tier"] = "huge"';      rc_is 1 $? "lint: an unknown tier fails"; has '"tier": '"'huge'"' is not one of prototype, small, growth, scale'
top 'del d["tier"]';           rc_is 0 $? "lint: tier is optional"
top 'del d["schema"]';         rc_is 0 $? "lint: a missing schema is read as 1"; has 'WARN  no "schema" field'
top 'd["schema"] = 2';         rc_is 1 $? "lint: schema 2 fails"; has '"schema": 2 is not supported'
top 'd["tasks"][1]["files"] = ["backend/src/tagging/{services,repo}/**"]'
rc_is 1 $? "lint: brace globs are rejected"; has "uses {a,b} braces"

# --- verify commands must replay without a shell, and never ship anything ---
for bad in 'pnpm test && pnpm lint|shell syntax' 'pnpm test > out.txt|shell syntax' \
           'CI=1 pnpm test|starts with an assignment' 'echo $HOME|expansion' \
           'git push origin main|gated action (git push)' 'npm publish|gated action (npm publish)' \
           "sh -c 'pnpm test && git commit -m x'|gated action (git commit)"; do
  cmd="${bad%|*}"; msg="${bad#*|}"
  top "d['tasks'][0]['verify'] = [$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$cmd")]"
  rc_is 1 $? "lint: verify '$cmd' is rejected"; has "$msg"
done
top "d['tasks'][0]['verify'] = [\"sh -c 'pnpm test && pnpm lint'\", 'env CI=1 pnpm test', 'git status', 'git diff --exit-code']"
rc_is 0 $? "lint: sh -c, env, and read-only git commands are accepted (no false positive)"

# --- a bare extensionless path is a directory for overlap ---
cat > "$TMP/bare.json" <<'JSON'
{"schema": 1, "feature": "f", "tasks": [
 {"id": "A", "owner": "backend-engineer", "files": ["src/auth"], "verify": ["true"], "acceptance": ["AC-1"]},
 {"id": "B", "owner": "backend-engineer", "files": ["src/auth/session.ts"], "verify": ["true"], "acceptance": ["AC-1"]}
]}
JSON
python3 "$P" lint "$TMP/bare.json" >"$O" 2>&1; rc_is 1 $? "lint: 'src/auth' owns src/auth/session.ts"
has "'src/auth' overlaps 'src/auth/session.ts'"
sed 's#"src/auth/session.ts"#"src/authz.ts"#' "$TMP/bare.json" > "$TMP/bare2.json"
python3 "$P" lint "$TMP/bare2.json" >"$O" 2>&1; rc_is 0 $? "lint: 'src/auth' does not own src/authz.ts"
python3 - "$ROOT" <<'PY' && ok "_globs: concrete paths are matched literally" || bad "_globs: path_matches"
import sys; sys.path.insert(0, sys.argv[1] + "/scripts")
from _globs import path_matches as m
assert m("src/auth/x.ts", "src/auth") and m("Makefile", "Makefile")
assert not m("src/authx/y.ts", "src/auth") and not m("src/x", "src/x/y.ts")
assert m("a/b/c.ts", "a/**/*.ts") and not m("a/b/c.tsx", "a/**/*.ts")
PY

# --- --spec resolves like every record argument ---
SP="$TMP/sp"; mkdir -p "$SP/docs/engineering/specs/album-tagging"
cp "$EX/spec.md" "$SP/docs/engineering/specs/album-tagging/spec.md"
( cd "$SP" && git init -q )
for arg in docs/engineering/specs/album-tagging/spec.md docs/engineering/specs/album-tagging \
           specs/album-tagging specs/album-tagging/spec.md album-tagging; do
  ( cd "$SP" && python3 "$P" lint "$EX/plan.json" --spec "$arg" ) >"$O" 2>&1
  rc_is 0 $? "lint --spec $arg resolves"
done
( cd "$SP" && python3 "$P" lint "$EX/plan.json" --spec nosuch ) >"$O" 2>&1
rc_is 2 $? "lint --spec: an unresolvable spec is exit 2"; has "no spec.md for 'nosuch'"

# --- --agents-dir extends the roster; without it the same owner is rejected ---
mkdir -p "$TMP/agents"; echo "# ux" > "$TMP/agents/ux-wizard.md"
python3 "$P" lint "$EX/invalid/unknown-owner.json" --agents-dir "$TMP/agents" >"$O" 2>&1
rc_is 0 $? "lint: --agents-dir accepts its *.md names"

# --- no false positives from the overlap approximation ---
cat > "$TMP/disjoint.json" <<'JSON'
{"schema": 1, "feature": "f", "tasks": [
 {"id": "A", "owner": "backend-engineer", "files": ["src/a/*.ts"], "verify": ["true"], "acceptance": ["AC-1"]},
 {"id": "B", "owner": "frontend-engineer", "files": ["src/a/*.tsx", "src/b/**"], "verify": ["true"], "acceptance": ["AC-1"]},
 {"id": "C", "owner": "qa-engineer", "depends_on": ["A"], "files": ["src/a/x.ts"], "verify": ["true"], "acceptance": ["AC-1"]}
]}
JSON
python3 "$P" lint "$TMP/disjoint.json" >"$O" 2>&1; rc_is 0 $? "lint: *.ts vs *.tsx, and a dependent re-owning a file, are not collisions"

cat > "$TMP/subdir.json" <<'JSON'
{"schema": 1, "feature": "f", "tasks": [
 {"id": "A", "owner": "backend-engineer", "files": ["src/"], "verify": ["true"], "acceptance": ["AC-1"]},
 {"id": "B", "owner": "backend-engineer", "files": ["./src/deep/x.py"], "verify": ["true"], "acceptance": ["AC-1"]}
]}
JSON
python3 "$P" lint "$TMP/subdir.json" >"$O" 2>&1; rc_is 1 $? "lint: a trailing-slash directory owns everything under it"

echo '{nope' > "$TMP/broken.json"
python3 "$P" lint "$TMP/broken.json" >"$O" 2>&1; rc_is 2 $? "lint: invalid JSON is exit 2, not a crash"

# --- the roster must track OPERATING-MODEL.md §1 ---
python3 - "$ROOT" >"$O" 2>&1 <<'PY'
import sys, pathlib
sys.path.insert(0, sys.argv[1] + "/scripts")
import plan_dag
doc = pathlib.Path(sys.argv[1], "docs/OPERATING-MODEL.md").read_text()
roles = doc.split("## 1. Roles", 1)[1].split("## 2.", 1)[0]
names = {l.split("|")[1].strip() for l in roles.splitlines()
         if l.startswith("| ") and not l.startswith("| agent") and "---" not in l}
missing = sorted(set(plan_dag.ROSTER) ^ names)
print("drift:", missing); sys.exit(1 if missing else 0)
PY
rc_is 0 $? "roster matches the §1 table in OPERATING-MODEL.md"

# --- waves ---
python3 "$P" waves "$EX/plan.json" --json >"$O" 2>&1; rc_is 0 $? "waves: runs"
python3 -c "import json,sys; w=json.load(open('$O')); sys.exit(0 if [x['tasks'] for x in w]==[['T0'],['T1','T2'],['T3']] else 1)" \
  && ok "waves: [T0] then [T1,T2] in parallel then [T3]" || bad "waves: wrong ordering"
python3 "$P" waves "$EX/plan.json" >"$O" 2>&1; has "| 2 | T2 | frontend-engineer | tag list UI |"
python3 "$P" waves "$EX/invalid/cycle.json" >"$O" 2>&1; rc_is 1 $? "waves: refuses a cyclic plan"

# --- next: blocked tasks hold only their dependents ---
nxt() { python3 "$P" next "$EX/plan.json" --json "$@" >"$O" 2>&1; }
jq_is() { python3 -c "import json,sys; d=json.load(open('$O')); sys.exit(0 if $1 else 1)" && ok "$2" || bad "$2"; }
nxt;                         jq_is "d['ready']==['T0'] and d['waiting']=={'T1':['T0'],'T2':['T0'],'T3':['T1','T2']}" "next: only the contract starts first"
nxt --done T0;               jq_is "d['ready']==['T1','T2']" "next: contract done releases both consumers"
nxt --done T0 --blocked T1;  jq_is "d['ready']==['T2'] and d['held']=={'T3':['T1']}" "next: blocked T1 holds T3, T2 continues"
nxt --done T0,T1,T2;         jq_is "d['ready']==['T3'] and not d['held']" "next: all deps done releases T3"
python3 "$P" next "$EX/plan.json" --done T9 >"$O" 2>&1; rc_is 2 $? "next: unknown id is a usage error"

echo
echo "plan_dag: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
