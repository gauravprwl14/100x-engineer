issue (blocking): an empty `tags` array deletes every tag on the note.
`PATCH /notes/9 {"tags": []}` → all tags removed, but the spec says omit means keep (#140).
