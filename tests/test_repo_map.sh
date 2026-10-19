#!/usr/bin/env bash
# Regression suite for scripts/repo_map.py — the fast-orientation tool.
# Asserts detection AND absence of crashes, not just happy-path output.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; trap 'rm -rf "$TMP" "$OUT"' EXIT
RM="$ROOT/scripts/repo_map.py"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf '  ok   %-58s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "$1"; [ -s $OUT/rm.out ] && sed 's/^/       /' $OUT/rm.out | head -8; }
rc_is(){ [ "$2" -eq "$1" ] && ok "$3" || bad "$3 (exit exp=$1 got=$2)"; }
has()  { grep -q "$1" $OUT/rm.out && ok "reports: $1" || bad "does NOT report: $1"; }
no()   { grep -q "$1" $OUT/rm.out && bad "false positive: $1" || ok "no false positive: $1"; }

# ---------- runs on this repo without error ----------
python3 "$RM" "$ROOT" >$OUT/rm.out 2>&1
rc_is 0 $? "repo_map: runs clean on this repo"
no "Traceback"

# ---------- detects Python and TypeScript ----------
has "Python"
has "TypeScript"

# ---------- entry points and doc locations from this repo's own shape ----------
has "__main__ guard"
has "AGENTS.md"
has "decisions/"
has "specs/"

# ---------- --top N ----------
python3 "$RM" "$ROOT" --top 3 >$OUT/rm.out 2>&1
rc_is 0 $? "repo_map: --top 3 runs clean"
n=$(sed -n '/Most-connected files/,/^$/p' $OUT/rm.out | grep -c "importer(s)")
[ "$n" -le 3 ] && ok "repo_map: --top 3 shows at most 3 ranked files (got $n)" \
  || bad "repo_map: --top 3 showed $n ranked files"

# ---------- --symbol AuthService finds the worked example ----------
python3 "$RM" "$ROOT" --symbol AuthService >$OUT/rm.out 2>&1
rc_is 0 $? "repo_map: --symbol runs clean"
has "examples/login/src/auth.service.ts"
has "examples/login/src/auth.controller.ts"

# a symbol that does not exist must say so cleanly, not crash
python3 "$RM" "$ROOT" --symbol ThisSymbolDoesNotExistAnywhereXYZ >$OUT/rm.out 2>&1
rc_is 0 $? "repo_map: unknown symbol exits clean"
has "none found"
no "Traceback"

# ---------- ranking is deterministic across runs ----------
python3 "$RM" "$ROOT" --top 20 >$OUT/rm1.out 2>&1
python3 "$RM" "$ROOT" --top 20 >$OUT/rm2.out 2>&1
if diff -q $OUT/rm1.out $OUT/rm2.out >/dev/null; then
  ok "repo_map: identical output across two runs"
else
  FAIL=$((FAIL+1)); printf '  FAIL %-58s\n' "repo_map: output differs across runs"
  diff $OUT/rm1.out $OUT/rm2.out | head -10 | sed 's/^/       /'
fi

# ---------- a small, controlled fixture: known import edges ----------
FX="$TMP/fixture"
mkdir -p "$FX/src"
cat > "$FX/src/util.py" <<'PY'
def helper():
    return 1
PY
cat > "$FX/src/a.py" <<'PY'
from src.util import helper
def a():
    return helper()
PY
cat > "$FX/src/b.py" <<'PY'
from src.util import helper
def b():
    return helper()
PY
cat > "$FX/src/service.ts" <<'TS'
export class WidgetService {
  make() { return 1; }
}
TS
cat > "$FX/src/controller.ts" <<'TS'
import { WidgetService } from './service';
export class WidgetController {
  constructor(private svc: WidgetService) {}
}
TS
python3 "$RM" "$FX" --json >$OUT/rm.out 2>&1
rc_is 0 $? "repo_map: --json runs clean on fixture"
python3 -c "import json; json.load(open('$OUT/rm.out'))" >$OUT/rm.parse 2>&1
rc_is 0 $? "repo_map: --json emits valid JSON"

python3 - "$FX" "$RM" <<'PYEOF' >$OUT/rm.out 2>&1
import json, subprocess, sys
root, rm = sys.argv[1], sys.argv[2]
out = subprocess.run(["python3", rm, root, "--json"], capture_output=True, text=True).stdout
d = json.loads(out)
ranked = {r["file"]: r["in_degree"] for r in d["ranking"]}
assert ranked.get("src/util.py") == 2, ranked
assert ranked.get("src/service.ts") == 1, ranked
print("util.py in-degree 2, service.ts in-degree 1 -- as expected")
PYEOF
rc_is 0 $? "repo_map: import graph resolves known Python and TS edges"
has "as expected"

# ---------- empty dir gives a clean message, not a traceback ----------
mkdir -p "$TMP/empty"
python3 "$RM" "$TMP/empty" >$OUT/rm.out 2>&1
rc_is 0 $? "repo_map: empty dir exits clean"
has "no recognized source files"
no "Traceback"

# ---------- nonexistent path is reported, not a traceback ----------
python3 "$RM" "$TMP/does-not-exist" >$OUT/rm.out 2>&1
rc_is 1 $? "repo_map: nonexistent path exits 1"
has "no such path"
no "Traceback"

# ---------- helper: assert against --json output with a python expression ----------
jcheck() {  # jcheck <root> <label> <python assertions using d>
  python3 - "$1" "$RM" "$3" >$OUT/rm.out 2>&1 <<'PYEOF'
import json, subprocess, sys
root, rm, code = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.loads(subprocess.run(["python3", rm, root, "--json", "--top", "50"],
                              capture_output=True, text=True).stdout)
files_seen = {e["file"] for e in d["entry_points"]} | {r["file"] for r in d["ranking"]} \
    | {r["file"] for r in d["largest_files"]} | set(d["generated"]) | {r["file"] for r in d["routes"]}
routes = {(r["method"], r["path"]) for r in d["routes"]}
ranked = {r["file"]: r["in_degree"] for r in d["ranking"]}
exec(code)
print("PASS")
PYEOF
  rc=$?; [ $rc -eq 0 ] && ok "$2" || bad "$2"
}
gitinit() { (cd "$1" && git init -q && git config user.email e@e && git config user.name e \
  && git add -A && git commit -qm init); }

# ---------- Rails: gitignored build output is invisible; routes.rb is found ----------
RA="$TMP/rails"; mkdir -p "$RA/config" "$RA/app/controllers/api" "$RA/app/assets/builds" "$RA/lib"
printf 'app/assets/builds/*\n!app/assets/builds/.keep\n' > "$RA/.gitignore"
touch "$RA/app/assets/builds/.keep"
cat > "$RA/config/routes.rb" <<'RB'
Rails.application.routes.draw do
  root "home#index"
  resources :photos
  namespace :api do
    get "status", to: "health#show"
    resources :albums
  end
end
RB
printf 'class PhotosController < ApplicationController\n  def index; end\nend\n' > "$RA/app/controllers/photos_controller.rb"
printf 'class Api::AlbumsController < ApplicationController\nend\n' > "$RA/app/controllers/api/albums_controller.rb"
printf 'class ApplicationController\nend\n' > "$RA/app/controllers/application_controller.rb"
echo 'source "https://rubygems.org"' > "$RA/Gemfile"
gitinit "$RA"
# build output written AFTER init, as a build would; ignored, so never listed
python3 -c "print('module.exports = function(){};\n' + 'var x = 1;\n' * 9000)" > "$RA/app/assets/builds/application.js"
echo 'def helper; end' > "$RA/lib/untracked_new.rb"   # untracked but NOT ignored: must appear
jcheck "$RA" "rails: gitignored app/assets/builds/* never appears" \
  'assert not any("assets/builds" in f for f in files_seen), files_seen; assert d["listing"].startswith("git")'
jcheck "$RA" "rails: config/routes.rb reported as an entry point" \
  'assert any(e["file"]=="config/routes.rb" and "Rails" in e["label"] for e in d["entry_points"]), d["entry_points"]'
jcheck "$RA" "rails: routes parsed (root, resources, namespaced get)" \
  'assert {("GET","/"),("RESOURCES","/photos"),("GET","/api/status"),("RESOURCES","/api/albums")} <= routes, routes'
jcheck "$RA" "rails: routes.rb ranks the controllers it dispatches to" \
  'assert ranked.get("app/controllers/photos_controller.rb")==1 and ranked.get("app/controllers/api/albums_controller.rb")==1, ranked'
jcheck "$RA" "rails: untracked-not-ignored file still listed (no false negative)" \
  'assert d["total_files"]>=7 and "Ruby" in d["languages"], d["total_files"]'
jcheck "$RA" "rails: application_controller is not a controller entry (no false positive)" \
  'assert not any(e["file"].endswith("application_controller.rb") for e in d["entry_points"])'

# ---------- NestJS controller routes ----------
NE="$TMP/nest"; mkdir -p "$NE/src/photos"
cat > "$NE/src/photos/photos.controller.ts" <<'TS'
import { Controller, Get, Post } from '@nestjs/common';
@Controller('photos')
export class PhotosController {
  @Get(':id')
  findOne() {}
  @Post()
  create() {}
}
TS
cat > "$NE/src/main.ts" <<'TS'
import { NestFactory } from '@nestjs/core';
async function bootstrap() { await NestFactory.create(AppModule); }
TS
jcheck "$NE" "nest: @Controller + @Get/@Post resolve to full paths" \
  'assert {("GET","/photos/:id"),("POST","/photos")} <= routes, routes'
jcheck "$NE" "nest: NestFactory bootstrap ranks above controllers" \
  'assert d["entry_points"][0]["file"]=="src/main.ts", d["entry_points"][:3]'

# ---------- Next.js app router (and no Next routes without Next) ----------
NX="$TMP/next"; mkdir -p "$NX/app/(marketing)/about" "$NX/app/api/items" "$NX/app/blog/[slug]"
echo '{"name":"web","dependencies":{"next":"15.0.0","react":"19.0.0"}}' > "$NX/package.json"
echo 'export default function About() { return null }' > "$NX/app/(marketing)/about/page.tsx"
echo 'export default function Post() { return null }' > "$NX/app/blog/[slug]/page.tsx"
printf 'export async function GET() {}\nexport async function POST() {}\n' > "$NX/app/api/items/route.ts"
jcheck "$NX" "next: app router pages, route groups dropped, API methods read" \
  'assert {("PAGE","/about"),("PAGE","/blog/[slug]"),("GET","/api/items"),("POST","/api/items")} <= routes, routes'
VI="$TMP/vite"; mkdir -p "$VI/src/pages"
echo '{"name":"spa","dependencies":{"react":"19.0.0","vite":"5.0.0"}}' > "$VI/package.json"
echo 'export default function Home() { return null }' > "$VI/src/pages/Home.tsx"
jcheck "$VI" "next: a non-Next src/pages/ is not reported as Next routes (no false positive)" \
  'assert not any(r["framework"]=="Next.js" for r in d["routes"]), d["routes"]'

# ---------- Go net/http + gin handlers, Go import ranking ----------
GO="$TMP/go"; mkdir -p "$GO/internal/store"
echo 'module example.com/svc' > "$GO/go.mod"
cat > "$GO/main.go" <<'GOF'
package main

import (
	"net/http"
	"example.com/svc/internal/store"
)

func main() {
	http.HandleFunc("/health", health)
	http.HandleFunc("GET /items/{id}", item)
	r.GET("/users", listUsers)
	_ = store.New()
}
GOF
printf 'package store\n\nfunc New() int { return 1 }\n' > "$GO/internal/store/store.go"
jcheck "$GO" "go: HandleFunc (incl. 1.22 method pattern) and gin routes" \
  'assert {("ANY","/health"),("GET","/items/{id}"),("GET","/users")} <= routes, routes'
jcheck "$GO" "go: func main ranked first; module import ranks the package" \
  'assert d["entry_points"][0]["file"]=="main.go"; assert ranked.get("internal/store/store.go")==1, ranked'

# ---------- Spring, Django, FastAPI, Express ----------
MX="$TMP/mixed"; mkdir -p "$MX/java/com/x" "$MX/py/shop" "$MX/js"
cat > "$MX/java/com/x/PhotoController.java" <<'JV'
package com.x;
@RestController
@RequestMapping("/api/photos")
public class PhotoController {
  @GetMapping("/{id}")
  public Photo get() { return null; }
  @PostMapping
  public Photo create() { return null; }
}
JV
printf 'from django.urls import path\nurlpatterns = [path("orders/", views.list)]\n' > "$MX/py/shop/urls.py"
printf 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/ping")\ndef ping(): pass\n' > "$MX/py/api.py"
printf 'const app = require("express")();\napp.get("/hello", (req, res) => res.send("x"));\n' > "$MX/js/server.js"
jcheck "$MX" "spring/django/fastapi/express routes detected" \
  'assert {("GET","/api/photos/{id}"),("POST","/api/photos"),("ANY","/orders/"),("GET","/ping"),("GET","/hello")} <= routes, routes'

# ---------- pnpm workspace with 2 packages ----------
WS="$TMP/ws"; mkdir -p "$WS/packages/a/src" "$WS/packages/b/src" "$WS/packages/notes"
printf "packages:\n  - 'packages/*'\n" > "$WS/pnpm-workspace.yaml"
echo '{"name":"root","private":true}' > "$WS/package.json"
echo '{"name":"@x/a"}' > "$WS/packages/a/package.json"
echo '{"name":"@x/b"}' > "$WS/packages/b/package.json"
echo 'export const a = 1;' > "$WS/packages/a/src/index.ts"
echo 'export const b = 1;' > "$WS/packages/b/src/index.ts"
echo '# notes, no manifest' > "$WS/packages/notes/README.md"
jcheck "$WS" "workspace: pnpm detected with exactly 2 packages, named" \
  'assert [w["tool"] for w in d["workspaces"]]==["pnpm"], d["workspaces"]; assert sorted(p["name"] for p in d["packages"])==["@x/a","@x/b"], d["packages"]'
jcheck "$NE" "workspace: none reported for a single-package repo (no false positive)" \
  'assert d["workspaces"]==[] and d["packages"]==[]'

# ---------- generated code is deprioritised ----------
GE="$TMP/gen"; mkdir -p "$GE/src"
printf '// @generated by protoc. DO NOT EDIT.\nexport const T = 1;\n' > "$GE/src/types.ts"
for i in 1 2 3; do printf "import { T } from './types';\nimport { R } from './real';\nexport const u$i = T;\n" > "$GE/src/use$i.ts"; done
echo 'export const R = 1;' > "$GE/src/real.ts"
python3 -c "print('// @generated\n' + 'export const z = 1;\n' * 3000)" > "$GE/src/huge.ts"
jcheck "$GE" "generated: @generated file sorts after a real file in the ranking" \
  'order=[r["file"] for r in d["ranking"]]; assert order.index("src/real.ts") < order.index("src/types.ts"), order; assert ranked["src/types.ts"]==3'
jcheck "$GE" "generated: excluded from largest files, counted separately" \
  'assert "src/huge.ts" not in [r["file"] for r in d["largest_files"]]; assert set(d["generated"])=={"src/types.ts","src/huge.ts"}, d["generated"]'
jcheck "$GE" "generated: a hand-written file is not flagged (no false positive)" \
  'assert "src/real.ts" not in d["generated"]'

# ---------- outside git: walk skips node_modules and generated dirs ----------
WK="$TMP/walk"; mkdir -p "$WK/node_modules/x" "$WK/generated" "$WK/src"
echo 'module.exports = 1;' > "$WK/node_modules/x/index.js"
echo 'export const g = 1;' > "$WK/generated/g.ts"
echo 'export const a = 1;' > "$WK/src/a.ts"
jcheck "$WK" "walk: outside git, node_modules/ and generated/ are skipped" \
  'assert d["total_files"]==1 and d["listing"].startswith("directory walk"), (d["total_files"], d["listing"])'

# ---------- --lint-note: the comprehension artifact ----------
NOTE="$TMP/note.md"
cat > "$NOTE" <<'MD'
# Architecture: photos

## Context

```mermaid
flowchart LR
  U[User] --> API[photos API]
```

## Entry points

| entry | where | tag |
|---|---|---|
| POST /photos | src/photos/photos.controller.ts:6 | verified |

## Data flow

1. Controller validates the DTO, then calls PhotosService.create (verified: src/photos/photos.service.ts:12)

## Boundaries

- Postgres via TypeORM repository — inferred from the module imports

## Hot file

- src/photos/photos.service.ts:1 holds the upload state machine — verified

## Predict, then confirm

| # | prediction | confirmed by | tag |
|---|---|---|---|
| 1 | an oversize upload returns 413 | ran `pnpm test photos` | verified |
| 2 | the service retries GCS once | read photos.service.ts:40 | verified |
| 3 | deleting an album soft-deletes photos | not yet checked | inferred |

## Glossary

- **album item** — one photo or video row

## Open questions

- none
MD
python3 "$RM" --lint-note "$NOTE" >$OUT/rm.out 2>&1
rc_is 0 $? "lint-note: a complete note passes"
sed 's/ — verified$//' "$NOTE" > "$TMP/n1.md"
python3 "$RM" --lint-note "$TMP/n1.md" >$OUT/rm.out 2>&1
rc_is 1 $? "lint-note: rejects an untagged claim"
has "not tagged verified/inferred"
sed '/```mermaid/,/^```$/d' "$NOTE" > "$TMP/n2.md"
python3 "$RM" --lint-note "$TMP/n2.md" >$OUT/rm.out 2>&1
rc_is 1 $? "lint-note: rejects a missing mermaid context diagram"
has "no \`\`\`mermaid"
sed '/^| 3 |/d' "$NOTE" > "$TMP/n3.md"
python3 "$RM" --lint-note "$TMP/n3.md" >$OUT/rm.out 2>&1
rc_is 1 $? "lint-note: rejects fewer than 3 predict-then-confirm claims"
has "need the top 3"
sed 's#src/photos/photos.controller.ts:6#the photos controller#' "$NOTE" > "$TMP/n4.md"
python3 "$RM" --lint-note "$TMP/n4.md" >$OUT/rm.out 2>&1
rc_is 1 $? "lint-note: rejects an entry point with no file:line"
python3 "$RM" --lint-note "$ROOT/skills/codebase-comprehension/references/architecture-template.md" >$OUT/rm.out 2>&1
rc_is 0 $? "lint-note: the skill's own template passes (template and lint agree)"
sed '/^## Open questions/,$d' "$NOTE" > "$TMP/n5.md"
python3 "$RM" --lint-note "$TMP/n5.md" >$OUT/rm.out 2>&1
rc_is 1 $? "lint-note: rejects a missing section"
has "missing section '## Open questions'"

echo
echo "repo_map: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
