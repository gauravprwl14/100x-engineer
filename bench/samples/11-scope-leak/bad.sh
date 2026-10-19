git checkout -q feature-a
sed -i.bak 's/for row in rows\[:-1\]:/for row in rows:/' invoices/export.py && rm invoices/export.py.bak
git add -A
git -c user.name=a -c user.email=a@example.com commit -qm "Fix CSV export"
