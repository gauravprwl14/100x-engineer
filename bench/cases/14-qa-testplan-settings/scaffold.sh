# No git: the agent's task never needs it. The app is case 13's fixture plus the settings page.
. "$(dirname "$0")/../_lib.sh"
copy_tree "$(dirname "$0")/../13-settings-screen-build/fixture"
copy_tree "$(dirname "$0")/fixture"
