#!/usr/bin/env bash
# Regression suite for check_diagrams.py. Asserts detection AND absence of false
# positives, against the real fixture (specs/login/spec.md) plus deliberately
# broken blocks. Run: bash tests/test_check_diagrams.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
CD="$ROOT/scripts/check_diagrams.py"

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [args...]
  local exp="$1" label="$2"; shift 2
  python3 "$CD" "$@" >/tmp/cd.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-55s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-55s exit exp=%s got=%s\n' "$label" "$exp" "$got"
       sed 's/^/       /' /tmp/cd.out; fi
}
has() { grep -qi "$1" /tmp/cd.out && { PASS=$((PASS+1)); printf '  ok   %-55s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "NOT reported: $1"; sed 's/^/       /' /tmp/cd.out; }; }

# --- real fixture: specs/login/spec.md has no `%% level:` directive, must still
#     pass clean (inference is reported, not a violation) ---
expect 0 "real fixture specs/login/spec.md passes" "$ROOT/specs/login/spec.md"
python3 "$CD" "$ROOT/specs/login/spec.md" >/tmp/cd.out 2>&1
has "inferred level 1"

# --- same fixture, forced to level 3: it has no alt/opt block and no step table,
#     so a forced-L3 run must fail on both structural requirements ---
expect 1 "specs/login/spec.md forced to --level 3 fails" "$ROOT/specs/login/spec.md" --level 3
has "shown branch/error path"
has "numbered step table"

# --- the worked example, all three levels, must pass clean ---
expect 0 "reviewers/_diagram-levels.md (L1+L2+L3) passes" "$ROOT/reviewers/_diagram-levels.md"

# --- directory mode over the whole specs/ tree ---
expect 0 "directory scan over specs/ passes" "$ROOT/specs"

# --- unknown diagram type ---
cat > "$TMP/unknown.md" << 'EOF'
# doc

```mermaid
this is not a real diagram keyword
A -> B
```
EOF
expect 1 "unrecognized diagram type rejected" "$TMP/unknown.md"
has "could not identify a diagram type"

# --- participant used before declaration ---
cat > "$TMP/undeclared.md" << 'EOF'
# doc

```mermaid
sequenceDiagram
  participant A
  A->>B: do the thing
  participant B
EOF
cat >> "$TMP/undeclared.md" << 'EOF'
```
EOF
expect 1 "undeclared participant used before declaration" "$TMP/undeclared.md"
has "used before"

# --- arrow form design_drift.py cannot parse (async -)) ---
cat > "$TMP/badarrow.md" << 'EOF'
# doc

```mermaid
sequenceDiagram
  participant A
  participant B
  A-)B: fire and forget
```
EOF
expect 1 "unsupported async arrow rejected" "$TMP/badarrow.md"
has "unrecognized sequence arrow"

# --- %% external referencing a never-declared alias ---
cat > "$TMP/badexternal.md" << 'EOF'
# doc

```mermaid
sequenceDiagram
  %% external: Z
  participant A
  participant B
  A->>B: hello
```
EOF
expect 1 "external directive with unknown alias rejected" "$TMP/badexternal.md"
has "never declared"

# --- flowchart label with unescaped parens ---
cat > "$TMP/badlabel.md" << 'EOF'
# doc

```mermaid
flowchart TD
  A[Do the thing (carefully)] --> B[Done]
```
EOF
expect 1 "unquoted parens in flowchart label rejected" "$TMP/badlabel.md"
has "needs quoting"

# --- placeholder text left in a diagram ---
cat > "$TMP/placeholder.md" << 'EOF'
# doc

```mermaid
sequenceDiagram
  participant A
  participant B
  A->>B: <!-- action -->
  A->>B: TODO fill this in
```
EOF
expect 1 "placeholder text rejected" "$TMP/placeholder.md"
has "placeholder text"

# --- L1 declared but node budget exceeded ---
cat > "$TMP/overbudget.md" << 'PYEOF'
# doc

```mermaid
sequenceDiagram
  %% level: 1
PYEOF
for i in $(seq 1 14); do echo "  participant P$i" >> "$TMP/overbudget.md"; done
echo '  P1->>P2: hi' >> "$TMP/overbudget.md"
echo '```' >> "$TMP/overbudget.md"
expect 1 "declared L1 over the 12-node budget rejected" "$TMP/overbudget.md"
has "allows <= 12 nodes"

# --- declared L2 within budget, no structural requirement, must pass ---
cat > "$TMP/goodl2.md" << 'EOF'
# doc

```mermaid
sequenceDiagram
  %% level: 2
  participant A
  participant B
  participant C
  A->>B: request
  B->>C: fetch
  C-->>B: data
  B-->>A: response
```
EOF
expect 0 "declared L2 within budget passes" "$TMP/goodl2.md"

# --- declared L3 with a branch but no step table ---
cat > "$TMP/l3notable.md" << 'EOF'
# doc

```mermaid
sequenceDiagram
  %% level: 3
  participant A
  participant B
  A->>B: request
  alt ok
    B-->>A: 200
  else failure
    B-->>A: 500
  end
```

No table here, just prose.
EOF
expect 1 "L3 with branch but no step table rejected" "$TMP/l3notable.md"
has "numbered step table"

# --- declared L3, branch + step table present: clean pass ---
cat > "$TMP/l3good.md" << 'EOF'
# doc

```mermaid
sequenceDiagram
  %% level: 3
  participant A
  participant B
  A->>B: request
  alt ok
    B-->>A: 200
  else failure
    B-->>A: 500
  end
```

| # | step |
|---|---|
| 1 | client sends request |
| 2 | server responds |
EOF
expect 0 "L3 with branch and step table passes" "$TMP/l3good.md"

# --- flowchart, clean, no explicit level: inferred and passes ---
cat > "$TMP/flowok.md" << 'EOF'
# doc

```mermaid
flowchart TD
  A[Start] --> B{Valid?}
  B -->|yes| C[Process]
  B -->|no| D[Reject]
```
EOF
expect 0 "clean flowchart with no level directive passes" "$TMP/flowok.md"

# --- empty/malformed mermaid block ---
cat > "$TMP/empty.md" << 'EOF'
# doc

```mermaid
flowchart TD
  just some text, no arrows
```
EOF
expect 1 "flowchart with no edges rejected" "$TMP/empty.md"
has "no recognizable edges"

# --- no mermaid blocks at all: not an error ---
cat > "$TMP/noblocks.md" << 'EOF'
# doc
Just prose, no diagrams here.
EOF
expect 0 "file with no mermaid blocks is not a violation" "$TMP/noblocks.md"

echo
echo "check_diagrams: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
