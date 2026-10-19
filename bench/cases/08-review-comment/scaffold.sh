. "$(dirname "$0")/../_lib.sh"
here="$(dirname "$0")"
copy_tree "$here/fixture"
git_init
commit_all "Mark invoices paid"
git checkout -q -b feature/refunds
cp -R "$here/branch/." .
commit_all "Add refunds for paid invoices"
