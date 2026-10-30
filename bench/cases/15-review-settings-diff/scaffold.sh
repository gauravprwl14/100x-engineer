# No git: the PR's head is on disk and its diff is PR.diff, so the agent never needs git.
. "$(dirname "$0")/../_lib.sh"
copy_tree "$(dirname "$0")/../13-settings-screen-build/fixture"
copy_tree "$(dirname "$0")/fixture"
