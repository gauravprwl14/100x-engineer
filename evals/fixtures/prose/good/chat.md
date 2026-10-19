Yes: the importer skips rows with an empty email, at `importer/rows.py:52`.

To keep them, set `allow_blank_email=True`; the welcome email is then not sent.
