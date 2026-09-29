#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
A="$ROOT/scripts/audit_ci_gates.py"
PASS=0; FAIL=0
t() { python3 "$A" "$2" >/tmp/cg.out 2>&1; local got=$?
  if [ "$got" -eq "$1" ]; then PASS=$((PASS+1)); printf '  ok   %-46s\n' "$3"
  else FAIL=$((FAIL+1)); printf '  FAIL %-46s exp=%s got=%s\n' "$3" "$1" "$got"; sed 's/^/       /' /tmp/cg.out; fi; }
has() { grep -q "$1" /tmp/cg.out && { PASS=$((PASS+1)); printf '  ok   reported: %-34s\n' "$1"; } \
      || { FAIL=$((FAIL+1)); printf '  FAIL NOT reported: %-30s\n' "$1"; }; }

mkdir -p "$TMP/none"; t 0 "$TMP/none" "repo with no CI config"

# a genuinely blocking workflow must stay clean
mkdir -p "$TMP/good/.github/workflows"
cat > "$TMP/good/.github/workflows/ci.yml" <<'EOF'
jobs:
  test:
    steps:
      - run: ruff check .
      - run: mypy --strict src/
      - run: pytest --cov=src --cov-fail-under=85
EOF
t 0 "$TMP/good" "blocking workflow is clean"

# each documented evasion mechanism
mkdir -p "$TMP/coe/.github/workflows"
printf 'jobs:\n t:\n  steps:\n   - continue-on-error: true\n     run: mypy .\n' > "$TMP/coe/.github/workflows/c.yml"
t 1 "$TMP/coe" "continue-on-error detected"; has "cannot block"

mkdir -p "$TMP/ortrue/.github/workflows"
printf 'jobs:\n t:\n  steps:\n   - run: pytest || true\n' > "$TMP/ortrue/.github/workflows/c.yml"
t 1 "$TMP/ortrue" "|| true detected"

mkdir -p "$TMP/sete/scripts"
printf '#!/bin/bash\nset +e\nmypy src/\n' > "$TMP/sete/scripts/lint.sh"
t 1 "$TMP/sete" "set +e detected"

mkdir -p "$TMP/info"
printf 'coverage:\n status:\n  patch:\n   default:\n    informational: true\n' > "$TMP/info/codecov.yml"
t 1 "$TMP/info" "informational coverage detected"

mkdir -p "$TMP/dis/.github/workflows"
touch "$TMP/dis/.github/workflows/tests.yml.disabled"
t 1 "$TMP/dis" "disabled workflow detected"; has "does not run"

mkdir -p "$TMP/zero"
printf '[tool.coverage.report]\nfail_under = 0\n' > "$TMP/zero/pyproject.toml"
t 1 "$TMP/zero" "fail_under = 0 detected"

mkdir -p "$TMP/exitzero/.github/workflows"
printf 'jobs:\n t:\n  steps:\n   - run: flake8 --exit-zero .\n' > "$TMP/exitzero/.github/workflows/c.yml"
t 1 "$TMP/exitzero" "--exit-zero detected"

echo
echo "audit_ci_gates: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
