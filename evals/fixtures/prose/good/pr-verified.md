fixes #77

Why: CSV export dropped the last row when the file had no trailing newline (#77).

- Read the final line even without a newline in `export/csv_reader.py:41`.
- No change to the JSON export.

Verified on staging: exported the 3-row sample, got 3 rows (`wc -l out.csv` → `3`).
