. "$(dirname "$0")/../_lib.sh"
here="$(dirname "$0")"
copy_tree "$here/fixture"
git_init
commit_all "Invoice model and outstanding total"
git checkout -q -b feature/late-fee
cp -R "$here/branch/." .
commit_all "Charge a late fee on overdue invoices (#42)"
