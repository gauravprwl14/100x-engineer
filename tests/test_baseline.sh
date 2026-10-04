#!/usr/bin/env bash
# Regression suite for baseline.py: lint catches malformed items, show filters by
# work type, load tier and risk. Asserts detection AND absence of false positives.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
OUT="$TMP/out"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-58s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "$1"; [ -s "$OUT" ] && sed 's/^/       /' "$OUT" | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -qF -- "$1" "$OUT" && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -qF -- "$1" "$OUT" && bad "false positive: $1" || ok "absent: $1"; }
B="$ROOT/scripts/baseline.py"

# ---------- lint: the shipped catalogue is clean ----------
python3 "$B" lint >"$OUT" 2>&1
rc_is 0 $? "lint: shipped baseline.json passes"
has "baseline is valid"

# ---------- lint: each defect detected on its own ----------
# mutate() writes a copy of the real catalogue with ONE item changed by a python expr
mutate() {
  python3 - "$ROOT/scripts/data/baseline.json" "$TMP/b.json" "$1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
items = {i["id"]: i for i in d["items"]}
exec(sys.argv[3])
json.dump(d, open(sys.argv[2], "w"))
PY
}
lint_bad() {  # $1 = mutation, $2 = expected message, $3 = label
  mutate "$1"
  python3 "$B" lint --file "$TMP/b.json" >"$OUT" 2>&1
  rc_is 1 $? "lint rejects: $3"
  has "$2"
}
lint_bad 'items["api.authz-every-endpoint"]["source"] = ""' "no source" "missing source"
lint_bad 'items["api.rate-limit"]["enforced_by"] = "make sure it is fine"' "enforced_by" "prose enforced_by"
lint_bad 'items["api.rate-limit"]["enforced_by"] = "100x no_such_tool"' "is not a plugin tool" "100x tool that does not exist"
lint_bad 'd["items"].append(dict(items["api.rate-limit"]))' "duplicate id" "duplicate id"
lint_bad 'items["ask.data-residency"]["default"] = "EU"' "null default" "C item with a default"
lint_bad 'items["ask.data-residency"]["ask"] = ""' "needs an \`ask\`" "C item with no ask"
lint_bad 'items["api.rate-limit"]["owner_skill"] = "no-such-skill"' "does not exist and is not a known pending skill" "unknown owner skill"
lint_bad 'items["api.rate-limit"]["from_tier"] = "prototype"' "class B is tier-dependent" "B item on at prototype"
lint_bad 'items["api.rate-limit"]["risk"] = "extreme"' "risk must be one of" "invalid risk"
lint_bad 'items["api.rate-limit"]["blocks_ready"] = True' "only to class C" "blocks_ready on a non-C item"

# no false positive: a pending skill and an external command are accepted
mutate 'items["api.rate-limit"]["owner_skill"] = "qa-strategy"; items["api.rate-limit"]["enforced_by"] = "npx k6 run load.js"'
python3 "$B" lint --file "$TMP/b.json" >"$OUT" 2>&1
rc_is 0 $? "lint accepts a pending owner skill and an external tool"

# ---------- show: filters ----------
ids() { python3 "$B" show "$@" --json | python3 -c 'import json,sys;print("\n".join(i["id"] for i in json.load(sys.stdin)["items"]))'; }

ids --work api,iac --tier small --risk regulated >"$OUT"
has "all.audit-trail"
has "all.privacy-impact-assessment"
has "ask.compliance-regime"
has "ask.data-residency"
no "iac.multi-region"
no "iac.multi-az"
no "api.rate-limit"
no "web-ui.reflow-320"

ids --work iac --tier scale --risk none >"$OUT"
has "iac.multi-region"
has "iac.multi-az"
no "all.audit-trail"
no "ask.data-residency"

ids --work web-ui --tier prototype --risk none >"$OUT"
has "web-ui.reflow-320"
has "all.wcag-aa-floor"
no "web-ui.core-web-vitals"
no "api.authz-every-endpoint"
no "all.pii-out-of-logs"

ids --work public-api --tier prototype --risk none >"$OUT"
has "api.authz-every-endpoint"
has "ask.api-audience"

python3 "$B" show --work web-ui --tier small >"$OUT" 2>&1
rc_is 0 $? "show: human output runs"
has "source: W3C WCAG 2.2"

python3 "$B" show --work nosuch --tier small >"$OUT" 2>&1
rc_is 2 $? "show: unknown work type rejected"
python3 "$B" show --work api --tier huge >"$OUT" 2>&1
rc_is 2 $? "show: unknown tier rejected"
python3 "$B" show --work api >"$OUT" 2>&1
rc_is 2 $? "show: tier is required"

echo
echo "baseline: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
