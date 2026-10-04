#!/usr/bin/env bash
# Regression suite: no record writer follows a committed symlink out of the repository.
# A cloned repo can commit AGENTS.md, INDEX.md, a collection directory or the records
# root itself as a symlink to anywhere; every writer must refuse (non-zero) and leave
# the outside directory exactly as it was. A clean control, with symlinks that stay
# inside the repo, must still write.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
S="$ROOT/scripts"
PASS=0; FAIL=0; N=0
ok()  { PASS=$((PASS+1)); printf '  ok   %-66s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL %-66s\n' "$1"; [ -s "$TMP/out" ] && sed 's/^/       /' "$TMP/out" | head -6; }

# new_repo: sets R (a fresh git repo) and X (an empty directory outside it)
new_repo() {
  N=$((N+1)); R="$TMP/repo$N"; X="$TMP/outside$N"; mkdir -p "$R" "$X"
  (cd "$R" && git init -q && git config user.email e@e && git config user.name e \
    && echo x > f.txt && printf '# AGENTS.md\n\n## Gotchas\n\n- existing\n' > AGENTS.md \
    && git add -A && git commit -qm init)
}
snap() { (cd "$X" && find . -type f -exec cksum {} + | sort; find . | sort); }

# refused <label> <cmd...>: run in $R; it must exit non-zero with the containment
# refusal, and $X must be byte-for-byte unchanged (and still empty if it was empty).
refused() {
  local label="$1"; shift
  local before was_empty=0
  before="$(snap)"; [ -z "$(ls -A "$X")" ] && was_empty=1
  (cd "$R" && "$@") >"$TMP/out" 2>&1; local rc=$?
  if [ "$rc" -eq 0 ]; then bad "$label: exited 0"; return; fi
  if ! grep -q "refusing to write" "$TMP/out"; then
    bad "$label: exit $rc without a containment refusal"; return
  fi
  if [ "$was_empty" -eq 1 ] && [ -n "$(ls -A "$X")" ]; then
    bad "$label: outside directory is no longer empty"; return
  fi
  [ "$(snap)" = "$before" ] && ok "$label" || bad "$label: changed a file outside the repo"
}

# Records-root variants. Each takes the collection directory name under the root.
dir_link()      { new_repo; mkdir -p "$R/docs/engineering"; ln -s "$X" "$R/docs/engineering/$1"; }
dir_dangling()  { new_repo; mkdir -p "$R/docs/engineering"; ln -s "$X/missing" "$R/docs/engineering/$1"; }
root_default()  { new_repo; mkdir -p "$R/docs"; ln -s "$X" "$R/docs/engineering"; }
root_config()   { new_repo; echo '{"root": "rec"}' > "$R/.100x.json"; ln -s "$X" "$R/rec"; }
# file variant: the collection directory is real, its INDEX.md (or $2) links outside
file_link()     { new_repo; mkdir -p "$R/docs/engineering/$1"; ln -s "$X/${2:-INDEX.md}" "$R/docs/engineering/$1/${2:-INDEX.md}"; }

LESSON=(add "Run make proto before the build, otherwise the client is stale" --kind gotcha --affects f.txt --source f.txt:1)

echo "--- record creators: collection dir, dangling dir, root via docs/engineering, root via .100x.json ---"
for v in dir_link dir_dangling root_default root_config; do
  $v lessons;   refused "learn add ($v)"   python3 "$S/learn.py" "${LESSON[@]}"
  $v decisions; refused "decide new ($v)"  python3 "$S/decide.py" new "Queue choice"
  $v rca;       refused "rca new ($v)"     python3 "$S/rca.py" new "Checkout outage"
done

echo "--- generated indexes: directory and file variants ---"
for v in dir_link dir_dangling root_default root_config file_link; do
  $v lessons;   refused "learn index ($v)"  python3 "$S/learn.py" index
  $v decisions; refused "decide index ($v)" python3 "$S/decide.py" index
  $v rca;       refused "rca index ($v)"    python3 "$S/rca.py" index
  $v ledger;    refused "ledger index ($v)" python3 "$S/ledger.py" index
  $v ledger MAP.md; refused "ledger map ($v)" python3 "$S/ledger.py" map
done
file_link lessons; refused "learn add (INDEX.md link)" python3 "$S/learn.py" "${LESSON[@]}"
file_link decisions; refused "decide new (INDEX.md link)" python3 "$S/decide.py" new "Queue choice"
file_link rca; refused "rca new (INDEX.md link)" python3 "$S/rca.py" new "Checkout outage"

echo "--- learn promote ---"
promote_repo() { new_repo; (cd "$R" && python3 "$S/learn.py" "${LESSON[@]}" >/dev/null 2>&1); }
promote_repo; mv "$R/AGENTS.md" "$X/AGENTS.md"; ln -s "$X/AGENTS.md" "$R/AGENTS.md"
refused "promote --yes (AGENTS.md links to an existing outside file)" \
  python3 "$S/learn.py" promote LESSON-0001 --yes
refused "promote without --yes is refused too" python3 "$S/learn.py" promote LESSON-0001
promote_repo; rm -f "$R/AGENTS.md"; ln -s "$X/AGENTS.md" "$R/AGENTS.md"
refused "promote --yes (dangling AGENTS.md link)" python3 "$S/learn.py" promote LESSON-0001 --yes
promote_repo; rm -f "$R/AGENTS.md"; ln -s "$X/CLAUDE.md" "$R/CLAUDE.md"; echo '# c' > "$X/CLAUDE.md"
refused "promote --yes (CLAUDE.md links outside)" python3 "$S/learn.py" promote LESSON-0001 --yes
promote_repo
refused "promote --file ../outside" python3 "$S/learn.py" promote LESSON-0001 --file "../outside$N/x.md" --yes
refused "promote --file <absolute outside path>" python3 "$S/learn.py" promote LESSON-0001 --file "$X/x.md" --yes
promote_repo; L1=$(ls "$R"/docs/engineering/lessons/LESSON-0001-*.md)
mv "$L1" "$X/lesson.md"; ln -s "$X/lesson.md" "$L1"; cp "$R/AGENTS.md" "$TMP/agents.before"
refused "promote --yes (the lesson record links outside)" python3 "$S/learn.py" promote LESSON-0001 --yes
cmp -s "$R/AGENTS.md" "$TMP/agents.before" && ok "promote: AGENTS.md untouched when the record is refused" \
  || bad "promote: AGENTS.md written before the record was refused"

echo "--- rca link ---"
new_repo; (cd "$R" && python3 "$S/rca.py" new "Checkout outage" >/dev/null 2>&1)
R1=$(ls "$R"/docs/engineering/rca/RCA-0001-*.md); mv "$R1" "$X/rca.md"; ln -s "$X/rca.md" "$R1"
refused "rca link (the RCA record links outside)" python3 "$S/rca.py" link RCA-0001 --decision ADR-0001

echo "--- ledger shard: source, destination and shard-index variants ---"
adr() { # adr <dir> <n>
  printf '# ADR-%04d: D\n\n```json meta\n{"id":"ADR-%04d","title":"D","status":"accepted","date":"2026-01-15"}\n```\n' \
    "$2" "$2" > "$1/ADR-$(printf %04d "$2")-d.md"
}
shard_repo() { new_repo; D="$R/docs/engineering/decisions"; mkdir -p "$D"; adr "$D" 1; adr "$D" 2; }
unmoved() { [ -f "$D/ADR-0001-d.md" ] && [ ! -L "$D/ADR-0001-d.md" ] && ok "$1: no record moved" || bad "$1: a record was moved"; }
shard_repo; ln -s "$X" "$D/2026"
refused "shard --yes (destination year dir links outside)" python3 "$S/ledger.py" shard --force --yes; unmoved "destination link"
shard_repo; ln -s "$X/missing" "$D/2026"
refused "shard --yes (destination year dir dangles outside)" python3 "$S/ledger.py" shard --force --yes; unmoved "dangling destination"
shard_repo; mv "$D/ADR-0002-d.md" "$X/ADR-0002-d.md"; ln -s "$X/ADR-0002-d.md" "$D/ADR-0002-d.md"
refused "shard --yes (a source record links outside)" python3 "$S/ledger.py" shard --force --yes; unmoved "source link"
shard_repo; mkdir -p "$D/2025"; ln -s "$X" "$D/2025/Q4"
refused "shard --yes (an existing shard dir links outside)" python3 "$S/ledger.py" shard --force --yes; unmoved "shard-index link"
shard_repo; mkdir -p "$R/docs/engineering"; ln -s "$X" "$R/docs/engineering/ledger"
refused "shard --yes (ledger dir links outside)" python3 "$S/ledger.py" shard --force --yes; unmoved "ledger link"

echo "--- check_index ---"
new_repo; ln -s "$X" "$R/skills"
refused "--gen-collections (skills/ links outside)" python3 "$S/check_index.py" --gen-collections
new_repo; mkdir -p "$R/research"; echo '# a' > "$R/research/a.md"; ln -s "$X/INDEX.md" "$R/research/INDEX.md"
refused "--gen-collections (research/INDEX.md links outside)" python3 "$S/check_index.py" --gen-collections
new_repo; ln -s "$X/TERMS.md" "$R/TERMS.md"
refused "--gen-terms (TERMS.md links outside)" python3 "$S/check_index.py" --gen-terms
new_repo
refused "--gen-terms --terms-out ../outside" python3 "$S/check_index.py" --gen-terms --terms-out "../outside$N/T.md"
refused "--gen-terms --terms-out <absolute outside path>" python3 "$S/check_index.py" --gen-terms --terms-out "$X/T.md"
new_repo; mkdir -p "$R/docs"; printf '# Auth\n\nHow auth works.\n' > "$R/docs/a.md"
refused "--register --index <absolute outside path>" python3 "$S/check_index.py" --register docs/a.md --index "$X/INDEX.md"
refused "--register --index ../outside" python3 "$S/check_index.py" --register docs/a.md --index "../outside$N/INDEX.md"
for v in file_link root_default root_config; do
  $v ""; mkdir -p "$R/docs"; printf '# Auth\n\nHow auth works.\n' > "$R/docs/a.md"
  refused "--register (records-root INDEX.md, $v)" python3 "$S/check_index.py" --register docs/a.md
done
new_repo; printf '# SECRET-TITLE\n\nSECRET-PARAGRAPH\n' > "$X/secret.md"
refused "--register <a note outside the repo>" python3 "$S/check_index.py" --register "$X/secret.md"
grep -rqs SECRET --exclude-dir=.git "$R" && bad "--register: copied an outside note into the repo" \
  || ok "--register: nothing from the outside note reached the repo"
new_repo; mkdir -p "$R/docs"
{ echo '# Long'; for s in 1 2 3 4 5; do printf '\n## Section %s\n\n' "$s"; for i in $(seq 1 35); do echo "line $i"; done; done; } > "$X/long.md"
ln -s "$X/long.md" "$R/docs/long.md"
refused "--fix-stubs --yes (a doc links outside)" python3 "$S/check_index.py" docs --fix-stubs --yes

echo "--- clean control: in-repo symlinks are followed, writes succeed ---"
new_repo; mkdir -p "$R/records" "$R/research" "$R/docs"; ln -s records "$R/rec"
echo '{"root": "rec"}' > "$R/.100x.json"; ln -s AGENTS.md "$R/CLAUDE.md"
printf '# Auth\n\nHow auth works.\n' > "$R/docs/a.md"
{ echo '# Long'; for s in 1 2 3 4 5; do printf '\n## Section %s\n\n' "$s"; for i in $(seq 1 35); do echo "line $i"; done; done; } > "$R/docs/long.md"
run() { local label="$1"; shift; (cd "$R" && "$@") >"$TMP/out" 2>&1 && ok "control: $label" || bad "control: $label (exit $?)"; }
run "learn add"            python3 "$S/learn.py" "${LESSON[@]}"
run "learn index"          python3 "$S/learn.py" index
run "learn promote --yes (via CLAUDE.md -> AGENTS.md)" python3 "$S/learn.py" promote LESSON-0001 --file CLAUDE.md --yes
run "decide new"           python3 "$S/decide.py" new "Queue choice"
run "decide index"         python3 "$S/decide.py" index
run "rca new"              python3 "$S/rca.py" new "Checkout outage"
run "rca index"            python3 "$S/rca.py" index
run "rca link"             python3 "$S/rca.py" link RCA-0001 --decision ADR-0001
run "ledger index"         python3 "$S/ledger.py" index
run "ledger map"           python3 "$S/ledger.py" map
run "ledger shard --yes"   python3 "$S/ledger.py" shard --force --yes
run "--fix-stubs --yes"    python3 "$S/check_index.py" docs --fix-stubs --yes
echo '# a' > "$R/research/a.md"   # after --fix-stubs: an uncatalogued research/ fails that run
run "--gen-collections"    python3 "$S/check_index.py" --gen-collections
run "--gen-terms"          python3 "$S/check_index.py" --gen-terms
run "--register"           python3 "$S/check_index.py" --register docs/a.md
[ -L "$R/CLAUDE.md" ] && grep -q "(LESSON-0001)" "$R/AGENTS.md" \
  && ok "control: promote wrote through the in-repo link and kept it a link" \
  || bad "control: promote replaced CLAUDE.md or missed AGENTS.md"
n=0; for f in records/lessons/INDEX.md records/decisions/INDEX.md records/rca/INDEX.md \
              records/ledger/INDEX.md records/ledger/MAP.md records/INDEX.md \
              research/INDEX.md TERMS.md; do [ -f "$R/$f" ] || { n=1; echo "missing $f" >"$TMP/out"; }; done
[ "$n" -eq 0 ] && ok "control: every generated file landed inside the repo" || bad "control: a generated file is missing"
[ -L "$R/rec" ] && ok "control: the records-root link is still a link" || bad "control: records-root link replaced"
grep -q "^## Contents" "$R/docs/long.md" && ok "control: --fix-stubs rewrote the in-repo doc" || bad "control: --fix-stubs did not write"
[ -z "$(ls -A "$X")" ] && ok "control: nothing written outside" || bad "control: wrote outside"

echo
echo "symlink-escape: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
