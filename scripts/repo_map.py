#!/usr/bin/env python3
"""Fast orientation for a repo you have never seen: stacks, workspaces and their
packages, HTTP routes per framework, ranked entry points, an import-graph ranking
of the most-connected files, test/source ratio, largest files, and which docs to
read before the code. Also lints the durable architecture note the
codebase-comprehension skill produces (`--lint-note`).

File listing. Inside a git work tree the file list is `git ls-files --cached
--others --exclude-standard`, so anything the project ignores (build output,
`app/assets/builds/*`, caches) never enters the map. An audit on a large Rails
repo found exactly that failure: gitignored compiled assets dominated "largest
files" and the ranking, while `config/routes.rb` was never reported. Outside git
it walks the tree, skipping dependency, build and generated directories.

Generated and vendored code (a `generated/` or `vendor/` path, a header marker
within the first lines such as the Go "Code generated ... DO NOT EDIT" line) is
deprioritised, not hidden: it sorts after everything else in entry points and the
ranking, is excluded from "largest files", and is counted separately.

Ranking. Aider's repo-map is the canonical version of this idea
(`Aider-AI/aider@main:aider/aider/repomap.py`; see
research/22-findings-agent-tool-internals.md, "Context selection / repo-map
algorithms"): tree-sitter def/ref tags (repomap.py:233), a weighted symbol graph
(repomap.py:365, 472-511), personalized PageRank (repomap.py:525), then a
token-budgeted slice (repomap.py:629-710). This script approximates only the
ranking step, with two deliberate cuts: imports are resolved with regex to files
(file-level, not symbol-level), and the score is in-degree, not PageRank, so a
file imported by an important file scores the same as one imported by a leaf.
Resolution exists for Python, JS/TS, Go (via go.mod module paths; a package import
credits every non-test file in that package directory), Java/Kotlin (via `package`
declarations), Ruby (`require_relative`, `require` into lib/) and Rails
(`config/routes.rb` credits the controllers it routes to). Other languages are
listed as unranked rather than silently scored 0.

    repo_map.py .                        # orientation summary
    repo_map.py . --top 20               # the N most-connected files
    repo_map.py . --symbol AuthService   # where is it defined, who references it
    repo_map.py . --json
    repo_map.py --lint-note docs/engineering/architecture/auth.md

Python stdlib only. SOURCE: original except where cited above.
"""
import argparse, json, os, re, subprocess, sys, pathlib
from collections import Counter, defaultdict

# Skipped when walking outside git. Inside git, .gitignore decides; only these
# dependency stores are dropped even if someone committed them.
ALWAYS_SKIP = {".git", "node_modules", ".pnpm-store", ".yarn"}
SKIP_DIRS = ALWAYS_SKIP | {
    "dist", "build", ".venv", "venv", "env", "__pycache__", ".next", "coverage",
    ".turbo", "vendor", "target", ".cache", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".idea", ".vscode", ".tox", ".terraform", "site-packages",
    ".eggs", "generated", "__generated__", ".gradle", "Pods", ".dart_tool",
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
JS_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
RESOLVABLE_EXT = {".py", ".go", ".java", ".kt", ".rb"} | JS_EXT

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
    r"|\.(test|spec)\.(ts|tsx|js|jsx)$|_spec\.rb$|Test\.(java|kt)$",
    re.I,
)

GENERATED_PATH_RX = re.compile(
    r"(^|/)(generated|__generated__|vendor|third_party|dist|build)/"
    r"|\.min\.(js|css)$|\.pb\.go$|_pb2(_grpc)?\.py$|\.g\.dart$|\.freezed\.dart$"
    r"|\.generated\.\w+$|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock)$"
)
GENERATED_HEADER_RX = re.compile(
    r"@" r"generated|DO NOT " r"EDIT|Code generated .* DO NOT|auto-?generated", re.I)
HEADER_LINES = 10

DOC_ROOT_NAMES = {
    "agents.md", "claude.md", "contributing.md", "contributing.rst",
    "codeowners", "security.md",
}
DOC_DIR_NAMES = {"decisions", "adr", "adrs", "specs", "rfcs", "docs", "architecture"}

MAX_READ_BYTES = 1_500_000  # content-scan cap; larger files are counted, not read

# (suffixes, regex, label, weight). Weight orders entry points: 3 = process or
# routing root, 2 = a handler surface, 1 = a weak conventional signal.
ENTRY_PATTERNS = [
    ({".py"}, re.compile(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]'), "__main__ guard", 3),
    ({".py"}, re.compile(r'@click\.(?:command|group)\b'), "CLI command (click)", 2),
    ({".py"}, re.compile(r'add_(?:sub)?parser\(|ArgumentParser\('), "CLI registration (argparse)", 2),
    (JS_EXT, re.compile(r'\.command\('), "CLI registration (commander/yargs-style)", 2),
    (JS_EXT, re.compile(r'NestFactory\.create\('), "NestJS bootstrap", 3),
    (JS_EXT, re.compile(r'export\s+default\s+(?:async\s+)?function'), "exported default handler", 1),
    (JS_EXT, re.compile(r'module\.exports\s*='), "exported module (CommonJS)", 1),
    ({".go"}, re.compile(r'^\s*func\s+main\s*\('), "func main", 3),
    ({".java", ".kt"}, re.compile(r'static\s+void\s+main\s*\(|^\s*fun\s+main\s*\('), "main method", 3),
    ({".java", ".kt"}, re.compile(r'@SpringBootApplication'), "Spring Boot application", 3),
    ({".java", ".kt"}, re.compile(r'@(?:Rest)?Controller\b'), "Spring controller", 2),
    ({".rs"}, re.compile(r'^\s*fn\s+main\s*\('), "fn main", 3),
]
FILENAME_ENTRY = {
    "main.py": ("conventional entry filename", 1), "app.py": ("conventional entry filename", 1),
    "manage.py": ("Django management entry", 3), "wsgi.py": ("WSGI entry", 2),
    "asgi.py": ("ASGI entry", 2), "cli.py": ("CLI entry filename", 1),
    "index.ts": ("conventional entry filename", 1), "index.js": ("conventional entry filename", 1),
    "main.ts": ("conventional entry filename", 1), "server.ts": ("conventional entry filename", 1),
    "server.js": ("conventional entry filename", 1), "main.go": ("Go entry filename", 1),
    "config.ru": ("Rack entry", 3),
}


# ---------------------------------------------------------------------------
# file listing
# ---------------------------------------------------------------------------
def git_listing(root):
    """Repo-relative paths git would track (tracked + untracked-not-ignored), or
    None when root is not inside a work tree."""
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others",
             "--exclude-standard"], capture_output=True, text=True)
    except OSError:
        return None
    if r.returncode != 0:
        return None
    out = set()
    for p in r.stdout.split("\0"):
        if not p or any(seg in ALWAYS_SKIP for seg in p.split("/")):
            continue
        if (root / p).is_file():  # drops submodules and tracked-but-deleted paths
            out.add(p)
    return sorted(out)


def walk_listing(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for fn in sorted(filenames):
            out.append(relpath(root, pathlib.Path(dirpath) / fn))
    return out


def list_files(root):
    g = git_listing(root)
    return (g, "git ls-files (respects .gitignore)") if g is not None \
        else (walk_listing(root), "directory walk (not a git work tree)")


def relpath(root, p):
    return os.path.normpath(os.path.relpath(p, root)).replace(os.sep, "/")


def read_text(path):
    try:
        if path.stat().st_size > MAX_READ_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def is_generated(rel, text):
    if GENERATED_PATH_RX.search(rel):
        return True
    if text:
        head = "\n".join(text.splitlines()[:HEADER_LINES])
        return bool(GENERATED_HEADER_RX.search(head))
    return False


def glob_rx(pattern):
    """Glob with `**` spanning directories and `*` staying inside one segment."""
    p = pattern.strip()
    p = (p[2:] if p.startswith("./") else p).rstrip("/")
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out += r"(?:.*/)?"; i += 3
        elif p.startswith("**", i):
            out += r".*"; i += 2
        elif p[i] == "*":
            out += r"[^/]*"; i += 1
        elif p[i] == "?":
            out += r"[^/]"; i += 1
        else:
            out += re.escape(p[i]); i += 1
    return re.compile(rf"^{out}$")


# ---------------------------------------------------------------------------
# workspaces
# ---------------------------------------------------------------------------
PKG_MANIFESTS = ("package.json", "go.mod", "Cargo.toml", "build.gradle", "build.gradle.kts",
                 "project.json", "pyproject.toml", "pom.xml")


def _yaml_list(text, key):
    items, inside = [], False
    for line in text.splitlines():
        if re.match(rf"^{key}\s*:", line):
            inside = True
            continue
        if inside:
            m = re.match(r"^\s*-\s*['\"]?([^'\"#]+?)['\"]?\s*(#.*)?$", line)
            if m:
                items.append(m.group(1).strip())
            elif line.strip() and not line.startswith((" ", "\t")):
                break
    return items


def detect_workspaces(root, files):
    fileset = set(files)
    tools, patterns, gradle_dirs = [], [], []

    def text(name):
        return read_text(root / name) if name in fileset else None

    t = text("pnpm-workspace.yaml")
    if t is not None:
        tools.append(("pnpm", "pnpm-workspace.yaml"))
        patterns += _yaml_list(t, "packages")
    t = text("package.json")
    if t is not None:
        try:
            ws = json.loads(t).get("workspaces")
        except (ValueError, AttributeError):
            ws = None
        if isinstance(ws, dict):
            ws = ws.get("packages")
        if isinstance(ws, list) and ws:
            tools.append(("npm/yarn workspaces", "package.json"))
            patterns += [w for w in ws if isinstance(w, str)]
    t = text("lerna.json")
    if t is not None:
        tools.append(("lerna", "lerna.json"))
        try:
            patterns += json.loads(t).get("packages") or ["packages/*"]
        except ValueError:
            patterns.append("packages/*")
    for marker, tool in (("turbo.json", "turborepo"), ("nx.json", "nx")):
        if marker in fileset:
            tools.append((tool, marker))
    t = text("go.work")
    if t is not None:
        tools.append(("go workspace", "go.work"))
        for m in re.finditer(r"^\s*use\s*\(\s*(.*?)\)", t, re.S | re.M):
            patterns += [x.strip() for x in m.group(1).split() if x.strip()]
        patterns += re.findall(r"^\s*use\s+([^\s(]+)", t, re.M)
    t = text("Cargo.toml")
    if t is not None and re.search(r"^\[workspace\]", t, re.M):
        tools.append(("cargo workspace", "Cargo.toml"))
        m = re.search(r"^\[workspace\].*?^members\s*=\s*\[(.*?)\]", t, re.S | re.M)
        if m:
            patterns += re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
    for g in ("settings.gradle", "settings.gradle.kts"):
        t = text(g)
        if t is not None:
            incs = []
            for m in re.finditer(r"^\s*include\s*\(?(.*)$", t, re.M):
                incs += re.findall(r"['\"]:?([^'\"]+)['\"]", m.group(1))
            if incs:
                tools.append(("gradle multi-project", g))
                gradle_dirs += [i.replace(":", "/") for i in incs]
    if not tools:
        return [], []

    dirs = set()
    for f in files:
        parts = f.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    has_manifest = {d for d in dirs for m in PKG_MANIFESTS if f"{d}/{m}" in fileset}
    pkg_dirs = set()
    for pat in patterns:
        if pat.startswith("!"):
            continue
        rx = glob_rx(pat)
        pkg_dirs |= {d for d in has_manifest if rx.match(d)}
    pkg_dirs |= {d for d in gradle_dirs if d in dirs}
    if any(t_ == "nx" for t_, _ in tools):
        pkg_dirs |= {d for d in has_manifest if f"{d}/project.json" in fileset}
    if any(t_ == "turborepo" for t_, _ in tools) and not pkg_dirs:
        pkg_dirs |= {d for d in has_manifest if re.match(r"^(apps|packages)/[^/]+$", d)}
    return [{"tool": a, "config": b} for a, b in tools], sorted(pkg_dirs)


def package_name(root, d, fileset):
    if f"{d}/package.json" in fileset:
        try:
            n = json.loads(read_text(root / d / "package.json") or "{}").get("name")
            if n:
                return n
        except ValueError:
            pass
    if f"{d}/go.mod" in fileset:
        m = re.search(r"^module\s+(\S+)", read_text(root / d / "go.mod") or "", re.M)
        if m:
            return m.group(1)
    if f"{d}/Cargo.toml" in fileset:
        m = re.search(r'^name\s*=\s*"([^"]+)"', read_text(root / d / "Cargo.toml") or "", re.M)
        if m:
            return m.group(1)
    return d


# ---------------------------------------------------------------------------
# route detectors (one per framework). Each returns [(method, path, line)].
# ---------------------------------------------------------------------------
HTTP = "get|post|put|patch|delete|all|options|head"


def routes_rails(lines):
    out, stack = [], []
    for i, l in enumerate(lines, 1):
        s = l.strip()
        if s.startswith("#"):
            continue
        prefix = "".join(stack)
        m = re.match(r"^(?:namespace|scope)\s+(?::(\w+)|['\"]([^'\"]*)['\"]|path:\s*['\"]([^'\"]*)['\"])", s)
        if m and re.search(r"\bdo\b", s):
            seg = (m.group(1) or m.group(2) or m.group(3) or "").strip("/")
            stack.append("/" + seg if seg else "")
            continue
        m = re.match(r"^(get|post|put|patch|delete|match)\s+['\"]([^'\"]+)['\"]", s)
        if m:
            out.append((m.group(1).upper(), prefix + "/" + m.group(2).lstrip("/"), i))
        m = re.match(r"^(resources?)\s+:(\w+)", s)
        if m:
            out.append((m.group(1).upper(), f"{prefix}/{m.group(2)}", i))
        if re.match(r"^root\b", s):
            out.append(("GET", prefix + "/", i))
        if re.search(r"\bdo\s*(\|[^|]*\|)?\s*$", s):
            stack.append("")
        elif re.match(r"^end\b", s) and stack:
            stack.pop()
    return out


def rails_controller_targets(lines):
    """controller paths config/routes.rb dispatches to, for the ranking."""
    out, ns = set(), []
    for l in lines:
        s = l.strip()
        m = re.match(r"^namespace\s+:(\w+)\s+do", s)
        if m:
            ns.append(m.group(1)); continue
        if re.match(r"^end\b", s) and ns:
            ns.pop()
        base = "/".join(ns)
        for m in re.finditer(r"^resources?\s+:(\w+)", s):
            out.add(f"app/controllers/{base + '/' if base else ''}{m.group(1)}_controller.rb")
        for m in re.finditer(r"to:\s*['\"]([\w/]+)#\w+['\"]|['\"]([\w/]+)#\w+['\"]", s):
            c = m.group(1) or m.group(2)
            out.add(f"app/controllers/{base + '/' if base and '/' not in c else ''}{c}_controller.rb")
    return out


def routes_nest(lines):
    out, prefix = [], ""
    for i, l in enumerate(lines, 1):
        m = re.search(r"@Controller\(\s*(?:\{[^}]*path:\s*)?(?:['\"`]([^'\"`]*)['\"`])?", l)
        if m:
            prefix = "/" + (m.group(1) or "").strip("/") if m.group(1) else ""
            continue
        m = re.search(r"@(Get|Post|Put|Patch|Delete|All|Options|Head)\(\s*(?:['\"`]([^'\"`]*)['\"`])?", l)
        if m:
            sub = (m.group(2) or "").strip("/")
            out.append((m.group(1).upper(), (prefix + ("/" + sub if sub else "")) or "/", i))
    return out


def routes_express(lines):
    rx = re.compile(rf"\b(?:app|router|server|fastify|api|routes)\.({HTTP})\(\s*['\"`](/[^'\"`]*)['\"`]")
    return [(m.group(1).upper(), m.group(2), i) for i, l in enumerate(lines, 1)
            for m in [rx.search(l)] if m]


def routes_python(lines):
    rx = re.compile(rf"@\w+\.({HTTP}|route|api_route)\(\s*['\"](/[^'\"]*)['\"]")
    out = []
    for i, l in enumerate(lines, 1):
        m = rx.search(l)
        if m:
            meth = m.group(1).upper()
            out.append(("ANY" if meth in ("ROUTE", "API_ROUTE") else meth, m.group(2), i))
    return out


def routes_django(lines):
    rx = re.compile(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]")
    return [("ANY", "/" + m.group(1).lstrip("^/"), i) for i, l in enumerate(lines, 1)
            for m in [rx.search(l)] if m]


def routes_go(lines):
    out = []
    for i, l in enumerate(lines, 1):
        m = re.search(r"\.(?:HandleFunc|Handle)\(\s*\"([^\"]+)\"", l)
        if m:
            pat = m.group(1)
            meth, _, path = pat.partition(" ") if " " in pat else ("ANY", "", pat)
            out.append((meth.upper(), path, i))
            continue
        m = re.search(r"\b\w+\.(GET|POST|PUT|PATCH|DELETE|Get|Post|Put|Patch|Delete|Any)\(\s*\"(/[^\"]*)\"", l)
        if m:
            out.append((m.group(1).upper(), m.group(2), i))
    return out


def routes_spring(lines):
    out, prefix, in_class = [], "", False
    rx = re.compile(r"@(Get|Post|Put|Patch|Delete|Request)Mapping\b(?:\(\s*(?:value\s*=\s*|path\s*=\s*)?"
                    r"(?:\[|arrayOf\(|\{)?\s*\"([^\"]*)\")?")
    for i, l in enumerate(lines, 1):
        if re.search(r"\bclass\s+\w+", l):
            in_class = True
            continue
        m = rx.search(l)
        if not m:
            continue
        path = (m.group(2) or "").strip("/")
        if m.group(1) == "Request" and not in_class:
            prefix = "/" + path if path else ""
            continue
        meth = "ANY" if m.group(1) == "Request" else m.group(1).upper()
        out.append((meth, (prefix + ("/" + path if path else "")) or "/", i))
    return out


NEXT_METHOD_RX = re.compile(r"export\s+(?:async\s+)?(?:function|const)\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b")


def next_route(rel):
    """(kind, url) for a Next.js app/ or pages/ file, else None."""
    m = re.match(r"^(?:.*/)?(?:src/)?app/(?:(.*)/)?(page|route)\.(tsx|ts|jsx|js|mdx)$", rel)
    if m:
        segs = [s for s in (m.group(1) or "").split("/")
                if s and not (s.startswith("(") and s.endswith(")")) and not s.startswith("@")]
        return ("PAGE" if m.group(2) == "page" else "API"), "/" + "/".join(segs)
    m = re.match(r"^(?:.*/)?(?:src/)?pages/(.*)\.(tsx|ts|jsx|js)$", rel)
    if m and not re.search(r"(^|/)_(app|document|error)$", m.group(1)):
        segs = m.group(1).split("/")
        if segs[-1] == "index":
            segs = segs[:-1]
        return ("API" if segs[:1] == ["api"] else "PAGE"), "/" + "/".join(segs)
    return None


# ---------------------------------------------------------------------------
# import extraction (resolved after the scan, once every file is indexed)
# ---------------------------------------------------------------------------
PY_IMPORT_RE = re.compile(r'^\s*(?:from\s+([.\w]+)\s+import|import\s+([.\w, ]+))', re.M)
JS_IMPORT_RE = re.compile(
    r'''(?:from|import)\s+['"](\.[^'"]+)['"]|require\(\s*['"](\.[^'"]+)['"]\s*\)''')
GO_IMPORT_BLOCK = re.compile(r'^import\s*\((.*?)\)', re.S | re.M)
GO_IMPORT_ONE = re.compile(r'^import\s+(?:[\w.]+\s+)?"([^"]+)"', re.M)
JVM_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)', re.M)
JVM_IMPORT = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)', re.M)
RB_REQUIRE = re.compile(r'''^\s*(require_relative|require)\s+['"]([^'"]+)['"]''', re.M)


def norm_join(base, ref):
    norm = []
    for part in (pathlib.PurePosixPath(base) / ref).parts:
        if part == "..":
            if norm:
                norm.pop()
        elif part != ".":
            norm.append(part)
    return "/".join(norm)


def py_targets(rel_file, module):
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
        mod = module.replace(".", "/")
        sibling = pathlib.PurePosixPath(rel_file).parent / mod  # script-dir imports
        return [mod + ".py", mod + "/__init__.py", f"{sibling}.py", f"{sibling}/__init__.py"]
    return [str(target) + ".py", str(target) + "/__init__.py"]


def js_targets(rel_file, ref):
    base = norm_join(pathlib.PurePosixPath(rel_file).parent, ref) or "."
    if pathlib.PurePosixPath(base).suffix in JS_EXT:
        return [base]
    return [base + e for e in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")] + \
           [f"{base}/index{e}" for e in (".ts", ".tsx", ".js", ".jsx")]


def extract_imports(rel, suffix, text):
    """Raw import references; ('file', path) or ('go', importpath) or ('jvm', fqname)."""
    refs = []
    if suffix == ".py":
        for m in PY_IMPORT_RE.finditer(text):
            for piece in (m.group(1) or m.group(2) or "").split(","):
                piece = piece.strip().split(" as ")[0].strip()
                if piece:
                    refs += [("file", t) for t in py_targets(rel, piece)]
    elif suffix in JS_EXT:
        for m in JS_IMPORT_RE.finditer(text):
            ref = m.group(1) or m.group(2)
            if ref:
                refs += [("file", t) for t in js_targets(rel, ref)]
    elif suffix == ".go":
        for m in GO_IMPORT_BLOCK.finditer(text):
            refs += [("go", p) for p in re.findall(r'"([^"]+)"', m.group(1))]
        refs += [("go", p) for p in GO_IMPORT_ONE.findall(text)]
    elif suffix in (".java", ".kt"):
        refs += [("jvm", p) for p in JVM_IMPORT.findall(text)]
    elif suffix == ".rb":
        for kind, ref in RB_REQUIRE.findall(text):
            ref = ref if ref.endswith(".rb") else ref + ".rb"
            if kind == "require_relative":
                refs.append(("file", norm_join(pathlib.PurePosixPath(rel).parent, ref)))
            else:
                refs += [("file", "lib/" + ref), ("file", ref)]
    return refs


# ---------------------------------------------------------------------------
# orientation scan: one read per file
# ---------------------------------------------------------------------------
def scan(root):
    files, listing = list_files(root)
    fileset = set(files)
    code_files = [f for f in files if pathlib.PurePosixPath(f).suffix in CODE_EXT]
    has_next = any(re.search(r"(^|/)next\.config\.(js|mjs|cjs|ts)$", f) for f in files) or any(
        f.endswith("package.json") and '"next"' in (read_text(root / f) or "")
        for f in files if f.count("/") <= 3)

    generated, line_counts, entries, routes = set(), {}, [], []
    raw_imports, jvm_index, go_files_by_dir = {}, {}, defaultdict(list)
    extra_edges = defaultdict(set)  # target -> importers, from non-import evidence
    unranked = set()

    for f in files:
        name = f.rsplit("/", 1)[-1]
        if name in FILENAME_ENTRY and not GENERATED_PATH_RX.search(f):
            label, w = FILENAME_ENTRY[name]
            entries.append((f, 0, label, w))

    for rel in code_files:
        p = root / rel
        suffix = pathlib.PurePosixPath(rel).suffix
        text = read_text(p)
        if is_generated(rel, text):
            generated.add(rel)
        if text is None:
            line_counts[rel] = 0
            continue
        lines = text.splitlines()
        line_counts[rel] = len(lines)
        if suffix not in RESOLVABLE_EXT:
            unranked.add(LANG_EXT[suffix])
        else:
            raw_imports[rel] = extract_imports(rel, suffix, text)
        if suffix in (".java", ".kt"):
            m = JVM_PACKAGE.search(text)
            stem = pathlib.PurePosixPath(rel).stem
            jvm_index[(m.group(1) + "." if m else "") + stem] = rel
        if suffix == ".go" and not rel.endswith("_test.go"):
            go_files_by_dir[str(pathlib.PurePosixPath(rel).parent)].append(rel)

        for suffixes, pat, label, w in ENTRY_PATTERNS:
            if suffix in suffixes:
                for i, line in enumerate(lines, 1):
                    if pat.search(line):
                        entries.append((rel, i, label, w))
                        break

        found = []
        if rel == "config/routes.rb" or rel.endswith("/config/routes.rb"):
            found.append(("Rails", routes_rails(lines), 3))
            base = rel[: -len("config/routes.rb")]
            for c in rails_controller_targets(lines):
                extra_edges[base + c].add(rel)
        elif suffix == ".rb" and re.search(r"(^|/)app/controllers/.+_controller\.rb$", rel) \
                and not rel.endswith("application_controller.rb"):
            entries.append((rel, 1, "Rails controller", 2))
        if suffix in JS_EXT:
            found.append(("NestJS", routes_nest(lines), 2))
            found.append(("Express/Fastify", routes_express(lines), 2))
            if has_next:
                nr = next_route(rel)
                if nr:
                    kind, url = nr
                    meths = NEXT_METHOD_RX.findall(text) if kind == "API" else []
                    found.append(("Next.js", [(m, url, 1) for m in meths] or [(kind, url, 1)], 2))
        if suffix == ".py":
            found.append(("FastAPI/Flask", routes_python(lines), 2))
            if rel.endswith("urls.py"):
                found.append(("Django", routes_django(lines), 3))
        if suffix == ".go":
            found.append(("Go net/http/chi/gin", routes_go(lines), 2))
        if suffix in (".java", ".kt"):
            found.append(("Spring", routes_spring(lines), 2))
        for fw, rs, w in found:
            if not rs:
                continue
            for meth, path, ln in rs:
                routes.append({"framework": fw, "method": meth, "path": path,
                               "file": rel, "line": ln})
            entries.append((rel, rs[0][2], f"HTTP routes: {fw} ({len(rs)})", w))

    # resolve imports
    go_mods = {}
    for f in files:
        if f == "go.mod" or f.endswith("/go.mod"):
            m = re.search(r"^module\s+(\S+)", read_text(root / f) or "", re.M)
            if m:
                go_mods[m.group(1)] = str(pathlib.PurePosixPath(f).parent)
    codeset = set(code_files)
    importers = defaultdict(set)
    for rel, refs in raw_imports.items():
        targets = set()
        for kind, ref in refs:
            if kind == "file":
                t = os.path.normpath(ref).replace(os.sep, "/")
                if t in codeset:
                    targets.add(t)
            elif kind == "go":
                for mod, d in go_mods.items():
                    if ref == mod or ref.startswith(mod + "/"):
                        sub = ref[len(mod):].lstrip("/")
                        pkg = "/".join(x for x in (d if d != "." else "", sub) if x) or "."
                        targets.update(go_files_by_dir.get(pkg, []))
            elif kind == "jvm":
                t = jvm_index.get(ref) or jvm_index.get(ref.rsplit(".", 1)[0])
                if t:
                    targets.add(t)
        for t in targets - {rel}:
            importers[t].add(rel)
    for t, srcs in extra_edges.items():
        if t in codeset:
            importers[t] |= srcs
    in_degree = {t: len(s) for t, s in importers.items()}

    ranking = sorted(in_degree.items(), key=lambda kv: (kv[0] in generated, -kv[1], kv[0]))
    entries = sorted(set(entries), key=lambda e: (e[0] in generated, -e[3],
                                                  -in_degree.get(e[0], 0), e[0], e[1], e[2]))

    test_files = [f for f in code_files if TEST_RE.search(f)]
    top_dirs = Counter(f.split("/")[0] if "/" in f else "." for f in files)
    dirs = set()
    for f in files:
        parts = f.split("/")[:-1]
        for i in range(1, min(len(parts), 4) + 1):
            dirs.add("/".join(parts[:i]))
    docs = sorted({f for f in files if "/" not in f and f.lower() in DOC_ROOT_NAMES} |
                  {d + "/" for d in dirs if d.rsplit("/", 1)[-1].lower() in DOC_DIR_NAMES})

    workspaces, pkg_dirs = detect_workspaces(root, files)
    packages = []
    for d in pkg_dirs:
        pre = d + "/"
        pf = [f for f in files if f.startswith(pre)]
        langs = Counter(LANG_EXT[pathlib.PurePosixPath(f).suffix] for f in pf
                        if pathlib.PurePosixPath(f).suffix in CODE_EXT)
        top = next((f for f, _ in ranking if f.startswith(pre) and f not in generated), None)
        packages.append({
            "path": d, "name": package_name(root, d, fileset), "files": len(pf),
            "languages": dict(langs.most_common(3)),
            "entry_points": sum(1 for e in entries if e[0].startswith(pre)),
            "routes": sum(1 for r in routes if r["file"].startswith(pre)),
            "most_connected": top,
        })

    lang_counts = Counter(LANG_EXT[pathlib.PurePosixPath(f).suffix] for f in code_files)
    return {
        "root": str(root),
        "listing": listing,
        "total_files": len(files),
        "code_files": len(code_files),
        "languages": dict(sorted(lang_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "stack_markers": sorted({label for fname, label in STACK_MARKERS
                                 if any(f == fname or f.endswith("/" + fname) for f in files)}),
        "workspaces": workspaces,
        "packages": packages,
        "routes": sorted(routes, key=lambda r: (r["file"] in generated, r["file"], r["line"])),
        "entry_points": entries,
        "ranking": ranking,
        "importers": {k: sorted(v) for k, v in importers.items()},
        "unranked_languages": sorted(unranked),
        "generated": sorted(generated),
        "test_files": len(test_files),
        "source_files": len(code_files) - len(test_files),
        "largest_files": sorted(((f, n) for f, n in line_counts.items() if f not in generated),
                                key=lambda kv: (-kv[1], kv[0]))[:15],
        "dirs_by_count": sorted(top_dirs.items(), key=lambda kv: (-kv[1], kv[0])),
        "docs_worth_reading": docs,
    }


# ---------------------------------------------------------------------------
# symbol lookup
# ---------------------------------------------------------------------------
def def_patterns(symbol):
    sym = re.escape(symbol)
    return [re.compile(p) for p in (
        rf'^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+{sym}\b',
        rf'^\s*(?:export\s+)?interface\s+{sym}\b',
        rf'^\s*(?:export\s+)?type\s+{sym}\b',
        rf'^\s*(?:export\s+)?(?:async\s+)?function\s+{sym}\b',
        rf'^\s*(?:export\s+)?const\s+{sym}\s*=',
        rf'^\s*def\s+(?:self\.)?{sym}\b',
        rf'^\s*class\s+{sym}\b',
        rf'^\s*module\s+{sym}\b',
        rf'^\s*func\s+(?:\([^)]*\)\s*)?{sym}\b',
        rf'^\s*type\s+{sym}\b',
        rf'\bstruct\s+{sym}\b',
        rf'^\s*(?:public|private|internal|protected)?\s*(?:final\s+|data\s+|open\s+)?'
        rf'(?:class|interface|object|enum)\s+{sym}\b',
        rf'^\s*fun\s+(?:<[^>]*>\s*)?(?:\w+\.)?{sym}\s*\(',
    )]


def find_symbol(root, symbol):
    defs, refs = [], []
    ref_pat = re.compile(rf'\b{re.escape(symbol)}\b')
    dpats = def_patterns(symbol)
    files, _ = list_files(root)
    for rel in files:
        if pathlib.PurePosixPath(rel).suffix not in CODE_EXT:
            continue
        text = read_text(root / rel)
        if text is None or symbol not in text:
            continue
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
# architecture-note lint (the codebase-comprehension skill's durable artifact)
# ---------------------------------------------------------------------------
NOTE_SECTIONS = [
    ("context", "Context"), ("entry points", "Entry points"), ("data flow", "Data flow"),
    ("boundaries", "Boundaries"), ("hot file", "Hot file"),
    ("predict", "Predict, then confirm"), ("glossary", "Glossary"),
    ("open questions", "Open questions"),
]
CLAIM_SECTIONS = ("entry points", "data flow", "boundaries", "hot file", "predict")
TAG_RX = re.compile(r"\b(verified|inferred)\b", re.I)
FILE_LINE_RX = re.compile(r"[\w./-]+\.\w+:\d+")


def note_sections(text):
    secs, cur, fence = {}, None, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence:
            m = re.match(r"^##\s+(.+?)\s*$", line)
            if m:
                cur = m.group(1).strip().lower()
                secs[cur] = []
                continue
        if cur is not None:
            secs[cur].append(line)
    return secs


def claim_lines(body):
    out, fence = [], False
    for l in body:
        if l.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        s = l.strip()
        if re.match(r"^([-*]|\d+\.)\s+\S", s):
            out.append(s)
        elif s.startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", s):
            out.append(s)
    return out


def lint_note(path):
    p = pathlib.Path(path)
    if not p.is_file():
        print(f"repo_map --lint-note: no such file: {path}", file=sys.stderr)
        return 2
    secs = note_sections(p.read_text(errors="replace"))
    errs = []

    def find(key):
        return next((v for k, v in secs.items() if k.startswith(key) or key in k), None)

    for key, label in NOTE_SECTIONS:
        if find(key) is None:
            errs.append(f"missing section '## {label}'")
    ctx = find("context")
    if ctx is not None and not any(l.strip().startswith("```mermaid") for l in ctx):
        errs.append("'## Context' has no ```mermaid diagram (the L1 context diagram)")
    for key in CLAIM_SECTIONS:
        body = find(key)
        if body is None:
            continue
        rows = claim_lines(body)
        data = [r for r in rows if not is_header_row(r, body)]
        if not data:
            errs.append(f"'## {key}' states no claims (bullets or table rows)")
        for r in data:
            if not TAG_RX.search(r):
                errs.append(f"'## {key}': claim not tagged verified/inferred: {r[:90]}")
            if key == "entry points" and not FILE_LINE_RX.search(r):
                errs.append(f"'## entry points': no file:line: {r[:90]}")
        if key == "predict" and len(data) < 3:
            errs.append(f"'## Predict, then confirm' has {len(data)} claim(s), need the top 3")
    oq = find("open questions")
    if oq is not None and not any(l.strip() for l in oq):
        errs.append("'## Open questions' is empty (write 'none' if there are none)")
    for e in errs:
        print(f"  ERROR {path}: {e}")
    print(f"\nlint-note: {path}: {len(errs)} error(s)")
    return 1 if errs else 0


def is_header_row(row, body):
    """A table's first row is its header when the next non-blank line is a separator."""
    if not row.startswith("|"):
        return False
    lines = [l.strip() for l in body if l.strip()]
    for i, l in enumerate(lines[:-1]):
        if l == row:
            return bool(re.match(r"^\|[\s:|-]+\|?$", lines[i + 1]))
    return False


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def print_orientation(r, top):
    gen = set(r["generated"])
    print(f"repo_map: {r['root']}")
    print(f"  {r['total_files']} files total, {r['code_files']} code files "
          f"(listing: {r['listing']})")
    if not r["code_files"]:
        print("  no recognized source files under this root")
        return

    print("\nLanguages (file count):")
    for lang, n in r["languages"].items():
        print(f"  {n:5d}  {lang}")
    if r["stack_markers"]:
        print("\nStack markers: " + ", ".join(r["stack_markers"]))

    if r["workspaces"]:
        print("\nWorkspaces: " + ", ".join(f"{w['tool']} ({w['config']})" for w in r["workspaces"]))
        print(f"Packages ({len(r['packages'])}):")
        for p in r["packages"]:
            langs = ", ".join(f"{k} {v}" for k, v in p["languages"].items()) or "no code"
            print(f"  {p['path']:32s} {p['name']:28s} {p['files']:5d} files  "
                  f"{p['entry_points']} entry  {p['routes']} routes  [{langs}]")
            if p["most_connected"]:
                print(f"  {'':32s} most connected: {p['most_connected']}")

    print(f"\nRoutes ({len(r['routes'])}, showing up to 30):")
    if not r["routes"]:
        print("  none detected")
    for x in r["routes"][:30]:
        mark = "  [generated]" if x["file"] in gen else ""
        print(f"  {x['method']:9s} {x['path'][:40]:40s} {x['file']}:{x['line']}  "
              f"({x['framework']}){mark}")
    if len(r["routes"]) > 30:
        print(f"  ... and {len(r['routes']) - 30} more (--json for all)")

    print(f"\nEntry points ({len(r['entry_points'])} signals, ranked, showing up to 25):")
    for rel, line, label, _w in r["entry_points"][:25]:
        loc = f"{rel}:{line}" if line else rel
        mark = "  [generated]" if rel in gen else ""
        print(f"  {loc:60s} {label}{mark}")
    if len(r["entry_points"]) > 25:
        print(f"  ... and {len(r['entry_points']) - 25} more")

    print(f"\nMost-connected files (in-degree, top {top} — cheaper approximation of "
          f"aider's PageRank repo-map, see module docstring):")
    if not r["ranking"]:
        print("  no internal import edges resolved")
    for rel, n in r["ranking"][:top]:
        mark = "  [generated]" if rel in gen else ""
        print(f"  {n:4d} importer(s)  {rel}{mark}")
    if r["unranked_languages"]:
        print(f"  (not ranked — no import-resolution heuristic for: "
              f"{', '.join(r['unranked_languages'])})")

    ratio = (r["test_files"] / r["source_files"]) if r["source_files"] else 0.0
    print(f"\nTest-to-source ratio: {r['test_files']} test files / "
          f"{r['source_files']} source files = {ratio:.2f}")

    print("\nLargest files (by line count, generated excluded):")
    for rel, n in r["largest_files"][:10]:
        print(f"  {n:6d}  {rel}")
    if gen:
        print(f"\nGenerated/vendored (deprioritised): {len(gen)} file(s), e.g. "
              + ", ".join(sorted(gen)[:3]))

    print("\nDirectories by file count:")
    for d, n in r["dirs_by_count"][:15]:
        print(f"  {n:5d}  {d}")

    print("\nRead before the code (AGENTS.md/CONTRIBUTING/ADR/spec locations):")
    for d in r["docs_worth_reading"] or ["none found"]:
        print(f"  {d}")


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
    ap.add_argument("--lint-note", metavar="FILE",
                    help="lint an architecture note: required sections, a mermaid context "
                         "diagram, file:line entry points, every claim tagged verified/inferred")
    a = ap.parse_args()

    if a.lint_note:
        return lint_note(a.lint_note)

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
        return 0

    data = scan(root)
    if a.json:
        gen = set(data["generated"])
        out = dict(data)
        out["ranking"] = [{"file": f, "in_degree": n, "generated": f in gen}
                          for f, n in data["ranking"][:a.top]]
        out["largest_files"] = [{"file": f, "lines": n} for f, n in data["largest_files"]]
        out["entry_points"] = [{"rank": i, "file": f, "line": l, "label": lab, "weight": w,
                                "generated": f in gen}
                               for i, (f, l, lab, w) in enumerate(data["entry_points"], 1)]
        out["dirs_by_count"] = [{"dir": d, "files": n} for d, n in data["dirs_by_count"]]
        out["generated_files"] = len(gen)
        print(json.dumps(out, indent=2))
    else:
        print_orientation(data, a.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
