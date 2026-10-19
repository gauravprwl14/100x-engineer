[MUST] Trailing slash in the folder name builds a key the bucket never has.
`folder="reports/"` → key `reports//q3.pdf` → `NoSuchKey` on download (`storage/keys.py:18`).
```suggestion
folder = folder.rstrip("/")
```
Is a trailing slash possible from the mobile client too?
