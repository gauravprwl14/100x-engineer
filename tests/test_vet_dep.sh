#!/usr/bin/env bash
# Exercises the real fetch/parse/verdict code path in scripts/vet_dep.py against
# committed registry fixtures (evals/fixtures/), so this suite needs no network.
# The registry base URLs are swapped for file:// URLs pointing at the fixtures --
# the exact same urllib.request.urlopen() call that hits the real registries.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
V="$ROOT/scripts/vet_dep.py"
FIX="$ROOT/evals/fixtures"
PASS=0; FAIL=0

export VET_DEP_NPM_REGISTRY="file://$FIX/npm"
export VET_DEP_NPM_DOWNLOADS="file://$FIX/npm-downloads"
export VET_DEP_PYPI_REGISTRY="file://$FIX/pypi"

run() { python3 "$V" "$@" >/tmp/vd.out 2>&1; }

t() {  # t <expected-exit> <description> -- args...
  local exp="$1" desc="$2"; shift 2
  run "$@"; local got=$?
  if [ "$got" = "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-58s\n' "$desc"
  else FAIL=$((FAIL+1)); printf '  FAIL %-58s exp=%s got=%s\n' "$desc" "$exp" "$got"
       sed 's/^/       /' /tmp/vd.out; fi
}

has() {  # has <substring> -- checked against the last run's captured output
  if grep -qF -e "$1" /tmp/vd.out; then PASS=$((PASS+1)); printf '  ok   contains: %-46s\n' "$1"
  else FAIL=$((FAIL+1)); printf '  FAIL missing:  %-46s\n' "$1"; fi
}

echo "=== --help works ==="
t 0 "--help exits 0" --help

echo
echo "=== verdicts against fixture data ==="
run express; has "->  ADOPT"; t 0 "healthy multi-maintainer package -> ADOPT (exit 0)" express

run request; has "->  AVOID"; has "deprecated in the registry"
t 1 "deprecated package ->  AVOID (exit 1)" request

run acme-no-license-pkg; has "->  AVOID"; has "no licence declared"
t 1 "missing licence ->  AVOID (exit 1)" acme-no-license-pkg

run lodash; has "->  REVIEW"; has "single maintainer"
t 0 "single-maintainer package ->  REVIEW, not blocking (exit 0)" lodash

echo
echo "=== --json emits valid JSON ==="
python3 "$V" express --json >/tmp/vd.json 2>/tmp/vd.err
if python3 -c "import json,sys; json.load(open('/tmp/vd.json'))" 2>/tmp/vd.jsonerr; then
  PASS=$((PASS+1)); printf '  ok   %-58s\n' "--json output parses as JSON"
else
  FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "--json output parses as JSON"
  cat /tmp/vd.jsonerr | sed 's/^/       /'
fi
python3 -c "
import json
d = json.load(open('/tmp/vd.json'))
assert d['verdict'] == 'ADOPT', d['verdict']
assert d['signals']['name'] == 'express'
" 2>/tmp/vd.jsonerr2 && { PASS=$((PASS+1)); printf '  ok   %-58s\n' "--json payload has verdict + signals"; } \
  || { FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "--json payload has verdict + signals"; cat /tmp/vd.jsonerr2 | sed 's/^/       /'; }

echo
echo "=== --check-manifest reads package.json and pyproject.toml (no network) ==="
TMPD="$(mktemp -d)"; trap 'rm -rf "$TMPD"' EXIT
cat > "$TMPD/package.json" <<'EOF'
{"name": "demo", "dependencies": {"express": "^5.0.0", "left-pad": "^1.3.0"},
 "devDependencies": {"jest": "^29.0.0"}}
EOF
cat > "$TMPD/pyproject.toml" <<'EOF'
[project]
name = "demo"
dependencies = ["pydantic>=2.0", "requests>=2.31"]

[tool.poetry.dependencies]
python = "^3.11"
click = "^8.0"
EOF
( cd "$TMPD" && python3 "$V" --check-manifest --list-only >/tmp/vd.out 2>&1 )
has "npm: 2 direct dep(s)"
has "pypi: 3 direct dep(s)"
has "  express"
has "  left-pad"
has "  pydantic"
has "  requests"
has "  click"
if grep -q "jest" /tmp/vd.out; then
  FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "devDependencies excluded (jest must not appear)"
else
  PASS=$((PASS+1)); printf '  ok   %-58s\n' "devDependencies excluded (jest must not appear)"
fi
( cd "$TMPD" && python3 "$V" --check-manifest --list-only --json >/tmp/vd.out 2>&1 )
python3 -c "
import json
d = json.load(open('/tmp/vd.out'))
assert d['npm'] == ['express', 'left-pad'], d
assert d['pypi'] == ['click', 'pydantic', 'requests'], d
" 2>/tmp/vd.jsonerr3 && { PASS=$((PASS+1)); printf '  ok   %-58s\n' "--check-manifest --list-only --json is exact"; } \
  || { FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "--check-manifest --list-only --json is exact"; cat /tmp/vd.jsonerr3 | sed 's/^/       /'; }

echo
echo "=== no network: fails closed, never silently ==="
( export VET_DEP_NPM_REGISTRY="http://127.0.0.1:1"
  export VET_DEP_NPM_DOWNLOADS="http://127.0.0.1:1/dl"
  python3 "$V" some-package >/tmp/vd.out 2>&1 )
got=$?
if [ "$got" -ne 0 ]; then PASS=$((PASS+1)); printf '  ok   %-58s\n' "unreachable registry exits non-zero"
else FAIL=$((FAIL+1)); printf '  FAIL %-58s got exit 0\n' "unreachable registry exits non-zero"; fi
has "could not reach the registry, cannot vet"

echo
echo "=== a package not found on the registry is reported, not silently passed ==="
run does-not-exist-anywhere-zzz
has "cannot vet"
t 2 "unknown package exits non-zero (not 0, not 1)" does-not-exist-anywhere-zzz

echo
echo "vet_dep: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
