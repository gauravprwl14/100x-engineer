. "$(dirname "$0")/../_lib.sh"
here="$(dirname "$0")"
copy_tree "$here/fixture"
git_init
commit_all "Invoice subtotal"
git checkout -q -b feature/discounts
cp -R "$here/branch/." .
commit_all "Add percentage discounts"
cp "$here/review_thread.md" REVIEW_THREAD.md
echo "REVIEW_THREAD.md" >> .git/info/exclude
