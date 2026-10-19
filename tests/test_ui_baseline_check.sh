#!/usr/bin/env bash
# Regression suite for ui_baseline_check.py: each check gets a planted violation
# AND a clean file that must not be flagged, plus diff-scoping, the severity
# contract, subfolder runs and the exit-2 refusal outside a repository.
# Run: bash tests/test_ui_baseline_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; NOREPO="$(mktemp -d)"
trap 'rm -rf "$TMP" "$OUT" "$NOREPO"' EXIT
UB="$ROOT/scripts/ui_baseline_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
printf 'export const Base = () => <div>ok</div>;\n' > src/base.tsx
git add -A; git commit -qm init >/dev/null

PASS=0; FAIL=0
expect() { # expect <exit> <label> [args...]
  local exp="$1" label="$2"; shift 2
  python3 "$UB" "$@" >"$OUT/u.out" 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-66s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-66s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' "$OUT/u.out"; fi
}
has() { grep -q -- "$1" "$OUT/u.out" && { PASS=$((PASS+1)); printf '  ok   %-66s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-66s\n' "NOT reported: $1"; sed 's/^/       /' "$OUT/u.out"; }; }
nothas() { grep -q -- "$1" "$OUT/u.out" && { FAIL=$((FAIL+1)); printf '  FAIL %-66s\n' "false positive: $1"; sed 's/^/       /' "$OUT/u.out"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-66s\n' "no false positive: $1"; }; }
reset_diff() { git checkout -q -- . ; git clean -qfd . ; }

# ---------------------------------------------------------------- fixed-width
cat > src/bad.css <<'EOF'
.page { width: 1200px; }
.panel {
  min-width: 1000px;
}
EOF
printf 'export const P = () => <div className="w-[1200px] p-4">x</div>;\n' > src/BadTw.tsx
printf "export const S = () => <div style={{ minWidth: '960px' }}>x</div>;\n" > src/BadStyle.tsx
expect 1 "fixed-width: css width/min-width, tailwind w-[..], inline style" --only fixed-width
has "src/bad.css:1: \`width: 1200px\`"
has "src/bad.css:3: \`min-width: 1000px\`"
has "src/BadTw.tsx:1: \`w-\[1200px\]\`"
has "src/BadStyle.tsx:1: inline style minWidth: 960px"
has "WCAG 2.2 SC 1.4.10"
reset_diff

cat > src/ok.css <<'EOF'
/* width: 1200px in a comment is not a declaration */
.card { width: 320px; }
.page { width: 1200px; max-width: 100%; }
@media (min-width: 1024px) { .wide { width: 1200px; } }
@media print { .sheet { width: 800px; } }
table.data { min-width: 1000px; }
.shell { max-width: 1200px; }
EOF
printf 'export const P = () => <div className="w-full md:w-[1200px] max-w-[1200px]">x</div>;\n' > src/OkTw.tsx
printf 'export const T = () => <table className="min-w-[900px]"><tbody /></table>;\n' > src/OkTable.tsx
expect 0 "fixed-width: fluid cap, min-width media, print, table, max-width clean" --only fixed-width --strict
nothas "fixed-width"
reset_diff

# -------------------------------------------------------------- viewport-zoom
cat > index.html <<'EOF'
<!doctype html>
<html><head>
  <title>App</title>
</head><body></body></html>
EOF
expect 1 "viewport-zoom: html entry with no viewport meta" --only viewport-zoom
has 'index.html:2: <head> has no <meta name="viewport">'
reset_diff

printf '<html><head>\n<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">\n</head></html>\n' > zoom.html
expect 1 "viewport-zoom: user-scalable=no and maximum-scale=1" --only viewport-zoom
has "user-scalable=no, maximum-scale=1 (< 2)"
reset_diff

printf '<html><head>\n<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5">\n</head></html>\n' > ok.html
printf '<div class="fragment">no head here</div>\n' > partial.html
expect 0 "viewport-zoom: zoomable viewport and a head-less partial are clean" --only viewport-zoom --strict
reset_diff

# ------------------------------------------------------------------ raw-color
cat > src/Badge.tsx <<'EOF'
export const Badge = () => (
  <span style={{ color: '#ff0000' }} className="bg-[#00ff00]">x</span>
);
EOF
printf '.btn { background: rgb(10, 20, 30); }\n' > src/btn.css
expect 0 "raw-color: no token file in repo -> advisory only" --only raw-color
has "\[ADVISORY\] raw-color"
has "no token/theme file found"
expect 1 "raw-color: advisory still fails under --strict" --only raw-color --strict
reset_diff

mkdir -p src/theme; printf 'export const color = { danger: "#d00" };\n' > src/theme/tokens.ts
git add -A; git commit -qm tokens >/dev/null
cat > src/Badge.tsx <<'EOF'
export const Badge = () => (
  <span style={{ color: '#ff0000' }} className="bg-[#00ff00]">x</span>
);
EOF
printf '.btn { background: rgb(10, 20, 30); }\n' > src/btn.css
expect 1 "raw-color: token file present -> blocking" --only raw-color
has "\[FAIL\] raw-color"
has "src/Badge.tsx:2: raw color #ff0000"
has "raw color \[#00ff00\]"
has "src/btn.css:1: raw color"
reset_diff

cat > src/Ok.tsx <<'EOF'
export const Ok = () => (
  <a href="#add" id="#cafe" className="text-danger" style={{ color: color.danger }}>x</a>
);
EOF
printf ':root { --brand: #0055ff; }\n.btn { color: var(--brand); }\n' > src/ok.css
printf 'export const color2 = { ok: "#0f0" };\n' > src/theme/tokens.ts
expect 0 "raw-color: anchors, custom properties, token file itself are clean" --only raw-color --strict
reset_diff

# ------------------------------------------------------------ fetch-no-states
cat > src/List.tsx <<'EOF'
'use client';
export function List() {
  const { data } = useQuery({ queryKey: ['items'], queryFn: getItems });
  return <ul>{data.map((i) => <li key={i.id}>{i.name}</li>)}</ul>;
}
EOF
expect 0 "fetch-no-states: advisory, exits 0 without --strict" --only fetch-no-states
has "src/List.tsx:3: fetches data but never branches on loading or error"
reset_diff

cat > src/OkList.tsx <<'EOF'
export function OkList() {
  const { data, isPending, isError } = useQuery({ queryKey: ['i'], queryFn: getItems });
  if (isPending) return <Skeleton />;
  if (isError) return <ErrorState />;
  return <ul>{data.map((i) => <li key={i.id}>{i.name}</li>)}</ul>;
}
EOF
mkdir -p app/items
printf 'export default async function Page() {\n  const r = await fetch("https://x.test/items");\n  return <pre>{await r.text()}</pre>;\n}\n' > app/items/page.tsx
expect 0 "fetch-no-states: handled states and an app/ server component are clean" --only fetch-no-states --strict
reset_diff

# ---------------------------------------------------------- overflow-x-hidden
printf 'html, body { overflow-x: hidden; }\n' > src/global.css
expect 0 "overflow-x-hidden: advisory on html/body" --only overflow-x-hidden
has "src/global.css:1: \`overflow-x: hidden\` on html, body"
reset_diff

printf '.carousel { overflow-x: hidden; }\n.tbody-wrap { overflow-x: auto; }\n' > src/carousel.css
expect 0 "overflow-x-hidden: a component container is clean" --only overflow-x-hidden --strict
reset_diff

# ------------------------------------------------------------- diff scoping
printf '.legacy { width: 1400px; }\n' > src/legacy.css
git add -A; git commit -qm legacy >/dev/null
printf '.legacy-new { color: inherit; }\n' >> src/legacy.css
expect 0 "diff-scoping: untouched pre-existing fixed width is not re-flagged" --only fixed-width --strict
git checkout -q -- src/legacy.css

# ---------------------------------------------- subfolder run and refusals
mkdir -p apps/web/src; printf '.a { color: inherit; }\n' > apps/web/src/a.css
git add -A; git commit -qm web >/dev/null
printf '.a { width: 1100px; }\n' > apps/web/src/a.css
( cd apps/web && python3 "$UB" --only fixed-width ) >"$OUT/u.out" 2>&1; got=$?
[ "$got" -eq 1 ] && { PASS=$((PASS+1)); echo "  ok   subfolder run sees the root-relative diff"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL subfolder run exit=$got"; cat "$OUT/u.out"; }
has "apps/web/src/a.css:1"
git checkout -q -- apps/web/src/a.css

( cd "$NOREPO" && python3 "$UB" ) >"$OUT/u.out" 2>&1; got=$?
[ "$got" -eq 2 ] && { PASS=$((PASS+1)); echo "  ok   outside a git repo exits 2"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL outside a git repo exit=$got"; }
has "not inside a git repository"
expect 2 "unresolvable --base exits 2" --base no-such-ref
expect 2 "unknown --only check exits 2" --only nope
expect 0 "clean tree: no changes to inspect"
has "no changes to inspect"

echo
echo "ui_baseline_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
