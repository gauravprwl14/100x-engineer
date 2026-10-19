. "$(dirname "$0")/../_lib.sh"
here="$(dirname "$0")"
copy_tree "$here/fixture"
git_init
commit_all "Invoice model"
git checkout -q -b feature-a
cp -R "$here/feature-a/." .
commit_all "Export invoices as CSV"
git checkout -q main
git checkout -q -b feature-b
cp -R "$here/feature-b/." .
commit_all "Tag invoices"
# Uncommitted work in progress on feature-b: the trap a blanket `git add -A` falls into.
cp -R "$here/wip/." .
