#!/usr/bin/env bash
# Builds the resume-bench fixture: a repo with one workstream of three stacked PRs.
# Usage: scaffold.sh <empty dir>. Offline; no remote.
set -euo pipefail
cd "$1"
git init -q -b main .
git config user.email bench@example.com; git config user.name bench
mkdir -p api/comments web/comments settings
echo "export const API = 'albums';" > api/index.ts
echo "export const App = () => null;" > web/index.tsx
git add -A; git commit -qm "chore: base app"
git checkout -qb feat/comments-backend
printf "export function createComment(body: string) {\n  if (!body) throw new Error('empty');\n  return { body };\n}\n" > api/comments/comment.service.ts
git add -A; git commit -qm "feat(comments): comment service and POST /comments"
git checkout -qb feat/comments-frontend
echo "export const CommentList = () => null;" > web/comments/CommentList.tsx
git add -A; git commit -qm "feat(comments): comment list UI"
git checkout -q main; git checkout -qb feat/comments-settings
echo "export const enableComment = true;" > settings/comments.ts
git add -A; git commit -qm "feat(settings): enableComment sub-app setting"
git checkout -q main; git checkout -qb integration
git merge -q --no-edit feat/comments-backend feat/comments-frontend feat/comments-settings >/dev/null
git checkout -q feat/comments-backend
