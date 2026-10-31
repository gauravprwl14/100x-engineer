#!/usr/bin/env python3
"""Code reference: every function and class in a file, read from the code, not written.

An overview page says how a flow works; a reader who then opens the file still faces
forty functions in no particular order. Asked to "list the functions", a model skips
some and invents others. This lists them from the parse tree instead: name, kind,
line span, signature, decorators, the first docstring line, a branch count as a rough
complexity score, and which other listed symbols use it. Think of it as the index
at the back of a book: generated from the pages, so it cannot name a page that is not
there. Descriptions are the code's own docstrings; a symbol without one says so.

    code_ref.py build FILE... [--repo DIR] [--rev REV] [-o reference.json] [--md]
    code_ref.py check reference.json [--repo DIR]

`build` reads each file from the working tree, or at REV with `git show` when --rev is
given (`flow build` uses that to pin a page's reference to its SHA). Each file carries
the sha256 of the content it was read from; `check` exits 1 when a file changed or
vanished since, so a stale reference is caught instead of read. "Used by" is resolved
by name across the files given together, so pass the files a reader will want to see
side by side. Being by name, it over-reports for a common name: a method called `get` is
"used by" every function that calls any `.get`. Python only in this version: any other file exits 2.

Exit: 0 written / fresh, 1 stale (check), 2 usage, unreadable or unsupported file.
"""
import argparse, ast, hashlib, json, os, subprocess, sys

SCHEMA = 1
BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.IfExp,
                ast.BoolOp, ast.comprehension, ast.ExceptHandler, ast.With, ast.AsyncWith)
if hasattr(ast, "Match"):
    BRANCH_NODES += (ast.match_case,)


class Unsupported(Exception):
    pass


def read_source(path, repo, rev):
    if not path.endswith(".py"):
        raise Unsupported(f"{path}: only Python (.py) files are supported in this version")
    if rev:
        r = subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise Unsupported(f"{path}: not readable at {rev}: {r.stderr.strip()}")
        return r.stdout
    try:
        with open(os.path.join(repo, path), encoding="utf-8") as fh:
            return fh.read()
    except OSError as e:
        raise Unsupported(f"{path}: {e.strerror}")


def signature(node):
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({ast.unparse(node.args)}){ret}"


def first_doc_line(node):
    doc = ast.get_docstring(node)
    return doc.strip().splitlines()[0].strip() if doc and doc.strip() else None


def names_used(node):
    """Every bare name and attribute name referenced in the body: what this uses. Decorators
    are left out: `@check("D-x")` registers the function, it is not a use by it."""
    used = set()
    for n in (x for stmt in node.body for x in ast.walk(stmt)):
        if isinstance(n, ast.Name):
            used.add(n.id)
        elif isinstance(n, ast.Attribute):
            used.add(n.attr)
    return used


def symbols_of(tree):
    """Top-level functions and classes, and the methods directly inside a class."""
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append((node, None))
            if isinstance(node, ast.ClassDef):
                out += [(m, node.name) for m in node.body
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return out


def build(paths, repo=".", rev=None):
    files, defs = [], []
    for path in paths:
        src = read_source(path, repo, rev)
        try:
            tree = ast.parse(src, filename=path)
        except SyntaxError as e:
            raise Unsupported(f"{path}: does not parse: {e.msg} (line {e.lineno})")
        entry = {"path": path, "sha256": hashlib.sha256(src.encode()).hexdigest(),
                 "lines": len(src.splitlines()), "doc": first_doc_line(tree), "symbols": []}
        for node, owner in symbols_of(tree):
            kind = "class" if isinstance(node, ast.ClassDef) else "method" if owner else "function"
            sym = {"name": f"{owner}.{node.name}" if owner else node.name, "kind": kind,
                   "line": node.lineno, "end": node.end_lineno, "signature": signature(node),
                   "decorators": [ast.unparse(d) for d in node.decorator_list],
                   "doc": first_doc_line(node),
                   "branches": sum(isinstance(n, BRANCH_NODES) for n in ast.walk(node)),
                   "used_by": []}
            entry["symbols"].append(sym)
            defs.append((sym, node.name, names_used(node) if kind != "class" else set()))
        files.append(entry)
    for sym, short, _ in defs:
        sym["used_by"] = sorted({other["name"] for other, oshort, used in defs
                                 if other is not sym and short in used})
    return {"schema": SCHEMA, "rev": rev, "files": files}


def check(ref, repo="."):
    """Paths whose content no longer matches the reference: (path, reason) pairs."""
    stale = []
    for f in ref.get("files", []):
        try:
            src = read_source(f["path"], repo, ref.get("rev"))
        except Unsupported as e:
            stale.append((f["path"], str(e)))
            continue
        if hashlib.sha256(src.encode()).hexdigest() != f["sha256"]:
            stale.append((f["path"], "changed since the reference was built"))
    return stale


def to_markdown(ref):
    out = []
    for f in ref["files"]:
        out.append(f"### `{f['path']}`\n")
        if f["doc"]:
            out.append(f"{f['doc']}\n")
        out.append(f"{f['lines']} lines, {len(f['symbols'])} symbols.\n")
        out.append("| symbol | line | what it does | used by | branches |")
        out.append("|---|---|---|---|---|")
        for s in f["symbols"]:
            what = (s["doc"] or "*no docstring*").replace("|", "\\|")
            deco = "".join(f" `@{d}`".replace("|", "\\|") for d in s["decorators"])
            used = ", ".join(f"`{c}`" for c in s["used_by"]) or "—"
            out.append(f"| `{s['name']}`{deco} | {s['line']}–{s['end']} | {what} | "
                       f"{used} | {s['branches']} |")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(prog="100x code_ref", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="list every function and class in the files")
    b.add_argument("files", nargs="+")
    b.add_argument("--repo", default=".")
    b.add_argument("--rev", help="read the files at this git revision")
    b.add_argument("-o", "--out", help="write the JSON here instead of stdout")
    b.add_argument("--md", action="store_true", help="print a markdown table instead of JSON")
    c = sub.add_parser("check", help="exit 1 when a file changed since the reference")
    c.add_argument("reference")
    c.add_argument("--repo", default=".")
    a = p.parse_args(argv)
    try:
        if a.cmd == "build":
            ref = build(a.files, a.repo, a.rev)
            text = to_markdown(ref) if a.md else json.dumps(ref, indent=1)
            if a.out:
                with open(a.out, "w", encoding="utf-8") as fh:
                    fh.write(text + "\n")
            else:
                print(text)
            return 0
        with open(a.reference, encoding="utf-8") as fh:
            ref = json.load(fh)
        stale = check(ref, a.repo)
        for path, why in stale:
            print(f"stale: {path}: {why}")
        print(f"code_ref check: {len(ref.get('files', []))} file(s), {len(stale)} stale")
        return 1 if stale else 0
    except (Unsupported, OSError, json.JSONDecodeError) as e:
        print(f"100x code_ref: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
