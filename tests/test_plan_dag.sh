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

# --- a ready spec in its own repo: lint --spec needs an audited, approved spec ---
# specs/login/spec.md is this plugin's audited worked example; `| prd | none |` keeps
# the copy self-contained. Its six ACs are AC-1..AC-6.
newrepo() { mkdir -p "$1" && ( cd "$1" && git init -q && git config user.email e@e \
  && git config user.name e && echo x > f.txt && git add -A && git commit -qm init ); }
ready_spec() { # ready_spec <repo> <feature> -> writes <repo>/docs/engineering/specs/<feature>/spec.md
  mkdir -p "$1/docs/engineering/specs/$2"
  sed -e 's#^| prd | examples/login |#| prd | none |#' -e "s#^| feature | login |#| feature | $2 |#" \
    "$ROOT/specs/login/spec.md" > "$1/docs/engineering/specs/$2/spec.md"
}
six_plan() { # six_plan <out>: the example plan with T3 also owning AC-5, AC-6
  python3 - "$EX/plan.json" "$1" <<'PY2'
import json, sys
d = json.load(open(sys.argv[1])); d["tasks"][3]["acceptance"] += ["AC-5", "AC-6"]
json.dump(d, open(sys.argv[2], "w"), indent=1)
PY2
}
RS="$TMP/rs"; newrepo "$RS"; ready_spec "$RS" album-tagging
RSPEC="$RS/docs/engineering/specs/album-tagging/spec.md"
RPLAN="$RS/docs/engineering/specs/album-tagging/plan.json"
six_plan "$RPLAN"

# --- the valid plan is clean, with the spec, once stamped ---
python3 "$P" lint "$RPLAN" --spec "$RSPEC" >"$O" 2>&1; rc_is 1 $? "lint --spec: an unstamped plan fails"
has "plan is not stamped against"
python3 "$P" stamp "$RPLAN" >"$O" 2>&1; rc_is 0 $? "stamp: the plan's feature resolves to its ready spec"
has "stamped"
python3 - "$RPLAN" "$RS" >"$O" 2>&1 <<'PY2'
import hashlib, json, subprocess, sys
d = json.load(open(sys.argv[1]))
head = subprocess.run(["git", "-C", sys.argv[2], "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
spec = sys.argv[2] + "/" + d["spec"]
assert d["spec"] == "docs/engineering/specs/album-tagging/spec.md", d["spec"]
assert d["spec_sha256"] == hashlib.sha256(open(spec, "rb").read()).hexdigest()
assert d["base"] == head, (d["base"], head)
assert list(d) == ["schema", "feature", "tier", "spec", "spec_sha256", "base", "tasks"], list(d)
PY2
rc_is 0 $? "stamp: records the repo-relative spec path, its sha256, base = HEAD, in field order"
python3 "$P" lint "$RPLAN" --spec "$RSPEC" >"$O" 2>&1; rc_is 0 $? "lint: valid stamped plan passes with --spec"
no "WARN"; no "1."
python3 "$P" lint "$RPLAN" >"$O" 2>&1; rc_is 0 $? "lint: --spec defaults to the plan's recorded spec"
no "WARN"
( cd "$TMP" && python3 "$P" lint "$RPLAN" ) >"$O" 2>&1; rc_is 0 $? "lint: the recorded spec resolves against the plan's repo, not the cwd"

# --- an edited spec breaks the stamp: re-plan or re-approve ---
cp "$RSPEC" "$TMP/spec.bak"
printf '\nA late edit.\n' >> "$RSPEC"
python3 "$P" lint "$RPLAN" >"$O" 2>&1; rc_is 1 $? "lint: a spec edited after stamping fails"
has "changed since the plan was stamped"; has "re-plan or re-approve"
cp "$TMP/spec.bak" "$RSPEC"
python3 "$P" lint "$RPLAN" >"$O" 2>&1; rc_is 0 $? "lint: restoring the stamped bytes passes again"

# --- a draft spec, and a spec that fails the audit, are rejected ---
sed 's#^| status | \*\*ready\*\* |#| status | **draft — not ready to implement** |#' "$TMP/spec.bak" > "$RSPEC"
grep -q '^| status | \*\*draft' "$RSPEC" && ok "fixture: spec set to draft" || bad "fixture: draft sed"
python3 "$P" lint "$RPLAN" >"$O" 2>&1; rc_is 1 $? "lint: a draft spec is rejected"
has "has status 'draft"; has "not \`ready\`"
python3 "$P" stamp "$RPLAN" >"$O" 2>&1; rc_is 1 $? "stamp: refuses a draft spec"
has "is not an approved spec"
cp "$TMP/spec.bak" "$RSPEC"
python3 "$P" lint "$EX/invalid/missing-ac.json" --spec "$EX/spec.md" >"$O" 2>&1
rc_is 1 $? "lint --spec: an unaudited spec is rejected"
has "does not pass \`100x plan_feature audit\`"

# --- the recorded spec must be the one linted ---
ready_spec "$RS" other
python3 "$P" lint "$RPLAN" --spec "$RS/docs/engineering/specs/other/spec.md" >"$O" 2>&1
rc_is 1 $? "lint: --spec naming a different spec than the stamped one fails"
has "is not the spec this plan was stamped against"
python3 - "$RPLAN" "$RS/gone.json" <<'PY2'
import json, sys
d = json.load(open(sys.argv[1])); d["spec"] = "docs/engineering/specs/nosuch/spec.md"
json.dump(d, open(sys.argv[2], "w"))
PY2
python3 "$P" lint "$RS/gone.json" >"$O" 2>&1; rc_is 1 $? "lint: a recorded spec that does not exist fails"
has "there is no such file"

# --- an AC a task claims but the spec does not define is an error ---
python3 - "$RPLAN" "$RS/extra.json" <<'PY2'
import json, sys
d = json.load(open(sys.argv[1])); d["tasks"][2]["acceptance"].append("AC-12")
json.dump(d, open(sys.argv[2], "w"))
PY2
python3 "$P" lint "$RS/extra.json" >"$O" 2>&1; rc_is 1 $? "lint: an undefined AC claimed by a task is an error"
has "AC-12 is claimed by T2 but docs/engineering/specs/album-tagging/spec.md does not define it"
no "WARN"

# --- stamp fields: shape checked, writes contained ---
stampf() { # stampf <python expr mutating d> -> lint of the mutated stamped plan
  python3 - "$RPLAN" "$RS/f.json" "$1" <<'PY2'
import json, sys
d = json.load(open(sys.argv[1])); exec(sys.argv[3]); json.dump(d, open(sys.argv[2], "w"))
PY2
  python3 "$P" lint "$RS/f.json" >"$O" 2>&1
}
stampf 'd["spec"] = "/etc/spec.md"';     rc_is 1 $? "lint: an absolute \"spec\" fails"; has "must be the spec's path relative to the repository root"
stampf 'd["spec"] = "../x/spec.md"';     rc_is 1 $? "lint: a '..' \"spec\" fails"
stampf 'd["spec_sha256"] = "abc"';       rc_is 1 $? "lint: a malformed spec_sha256 fails"; has "is not a sha256 hex digest"
stampf 'd["base"] = "main"';             rc_is 1 $? "lint: a base that is not a commit id fails"; has "is not a git commit id"
stampf 'del d["spec"]';                  rc_is 1 $? "lint: spec_sha256 without spec fails"; has "without \"spec\""
stampf 'd["spek"] = 1';                  rc_is 1 $? "lint: a misspelt stamp field fails"; has "did you mean 'spec'?"
cp "$RPLAN" "$TMP/outside.json"
ln -s "$TMP/outside.json" "$RS/link.json"
python3 "$P" stamp "$RS/link.json" >"$O" 2>&1; rc_is 2 $? "stamp: refuses a plan.json symlinked out of the repo"; has "outside the repository"
cmp -s "$RPLAN" "$TMP/outside.json" && ok "stamp: the symlink target was not written" || bad "stamp: wrote through a symlink"
mkdir -p "$TMP/nogit"; cp "$RPLAN" "$TMP/nogit/plan.json"
python3 "$P" stamp "$TMP/nogit/plan.json" --spec "$RSPEC" >"$O" 2>&1; rc_is 2 $? "stamp: refuses outside a git repo"
has "not inside a git repository"

# --- the audit verdict is plan_feature's: audit_spec when present, the CLI otherwise ---
python3 - "$ROOT" "$RSPEC" "$EX/spec.md" >"$O" 2>&1 <<'PY2'
import sys
sys.path.insert(0, sys.argv[1] + "/scripts")
import plan_dag, plan_feature
had = hasattr(plan_feature, "audit_spec")
saved = getattr(plan_feature, "audit_spec", None)
plan_feature.audit_spec = lambda p: (["seeded"], [], "ready")
e, w, s = plan_dag.audit_spec(sys.argv[2])
assert e == ["seeded"], (e, s)
plan_feature.audit_spec = lambda p: ([], [], "draft")
assert plan_dag.spec_gate({}, sys.argv[2], "x")[0].startswith("spec x has status 'draft'")
del plan_feature.audit_spec
e, w, s = plan_dag.audit_spec(sys.argv[2])
assert not e and plan_dag._is_ready(s), (e, s)
e, w, s = plan_dag.audit_spec(sys.argv[3])
assert e and any("Non-functional" in x for x in e), e
if had:
    plan_feature.audit_spec = saved
PY2
rc_is 0 $? "audit_spec: uses plan_feature.audit_spec if present, else the audit CLI"

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
printf '\n| V1 | unit | npm test | pre-PR | AC-9 |\nSee AC-9 in the follow-up, not this spec.\n' >> "$RSPEC"
python3 "$P" stamp "$RPLAN" >/dev/null 2>&1
python3 "$P" lint "$RPLAN" >"$O" 2>&1
rc_is 0 $? "lint --spec: a mentioned-but-undefined id is not required (no false positive)"
no "AC-9"
cp "$TMP/spec.bak" "$RSPEC"; python3 "$P" stamp "$RPLAN" >/dev/null 2>&1
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
has "WARN  no spec: acceptance coverage and spec approval were not checked"

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

# replay runs shlex.split(cmd), which keeps '#': the screen must see that same argv,
# not a comment-stripped one that hides the gated command after a '#'
for bad in 'env A=1#x git tag -a v9 -m shipped|gated action (git tag)' \
           'env X=1#y npm publish|gated action (npm publish)' \
           "sh -c 'echo a#b; git push origin HEAD'|gated action (git push)" \
           "bash -o pipefail -c 'git push origin HEAD'|gated action (git push)" \
           "bash -euo pipefail -c 'npm publish'|gated action (npm publish)" \
           "bash -O extglob -c 'git tag v1'|gated action (git tag)" \
           "bash --norc -ec 'git commit -m x'|gated action (git commit)" \
           "sh -c \"sh -c 'echo a#b; npm publish'\"|gated action (npm publish)"; do
  cmd="${bad%|*}"; msg="${bad#*|}"
  top "d['tasks'][0]['verify'] = [$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$cmd")]"
  rc_is 1 $? "lint: verify '$cmd' is rejected"; has "$msg"
done
top "d['tasks'][0]['verify'] = ['echo a#b', \"bash -euo pipefail -c 'pnpm test | tee out.txt'\", \"bash -O extglob -c 'ls *.ts'\", \"sh -c 'echo done # git tag v1 is a comment'\"]"
rc_is 0 $? "lint: '#' in a word and shell options before -c are not rejected (no false positive)"
python3 - "$ROOT" >"$O" 2>&1 <<'PY'
import shlex, sys
sys.path.insert(0, sys.argv[1] + "/scripts")
from plan_dag import shell_wrapped as w, replay_argv_problems as r, command_problems as c
s = lambda x: w(shlex.split(x))
assert s("sh -c 'a b'") == "a b"
assert s("bash -o pipefail -c 'a | b'") == "a | b"
assert s("bash -euo pipefail -c 'x'") == "x"
assert s("bash +O extglob -ec 'y'") == "y"
assert s("bash --rcfile rc -c 'z'") == "z"
assert s("bash script.sh") is None and s("pnpm -c x") is None
assert s("bash -o pipefail -c") == ""
assert s("bash -c -o") is not None
assert c is r
PY
rc_is 0 $? "shell_wrapped: finds the script after -o/-O values and combined flags; command_problems is replay_argv_problems"

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
for arg in docs/engineering/specs/album-tagging/spec.md docs/engineering/specs/album-tagging \
           specs/album-tagging specs/album-tagging/spec.md album-tagging; do
  ( cd "$RS" && python3 "$P" lint "$RPLAN" --spec "$arg" ) >"$O" 2>&1
  rc_is 0 $? "lint --spec $arg resolves"
done
SP="$RS"
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
