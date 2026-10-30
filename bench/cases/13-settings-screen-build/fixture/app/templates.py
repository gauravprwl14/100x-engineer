from html import escape


def esc(value) -> str:
    return escape(str(value), quote=True)


def page(title: str, body: str) -> str:
    """A whole HTML document around body. Callers escape anything user-supplied in body."""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{esc(title)}</title>\n</head>\n<body>\n"
        f"<main>\n{body}\n</main>\n</body>\n</html>\n"
    )
