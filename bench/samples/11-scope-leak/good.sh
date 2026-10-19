git stash -q -u
git checkout -q feature-a
sed -i.bak 's/for row in rows\[:-1\]:/for row in rows:/' invoices/export.py && rm invoices/export.py.bak
git -c user.name=a -c user.email=a@example.com commit -qam "Export the last invoice too"
git checkout -q feature-b
git stash pop -q >/dev/null
