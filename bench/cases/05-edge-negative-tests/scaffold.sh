. "$(dirname "$0")/../_lib.sh"
copy_tree "$(dirname "$0")/fixture"
git_init
commit_all "Create booking endpoint"
