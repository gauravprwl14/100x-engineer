#!/usr/bin/env bash
# The plugin promises to run on the stock interpreter, and macOS ships Python 3.9 as
# /usr/bin/python3. A 3.10+ construct (tomllib, a match statement, `X | None` evaluated
# at import) passes every other suite on a newer python3 and fails only there, where
# vet_dep once dropped every pyproject dependency and exited 0. With /usr/bin/python3
# present this compiles every script and hook with it, runs every tool's --help, and
# reruns a smoke subset of suites with python3 resolving to it. Without it: skipped.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY39="${PY39:-/usr/bin/python3}"
# macOS without the command-line tools has a /usr/bin/python3 stub that only offers
# to install them; it cannot run anything, so it counts as absent.
if [ ! -x "$PY39" ] || ! "$PY39" -c 'import sys' >/dev/null 2>&1; then
  echo "py39: $PY39 not present -- skipped"
  exit 0
fi
VER="$("$PY39" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
SHIM="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$SHIM" "$OUT"' EXIT
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-64s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "$1"; sed 's/^/       /' "$OUT/r.out" | tail -8; }
echo "py39: interpreter $PY39 (Python $VER)"

# (a) compile in memory, so no __pycache__ lands in the tree
for f in "$ROOT"/scripts/*.py "$ROOT"/hooks/*.py; do
  rel="${f#$ROOT/}"
  if "$PY39" -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' \
       "$f" >"$OUT/r.out" 2>&1; then ok "compiles: $rel"
  else bad "does not compile under $VER: $rel"; fi
done

# --help imports the module and builds its parser: catches import-time 3.10+ use
for f in "$ROOT"/scripts/[a-z]*.py; do
  rel="${f#$ROOT/}"
  ( cd "$OUT" && "$PY39" "$f" --help ) >"$OUT/r.out" 2>&1
  if grep -q '^Traceback' "$OUT/r.out"; then bad "--help crashes under $VER: $rel"
  else ok "--help runs: $rel"; fi
done

# (b) smoke suites with python3 -> the 3.9 interpreter
ln -s "$PY39" "$SHIM/python3"
for t in test_vet_dep test_schema_check test_git_root; do
  if PATH="$SHIM:$PATH" bash "$ROOT/tests/$t.sh" >"$OUT/r.out" 2>&1; then
    ok "$t.sh passes under $VER ($(tail -1 "$OUT/r.out" | sed 's/^[^:]*: //'))"
  else bad "$t.sh fails under $VER"; fi
done
if [ "$(PATH="$SHIM:$PATH" python3 -c 'import sys; print(sys.executable)')" = "$("$PY39" -c 'import sys; print(sys.executable)')" ]; then
  ok "smoke suites really ran on $VER"
else bad "PATH shim did not take effect"; fi

echo
echo "py39: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
