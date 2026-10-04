# album-tagging — spec

Minimal spec used by the orchestration examples and tests. Acceptance criteria carry
`AC-<n>` ids so `100x plan_dag lint --spec` can check every one is owned by a task.

## Acceptance criteria

AC-1: A member can add a tag to a photo in an album they can view.
AC-2: Tags are listed on the photo detail view, newest first.
AC-3: A tag can be removed by its author or an album admin.
AC-4: Adding, listing and removing tags are covered by automated tests.
