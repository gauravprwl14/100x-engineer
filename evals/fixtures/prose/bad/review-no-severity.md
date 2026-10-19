This loop queries the database once per note; `notes.select_related("owner")` avoids it.
