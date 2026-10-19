[← INDEX](INDEX.md)

# Sync conflicts

**Answer:** the last writer wins per field, and a conflict banner appears when two edits land within 5 seconds (`sync/merge.py:88`).

## How a conflict is detected
- Each field carries a version counter.
- A write with a stale counter is merged field by field.

## What the user sees
A banner with both values and a "keep mine" button.
