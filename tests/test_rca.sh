#!/usr/bin/env bash
# Regression suite for scripts/rca.py — root-cause-analysis records.
# Asserts detection AND absence of false positives, same shape as test_planning_tools.sh.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-54s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-54s\n' "$1"; [ -s $OUT/rca.out ] && sed 's/^/       /' $OUT/rca.out | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -q "$1" $OUT/rca.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -q "$1" $OUT/rca.out && bad "false positive: $1" || ok "no false positive: $1"; }

# rca.py must write into the CONSUMER repo, never into the plugin dir.
CONS="$TMP/consumer"; mkdir -p "$CONS"; cd "$CONS"
git init -q; git config user.email e@e; git config user.name e
echo x > f.txt; git add -A; git commit -qm init

# ---------- new: scaffold a fresh record ----------
python3 "$ROOT/scripts/rca.py" new "Sessions dropped after deploy" --affects "src/auth/**" --severity high \
  >$OUT/rca.out 2>&1
rc_is 0 $? "new: exits 0"
has "recorded as SEV2"
RECFILE=$(ls "$CONS"/docs/engineering/rca/RCA-0001-*.md 2>/dev/null | head -1)
[ -n "$RECFILE" ] && ok "new: record created in the consumer repo" || bad "new: record not created"
[ ! -d "$ROOT/rca" ] && ok "new: did NOT write into the plugin dir" \
  || bad "new: leaked an rca/ dir into the plugin dir"

# ---------- lint: a fresh (unfilled) record fails ----------
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: fresh record fails"
has "no reproduction recorded"
has "no root cause recorded"
has "no timeline recorded"
has "no hypotheses recorded"
has "five-whys has 0 real level"
has "contributing-factors section is empty"
has "no regression test reference"
has "impact.users_affected missing"
has "no action items"
grep -q '"severity": "SEV2"' "$RECFILE" && ok "new: legacy --severity high stored as the SEV2 enum" \
  || bad "new: severity not normalised to the enum"

# ---------- fill the record completely, in isolation, one violation removed at a time ----------
fill_complete() {
  python3 - "$RECFILE" <<'PY'
import json, re, pathlib, sys
p = pathlib.Path(sys.argv[1])
text = p.read_text()
m = re.search(r"```json meta\n(.*?)\n```", text, re.S)
meta = json.loads(m.group(1))
meta["symptom"] = "Users were logged out about 5 minutes after the 14:02 UTC deploy."
meta["trigger"] = "Deploy abc123 changed the session cookie's SameSite attribute to Strict."
meta["mechanism"] = "SameSite=Strict caused the browser to drop the cookie on the SSO " \
                     "redirect back from the identity provider, so the session lookup 404'd."
meta["root_cause"] = "The SSO callback flow requires SameSite=Lax; nothing enforces or " \
                      "tests that constraint in the auth module."
meta["reproduction"]["command"] = "bash tests/repro_sso_samesite.sh"
meta["reproduction"]["verified"] = True
meta["severity"] = "SEV2"
meta["status"] = "fixed"
meta["impact"] = {"users_affected": 1200, "duration_minutes": 65,
                  "data_impact": "none; sessions only",
                  "revenue_or_sla_impact": "40% of the monthly login SLO error budget"}
meta["timeline"] = [
    {"at": "2026-09-28T14:00:00Z", "type": "started", "event": "deploy abc123 shipped the SameSite change"},
    {"at": "2026-09-28T14:05:00Z", "type": "detected", "event": "login error-rate alert fired"},
    {"at": "2026-09-28T14:12:00+00:00", "type": "escalated", "event": "auth on-call paged"},
    {"at": "2026-09-28T23:20:00+09:00", "type": "note", "event": "git bisect isolated abc123"},
    {"at": "2026-09-28T14:35:00Z", "type": "mitigated", "event": "rolled back to the previous release"},
    {"at": "2026-09-28T15:05:00Z", "type": "resolved", "event": "fix shipped with SameSite=Lax"},
]
meta["fault_tree"] = None
meta["lucky"] = ["The deploy happened during low-traffic hours."]
meta["action_items"] = [
    {"what": "Add an end-to-end SSO redirect test to CI", "owner": "auth-team",
     "due": "2026-10-15", "type": "prevent", "ticket": "AUTH-412"},
    {"what": "Alert on login success rate below 95% for 3 minutes", "owner": "sre-oncall",
     "due": "2026-10-08", "type": "detect", "ticket": "SRE-88"},
]
meta["hypotheses"] = [
    {"id": "H1", "claim": "Redis session store lost data",
     "falsify_with": "redis-cli dbsize showed no drop", "result": "rejected"},
    {"id": "H2", "claim": "SameSite=Strict drops the cookie on the SSO redirect",
     "falsify_with": "reproduced locally with SameSite=Lax and the session survived",
     "result": "confirmed"},
]
meta["five_whys"] = [
    {"level": 1, "why": "Why were users logged out?",
     "because": "The session cookie was not sent after the SSO redirect."},
    {"level": 2, "why": "Why was the cookie not sent?",
     "because": "SameSite=Strict blocks it on a cross-site top-level navigation."},
    {"level": 3, "why": "Why was SameSite set to Strict?",
     "because": "A blanket hardening change shipped with no cross-flow check."},
]
meta["stop_condition"] = "Stopped at 'hardening change had no cross-flow check' -- a " \
                          "process gap, not deeper physics."
meta["contributing_factors"] = [
    "No integration test exercises the SSO redirect path end to end.",
    "The cookie-attribute change was reviewed by someone unfamiliar with the SSO flow.",
]
meta["regression_test"] = "tests/repro_sso_samesite.sh"
p.write_text(text[:m.start(1)] + json.dumps(meta, indent=2) + text[m.end(1):])
PY
}
set_field() {
  # set_field <python expr acting on `meta` dict>
  python3 - "$RECFILE" "$1" <<'PY'
import json, re, pathlib, sys
p = pathlib.Path(sys.argv[1])
text = p.read_text()
m = re.search(r"```json meta\n(.*?)\n```", text, re.S)
meta = json.loads(m.group(1))
exec(sys.argv[2])
p.write_text(text[:m.start(1)] + json.dumps(meta, indent=2) + text[m.end(1):])
PY
}

fill_complete
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 0 $? "lint: a complete record passes"

# each individual rule rejects its own violation, with everything else complete
fill_complete; set_field 'meta["root_cause"] = meta["symptom"]'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects root cause identical to symptom"
has "identical to the symptom"

fill_complete; set_field 'meta["regression_test"] = ""'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects missing regression test"
has "no regression test reference"

fill_complete; set_field 'meta["reproduction"]["command"] = ""'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects missing reproduction"
has "no reproduction recorded"

fill_complete; set_field 'meta["hypotheses"] = []'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects no hypotheses at all"
has "no hypotheses recorded"

fill_complete; set_field 'meta["hypotheses"][0]["falsify_with"] = ""; meta["hypotheses"][1]["falsify_with"] = ""'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects hypotheses with no falsifying evidence"
has "no hypothesis states falsifying evidence"

fill_complete; set_field 'meta["timeline"] = []'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects missing timeline"
has "no timeline recorded"

fill_complete; set_field 'meta["five_whys"] = meta["five_whys"][:1]'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects five-whys with fewer than 2 levels"
has "five-whys has 1 real level"

fill_complete; set_field 'meta["contributing_factors"] = []'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects empty contributing-factors section"
has "contributing-factors section is empty"

# ---------- incident-standard fields ----------
fill_complete; set_field 'meta["action_items"][0]["owner"] = ""'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects an action item with no owner"
has "has no owner"

fill_complete; set_field 'del meta["action_items"][1]["due"]'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects an action item with no due date"
has "has no due date"

fill_complete; set_field 'meta["action_items"][1]["due"] = "next sprint"'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects a due that is not YYYY-MM-DD"

fill_complete; set_field 'meta["action_items"][0]["type"] = "fix"'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects an action item type outside prevent|detect|mitigate"
has "not in ('prevent', 'detect', 'mitigate')"

fill_complete; set_field 'del meta["action_items"][0]["type"]'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects an action item with no type"

fill_complete; set_field 'meta["action_items"] = []'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects a record with no action items"

fill_complete; set_field 'del meta["impact"]'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects missing impact"
has "no impact recorded"

fill_complete; set_field 'del meta["impact"]["revenue_or_sla_impact"]'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects an impact with a missing field"
has "impact.revenue_or_sla_impact missing"

fill_complete; set_field 'meta["impact"]["duration_minutes"] = "about an hour"'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects a non-numeric impact duration"

fill_complete; set_field 'meta["severity"] = "high"'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects a free-text severity"
has "is free text"

fill_complete; set_field 'meta["timeline"][1]["at"] = "2026-09-28T14:05:00"'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects a naive (timezone-less) timestamp"
has "not ISO-8601 with a timezone"

fill_complete; set_field 'meta["timeline"][1]["at"] = "Sept 28, 2pm"'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects a non-ISO timestamp"

fill_complete; set_field 'meta["timeline"][2]["type"] = "panic"'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects an untyped timeline event"

fill_complete; set_field 'meta["timeline"] = [e for e in meta["timeline"] if e["type"] != "resolved"]'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects status fixed with no resolved event"
has "no 'resolved' event"

fill_complete; set_field 'meta["timeline"][4]["at"] = "2026-09-28T13:00:00Z"'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects mitigation before detection"
has "timeline order is impossible"

# fault tree may stand in for five whys when several causes combined
fill_complete; set_field 'meta["five_whys"] = []; meta["fault_tree"] = {"event": "sessions dropped", "gate": "AND", "children": [{"event": "SameSite=Strict shipped"}, {"event": "no SSO e2e test"}]}'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 0 $? "lint: a fault tree with 2 leaf causes replaces five whys"
fill_complete; set_field 'meta["five_whys"] = []; meta["fault_tree"] = {"event": "sessions dropped", "children": [{"event": "a"}, {"event": "b"}]}'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 1 $? "lint: rejects a fault-tree node with children but no AND/OR gate"
has "is not AND/OR"

# blameless language warns, never errors
fill_complete; set_field 'meta["contributing_factors"].append("The engineer should have tested the SSO flow.")'
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 0 $? "lint: blame phrasing is a warning, not an error"
has "blame phrasing 'should have'"

# durations: started 14:00, detected 14:05, mitigated 14:35, resolved 15:05 (UTC)
fill_complete
python3 "$ROOT/scripts/rca.py" durations RCA-0001 --json >$OUT/rca.out 2>&1
rc_is 0 $? "durations: exits 0"
python3 - "$OUT/rca.out" <<'PY' >$OUT/rca.chk 2>&1
import json, sys
d = json.load(open(sys.argv[1]))["RCA-0001"]
assert d == {"time_to_detect": 5.0, "time_to_mitigate": 30.0, "time_to_resolve": 60.0,
             "impact_window": 65.0}, d
PY
rc_is 0 $? "durations: detect 5m, mitigate 30m, resolve 60m, window 65m"
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
has "time to mitigate 30m"
no "blame phrasing"
no "has no ticket"

# restore a fully complete record for the rest of the suite
fill_complete
python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 0 $? "lint: complete record passes again after restore"

# a complete record with no decision link still passes lint, but warns
grep -q "no decision link recorded" $OUT/rca.out && ok "lint: warns (not errors) on no decision link" \
  || bad "lint: missing the no-decision-link warning"

# ---------- index ----------
python3 "$ROOT/scripts/rca.py" index >$OUT/rca.out 2>&1
rc_is 0 $? "index: regenerates cleanly for a complete record"
[ -f "$CONS/docs/engineering/rca/INDEX.md" ] && ok "index: INDEX.md exists" || bad "index: no INDEX.md"
grep -qE "^\| \[RCA-0001\]" "$CONS/docs/engineering/rca/INDEX.md" 2>/dev/null \
  && ok "index: table contains the RCA row" || bad "index: RCA row missing"
grep -qE "\| yes \|" "$CONS/docs/engineering/rca/INDEX.md" 2>/dev/null \
  && ok "index: reports regression test present" || bad "index: regression-test column wrong"

# ---------- link ----------
mkdir -p "$CONS/docs/engineering/decisions"
cat > "$CONS/docs/engineering/decisions/ADR-0001-session-strategy.md" <<'MD'
# ADR-0001: Session strategy
```json meta
{"id":"ADR-0001","title":"Session strategy","status":"accepted",
 "options":[{"name":"A","chosen":true,"why":"x"},{"name":"B","chosen":false,"why_not":"y"}],
 "assumptions":[{"id":"A1","claim":"c","revisit_when":"r"}]}
```
MD
python3 "$ROOT/scripts/rca.py" link RCA-0001 --decision ADR-0001 --assumption A1 \
  --note "SameSite hardening violated the SSO assumption" >$OUT/rca.out 2>&1
rc_is 0 $? "link: exits 0 against an existing decision"
has "linked RCA-0001 -> ADR-0001"
grep -q '"decision": "ADR-0001"' "$RECFILE" && ok "link: decision reference written into the record" \
  || bad "link: decision reference not written"
grep -q '"assumption": "A1"' "$RECFILE" && ok "link: assumption id written into the record" \
  || bad "link: assumption id not written"
grep -q '"status": "violated"' "$RECFILE" && ok "link: violated status recorded" \
  || bad "link: violated status not recorded"

python3 "$ROOT/scripts/rca.py" lint >$OUT/rca.out 2>&1
rc_is 0 $? "lint: still passes after link"
grep -q "no decision link recorded" $OUT/rca.out && bad "lint: still warns after a link was recorded" \
  || ok "lint: warning clears once a decision link is recorded"

# link against a decision that doesn't exist on disk: recorded anyway, with a warning
python3 "$ROOT/scripts/rca.py" link RCA-0001 --decision ADR-9999 >$OUT/rca.out 2>&1
rc_is 0 $? "link: still exits 0 for an unknown decision id"
has "no decision record found for ADR-9999"

# link against an unknown RCA id fails
python3 "$ROOT/scripts/rca.py" link RCA-9999 --decision ADR-0001 >$OUT/rca.out 2>&1
rc_is 2 $? "link: rejects an unknown RCA id"
has "no such RCA record"

cd "$ROOT"

echo
echo "rca: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
