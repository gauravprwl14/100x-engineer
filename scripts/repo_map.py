#!/usr/bin/env python3
"""Fast orientation for a repo you have never seen: stacks, entry points, an
import-graph ranking of the most-connected files, test/source ratio, largest
files, directory shape, and which docs to read before the code.

Inspiration and explicit limitation. Aider's repo-map is the canonical version of
this idea (`Aider-AI/aider@main:aider/aider/repomap.py`; see
research/22-findings-agent-tool-internals.md, "Context selection / repo-map
algorithms"): tree-sitter-parses every file into def/ref tags (repomap.py:233),
builds a weighted symbol graph across ALL definitions and references
(repomap.py:365, edge weights repomap.py:472-511), ranks it with personalized
PageRank so importance propagates transitively and favors what the model is
already touching (repomap.py:525), then binary-searches a rendered slice of that
ranking to fit a token budget (repomap.py:629-710).

This script is a cheaper approximation of the RANKING step only, with two
deliberate cuts:
  1. No tree-sitter, no per-symbol graph. It parses `import`/`require`/`from`
     statements with regex and resolves them to files that exist in the repo,
     so the graph is file-level, not symbol-level.
  2. In-degree, not PageRank. A file imported by an important file scores the
     same as one imported by a leaf. That is a real gap versus aider — it will
     occasionally under-rank a central-but-indirectly-reached file — accepted
     because PageRank needs a real graph library or a from-scratch power
     iteration, and in-degree is legible enough for "where do I start reading"
     without either.
Import resolution is implemented for Python and JS/TS/JSX/TSX only — the two
stacks where `import`/`from`/`require` paths are regular enough to resolve with
regex. Other languages are still counted and listed; they are explicitly marked
unranked rather than silently scored 0, which would misreport absence of a
heuristic as absence of connectivity.

    repo_map.py .                      # orientation summary
    repo_map.py . --top 20             # the N most-connected files
    repo_map.py . --symbol AuthService # where is it defined, who references it
    repo_map.py . --json

Python stdlib only. SOURCE: original except where cited above.
"""
import argparse, json, os, re, sys, pathlib
from collections import Counter, defaultdict

SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv", "env",
    "__pycache__", ".next", "coverage", ".turbo", "vendor", "target",
    ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea",
    ".vscode", ".tox", ".terraform", "site-packages", ".eggs", "*.egg-info",
    ".pnpm-store", ".yarn",
}

LANG_EXT = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript (React)",
    ".js": "JavaScript", ".jsx": "JavaScript (React)", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".go": "Go", ".java": "Java", ".kt": "Kotlin",
    ".swift": "Swift", ".dart": "Dart", ".rb": "Ruby", ".cs": "C#",
    ".rs": "Rust", ".php": "PHP", ".c": "C", ".cpp": "C++",
    ".h": "C/C++ header", ".hpp": "C++ header", ".scala": "Scala",
    ".m": "Objective-C", ".mm": "Objective-C++", ".sh": "Shell",
}
CODE_EXT = set(LANG_EXT)
RESOLVABLE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
JS_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

STACK_MARKERS = [
    ("package.json", "Node.js"), ("pyproject.toml", "Python"),
    ("requirements.txt", "Python"), ("setup.py", "Python"),
    ("go.mod", "Go"), ("Cargo.toml", "Rust"), ("pom.xml", "Java (Maven)"),
    ("build.gradle", "Java/Kotlin (Gradle)"), ("build.gradle.kts", "Java/Kotlin (Gradle)"),
    ("Gemfile", "Ruby"), ("pubspec.yaml", "Dart/Flutter"),
    ("composer.json", "PHP"), ("Package.swift", "Swift"),
]

TEST_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec)(/|$)"
    r"|(^|/)test_[^/]+\.py$|_test\.(py|go)$"
    r"|\.(test|spec)\.(ts|tsx|js|jsx)$",
    re.I,
)

DOC_ROOT_NAMES = {
    "agents.md", "claude.md", "contributing.md", "contributing.rst",
    "codeowners", "security.md",
}
DOC_DIR_NAMES = {"decisions", "adr", "adrs", "specs", "rfcs", "docs", "architecture"}

MAX_READ_BYTES = 1_500_000  # content-scan cap; files past this are still counted, not read

# ---------------------------------------------------------------------------
# entry-point heuristics: (suffixes, compiled regex, label)
# ---------------------------------------------------------------------------
ENTRY_PATTERNS = [
    ({".py"}, re.compile(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]'), "__main__ guard"),
    ({".py"}, re.compile(r'@(?:app|router|bp|blueprint)\.(?:route|get|post|put|delete|patch)\('),
     "HTTP route (Flask/FastAPI-style)"),
    ({".py"}, re.compile(r'@click\.(?:command|group)\b'), "CLI command (click)"),
    ({".py"}, re.compile(r'add_(?:sub)?parser\(|ArgumentParser\('), "CLI registration (argparse)"),
    (JS_EXT, re.compile(r'\b(?:app|router)\.(?:get|post|put|delete|patch|use)\('),
     "HTTP route (Express-style)"),
    (JS_EXT, re.compile(r'@(?:Get|Post|Put|Delete|Patch|Controller)\('), "route decorator (NestJS-style)"),
    (JS_EXT, re.compile(r'\.command\('), "CLI registration (commander/yargs-style)"),
    (JS_EXT, re.compile(r'export\s+default\s+(?:async\s+)?function'), "exported default handler"),
    (JS_EXT, re.compile(r'module\.exports\s*='), "exported module (CommonJS)"),
    ({".go"}, re.compile(r'^\s*func\s+main\s*\('), "func main"),
    ({".java", ".kt"}, re.compile(r'static\s+void\s+main\s*\(|fun\s+main\s*\('), "main method"),
    ({".rs"}, re.compile(r'^\s*fn\s+main\s*\('), "fn main"),
]
FILENAME_ENTRY = {
    "main.py": "conventional entry filename", "app.py": "conventional entry filename",
    "manage.py": "Django management entry", "wsgi.py": "WSGI entry", "asgi.py": "ASGI entry",
    "cli.py": "CLI entry filename", "index.ts": "conventional entry filename",
    "index.js": "conventional entry filename", "main.ts": "conventional entry filename",
    "server.ts": "conventional entry filename", "server.js": "conventional entry filename",
    "main.go": "Go entry filename",
}


def iter_files(root: pathlib.Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            yield pathlib.Path(dirpath) / fn


def relpath(root, p):
    return os.path.normpath(os.path.relpath(p, root)).replace(os.sep, "/")


def read_text(path: pathlib.Path):
    try:
        if path.stat().st_size > MAX_READ_BYTES:
            return None
    except OSError:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


# ---------------------------------------------------------------------------
# import graph (Python + JS/TS only — see module docstring)
# ---------------------------------------------------------------------------
PY_IMPORT_RE = re.compile(r'^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w]+))', re.M)
JS_IMPORT_RE = re.compile(
    r'''(?:from|import)\s+['"](\.[^'"]+)['"]|require\(\s*['"](\.[^'"]+)['"]\s*\)'''
)


def py_targets(rel_file, module):
    """Resolve a Python import string to candidate repo-relative module paths."""
    if module.startswith("."):
        level = len(module) - len(module.lstrip("."))
        rest = module[level:]
        base = pathlib.PurePosixPath(rel_file).parent
        for _ in range(level - 1):
            base = base.parent
        if not rest:
            return []
        target = base / rest.replace(".", "/")
    else:
        target = pathlib.PurePosixPath(module.replace(".", "/"))
    return [str(target) + ".py", str(target) + "/__init__.py"]


def js_targets(rel_file, ref):
    base = pathlib.PurePosixPath(rel_file).parent / ref
    parts = base.parts
    norm = []
    for part in parts:
        if part == "..":
            if norm:
                norm.pop()
        elif part == ".":
            continue
        else:
            norm.append(part)
    base = pathlib.PurePosixPath(*norm) if norm else pathlib.PurePosixPath(".")
    cands = []
    if base.suffix in JS_EXT:
        cands.append(str(base))
    else:
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            cands.append(str(base) + ext)
        for ext in (".ts", ".tsx", ".js", ".jsx"):
            cands.append(str(base / f"index{ext}"))
    return cands


def build_graph(root, code_files):
    """File-level in-degree ranking. Returns (in_degree, importers, unranked_langs)."""
    index = {relpath(root, f) for f in code_files}
    in_degree = Counter()
    importers = defaultdict(set)
    unranked_langs = set()
    for f in code_files:
        rel = relpath(root, f)
        if f.suffix not in RESOLVABLE_EXT:
            unranked_langs.add(LANG_EXT.get(f.suffix, f.suffix))
            continue
        text = read_text(f)
        if text is None:
            continue
        targets = []
        if f.suffix == ".py":
            for m in PY_IMPORT_RE.finditer(text):
                module = m.group(1) or m.group(2)
                if not module:
                    continue
                for piece in module.split(","):
                    piece = piece.strip().split(" as ")[0].strip()
                    if piece:
                        targets.extend(py_targets(rel, piece))
        else:
            for m in JS_IMPORT_RE.finditer(text):
                ref = m.group(1) or m.group(2)
                if ref:
                    targets.extend(js_targets(rel, ref))
        seen_this_file = set()
        for t in targets:
            t = os.path.normpath(t).replace(os.sep, "/")
            if t in index and t != rel and t not in seen_this_file:
                seen_this_file.add(t)
                in_degree[t] += 1
                importers[t].add(rel)
    return in_degree, importers, unranked_langs


# ---------------------------------------------------------------------------
# orientation scan
# ---------------------------------------------------------------------------
def scan(root: pathlib.Path):
    all_files = list(iter_files(root))
    code_files = [f for f in all_files if f.suffix in CODE_EXT]

    lang_counts = Counter(LANG_EXT[f.suffix] for f in code_files)
    stack_markers = sorted({
        label for fname, label in STACK_MARKERS
        if any(relpath(root, f) == fname or relpath(root, f).endswith("/" + fname) for f in all_files)
    })

    entry_points = []
    for f in code_files:
        rel = relpath(root, f)
        if f.name in FILENAME_ENTRY:
            entry_points.append((rel, 0, FILENAME_ENTRY[f.name]))
        if "/pages/api/" in "/" + rel or re.search(r'(^|/)app/.*/route\.(ts|js)$', rel):
            entry_points.append((rel, 0, "Next.js API route (path convention)"))
        text = read_text(f)
        if text is None:
            continue
        lines = text.splitlines()
        for suffixes, pat, label in ENTRY_PATTERNS:
            if f.suffix not in suffixes:
                continue
            for i, line in enumerate(lines, 1):
                if pat.search(line):
                    entry_points.append((rel, i, label))
                    break  # one hit per pattern per file is enough signal

    line_counts = {}
    for f in code_files:
        text = read_text(f)
        line_counts[relpath(root, f)] = text.count("\n") + 1 if text is not None else 0

    test_files = [f for f in code_files if TEST_RE.search(relpath(root, f))]
    source_files = [f for f in code_files if f not in test_files]

    top_dirs = Counter()
    for f in all_files:
        rel = relpath(root, f)
        top = rel.split("/")[0] if "/" in rel else "."
        top_dirs[top] += 1

    docs = []
    for f in all_files:
        if f.parent == root and f.name.lower() in DOC_ROOT_NAMES:
            docs.append(relpath(root, f))
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        depth = len(pathlib.Path(os.path.relpath(dirpath, root)).parts)
        if depth > 3:
            dirnames[:] = []
            continue
        for d in dirnames:
            if d.lower() in DOC_DIR_NAMES:
                docs.append(relpath(root, pathlib.Path(dirpath) / d) + "/")
    docs = sorted(set(docs))

    in_degree, importers, unranked_langs = build_graph(root, code_files)

    return {
        "root": str(root),
        "total_files": len(all_files),
        "code_files": len(code_files),
        "languages": dict(sorted(lang_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "stack_markers": stack_markers,
        "entry_points": sorted(set(entry_points), key=lambda t: (t[0], t[1], t[2])),
        "ranking": sorted(in_degree.items(), key=lambda kv: (-kv[1], kv[0])),
        "importers": {k: sorted(v) for k, v in importers.items()},
        "unranked_languages": sorted(unranked_langs),
        "test_files": len(test_files),
        "source_files": len(source_files),
        "largest_files": sorted(line_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:15],
        "dirs_by_count": sorted(top_dirs.items(), key=lambda kv: (-kv[1], kv[0])),
        "docs_worth_reading": docs,
    }


# ---------------------------------------------------------------------------
# symbol lookup (definition + reference, across languages)
# ---------------------------------------------------------------------------
def def_patterns(symbol):
    sym = re.escape(symbol)
    return [re.compile(p) for p in (
        rf'^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+{sym}\b',
        rf'^\s*(?:export\s+)?interface\s+{sym}\b',
        rf'^\s*(?:export\s+)?type\s+{sym}\b',
        rf'^\s*(?:export\s+)?(?:async\s+)?function\s+{sym}\b',
        rf'^\s*(?:export\s+)?const\s+{sym}\s*=',
        rf'^\s*def\s+{sym}\b',
        rf'^\s*class\s+{sym}\b',
        rf'^\s*func\s+(?:\([^)]*\)\s*)?{sym}\b',
        rf'^\s*type\s+{sym}\b',
        rf'^\s*struct\s+{sym}\b',
        rf'\bstruct\s+{sym}\b',
        rf'^\s*(?:public|private|internal)?\s*(?:final\s+)?class\s+{sym}\b',
    )]


def find_symbol(root: pathlib.Path, symbol: str):
    defs, refs = [], []
    ref_pat = re.compile(rf'\b{re.escape(symbol)}\b')
    dpats = def_patterns(symbol)
    for f in iter_files(root):
        if f.suffix not in CODE_EXT:
            continue
        text = read_text(f)
        if text is None or symbol not in text:
            continue
        rel = relpath(root, f)
        for i, line in enumerate(text.splitlines(), 1):
            if not ref_pat.search(line):
                continue
            if any(p.search(line) for p in dpats):
                defs.append((rel, i, line.strip()))
            else:
                refs.append((rel, i))
    ref_counts = Counter(r[0] for r in refs)
    return defs, sorted(ref_counts.items(), key=lambda kv: (-kv[1], kv[0])), refs


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def print_orientation(data, top):
    r = data
    print(f"repo_map: {r['root']}")
    print(f"  {r['total_files']} files total, {r['code_files']} code files")
    if not r["code_files"]:
        print("  no recognized source files under this root")
        return

    print("\nLanguages (file count):")
    for lang, n in r["languages"].items():
        print(f"  {n:5d}  {lang}")
    if r["stack_markers"]:
        print("\nStack markers: " + ", ".join(r["stack_markers"]))

    print(f"\nEntry points ({len(r['entry_points'])} signals, showing up to 25):")
    for rel, line, label in r["entry_points"][:25]:
        loc = f"{rel}:{line}" if line else rel
        print(f"  {loc:60s} {label}")
    if len(r["entry_points"]) > 25:
        print(f"  ... and {len(r['entry_points']) - 25} more")

    print(f"\nMost-connected files (in-degree, top {top} — cheaper approximation of "
          f"aider's PageRank repo-map, see module docstring):")
    if not r["ranking"]:
        print("  no internal import edges resolved")
    for rel, n in r["ranking"][:top]:
        print(f"  {n:4d} importer(s)  {rel}")
    if r["unranked_languages"]:
        print(f"  (not ranked — no import-resolution heuristic for: "
              f"{', '.join(r['unranked_languages'])})")

    total_src = r["test_files"] + r["source_files"]
    ratio = (r["test_files"] / r["source_files"]) if r["source_files"] else 0.0
    print(f"\nTest-to-source ratio: {r['test_files']} test files / "
          f"{r['source_files']} source files = {ratio:.2f}")

    print("\nLargest files (by line count):")
    for rel, n in r["largest_files"][:10]:
        print(f"  {n:6d}  {rel}")

    print("\nDirectories by file count:")
    for d, n in r["dirs_by_count"][:15]:
        print(f"  {n:5d}  {d}")

    print("\nRead before the code (AGENTS.md/CONTRIBUTING/ADR/spec locations):")
    if r["docs_worth_reading"]:
        for d in r["docs_worth_reading"]:
            print(f"  {d}")
    else:
        print("  none found")


def print_symbol(symbol, defs, ref_counts, refs):
    print(f"symbol: {symbol}")
    print(f"\nDefinitions ({len(defs)}):")
    if not defs:
        print("  none found")
    for rel, line, snippet in defs:
        print(f"  {rel}:{line}  {snippet}")
    print(f"\nReferenced by {len(ref_counts)} file(s), {len(refs)} occurrence(s):")
    for rel, n in ref_counts[:25]:
        print(f"  {n:4d}  {rel}")
    if len(ref_counts) > 25:
        print(f"  ... and {len(ref_counts) - 25} more files")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=".", help="directory to map")
    ap.add_argument("--top", type=int, default=15, help="how many ranked files to show")
    ap.add_argument("--symbol", help="definition + reference lookup for this identifier")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    a = ap.parse_args()

    root = pathlib.Path(a.root)
    if not root.exists():
        print(f"repo_map: no such path: {a.root}", file=sys.stderr)
        return 1
    if not root.is_dir():
        print(f"repo_map: not a directory: {a.root}", file=sys.stderr)
        return 1

    if a.symbol:
        defs, ref_counts, refs = find_symbol(root, a.symbol)
        if a.json:
            print(json.dumps({
                "symbol": a.symbol,
                "definitions": [{"file": r, "line": l, "text": s} for r, l, s in defs],
                "referenced_by": [{"file": r, "count": n} for r, n in ref_counts],
                "occurrences": len(refs),
            }, indent=2))
        else:
            print_symbol(a.symbol, defs, ref_counts, refs)
        return 0 if defs else 0

    data = scan(root)
    if a.json:
        out = dict(data)
        out["ranking"] = [{"file": f, "in_degree": n} for f, n in data["ranking"][:a.top]]
        out["largest_files"] = [{"file": f, "lines": n} for f, n in data["largest_files"]]
        out["entry_points"] = [{"file": f, "line": l, "label": lab} for f, l, lab in data["entry_points"]]
        out["dirs_by_count"] = [{"dir": d, "files": n} for d, n in data["dirs_by_count"]]
        print(json.dumps(out, indent=2))
    else:
        print_orientation(data, a.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
