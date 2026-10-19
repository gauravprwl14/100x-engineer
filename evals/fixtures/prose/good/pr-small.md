closes #214

## Why
Shared notebooks showed deleted pages to viewers, which breaks the retention decision in #198.

## What
- Hide pages with `deleted_at` set from the viewer list query.
- Does not purge rows; the nightly job in #201 still owns deletion.

## Verified
`pytest tests/test_viewer_pages.py` → `6 passed in 0.41s`

## Out of scope
- Same filter for the export endpoint → #219
