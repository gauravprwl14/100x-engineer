#!/usr/bin/env bash
# Regression suite for check_diagrams.py. Asserts detection AND absence of false
# positives, against the real fixture (specs/login/spec.md) plus deliberately
# broken blocks. Run: bash tests/test_check_diagrams.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
CD="$ROOT/scripts/check_diagrams.py"

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [args...]
  local exp="$1" label="$2"; shift 2
  python3 "$CD" "$@" >$OUT/cd.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-55s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-55s exit exp=%s got=%s\n' "$label" "$exp" "$got"
       sed 's/^/       /' $OUT/cd.out; fi
}
has() { grep -qi "$1" $OUT/cd.out && { PASS=$((PASS+1)); printf '  ok   %-55s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "NOT reported: $1"; sed 's/^/       /' $OUT/cd.out; }; }

# --- real fixture: specs/login/spec.md has no `%% level:` directive, must still
#     pass clean (inference is reported, not a violation) ---
expect 0 "real fixture specs/login/spec.md passes" "$ROOT/specs/login/spec.md"
python3 "$CD" "$ROOT/specs/login/spec.md" >$OUT/cd.out 2>&1
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

# --- mindmap: a clean one passes; icons, classes and comments are not nodes ---
cat > "$TMP/mindok.md" << 'EOF'
# doc

```mermaid
mindmap
  %% level: 1
  root((Notes service))
    Routes
      GET /notes/:id
      PATCH /notes/:id
    ::icon(fa fa-database)
    Data
      Cache
      Database
    Risks
      :::urgent
      Stale write-back
```
EOF
expect 0 "clean mindmap passes" "$TMP/mindok.md"
has "type=mindmap nodes=9 edges=8 level=L1"

# --- a mindmap whose node text names another type is still a mindmap ---
cat > "$TMP/mindwords.md" << 'EOF'
# doc

```mermaid
mindmap
  root[Diagram kinds]
    sequenceDiagram
    flowchart LR
    graph TD
```
EOF
expect 0 "mindmap holding other type keywords passes" "$TMP/mindwords.md"
has "type=mindmap nodes=4"

# --- mermaid frontmatter above the header does not hide the type ---
printf '# doc\n\n```mermaid\n---\ntitle: Parts\n---\nmindmap\n  root((Notes))\n    Routes\n```\n' > "$TMP/mindfront.md"
expect 0 "mindmap under frontmatter passes" "$TMP/mindfront.md"
has "type=mindmap nodes=2"

# --- a flowchart with a node called mindmap stays a flowchart ---
cat > "$TMP/flowmind.md" << 'EOF'
# doc

```mermaid
flowchart TD
  mindmap --> B[Done]
```
EOF
expect 0 "flowchart with a node named mindmap stays a flowchart" "$TMP/flowmind.md"
has "type=flowchart"

# --- two roots ---
cat > "$TMP/mindroots.md" << 'EOF'
# doc

```mermaid
mindmap
  root((Notes))
    Routes
  Second root
    Data
```
EOF
expect 1 "mindmap with two roots rejected" "$TMP/mindroots.md"
has "more than one root: 'Second root'"

# --- a child that dedents to a level no sibling uses ---
cat > "$TMP/mindindent.md" << 'EOF'
# doc

```mermaid
mindmap
  root((Notes))
    Routes
        GET
      PATCH
```
EOF
expect 1 "mindmap with an in-between dedent rejected" "$TMP/mindindent.md"
has "indentation is inconsistent: 'PATCH'"

# --- deeper-then-back to a sibling level is fine (no false positive) ---
cat > "$TMP/mindback.md" << 'EOF'
# doc

```mermaid
mindmap
  root((Notes))
    Routes
      GET
        cached read
    Data
```
EOF
expect 0 "mindmap stepping back to a sibling level passes" "$TMP/mindback.md"

# --- tabs and spaces mixed ---
printf '# doc\n\n```mermaid\nmindmap\n  root((Notes))\n\tRoutes\n```\n' > "$TMP/mindtabs.md"
expect 1 "mindmap mixing tabs and spaces rejected" "$TMP/mindtabs.md"
has "mixes tabs and spaces"

# --- a header with no nodes ---
printf '# doc\n\n```mermaid\nmindmap\n```\n' > "$TMP/mindempty.md"
expect 1 "mindmap with no nodes rejected" "$TMP/mindempty.md"
has "mindmap has no root node"

# --- placeholder text and the declared level budget apply to mindmaps too ---
cat > "$TMP/mindtodo.md" << 'EOF'
# doc

```mermaid
mindmap
  root((Notes))
    TODO add the risks
```
EOF
expect 1 "placeholder in a mindmap rejected" "$TMP/mindtodo.md"
has "placeholder text"
{ printf '# doc\n\n```mermaid\nmindmap\n  %%%% level: 1\n  root((Big))\n'
  for i in $(seq 1 12); do printf '    child %s\n' "$i"; done; printf '```\n'; } > "$TMP/mindbig.md"
expect 1 "declared L1 mindmap over the 12-node budget rejected" "$TMP/mindbig.md"
has "allows <= 12 nodes; diagram has 13"

echo
echo "check_diagrams: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
