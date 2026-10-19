#!/usr/bin/env bash
# Regression suite for stack_audit.py's reviewer routing and Ruby layers. Asserts each
# framework maps to its reviewer file AND that look-alikes (a non-Rails Gemfile, a
# django-* helper package, a JVM build.gradle, NestJS's own express dependency) do not.
# Run: bash tests/test_stack_audit.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SA="$ROOT/scripts/stack_audit.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

new() { D="$TMP/$1"; mkdir -p "$D/.github/workflows"; touch "$D/.github/workflows/ci.yml"; }
run() { python3 "$SA" --here "$D" >"$TMP/out" 2>&1; RC=$?; }
has() { grep -qF -- "$1" "$TMP/out" && { PASS=$((PASS+1)); printf '  ok   %-60s\n' "$2"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-60s\n' "$2"; sed 's/^/       /' "$TMP/out"; }; }
nothas() { grep -qF -- "$1" "$TMP/out" && { FAIL=$((FAIL+1)); printf '  FAIL %-60s\n' "$2"; sed 's/^/       /' "$TMP/out"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-60s\n' "$2"; }; }

# --- detection ---
new rails; printf 'source "https://rubygems.org"\ngem "rails", "~> 8.0"\n' > "$D/Gemfile"; run
has "reviewers/rails.md" "Gemfile with rails -> rails.md"
has "=== Ruby ===" "Gemfile -> Ruby layers audited"
[ "$RC" -eq 0 ] && { PASS=$((PASS+1)); echo "  ok   Ruby gaps warn only (exit 0 with CI present)"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL Ruby gaps changed the exit code ($RC)"; }

new mono; mkdir -p "$D/backend" "$D/frontend"
printf 'GEM\n  specs:\n    rails (8.0.1)\n' > "$D/backend/Gemfile.lock"
printf '{"dependencies":{"react":"19.0.0"}}\n' > "$D/frontend/package.json"; run
has "reviewers/rails.md" "Rails app in backend/ of a monorepo -> rails.md"

new django; printf 'Django>=5.0\npsycopg[binary]\n' > "$D/requirements.txt"; run
has "reviewers/django-fastapi.md" "requirements.txt with Django -> django-fastapi.md"

new fastapi; printf '[project]\ndependencies = ["fastapi>=0.115", "uvicorn"]\n' > "$D/pyproject.toml"; run
has "reviewers/django-fastapi.md" "pyproject with fastapi -> django-fastapi.md"

new express; printf '{"dependencies":{"express":"^5.1.0"}}\n' > "$D/package.json"; run
has "reviewers/express-node.md" "package.json with express -> express-node.md"

new go; printf 'module example.com/svc\n\ngo 1.23\n' > "$D/go.mod"; run
has "reviewers/go-service.md" "go.mod -> go-service.md"

new tf; mkdir -p "$D/infra"; printf 'resource "aws_s3_bucket" "b" {}\n' > "$D/infra/main.tf"; run
has "reviewers/cloud-iac.md" "*.tf -> cloud-iac.md"

new android; mkdir -p "$D/app"
printf 'plugins {\n  alias(libs.plugins.android.application)\n}\n' > "$D/app/build.gradle.kts"; run
has "reviewers/native-mobile.md" "Android app module -> native-mobile.md"

# --- no false positives ---
new nest; printf '{"dependencies":{"@nestjs/core":"^11","express":"^5"}}\n' > "$D/package.json"; run
has "reviewers/nestjs.md" "NestJS -> nestjs.md"
nothas "reviewers/express-node.md" "NestJS's express dependency is not plain Express"

new sinatra; printf 'gem "sinatra"\ngem "rails-html-sanitizer"\n' > "$D/Gemfile"; run
nothas "reviewers/rails.md" "Gemfile without rails is not Rails"

new helper; printf 'django-environ==0.11\nrequests\n' > "$D/requirements.txt"; run
nothas "reviewers/django-fastapi.md" "django-environ alone is not Django"

new spring; printf 'plugins { id("org.springframework.boot") version "3.3.0" }\n' > "$D/build.gradle.kts"; run
nothas "reviewers/native-mobile.md" "JVM build.gradle is not native mobile"

new empty; printf '# notes\n' > "$D/README.md"; run
has "none: no framework" "empty repo -> no reviewer"
nothas "=== Ruby ===" "no Gemfile -> no Ruby section"

echo
echo "test_stack_audit: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
