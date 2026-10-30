# No git: the agent's task never needs it, and the sandbox's git shim fails on macOS.
. "$(dirname "$0")/../_lib.sh"
copy_tree "$(dirname "$0")/fixture"
