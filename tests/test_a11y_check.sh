#!/usr/bin/env bash
# Regression suite for a11y_check.py. For every check: a planted violation AND a
# clean file that must NOT be flagged. The clean-file assertions are the important
# half -- a static a11y checker with false positives gets disabled, same rationale
# as tests/test_craft_check.sh and tests/test_perf_check.sh.
# Run: bash tests/test_a11y_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
AC="$ROOT/scripts/a11y_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
printf 'export function Base() { return <div>ok</div>; }\n' > src/base.tsx
git add -A; git commit -qm init >/dev/null

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [--only X ...]
  local exp="$1" label="$2"; shift 2
  python3 "$AC" "$@" >$OUT/ac.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-64s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-64s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' $OUT/ac.out; fi
}
has() { grep -q -- "$1" $OUT/ac.out && { PASS=$((PASS+1)); printf '  ok   %-64s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "NOT reported: $1"; }; }
nothas() { grep -q -- "$1" $OUT/ac.out && { FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "false positive: $1"; } \
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
  return <div role="button" tabIndex={0} onClick={onSelect} onKeyDown={onKey}>click me</div>;
}
EOF
expect 0 "onclick-non-interactive: div+onClick+role+tabIndex+key handler is clean" --only onclick-non-interactive --strict
nothas "no role/tabIndex"
nothas "not keyboard-operable"
reset_diff

for tag in section article p img td li; do
  printf 'export function R({ f }) {\n  return <%s onClick={f}>x</%s>;\n}\n' "$tag" "$tag" > "src/bad_$tag.tsx"
  expect 1 "onclick-non-interactive: <$tag onClick> detected" --only onclick-non-interactive
  has "<$tag> has onClick"
  reset_diff
done

printf 'export function R({ f }) {\n  return <div role="button" onClick={f}>x</div>;\n}\n' > src/bad_role1.tsx
printf 'export function R({ f }) {\n  return <span role="button" tabIndex={0} onClick={f}>x</span>;\n}\n' > src/bad_role2.tsx
printf 'export function R({ f }) {\n  return <div role="link" onKeyDown={f}>x</div>;\n}\n' > src/bad_role3.tsx
expect 1 "onclick-non-interactive: widget role missing tabIndex or key handler" --only onclick-non-interactive
has 'bad_role1.tsx:2: <div role="button"> without tabIndex or a key handler'
has 'bad_role2.tsx:2: <span role="button"> without a key handler'
has 'bad_role3.tsx:2: <div role="link"> without tabIndex --'
reset_diff

cat > src/ok_label.tsx <<'EOF'
export function R({ f }) {
  return (<><label onClick={f}>Name</label><div role="presentation">x</div><div role={kind} onClick={f}>y</div></>);
}
EOF
expect 0 "onclick-non-interactive: <label>, presentation role, dynamic role are clean" --only onclick-non-interactive --strict
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
# Tailwind: outline-none without focus-visible:, animate-* without motion-*
# =========================================================================
cat > src/bad_tw_outline.tsx <<'EOF'
export function A() {
  return (<>
    <button className="px-2 outline-none">a</button>
    <input aria-label="q" className="focus:outline-none border" />
  </>);
}
EOF
expect 1 "outline-none-no-focus-visible: Tailwind outline-none / focus:outline-none" --only outline-none-no-focus-visible --strict
has 'bad_tw_outline.tsx:3: `outline-none`'
has 'bad_tw_outline.tsx:4: `focus:outline-none`'
reset_diff

cat > src/ok_tw_outline.tsx <<'EOF'
export function A() {
  return (<>
    <button className="outline-none focus-visible:ring-2 focus-visible:ring-blue-500">a</button>
    <input aria-label="q" className={`focus:outline-none focus:ring-2`} />
    <div className="outline-dashed">x</div>
  </>);
}
EOF
expect 0 "outline-none-no-focus-visible: Tailwind replacement indicator is clean" --only outline-none-no-focus-visible --strict
reset_diff

cat > src/bad_tw_anim.tsx <<'EOF'
export function A() {
  return <span className="h-4 w-4 animate-spin">.</span>;
}
EOF
expect 1 "animation-no-reduced-motion: Tailwind animate-spin unguarded" --only animation-no-reduced-motion --strict
has 'bad_tw_anim.tsx:2: `animate-spin`'
reset_diff

cat > src/ok_tw_anim.tsx <<'EOF'
export function A() {
  return (<>
    <span className="motion-safe:animate-spin">.</span>
    <span className="animate-pulse motion-reduce:animate-none">.</span>
    <span className="animate-none">.</span>
  </>);
}
EOF
expect 0 "animation-no-reduced-motion: motion-safe:/motion-reduce: handling is clean" --only animation-no-reduced-motion --strict
reset_diff

# =========================================================================
# --strict changes the exit code, never the reported severity
# =========================================================================
cat > src/mixed.tsx <<'EOF'
export function A({ f }) {
  return (<>
    <div onClick={f}>x</div>
    <div tabIndex={3}>y</div>
    <input autoFocus aria-label="q" />
  </>);
}
EOF
expect 1 "--strict: advisory findings fail the run" --strict
has "1 blocking, 2 advisory"
has "(--strict: advisory findings fail)"
has "\[ADVISORY\] positive-tabindex"
expect 1 "without --strict: same summary, fails on the blocking finding"
has "1 blocking, 2 advisory"
reset_diff

printf 'export function A() { return <div tabIndex={3}>x</div>; }\n' > src/adv_only.tsx
expect 1 "--strict: an advisory-only diff fails" --only positive-tabindex --strict
has "0 blocking, 1 advisory"
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

# =========================================================================
# adversarial input: bounded time, oversized files reported, never silent
# =========================================================================
# 200KB of unclosed tags of each shape that used to read to end of file per tag.
python3 - <<'EOF'
units = ["<img ", "<a{", "<button>", '<input id="x">', "<img alt='", "<div\n", '<a href="#">']
for k, u in enumerate(units):
    open(f"src/adv{k}.tsx", "w").write(u * (200_000 // len(u)))
with open("src/adv0.tsx", "a") as f:
    f.write('\nexport const Z = () => <img src="/z.png" />;\n')
EOF
start=$(python3 -c 'import time; print(time.time())')
python3 "$AC" >$OUT/ac.out 2>&1; got=$?
secs=$(python3 -c "import time; print(round(time.time() - $start, 2))")
if python3 -c "import sys; sys.exit(0 if $secs < 5 else 1)"; then
  PASS=$((PASS+1)); printf '  ok   %-64s\n' "7 x 200KB adversarial files scanned in ${secs}s (< 5s)"
else FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "adversarial files took ${secs}s (>= 5s)"; fi
if [ "$got" -eq 0 ] || [ "$got" -eq 1 ]; then PASS=$((PASS+1)); printf '  ok   %-64s\n' "adversarial run completed with a verdict (exit $got)"
else FAIL=$((FAIL+1)); printf '  FAIL %-64s\n' "adversarial run crashed (exit $got)"; sed 's/^/       /' $OUT/ac.out; fi
has "src/adv0.tsx:2: "
reset_diff

python3 -c 'open("src/huge.tsx", "w").write("export const A = () => <img src=\"/a.png\" />;\n" + "// pad\n" * 400_000)'
expect 0 "file over the size cap is skipped, not scanned" --only img-no-alt
has "file-too-large"
has "src/huge.tsx: over 2 MB -- NOT scanned"
expect 1 "a skipped file still fails --strict" --only img-no-alt --strict
reset_diff

echo
echo "a11y_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
