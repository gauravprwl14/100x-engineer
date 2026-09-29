#!/usr/bin/env bash
# Regression suite for a11y_check.py. For every check: a planted violation AND a
# clean file that must NOT be flagged. The clean-file assertions are the important
# half -- a static a11y checker with false positives gets disabled, same rationale
# as tests/test_craft_check.sh and tests/test_perf_check.sh.
# Run: bash tests/test_a11y_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
AC="$ROOT/scripts/a11y_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
printf 'export function Base() { return <div>ok</div>; }\n' > src/base.tsx
git add -A; git commit -qm init >/dev/null

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X ...]
  local exp="$1" label="$2"; shift 2
  python3 "$AC" "$@" >/tmp/ac.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-64s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-64s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' /tmp/ac.out; fi
}
has() { grep -q -- "$1" /tmp/ac.out && { PASS=$((PASS+1)); printf '  ok   %-64s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "NOT reported: $1"; }; }
nothas() { grep -q -- "$1" /tmp/ac.out && { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "false positive: $1"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-64s\n' "no false positive: $1"; }; }
reset_diff() { git checkout -q -- . ; git clean -qfd . ; }

# =========================================================================
# onclick-non-interactive (BLOCKING)
# =========================================================================
cat > src/bad.tsx <<'EOF'
export function Row({ onSelect }) {
  return <div onClick={onSelect}>click me</div>;
}
EOF
expect 1 "onclick-non-interactive: div+onClick, no role/tabIndex" --only onclick-non-interactive
has "no role/tabIndex"
reset_diff

cat > src/ok_role.tsx <<'EOF'
export function Row({ onSelect }) {
  return <div role="button" tabIndex={0} onClick={onSelect}>click me</div>;
}
EOF
expect 0 "onclick-non-interactive: div+onClick+role+tabIndex is clean" --only onclick-non-interactive --strict
nothas "no role/tabIndex"
reset_diff

cat > src/ok_button.tsx <<'EOF'
export function Row({ onSelect }) {
  return <button onClick={onSelect}>click me</button>;
}
EOF
expect 0 "onclick-non-interactive: real <button> is clean" --only onclick-non-interactive --strict
nothas "no role/tabIndex"
reset_diff

# =========================================================================
# img-no-alt (BLOCKING) -- alt="" must NOT be flagged
# =========================================================================
printf 'export function P() { return <img src="/a.png" />; }\n' > src/bad_img.tsx
expect 1 "img-no-alt: <img> with no alt attribute" --only img-no-alt
has "no alt attribute"
reset_diff

printf 'export function P() { return <img src="/a.png" alt="a photo of a cat" />; }\n' > src/ok_alt.tsx
expect 0 "img-no-alt: <img> with real alt text is clean" --only img-no-alt --strict
nothas "no alt attribute"
reset_diff

printf 'export function P() { return <img src="/a.png" alt="" />; }\n' > src/ok_alt_empty.tsx
expect 0 "img-no-alt: alt=\"\" (decorative) is clean, not a missing-alt violation" --only img-no-alt --strict
nothas "no alt attribute"
reset_diff

# =========================================================================
# img-no-dimensions (advisory) -- CLS risk
# =========================================================================
printf 'export function P() { return <Image src="/a.png" alt="x" />; }\n' > src/bad_dims.tsx
expect 1 "img-no-dimensions: <Image> with no width/height/fill/aspect-ratio" --only img-no-dimensions --strict
has "CLS risk"
reset_diff

printf 'export function P() { return <Image src="/a.png" alt="x" width={200} height={100} />; }\n' > src/ok_wh.tsx
expect 0 "img-no-dimensions: width+height is clean" --only img-no-dimensions --strict
nothas "CLS risk"
reset_diff

printf 'export function P() { return <Image src="/a.png" alt="x" fill />; }\n' > src/ok_fill.tsx
expect 0 "img-no-dimensions: fill is clean" --only img-no-dimensions --strict
nothas "CLS risk"
reset_diff

# =========================================================================
# form-field-no-label (BLOCKING)
# =========================================================================
printf 'export function F() { return <input type="text" />; }\n' > src/bad_input.tsx
expect 1 "form-field-no-label: <input> with no id/aria-label" --only form-field-no-label
has "no accessible label"
reset_diff

cat > src/ok_label.tsx <<'EOF'
export function F() {
  return (
    <div>
      <label htmlFor="email">Email</label>
      <input id="email" type="text" />
    </div>
  );
}
EOF
expect 0 "form-field-no-label: id paired with label htmlFor is clean" --only form-field-no-label --strict
nothas "no accessible label"
reset_diff

printf 'export function F() { return <input type="text" aria-label="Search" />; }\n' > src/ok_arialabel.tsx
expect 0 "form-field-no-label: aria-label is clean" --only form-field-no-label --strict
nothas "no accessible label"
reset_diff

printf 'export function F() { return <input type="hidden" name="csrf" />; }\n' > src/ok_hidden.tsx
expect 0 "form-field-no-label: type=hidden is exempt" --only form-field-no-label --strict
nothas "no accessible label"
reset_diff

# =========================================================================
# control-no-accessible-name (BLOCKING)
# =========================================================================
cat > src/bad_icon.tsx <<'EOF'
export function Del() {
  return <button onClick={onDelete}><TrashIcon /></button>;
}
EOF
expect 1 "control-no-accessible-name: icon-only button, no aria-label" --only control-no-accessible-name
has "no accessible name"
reset_diff

cat > src/ok_iconlabel.tsx <<'EOF'
export function Del() {
  return <button onClick={onDelete} aria-label="Delete item"><TrashIcon /></button>;
}
EOF
expect 0 "control-no-accessible-name: icon-only + aria-label is clean" --only control-no-accessible-name --strict
nothas "no accessible name"
reset_diff

cat > src/ok_icontext.tsx <<'EOF'
export function Del() {
  return <button onClick={onDelete}><TrashIcon /> Delete</button>;
}
EOF
expect 0 "control-no-accessible-name: icon + visible text is clean" --only control-no-accessible-name --strict
nothas "no accessible name"
reset_diff

# =========================================================================
# outline-none-no-focus-visible (advisory)
# =========================================================================
cat > src/bad_outline.css <<'EOF'
button { outline: none; }
EOF
expect 1 "outline-none-no-focus-visible: outline:none with no :focus-visible" --only outline-none-no-focus-visible --strict
has "focus indicator"
reset_diff

cat > src/ok_outline.css <<'EOF'
button { outline: none; }
button:focus-visible { outline: 2px solid blue; }
EOF
expect 0 "outline-none-no-focus-visible: :focus-visible replacement present is clean" --only outline-none-no-focus-visible --strict
nothas "focus indicator"
reset_diff

# =========================================================================
# positive-tabindex (advisory)
# =========================================================================
printf 'export function A() { return <div tabIndex={3}>x</div>; }\n' > src/bad_tabindex.tsx
expect 1 "positive-tabindex: tabIndex={3} detected" --only positive-tabindex --strict
has "is positive"
reset_diff

printf 'export function A() { return (<><div tabIndex={0}>x</div><div tabIndex={-1}>y</div></>); }\n' > src/ok_tabindex.tsx
expect 0 "positive-tabindex: tabIndex 0 and -1 are clean" --only positive-tabindex --strict
nothas "is positive"
reset_diff

# =========================================================================
# anchor-no-href (advisory)
# =========================================================================
printf 'export function A() { return <a onClick={go}>Go</a>; }\n' > src/bad_anchor.tsx
expect 1 "anchor-no-href: <a onClick> with no href" --only anchor-no-href --strict
has "used as a button"
reset_diff

printf 'export function A() { return <a href="/go" onClick={go}>Go</a>; }\n' > src/ok_anchor.tsx
expect 0 "anchor-no-href: <a href onClick> is clean" --only anchor-no-href --strict
nothas "used as a button"
reset_diff

# =========================================================================
# unknown-aria-attribute (advisory) -- typo detection
# =========================================================================
printf 'export function A() { return <div aria-lable="x">y</div>; }\n' > src/bad_aria.tsx
expect 1 "unknown-aria-attribute: aria-lable typo detected" --only unknown-aria-attribute --strict
has "aria-lable"
reset_diff

printf 'export function A() { return <div aria-label="x" aria-hidden="true">y</div>; }\n' > src/ok_aria.tsx
expect 0 "unknown-aria-attribute: valid aria-label/aria-hidden are clean" --only unknown-aria-attribute --strict
nothas "not a known ARIA attribute"
reset_diff

# =========================================================================
# autofocus (advisory)
# =========================================================================
printf 'export function A() { return <input autoFocus />; }\n' > src/bad_autofocus.tsx
expect 1 "autofocus: autoFocus detected" --only autofocus --strict
has "autoFocus"
reset_diff

printf 'export function A() { return <input />; }\n' > src/ok_autofocus.tsx
expect 0 "autofocus: no autoFocus is clean" --only autofocus --strict
nothas "autoFocus --"
reset_diff

# =========================================================================
# animation-no-reduced-motion (advisory)
# =========================================================================
cat > src/bad_anim.css <<'EOF'
.spin { animation: spin 1s linear infinite; }
EOF
expect 1 "animation-no-reduced-motion: animation with no reduced-motion guard" --only animation-no-reduced-motion --strict
has "prefers-reduced-motion guard"
reset_diff

cat > src/ok_anim_guard.css <<'EOF'
.spin { animation: spin 1s linear infinite; }
@media (prefers-reduced-motion: reduce) {
  .spin { animation: none; }
}
EOF
expect 0 "animation-no-reduced-motion: guard present in file is clean" --only animation-no-reduced-motion --strict
nothas "prefers-reduced-motion guard"
reset_diff

cat > src/ok_anim_zero.css <<'EOF'
.x { transition: color 0s; }
EOF
expect 0 "animation-no-reduced-motion: zero-duration transition is clean" --only animation-no-reduced-motion --strict
nothas "prefers-reduced-motion guard"
reset_diff

# =========================================================================
# blocking vs advisory exit-code contract
# =========================================================================
printf 'export function A() { return <div tabIndex={3}>x</div>; }\n' > src/adv.tsx
expect 0 "advisory finding does NOT fail without --strict" --only positive-tabindex
reset_diff

printf 'export function A() { return <img src="/a.png" />; }\n' > src/blk.tsx
expect 1 "blocking finding fails even without --strict" --only img-no-alt
reset_diff

# =========================================================================
# diff-scoping: a pre-existing violation untouched by the diff is not re-flagged
# =========================================================================
cat > src/legacy.tsx <<'EOF'
export function Legacy() {
  return <img src="/x.png" />;
}
EOF
git add -A; git commit -qm "pre-existing violation, committed to baseline" >/dev/null
printf '\nexport function Extra() { return <div>hi</div>; }\n' >> src/legacy.tsx
expect 0 "diff-scoping: untouched pre-existing violation is not re-flagged" --only img-no-alt --strict
nothas "no alt attribute"
git checkout -q -- src/legacy.tsx

echo
echo "a11y_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
