#!/usr/bin/env bash
# Run the bench: every scenario in bench/cases x N runs x 3 arms (no plugin, OLD plugin at
# --old-ref, default 4c1cd93, NEW plugin = this working tree), then score and compare them
# with compare.py.
#
#   bench/run.sh --yes [--runs 3] [--model M] [--concurrency 2] [--case GLOB]
#                [--arms all|new|old] [--old-ref REF] [--max-cost-usd N] [--out DIR]
#
# `claude plugin eval` only accepts an eval dir below the plugin, so each arm runs from its
# own copy of the plugin with bench/cases inside it. NEW is frozen into a snapshot first,
# because other agents keep editing the working tree while a run is in flight.
set -euo pipefail

OLD_REF=4c1cd93
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/.." && pwd)"
runs=3 model="" concurrency=2 case_glob="" arms=all max_cost="" yes=0
out="$here/results/$(date +%Y%m%d-%H%M%S)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) yes=1 ;;
    --runs) runs="$2"; shift ;;
    --model) model="$2"; shift ;;
    --concurrency) concurrency="$2"; shift ;;
    --case) case_glob="$2"; shift ;;
    --arms) arms="$2"; shift ;;
    --old-ref) OLD_REF="$2"; shift ;;
    --max-cost-usd) max_cost="$2"; shift ;;
    --out) out="$2"; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "run.sh: unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done

# Resolve OLD before the cost warning, so a mistyped ref fails offline and before any session.
if ! old_sha="$(git -C "$repo" rev-parse --verify --quiet "$OLD_REF^{commit}")"; then
  echo "run.sh: --old-ref '$OLD_REF' is not a commit in $repo" >&2
  exit 2
fi

cases=$(find "$here/cases" -mindepth 1 -maxdepth 1 -type d -name "${case_glob:-[0-9]*}" | wc -l | tr -d ' ')
case "$arms" in
  all) arm_count=3 ;;
  new) arm_count=2 ;;
  old) arm_count=1 ;;
  *) echo "run.sh: --arms must be all, new or old" >&2; exit 2 ;;
esac
total=$((cases * runs * arm_count))

cat <<EOF
COST WARNING: this starts $total real agent sessions ($cases cases x $runs runs x $arm_count arms),
OLD plugin = $OLD_REF ($old_sha),
each up to 40 turns with Bash, Write and Edit, on your own credential and rate limit, plus
one haiku judge call per llm grader per run. Measured: \$0.16-0.25 per session on the smallest
case (default model, 11-12 turns); budget \$0.25-0.80 per session, so roughly
\$$((total / 4))-\$$((total * 4 / 5)) in all. --max-cost-usd N caps each eval invocation.
Scaffold scripts from bench/cases run as you (--scaffold); kept workspaces land in \$TMPDIR.
EOF
if [[ $yes -ne 1 ]]; then
  echo "Re-run with --yes to proceed."
  exit 2
fi

# The eval sandbox blocks writes to the per-user temp dir, where macOS's /usr/bin/git shim
# (xcrun) keeps its cache, so every git command an agent runs fails in every arm. Agents
# take PATH from your login shell, so a real git must come before /usr/bin there.
agent_git="$("${SHELL:-/bin/zsh}" -lic 'command -v git' 2>/dev/null | tail -1)"
if [[ "$(uname)" == Darwin && "$agent_git" == /usr/bin/git && "${BENCH_ALLOW_GIT_SHIM:-0}" != 1 ]]; then
  cat >&2 <<EOF
run.sh: agents would run git as /usr/bin/git, the xcrun shim the eval sandbox blocks
("couldn't create cache file ... Operation not permitted"). Cases 09 and 11 would then
score the sandbox, not the plugin. Link the real git into a directory that comes before
/usr/bin on your login PATH (bench/README.md, "Git in the sandbox"), for example:
  ln -s "\$(xcrun --find git)" <dir-before-usr-bin>/git
or set BENCH_ALLOW_GIT_SHIM=1 to run anyway.
EOF
  exit 2
fi

mkdir -p "$out"
new_root="$out/snapshot-new"
old_root="$(mktemp -d)/old"
cleanup() {
  git -C "$repo" worktree remove --force "$old_root" 2>/dev/null || true
}
trap cleanup EXIT

rsync -a --exclude .git --exclude bench/results "$repo/" "$new_root/"
git -C "$repo" rev-parse HEAD > "$out/new-base-commit.txt"
git -C "$repo" status --porcelain > "$out/new-uncommitted-files.txt"
echo "$OLD_REF $old_sha" > "$out/old-ref.txt"

common=(--eval-dir bench/cases --runs "$runs" --scaffold --keep-temp --trust-plugin
        --allow-tools Bash Write Edit --no-publish --threshold 0 -j "$concurrency")
[[ -n "$model" ]] && common+=(--model "$model")
[[ -n "$case_glob" ]] && common+=(--case "$case_glob")
[[ -n "$max_cost" ]] && common+=(--max-cost-usd "$max_cost")

if [[ "$arms" != old ]]; then
  # with-without gives the NEW arm and the no-plugin arm from one invocation.
  claude plugin eval "$new_root" "${common[@]}" --ablation with-without \
    --json "$out/new.json" --output-dir "$out/new" || echo "new arm exited $?"
fi
if [[ "$arms" != new ]]; then
  git -C "$repo" worktree add --detach "$old_root" "$old_sha" >/dev/null
  mkdir -p "$old_root/bench"
  cp -R "$here/cases" "$old_root/bench/cases"
  claude plugin eval "$old_root" "${common[@]}" --ablation none \
    --json "$out/old.json" --output-dir "$out/old" || echo "old arm exited $?"
fi

if [[ -f "$out/new.json" && -f "$out/old.json" ]]; then
  python3 "$here/compare.py" --new "$out/new.json" --old "$out/old.json" \
    --tools-root "$new_root" --json "$out/scores.json" | tee "$out/summary.txt"
fi
echo "results: $out"
