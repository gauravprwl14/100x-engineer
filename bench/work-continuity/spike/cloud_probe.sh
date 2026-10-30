#!/usr/bin/env bash
# Phase 0 cloud check. Run INSIDE a `claude --cloud` session on this repo:
#   bash bench/work-continuity/spike/cloud_probe.sh
# Answers PRD Q1: are plugin hooks and tools present, is gh signed in, can refs/100x/* be pushed.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
pass=0; fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "PASS  $1"; pass=$((pass+1)); else echo "FAIL  $1"; fail=$((fail+1)); fi; }

check "100x plugin tools are on PATH (plugin loaded)" "command -v 100x"
check "100x resolves its plugin root (whether the SessionStart hook ran: look for its notice at the top of the session)" "100x root"
check "gh is installed" "command -v gh"
check "gh is authenticated" "gh auth status"
echo "--- private ref probe"
if bash "$HERE/probe_ref.sh" origin; then pass=$((pass+1)); else fail=$((fail+1)); fi
echo "cloud_probe: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
