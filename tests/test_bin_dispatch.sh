#!/usr/bin/env bash
# bin/100x must run plugin tools from a project that is not this repo — the way the
# plugin is actually used once installed — and must refuse anything that is not a tool.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/bin/100x"
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }

# a foreign repo with a bad component, committed base + a change under test
REPO="$OUT/foreign"; mkdir -p "$REPO/apps/web/src"
git -C "$REPO" init -q
git -C "$REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m base
cat > "$REPO/apps/web/src/Card.tsx" <<'EOF'
export function Card() {
  return <div onClick={() => go()}><img src="/x.png" /></div>;
}
EOF
git -C "$REPO" add -A

( cd "$REPO" && "$BIN" a11y_check --base HEAD >"$OUT/a.out" 2>&1 ); rc=$?
[ "$rc" -ne 0 ] && grep -qi "img\|alt\|click" "$OUT/a.out" \
  && ok "a11y_check via 100x from a foreign repo detects the bad component" \
  || { bad "a11y_check via 100x from a foreign repo (rc=$rc)"; sed 's/^/       /' "$OUT/a.out"; }

( cd "$REPO/apps/web" && "$BIN" a11y_check --base HEAD >"$OUT/b.out" 2>&1 ); rc=$?
[ "$rc" -ne 0 ] && ok "same check from a monorepo subfolder still detects" \
  || bad "subfolder run passed silently (rc=$rc)"

"$BIN" unknown_tool >/dev/null 2>&1; [ $? -eq 2 ] && ok "unknown tool exits 2" || bad "unknown tool exit code"
"$BIN" ../hooks/require_verification >/dev/null 2>&1; [ $? -eq 2 ] && ok "path traversal refused" || bad "path traversal accepted"
"$BIN" 01_harvest_candidates >/dev/null 2>&1; [ $? -eq 2 ] && ok "research pipeline script is not a tool" || bad "pipeline script exposed"
"$BIN" _mutation_guard >/dev/null 2>&1; [ $? -eq 2 ] && ok "private helper is not a tool" || bad "helper exposed"
[ "$("$BIN" root)" = "$ROOT" ] && ok "100x root prints the plugin root" || bad "100x root"
"$BIN" list | grep -qx "  a11y_check" && ok "100x list names the tools" || bad "100x list"

# a symlinked bin (how a PATH entry may point at it) still resolves the root
ln -s "$BIN" "$OUT/100x-link"
[ "$("$OUT/100x-link" root)" = "$ROOT" ] && ok "symlinked entry resolves the real root" || bad "symlink root"

# no SKILL.md may fall back to a plugin-relative script path
if grep -rnE 'python3 "?scripts/[a-z]' "$ROOT/skills" "$ROOT/reviewers" "$ROOT/docs" >"$OUT/rel.out"; then
  bad "plugin-relative script paths remain"; sed 's/^/       /' "$OUT/rel.out" | head -10
else ok "no plugin-relative 'python3 scripts/' paths in skills, reviewers, docs"; fi

echo
echo "bin_dispatch: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
