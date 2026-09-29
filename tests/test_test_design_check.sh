#!/usr/bin/env bash
# Regression suite for test_design_check.py. Asserts detection AND absence of
# false positives -- per skills/test-design, a false positive is what gets a
# checker deleted, so the clean-file assertions are the important half.
# Run: bash tests/test_test_design_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
TC="$ROOT/scripts/test_design_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src tests
printf 'def add(a, b):\n    return a + b\n' > src/core.py
printf 'from src.core import add\ndef test_add_returns_sum():\n    assert add(1, 2) == 3\n' > tests/test_core.py
git add -A; git commit -qm init

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X ...]
  local exp="$1" label="$2"; shift 2
  python3 "$TC" "$@" >/tmp/tdc.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-55s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-55s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' /tmp/tdc.out; fi
}
has() { grep -q "$1" /tmp/tdc.out && { PASS=$((PASS+1)); printf '  ok   %-55s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "NOT reported: $1"; sed 's/^/       /' /tmp/tdc.out; }; }
nothas() { grep -q "$1" /tmp/tdc.out && { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "false positive: $1"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-55s\n' "no false positive: $1"; }; }

reset_diff() { git add -A >/dev/null 2>&1; git commit -qm wip --allow-empty >/dev/null 2>&1; }

# --- clean change: must pass every check ---
printf 'def add(a,b):\n    return a+b\n\ndef sub(a,b):\n    return a-b\n' > src/core.py
printf '\ndef test_sub_returns_difference():\n    from src.core import sub\n    assert sub(3, 1) == 2\n' >> tests/test_core.py
expect 0 "clean diff produces no blocking findings"
nothas "FAIL"
reset_diff

### --- sleep / real-timer delay (blocking) ---
printf 'import time\ndef test_polls_until_ready():\n    time.sleep(2)\n    assert True\n' > tests/test_sleep.py
printf "it('loads data', () => {\n  setTimeout(() => {}, 100);\n  expect(1).toBe(1);\n});\n" > tests/sleep.test.js
expect 1 "sleep in test detected (blocking)" --only sleep
has "test_sleep.py"; has "sleep.test.js"
rm tests/test_sleep.py tests/sleep.test.js

# clock frozen in the file -- must NOT flag
printf 'import time\nfrom freezegun import freeze_time\n@freeze_time("2020-01-01")\ndef test_waits_with_frozen_clock():\n    time.sleep(0)\n    assert True\n' > tests/test_frozen.py
expect 0 "sleep under a frozen clock is not flagged" --only sleep
nothas "test_frozen.py"
rm tests/test_frozen.py
reset_diff

### --- real current time, uninjected (advisory) ---
printf 'import datetime\ndef test_stamps_event():\n    ts = datetime.datetime.now()\n    assert ts is not None\n' > tests/test_now.py
expect 0 "real-clock use is advisory, not blocking" --only realtime
has "test_now.py"
rm tests/test_now.py

printf 'import time_machine\ndef test_stamps_event_at_fixed_time():\n    with time_machine.travel("2020-01-01"):\n        import datetime\n        assert datetime.datetime.now()\n' > tests/test_now_frozen.py
expect 0 "time_machine-frozen real-clock use is not flagged" --only realtime
nothas "test_now_frozen.py"
rm tests/test_now_frozen.py
reset_diff

### --- assertion count (advisory) ---
printf 'def test_configures_widget():\n    assert 1 == 1\n    assert 2 == 2\n    assert 3 == 3\n    assert 4 == 4\n    assert 5 == 5\n' > tests/test_many.py
expect 0 "5 assertions over default-4 threshold is advisory" --only assert-count
has "test_many.py"
rm tests/test_many.py

printf 'def test_configures_widget():\n    assert 1 == 1\n    assert 2 == 2\n' > tests/test_few.py
expect 0 "2 assertions under threshold is clean" --only assert-count
nothas "test_few.py"
rm tests/test_few.py
reset_diff

### --- test naming as specification (blocking) ---
printf 'def test_1():\n    assert 1 == 1\n' > tests/test_numbered.py
printf 'def testFoo():\n    assert 1 == 1\n' > tests/test_camel.py
printf "it('works', () => { expect(1).toBe(1); });\n" > tests/vague.test.js
expect 1 "non-descriptive test names detected" --only test-name
has "test_1"; has "testFoo"; has "'works'"
rm tests/test_numbered.py tests/test_camel.py tests/vague.test.js

printf 'def test_handles_empty_input():\n    assert 1 == 1\n' > tests/test_named.py
printf "it('returns the cached value on a second call', () => { expect(1).toBe(1); });\n" > tests/named.test.js
printf 'package s\n\nimport "testing"\n\nfunc TestAdd(t *testing.T) {\n if 1+1 != 2 { t.Fatal("x") }\n}\n' > tests/s_test.go
expect 0 "behaviour-describing names, incl. Go's TestAdd convention, pass" --only test-name
nothas "test_named.py"; nothas "named.test.js"; nothas "TestAdd"
rm tests/test_named.py tests/named.test.js tests/s_test.go
reset_diff

### --- single-value boundary heuristic (advisory, added files only) ---
printf 'def test_clamps_length():\n    assert clamp(5) == 5\n' > tests/test_one_value.py
expect 0 "single test at one numeric value is advisory only" --only single-value
has "test_one_value.py"
rm tests/test_one_value.py

printf 'import pytest\n@pytest.mark.parametrize("n,expected", [(0,0),(1,1),(100,100),(101,100)])\ndef test_clamps_length(n, expected):\n    assert clamp(n) == expected\n' > tests/test_table.py
expect 0 "parametrized boundary table is not flagged" --only single-value
nothas "test_table.py"
rm tests/test_table.py
reset_diff

### --- mock ownership (advisory) ---
mkdir -p mypkg
printf 'def widget():\n    return 1\n' > mypkg/widget.py
printf 'from unittest import mock\ndef test_calls_stripe_api():\n    with mock.patch("stripe.Charge.create"):\n        assert True\n' > tests/test_thirdparty_mock.py
expect 0 "mocking a third-party path is advisory" --only mock-thirdparty
has "stripe.Charge.create"
rm tests/test_thirdparty_mock.py

printf 'from unittest import mock\ndef test_calls_widget():\n    with mock.patch("mypkg.widget.widget"):\n        assert True\n' > tests/test_own_mock.py
expect 0 "mocking your own package is not flagged" --only mock-thirdparty
nothas "mypkg.widget.widget"
rm tests/test_own_mock.py
reset_diff

### --- snapshot written in the same diff as the code it approves (advisory) ---
mkdir -p tests/__snapshots__
printf 'def render():\n    return "v2"\n' > src/core.py
printf 'new-snapshot-content-v2\n' > tests/__snapshots__/render.snap
expect 0 "snapshot changed alongside prod code is advisory" --only snapshot-same-diff
has "render.snap"
rm -rf tests/__snapshots__
git checkout -q -- src/core.py 2>/dev/null || true
reset_diff

mkdir -p tests/__snapshots__
printf 'unrelated-snapshot-update\n' > tests/__snapshots__/other.snap
expect 0 "snapshot changed alone (no prod diff) is clean" --only snapshot-same-diff
nothas "other.snap"
rm -rf tests/__snapshots__
reset_diff

### --- refactor + behaviour change in one commit (advisory, >max-files) ---
for i in $(seq 1 16); do printf 'x = %d\n' "$i" > "src/pad_$i.py"; done
printf 'def add(a, b):\n    return a + b + 0\n' > src/core.py
printf 'from src.core import add\ndef test_add_returns_sum():\n    assert add(1, 2) == 4\n' > tests/test_core.py
expect 0 "big diff with a changed expectation + prod change is advisory" --only refactor-behavior --max-files 15
has "test_core.py"
git checkout -q -- src/core.py tests/test_core.py
rm -f src/pad_*.py
reset_diff

for i in $(seq 1 16); do printf 'x = %d\n' "$i" > "src/pad_$i.py"; done
printf 'def add(a, b):\n    return a + b + 0\n' > src/core.py
expect 0 "big diff with NO changed test expectation is clean" --only refactor-behavior --max-files 15
nothas "test_core.py"
git checkout -q -- src/core.py
rm -f src/pad_*.py
reset_diff

echo
echo "test_design_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
