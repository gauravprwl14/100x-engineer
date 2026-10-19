# Shared by every case's scaffold.sh. The harness runs `bash <case>/scaffold.sh` with the
# empty workspace as cwd and a minimal env, so everything is located from the script path.
set -euo pipefail

# Fixed identity and dates keep the fixture commits byte-identical between the run and the
# scorer's own rebuild, so the scorer can diff the agent's result against a pristine copy.
export GIT_AUTHOR_NAME="Fixture Author" GIT_AUTHOR_EMAIL="fixture@example.com"
export GIT_COMMITTER_NAME="Fixture Author" GIT_COMMITTER_EMAIL="fixture@example.com"
export GIT_AUTHOR_DATE="2026-01-05T10:00:00Z" GIT_COMMITTER_DATE="2026-01-05T10:00:00Z"

copy_tree() {
  cp -R "$1/." .
}

git_init() {
  git init -q -b main .
  git config user.name "Fixture Author"
  git config user.email "fixture@example.com"
  git config commit.gpgsign false
}

commit_all() {
  git add -A
  git commit -q -m "$1"
}
