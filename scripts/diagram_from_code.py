#!/usr/bin/env python3
"""Generate a mermaid diagram FROM source code, at a selectable level of detail.

The gap this closes: design_drift.py checks a hand-drawn diagram against the code
and flags drift, which assumes a diagram already exists. Most of the time, for
code someone else wrote, none does -- reading the source linearly is slow, and
that is exactly when a diagram would help most. This script derives one instead
of validating one: point it at a path and it produces something to read.

    diagram_from_code.py <path> --kind sequence --level 2
    diagram_from_code.py <path> --kind flow --level 1 --entry "AuthService.login"
    diagram_from_code.py <path> --kind deps --level 1

--kind
  sequence  call flow between components -> mermaid sequenceDiagram
  flow      control flow inside one function/method -> mermaid flowchart
  deps      module/import graph -> mermaid flowchart

--level (the feature this tool exists for -- every level must render something
useful on its own; nothing here is a stub)
  1  high      top-level components/modules and the calls between them only,
                the first hop out of the entry point. No internals.
                Aim: <=12 nodes, fits on a slide.
  2  medium    classes/services and their public methods; every call that
                crosses a component boundary, at whatever depth. Aim: <=30 nodes.
  3  detailed  everything in the traced path: internal (same-class) calls,
                conditionals, error branches, each call kept as its own numbered
                step (autonumber), with a step-by-step table printed beneath
                the diagram.

Language support -- stated plainly, because a heuristic that is not labelled as
one is worse than no tool:
  Python              PROPERLY SUPPORTED. Parsed with the stdlib `ast` module.
                       Constructor/DI parameter types are resolved structurally,
                       so `self.hasher.verify(...)` is known to reach
                       PasswordHasher.verify. Branches, try/except and raises are
                       read from the real syntax tree, not guessed.
  TypeScript/JS       HEURISTIC. No parser (stdlib only) -- a hand-written
                       lexer/brace-matcher over regex. Handles the common NestJS/
                       Express shape (constructor DI, decorators, this.x.y()).
                       Multi-line generics, computed member access, and decorators
                       it does not recognise degrade to `%% unresolved`, not to a
                       wrong answer.
  Go                  NOT ANALYSED for sequence/flow. `deps` counts .go files and
                       does line-level `import (...)` block parsing only.
  Anything else       file is listed, not parsed.

Honesty about what cannot be resolved: dynamic dispatch (`obj[name]()`), DI
containers that wire by string/token, callbacks passed as values, and calls
through untyped fields all defeat static resolution here. Those calls are still
emitted as an edge to a node, tagged `%% unresolved` -- never silently dropped,
because a diagram that quietly omits edges is worse than no diagram.

Entry points are inferred when --entry is not given: HTTP route decorators
(NestJS @Get/@Post/..., Flask/FastAPI @app.route/@app.get/...), `main`, a
`if __name__ == "__main__"` block, or (falling back) the first public
method/function found. --entry "Class.method" or --entry "function_name" seeds
the trace explicitly.

Participants that are not defined anywhere in the scanned path (an imported
library class, a framework base) are emitted with `%% external: Alias` so
design_drift.py -- which reads that exact marker -- does not flag them as
missing. This is what makes the round-trip promise below hold.

Round-trip promise: a `sequence` diagram this script generates from a path,
fed back into `design_drift.py <spec-containing-it> <that-same-path>`, reports
no drift. Every label used in a message is built from the real method/attribute
names found in the code, so design_drift's name-level match always has a
counterpart to find.

Mermaid syntax is checked before printing: `mmdc` (@mermaid-js/mermaid-cli) via
`npx` if it is reachable, else a small stdlib syntax validator that checks
participant/arrow/flowchart-edge grammar -- and the output says plainly which
check ran, because a silent heuristic is exactly what this docstring warns
against elsewhere.

Exit codes: 0 diagram produced and it passed the syntax check; 1 the generated
mermaid FAILED the syntax check; 2 bad usage, empty/unsupported input, or an
--entry that cannot be found.

Python stdlib only.
"""
import argparse, ast, json, pathlib, re, shutil, subprocess, sys, tempfile

CODE_EXT_PY = {".py"}
CODE_EXT_TS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
CODE_EXT_GO = {".go"}
ALL_CODE_EXT = CODE_EXT_PY | CODE_EXT_TS | CODE_EXT_GO
SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv",
             "__pycache__", ".next", "coverage", ".turbo", ".mypy_cache"}

# calls to these are noise, not collaborators -- filtered out entirely rather
# than reported as "unresolved", because flooding the diagram with print/len
# hides the calls that actually matter.
BUILTIN_IGNORE = {
    "print", "len", "str", "int", "float", "bool", "dict", "list", "set",
    "tuple", "isinstance", "super", "range", "sorted", "enumerate", "zip",
    "map", "filter", "getattr", "setattr", "hasattr", "repr", "format",
    "open", "vars", "type", "id", "abs", "min", "max", "sum", "any", "all",
    "console", "JSON", "Object", "Array", "Promise", "Math", "Number",
    "String", "Boolean", "parseInt", "parseFloat",
}
IGNORE_ATTR_BASES = {"logger", "log", "logging", "console"}

ROUTE_DECORATORS = {"get", "post", "put", "delete", "patch", "route",
                     "options", "head"}


# --------------------------------------------------------------------------
# small shared helpers
# --------------------------------------------------------------------------

def alias_of(name, taken):
    """Mermaid participant/node id: word chars only, unique, stable."""
    a = re.sub(r"\W", "_", name).strip("_") or "N"
    if a[0].isdigit():
        a = "N_" + a
    base, i = a, 2
    while a in taken and taken[a] != name:
        a = f"{base}_{i}"; i += 1
    taken[a] = name
    return a


def sanitize_label(text, limit=72):
    """One mermaid line, no stray colons-at-start, no newlines."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text or "(...)"


def strip_generic(type_text):
    """'Optional[PasswordHasher]' / 'Promise<UserRepository>' -> 'PasswordHasher'.
    Heuristic: last CapitalizedWord token wins. Good enough for DI annotations,
    wrong for e.g. `Dict[str, Foo]` -> picks 'Foo', which is usually still the
    useful part."""
    if not type_text:
        return None
    caps = re.findall(r"[A-Z]\w*", type_text)
    return caps[-1] if caps else None


def find_source_files(root):
    root = pathlib.Path(root)
    files = {"python": [], "ts": [], "go": [], "other": 0}
    if root.is_file():
        candidates = [root]
    else:
        candidates = sorted(p for p in root.rglob("*")
                             if p.is_file() and not any(part in SKIP_DIRS for part in p.parts))
    for p in candidates:
        if p.suffix in CODE_EXT_PY:
            files["python"].append(p)
        elif p.suffix in CODE_EXT_TS:
            files["ts"].append(p)
        elif p.suffix in CODE_EXT_GO:
            files["go"].append(p)
        elif p.is_file():
            files["other"] += 1
    return files


# --------------------------------------------------------------------------
# common model
# --------------------------------------------------------------------------

class Component:
    """A class/service (Python class, TS class). One per scanned symbol."""
    def __init__(self, name, file, lang):
        self.name = name
        self.file = file
        self.lang = lang
        self.field_types = {}     # attr name -> resolved type name (or None)
        self.decorators = []      # raw decorator text, class-level
        self.methods = {}         # name -> lang-specific body handle
        self.method_decorators = {}  # method name -> [raw decorator text]

    def is_route_controller(self):
        return any(re.search(r"\bController\b", d) for d in self.decorators)


class Step:
    """One ordered event inside a method/function body."""
    __slots__ = ("kind", "text", "method", "attr", "resolved", "internal",
                 "unresolved", "is_construct", "branch", "is_error", "line")

    def __init__(self, kind, text, method=None, attr=None, resolved=None,
                 internal=False, unresolved=False, is_construct=False,
                 branch=None, is_error=False, line=0):
        self.kind = kind            # 'call' | 'raise'
        self.text = text
        self.method = method
        self.attr = attr
        self.resolved = resolved
        self.internal = internal
        self.unresolved = unresolved
        self.is_construct = is_construct
        self.branch = branch or []  # [(kind, label), ...] outer -> inner
        self.is_error = is_error
        self.line = line


# --------------------------------------------------------------------------
# Python analysis (properly supported: ast)
# --------------------------------------------------------------------------

def _unparse(node):
    try:
        return ast.unparse(node)
    except Exception:
        return "<expr>"


class _PyStepWalker(ast.NodeVisitor):
    def __init__(self):
        self.steps = []   # raw dicts with call ast.Call node, pre-resolution
        self.branch_stack = []

    def _collect(self, node, is_error=False):
        if node is None:
            return
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                self.steps.append({"node": sub, "branch": list(self.branch_stack),
                                    "is_error": is_error, "line": getattr(sub, "lineno", 0)})

    def visit_If(self, node):
        self._collect(node.test)
        cond = sanitize_label(_unparse(node.test), 40)
        self.branch_stack.append(("if", cond))
        for s in node.body:
            self.visit(s)
        self.branch_stack.pop()
        if node.orelse:
            is_elif = len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)
            label = "else" if not is_elif else "elif"
            self.branch_stack.append(("else", label))
            for s in node.orelse:
                self.visit(s)
            self.branch_stack.pop()

    def visit_Try(self, node):
        self.branch_stack.append(("try", "try"))
        for s in node.body:
            self.visit(s)
        self.branch_stack.pop()
        for h in node.handlers:
            etype = _unparse(h.type) if h.type else "Exception"
            self.branch_stack.append(("except", sanitize_label(etype, 30)))
            for s in h.body:
                self.visit(s)
            self.branch_stack.pop()
        for s in node.finalbody:
            self.branch_stack.append(("finally", "finally"))
            self.visit(s)
            self.branch_stack.pop()

    def visit_For(self, node):
        self.branch_stack.append(("loop", "for " + sanitize_label(_unparse(node.target), 20)))
        for s in node.body:
            self.visit(s)
        self.branch_stack.pop()

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.branch_stack.append(("loop", "while " + sanitize_label(_unparse(node.test), 20)))
        for s in node.body:
            self.visit(s)
        self.branch_stack.pop()

    def visit_With(self, node):
        for item in node.items:
            self._collect(item.context_expr)
        for s in node.body:
            self.visit(s)

    visit_AsyncWith = visit_With

    def visit_Raise(self, node):
        text = _unparse(node.exc) if node.exc else "re-raise"
        self.steps.append({"raise": text, "branch": list(self.branch_stack),
                            "is_error": True, "line": node.lineno})
        self._collect(node.exc, is_error=True)

    def visit_Return(self, node):
        self._collect(node.value)

    def visit_Expr(self, node):
        self._collect(node.value)

    def visit_Assign(self, node):
        self._collect(node.value)

    def visit_AnnAssign(self, node):
        self._collect(node.value)

    def visit_AugAssign(self, node):
        self._collect(node.value)

    def visit_FunctionDef(self, node):
        return  # opaque: nested defs are not inlined

    visit_AsyncFunctionDef = visit_FunctionDef


def py_build_component(node, path):
    comp = Component(node.name, path, "python")
    comp.decorators = [_unparse(d) for d in node.decorator_list]
    field_types, methods, method_decorators, init_node = {}, {}, {}, None
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            field_types[item.target.id] = strip_generic(_unparse(item.annotation))
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods[item.name] = item
            method_decorators[item.name] = [_unparse(d) for d in item.decorator_list]
            if item.name == "__init__":
                init_node = item
    if init_node is not None:
        args = init_node.args
        all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        param_types = {a.arg: strip_generic(_unparse(a.annotation))
                       for a in all_args if a.arg != "self" and a.annotation is not None}
        for stmt in ast.walk(init_node):
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == "self"):
                        val, t = stmt.value, None
                        if isinstance(val, ast.Name) and val.id in param_types:
                            t = param_types[val.id]
                        elif isinstance(val, ast.Call):
                            t = strip_generic(_unparse(val.func))
                        if t:
                            field_types[tgt.attr] = t
            elif isinstance(stmt, ast.AnnAssign):
                if (isinstance(stmt.target, ast.Attribute)
                        and isinstance(stmt.target.value, ast.Name)
                        and stmt.target.value.id == "self"):
                    field_types[stmt.target.attr] = strip_generic(_unparse(stmt.annotation))
    comp.field_types = field_types
    comp.methods = methods
    comp.method_decorators = method_decorators
    return comp


def py_parse_file(path, text):
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return [], {}
    components, module_functions = [], {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            components.append(py_build_component(node, path))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_functions[node.name] = node
    return components, module_functions


def py_resolve_call(call_node, comp, known_names):
    func = call_node.func
    args_text = sanitize_label(", ".join(_unparse(a) for a in call_node.args), 40)

    def mk(**kw):
        kw.setdefault("attr", None); kw.setdefault("resolved", None)
        kw.setdefault("internal", False); kw.setdefault("unresolved", False)
        kw.setdefault("is_construct", False)
        return kw

    if isinstance(func, ast.Attribute):
        if (isinstance(func.value, ast.Attribute) and isinstance(func.value.value, ast.Name)
                and func.value.value.id in ("self", "cls")):
            attr, method = func.value.attr, func.attr
            target = comp.field_types.get(attr) if comp else None
            return mk(text=f"{attr}.{method}({args_text})", method=method, attr=attr,
                       resolved=target, unresolved=target is None)
        if isinstance(func.value, ast.Name) and func.value.id in ("self", "cls"):
            method = func.attr
            return mk(text=f"self.{method}({args_text})", method=method,
                       resolved=comp.name if comp else None, internal=True)
        if isinstance(func.value, ast.Name):
            base, method = func.value.id, func.attr
            if base in IGNORE_ATTR_BASES or base in BUILTIN_IGNORE:
                return None
            if base in known_names:
                return mk(text=f"{base}.{method}({args_text})", method=method,
                           attr=base, resolved=base)
            return mk(text=f"{base}.{method}({args_text})", method=method, attr=base,
                       unresolved=True)
        return mk(text=sanitize_label(f"{_unparse(func)}({args_text})"),
                   method=getattr(func, "attr", "?"), unresolved=True)
    if isinstance(func, ast.Name):
        name = func.id
        if name in BUILTIN_IGNORE:
            return None
        if name in known_names:
            return mk(text=f"{name}({args_text})", method="__init__", resolved=name,
                       is_construct=True)
        return mk(text=f"{name}({args_text})", method=name, unresolved=True)
    return mk(text=sanitize_label(f"{_unparse(func)}({args_text})"), method="?", unresolved=True)


def py_get_steps(comp, method_name, known_names):
    """Ordered Step list for one Python method/function, resolved against `known_names`."""
    node = comp.methods.get(method_name) if comp else None
    if node is None:
        return None
    walker = _PyStepWalker()
    for stmt in node.body:
        walker.visit(stmt)
    steps = []
    for raw in walker.steps:
        if "raise" in raw:
            steps.append(Step("raise", sanitize_label("raise " + raw["raise"]),
                               branch=raw["branch"], is_error=True, line=raw["line"]))
            continue
        r = py_resolve_call(raw["node"], comp, known_names)
        if r is None:
            continue
        steps.append(Step("call", r["text"], method=r["method"], attr=r["attr"],
                           resolved=r["resolved"], internal=r["internal"],
                           unresolved=r["unresolved"], is_construct=r["is_construct"],
                           branch=raw["branch"], is_error=raw["is_error"], line=raw["line"]))
    return steps


# --------------------------------------------------------------------------
# TS/JS analysis (heuristic: hand lexer + regex, no parser dependency)
# --------------------------------------------------------------------------

def mask_ts(text):
    """Blank out comments and string/template contents, preserving length and
    newlines, so brace-matching and call regexes don't trip on `"{"` inside a
    string. Positions in the masked text line up 1:1 with the original."""
    out = list(text)
    i, n = 0, len(text)
    state = None
    while i < n:
        c = text[i]
        if state is None:
            if c == "/" and i + 1 < n and text[i + 1] == "/":
                out[i] = out[i + 1] = " "; state = "line"; i += 2; continue
            if c == "/" and i + 1 < n and text[i + 1] == "*":
                out[i] = out[i + 1] = " "; state = "block"; i += 2; continue
            if c in ("'", '"', "`"):
                out[i] = " "; state = ("str", c); i += 1; continue
            i += 1; continue
        if state == "line":
            if c == "\n":
                state = None
            else:
                out[i] = " "
            i += 1; continue
        if state == "block":
            if c == "*" and i + 1 < n and text[i + 1] == "/":
                out[i] = out[i + 1] = " "; state = None; i += 2; continue
            if c != "\n":
                out[i] = " "
            i += 1; continue
        if isinstance(state, tuple) and state[0] == "str":
            q = state[1]
            if c == "\\" and i + 1 < n:
                out[i] = out[i + 1] = " "; i += 2; continue
            if c == q:
                out[i] = " "; state = None; i += 1; continue
            if c != "\n":
                out[i] = " "
            i += 1; continue
        i += 1
    return "".join(out)


def find_matching_brace(masked, open_pos):
    depth = 0
    for i in range(open_pos, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(masked) - 1


TS_CLASS_RE = re.compile(
    r"\bclass\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+[\w,\s.<>\[\]]+)?\s*\{")
TS_DECORATOR_RE = re.compile(r"@([\w.]+)\s*(\([^)]*\))?")
TS_CTOR_RE = re.compile(r"\bconstructor\s*\(")
TS_METHOD_RE = re.compile(
    r"(?:^|\n)\s*(?:public|private|protected|static|readonly|async|\s)*\s*"
    r"(?P<name>[A-Za-z_]\w*)\s*\(")
RESERVED_TS = {"if", "for", "while", "switch", "catch", "function", "constructor",
               "return", "typeof", "new", "else", "try", "do"}


def ts_decorators_before(orig, pos):
    """Decorator lines immediately above position `pos` (start of class/method line)."""
    line_start = orig.rfind("\n", 0, pos) + 1
    window = orig[max(0, line_start - 400):line_start]
    decs = []
    for m in re.finditer(r"@([\w.]+)\s*(\([^)]*\))?", window):
        decs.append((m.group(1) + (m.group(2) or "")).strip())
    return decs


def ts_split_params(param_text):
    parts, depth, cur = [], 0, ""
    for c in param_text:
        if c in "([{<":
            depth += 1
        elif c in ")]}>":
            depth -= 1
        if c == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += c
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def ts_parse_file(path, text):
    masked = mask_ts(text)
    components = []
    for m in TS_CLASS_RE.finditer(masked):
        name = m.group(1)
        brace_open = masked.index("{", m.end() - 1)
        brace_close = find_matching_brace(masked, brace_open)
        body_masked = masked[brace_open + 1:brace_close]
        body_orig = text[brace_open + 1:brace_close]
        comp = Component(name, path, "ts")
        comp.decorators = ts_decorators_before(text, m.start())

        # constructor -> field types from typed DI params
        field_types = {}
        ctor_m = TS_CTOR_RE.search(body_masked)
        if ctor_m:
            popen = body_masked.index("(", ctor_m.start())
            depth, i = 0, popen
            for i in range(popen, len(body_masked)):
                if body_masked[i] == "(":
                    depth += 1
                elif body_masked[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
            param_text = body_orig[popen + 1:i]
            for p in ts_split_params(param_text):
                pm = re.match(r"(?:public|private|protected|readonly|\s)*\s*"
                               r"(\w+)\s*:\s*([\w.\[\]<>, ]+)", p)
                if pm:
                    field_types[pm.group(1)] = strip_generic(pm.group(2)) or pm.group(2).strip()
            cbrace = body_masked.index("{", i)
            cclose = find_matching_brace(body_masked, cbrace)
            ctor_body = body_orig[cbrace + 1:cclose]
            for am in re.finditer(r"this\.(\w+)\s*=\s*(\w+)\s*;", ctor_body):
                attr, val = am.groups()
                if val in field_types and attr not in field_types:
                    field_types[attr] = field_types[val]

        comp.field_types = field_types

        # methods: scan body for `name(` not preceded by `.` and not reserved
        seen_spans = set()
        for mm in re.finditer(r"(?<![.\w])(\w+)\s*\(", body_masked):
            mname = mm.group(1)
            if mname in RESERVED_TS or mname == name:
                continue
            popen = mm.end() - 1
            depth, j = 0, popen
            for j in range(popen, len(body_masked)):
                if body_masked[j] == "(":
                    depth += 1
                elif body_masked[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
            after = body_masked[j + 1:j + 200]
            brace_m = re.match(r"\s*(?::\s*[\w.<>\[\],\s|]+)?\s*\{", after)
            if not brace_m or mname in comp.methods:
                continue
            mbrace_open = j + 1 + brace_m.end() - 1
            mbrace_close = find_matching_brace(body_masked, mbrace_open)
            if mm.start() in seen_spans:
                continue
            seen_spans.add(mm.start())
            comp.methods[mname] = (mbrace_open + 1, mbrace_close, path)
            comp.method_decorators[mname] = ts_decorators_before(body_orig, mm.start())
        components.append((comp, body_orig, body_masked, brace_open))
    return components


TS_CALL_RE = re.compile(
    r"\bthis\.(?P<attr>\w+)\.(?P<m1>\w+)\s*\("
    r"|\bthis\.(?P<selfm>\w+)\s*\("
    r"|\bnew\s+(?P<ctor>\w+)\s*\("
    r"|\b(?P<base>[A-Za-z_]\w*)\.(?P<m2>\w+)\s*\("
    r"|\b(?P<fn>[a-zA-Z_]\w*)\s*\("
)


def ts_get_steps(comp, method_name, known_names, body_orig_full, body_masked_full):
    """Ordered Step list for one TS method, using the class-body text captured
    at parse time. Branch context is approximated by brace-depth + a keyword
    lookback immediately before the opening brace -- heuristic, documented."""
    span = comp.methods.get(method_name)
    if not span or not isinstance(span, tuple):
        return None
    start, end, _ = span
    masked = body_masked_full[start:end]
    orig = body_orig_full[start:end]

    # brace-depth stack labelled by the keyword immediately preceding each '{'
    stack = []          # [(kind, label)]
    stack_at = {}        # position -> stack snapshot (list of tuples)
    depth_labels = [None] * (len(masked) + 1)
    cur_stack = []
    i = 0
    while i < len(masked):
        c = masked[i]
        if c == "{":
            window = orig[max(0, i - 60):i]
            if re.search(r"\}\s*else\s+if\s*\([^{]*$", window):
                cur_stack.append(("elif", "elif"))
            elif re.search(r"\}\s*else\s*$", window):
                cur_stack.append(("else", "else"))
            elif re.search(r"\bif\s*\([^{]*$", window):
                cond = re.search(r"\bif\s*\(([^{]*)$", window)
                cur_stack.append(("if", sanitize_label(cond.group(1), 30) if cond else "if"))
            elif re.search(r"\}\s*catch\s*\([^{]*$", window):
                cm = re.search(r"catch\s*\(([^)]*)\)", window)
                cur_stack.append(("except", sanitize_label(cm.group(1), 20) if cm else "catch"))
            elif re.search(r"\btry\s*$", window):
                cur_stack.append(("try", "try"))
            elif re.search(r"\bfor\s*\([^{]*$", window) or re.search(r"\bwhile\s*\([^{]*$", window):
                cur_stack.append(("loop", "loop"))
            else:
                cur_stack.append(("block", None))
            stack.append(cur_stack[-1])
        elif c == "}":
            if cur_stack:
                cur_stack.pop()
        depth_labels[i] = list(b for b in cur_stack if b[1])
        i += 1

    steps = []
    for m in TS_CALL_RE.finditer(masked):
        pos = m.start()
        branch = depth_labels[pos] or []
        if m.group("attr"):
            attr, method = m.group("attr"), m.group("m1")
            if attr in IGNORE_ATTR_BASES:
                continue
            target = comp.field_types.get(attr)
            steps.append(Step("call", sanitize_label(f"{attr}.{method}(...)"), method=method,
                               attr=attr, resolved=target, unresolved=target is None,
                               branch=branch, line=orig.count("\n", 0, pos) + 1))
        elif m.group("selfm"):
            method = m.group("selfm")
            steps.append(Step("call", sanitize_label(f"this.{method}(...)"), method=method,
                               resolved=comp.name, internal=True, branch=branch,
                               line=orig.count("\n", 0, pos) + 1))
        elif m.group("ctor"):
            cname = m.group("ctor")
            if cname in known_names:
                steps.append(Step("call", sanitize_label(f"new {cname}(...)"), method="constructor",
                                   resolved=cname, is_construct=True, branch=branch,
                                   line=orig.count("\n", 0, pos) + 1))
            elif cname not in TS_CTOR_IGNORE:
                # constructing a type we can't resolve (e.g. a framework exception
                # class) -- emit it rather than silently dropping the call.
                steps.append(Step("call", sanitize_label(f"new {cname}(...)"), method="new",
                                   attr=cname, unresolved=True, branch=branch,
                                   line=orig.count("\n", 0, pos) + 1))
        elif m.group("base"):
            base, method = m.group("base"), m.group("m2")
            if base in IGNORE_ATTR_BASES or base in BUILTIN_IGNORE:
                continue
            resolved = base if base in known_names else None
            steps.append(Step("call", sanitize_label(f"{base}.{method}(...)"), method=method,
                               attr=base, resolved=resolved, unresolved=resolved is None,
                               branch=branch, line=orig.count("\n", 0, pos) + 1))
        else:
            fn = m.group("fn")
            if fn in RESERVED_TS or fn in BUILTIN_IGNORE or fn in IGNORE_ATTR_BASES:
                continue
            if fn in known_names:
                continue  # bare uppercase-less constructor-style call, rare; skip noise
            steps.append(Step("call", sanitize_label(f"{fn}(...)"), method=fn, unresolved=True,
                               branch=branch, line=orig.count("\n", 0, pos) + 1))
    for tm in re.finditer(r"\bthrow\s+([^;]{1,60})", masked):
        pos = tm.start()
        branch = depth_labels[pos] or []
        text = orig[tm.start():tm.end()]
        steps.append(Step("raise", sanitize_label(text), branch=branch, is_error=True,
                           line=orig.count("\n", 0, pos) + 1))
    steps.sort(key=lambda s: s.line)
    return steps


# --------------------------------------------------------------------------
# scanning: build the whole-project symbol table
# --------------------------------------------------------------------------

class Project:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.components = {}          # name -> Component
        self.module_functions = {}    # name -> (lang, node/span, file, ...)
        self.py_module_functions = {}
        self.ts_bodies = {}           # Component -> (body_orig, body_masked)
        self.files = find_source_files(root)
        self._scan()

    def _scan(self):
        for p in self.files["python"]:
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            comps, funcs = py_parse_file(p, text)
            for c in comps:
                self.components[c.name] = c
            for name, node in funcs.items():
                self.py_module_functions.setdefault(name, (p, node))
        for p in self.files["ts"]:
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            for comp, body_orig, body_masked, _ in ts_parse_file(p, text):
                self.components[comp.name] = comp
                self.ts_bodies[comp.name] = (body_orig, body_masked)

    def get_steps(self, comp, method_name):
        if comp.lang == "python":
            return py_get_steps(comp, method_name, self.components)
        if comp.lang == "ts":
            body_orig, body_masked = self.ts_bodies[comp.name]
            return ts_get_steps(comp, method_name, self.components, body_orig, body_masked)
        return None

    def find_entry(self, spec):
        """--entry 'Class.method' or 'function_name'. Returns (comp_or_None, method_name)."""
        if "." in spec:
            cname, mname = spec.split(".", 1)
            comp = self.components.get(cname)
            if comp and mname in comp.methods:
                return comp, mname
            return None, None
        if spec in self.py_module_functions:
            return None, spec
        for comp in self.components.values():
            if spec in comp.methods:
                return comp, spec
        return None, None

    def infer_entries(self):
        """Best-effort entry points: route handlers first, then main(), then any
        public method/function. Returns list of (comp_or_None, method_name, why)."""
        found = []
        for comp in self.components.values():
            for mname, decs in comp.method_decorators.items():
                low = " ".join(decs).lower()
                if any(re.search(rf"\b{d}\b", low) for d in ROUTE_DECORATORS):
                    found.append((comp, mname, "route handler"))
        if found:
            return found
        if "main" in self.py_module_functions:
            return [(None, "main", "main()")]
        for comp in self.components.values():
            for mname in comp.methods:
                if mname in ("__init__", "constructor") or mname.startswith("_"):
                    continue
                found.append((comp, mname, "first public method found"))
        return found[:1]


# --------------------------------------------------------------------------
# sequence: trace + level filter + render
# --------------------------------------------------------------------------

def build_sequence_trace(proj, entry_comp, entry_method, max_steps=300, max_depth=40):
    """Full (level-3-grade) ordered list of messages by DFS from the entry point,
    flattening same-class internal hops so cross-component calls made from a
    helper method are still discovered."""
    messages = []   # dicts: seq, src, dst, method, text, branch, is_error, unresolved, internal
    visited_stack = set()

    def walk(comp, method_name, depth):
        if len(messages) >= max_steps or depth > max_depth:
            return
        key = (comp.name if comp else None, method_name)
        if key in visited_stack:
            return
        visited_stack.add(key)
        steps = proj.get_steps(comp, method_name) if comp else None
        if steps is None:
            visited_stack.discard(key)
            return
        for s in steps:
            if len(messages) >= max_steps:
                break
            if s.kind == "raise":
                messages.append({"src": comp.name, "dst": "Caller", "method": None,
                                  "text": s.text, "branch": s.branch, "is_error": True,
                                  "unresolved": False, "internal": False, "error_only": True})
                continue
            if s.internal:
                messages.append({"src": comp.name, "dst": comp.name, "method": s.method,
                                  "text": s.text, "branch": s.branch, "is_error": s.is_error,
                                  "unresolved": False, "internal": True})
                target_comp = comp
                walk(target_comp, s.method, depth + 1)
                continue
            if s.unresolved:
                messages.append({"src": comp.name, "dst": f"Unresolved_{s.attr or s.method}",
                                  "method": s.method, "text": s.text, "branch": s.branch,
                                  "is_error": s.is_error, "unresolved": True, "internal": False})
                continue
            if s.is_construct:
                # constructing a known component isn't a call into it; don't recurse
                continue
            target = proj.components.get(s.resolved) if s.resolved else None
            messages.append({"src": comp.name, "dst": s.resolved, "method": s.method,
                              "text": s.text, "branch": s.branch, "is_error": s.is_error,
                              "unresolved": False, "internal": False,
                              "external": target is None})
            if target is not None and s.method in target.methods:
                walk(target, s.method, depth + 1)
        visited_stack.discard(key)

    walk(entry_comp, entry_method, 0)
    return messages


def filter_by_level(messages, level, entry_name):
    if level >= 3:
        return messages
    cross = [m for m in messages if not m.get("internal") and not m.get("error_only")]
    if level == 2:
        seen, out = set(), []
        for m in cross:
            k = (m["src"], m["dst"], m["method"])
            if k in seen:
                continue
            seen.add(k)
            out.append(m)
        return out
    # level 1: first hop out of the entry point only, one edge per (src,dst)
    seen, out = set(), []
    for m in cross:
        if m["src"] != entry_name:
            continue
        k = (m["src"], m["dst"])
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    return out


def render_sequence(proj, entry_comp, entry_method, level, entry_spec_label):
    entry_name = entry_comp.name if entry_comp else "__module__"
    all_msgs = build_sequence_trace(proj, entry_comp, entry_method)
    msgs = filter_by_level(all_msgs, level, entry_name)

    taken = {}
    lines = ["sequenceDiagram"]
    lines.append(f"  %% diagram_from_code: kind=sequence level={level} entry={entry_spec_label}")
    if level == 3:
        lines.append("  autonumber")

    participants = []  # (alias, label, is_actor, is_external, is_unresolved)
    order = []

    def add_participant(name, is_unresolved=False):
        if name in order:
            return alias_of(name, taken)
        order.append(name)
        alias = alias_of(name, taken)
        comp = proj.components.get(name)
        is_external = (comp is None) and not is_unresolved and name not in ("Caller",)
        participants.append((alias, name, False, is_external, is_unresolved))
        return alias

    caller_alias = alias_of("Caller", taken)
    order.append("Caller")
    entry_alias = add_participant(entry_name)
    for m in msgs:
        add_participant(m["src"])
        is_unres = bool(m.get("unresolved"))
        add_participant(m["dst"], is_unresolved=is_unres)

    lines.append(f"  actor {caller_alias}")
    for alias, name, _, is_external, is_unresolved in participants:
        if is_unresolved:
            lines.append(f"  participant {alias} as {sanitize_label(name, 30)}")
            lines.append(f"  %% unresolved: {sanitize_label(name, 40)} -- call target could not be resolved statically")
        elif is_external:
            lines.append(f"  participant {alias} as {sanitize_label(name, 30)}")
            lines.append(f"  %% external: {alias}")
        else:
            lines.append(f"  participant {alias} as {sanitize_label(name, 30)}")

    entry_call_label = sanitize_label(f"{entry_method}(...)")
    lines.append(f"  {caller_alias}->>{entry_alias}: {entry_call_label}")

    steps_table = [{"step": 1, "from": "Caller", "to": entry_name, "call": entry_call_label,
                     "context": ""}]
    n = 2
    for m in msgs:
        src_alias = alias_of(m["src"], taken)
        dst_alias = alias_of(m["dst"], taken)
        ctx = " / ".join(f"{k}:{v}" for k, v in m.get("branch", [])) if level == 3 else ""
        if m.get("error_only"):
            lines.append(f"  %% error branch: {' / '.join(v for _, v in m.get('branch', []))}"
                          if level == 3 else "")
            lines.append(f"  {src_alias}-x{caller_alias}: {sanitize_label(m['text'])}")
            steps_table.append({"step": n, "from": m["src"], "to": "Caller",
                                 "call": sanitize_label(m["text"]), "context": ctx})
            n += 1
            continue
        arrow = "-x" if m.get("is_error") else "->>"
        if level == 3 and ctx:
            lines.append(f"  Note over {src_alias}: {sanitize_label(ctx, 40)}")
        lines.append(f"  {src_alias}{arrow}{dst_alias}: {sanitize_label(m['text'])}")
        steps_table.append({"step": n, "from": m["src"], "to": m["dst"],
                             "call": sanitize_label(m["text"]), "context": ctx})
        n += 1

    lines = [l for l in lines if l != ""]
    mermaid = "\n".join(lines)
    return mermaid, participants, msgs, steps_table


# --------------------------------------------------------------------------
# deps: module/import graph (both languages; Go gets file-level only)
# --------------------------------------------------------------------------

PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+([\w, .*()\n]+)|import\s+([\w., ]+))",
                           re.M)
TS_IMPORT_RE = re.compile(
    r"import\s+(?:type\s+)?(?:\{([^}]*)\}|(\w+)|\*\s+as\s+(\w+))?\s*(?:,\s*\{([^}]*)\})?\s*"
    r"from\s+['\"]([^'\"]+)['\"]"
    r"|require\(\s*['\"]([^'\"]+)['\"]\s*\)")
GO_IMPORT_BLOCK_RE = re.compile(r"import\s*\(([^)]*)\)", re.S)
GO_IMPORT_SINGLE_RE = re.compile(r'import\s+"([^"]+)"')


def deps_scan(proj, level):
    edges = []   # (src_file, dst, symbol, kind: 'internal'|'external'|'unresolved')
    root = proj.root if proj.root.is_dir() else proj.root.parent

    def resolve_relative(from_file, spec):
        base = (from_file.parent / spec).resolve()
        for cand in (base, base.with_suffix(".ts"), base.with_suffix(".tsx"),
                     base.with_suffix(".js"), base / "index.ts", base / "index.js",
                     base.with_suffix(".py"), base / "__init__.py"):
            if cand.exists():
                return cand
        return None

    all_files = proj.files["python"] + proj.files["ts"] + proj.files["go"]
    for f in all_files:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        if f.suffix in CODE_EXT_PY:
            for m in PY_IMPORT_RE.finditer(text):
                mod = m.group(1) or m.group(3)
                if not mod:
                    continue
                mod = mod.strip().split(",")[0].strip()
                if mod.startswith("."):
                    target = resolve_relative(f, mod.replace(".", "/", 1))
                else:
                    target = None
                    for cand in root.rglob(mod.split(".")[0] + ".py"):
                        target = cand; break
                sym = (m.group(2) or "").strip() or mod
                edges.append((f, target, sym, "internal" if target else "external"))
        elif f.suffix in CODE_EXT_TS:
            for m in TS_IMPORT_RE.finditer(text):
                spec = m.group(5) or m.group(6)
                if not spec:
                    continue
                names = m.group(1) or m.group(4) or m.group(2) or m.group(3) or spec
                if spec.startswith("."):
                    target = resolve_relative(f, spec)
                    edges.append((f, target, names.strip(), "internal" if target else "unresolved"))
                else:
                    edges.append((f, None, names.strip(), "external"))
        elif f.suffix in CODE_EXT_GO:
            block = GO_IMPORT_BLOCK_RE.search(text)
            specs = []
            if block:
                specs = re.findall(r'"([^"]+)"', block.group(1))
            specs += GO_IMPORT_SINGLE_RE.findall(text)
            for spec in specs:
                edges.append((f, None, spec, "external"))
    return edges


def render_deps(proj, level):
    edges = deps_scan(proj, level)
    root = proj.root if proj.root.is_dir() else proj.root.parent
    taken = {}
    lines = ["flowchart LR", f"  %% diagram_from_code: kind=deps level={level}"]

    def node_key(path_or_pkg, is_file):
        if not is_file:
            return f"pkg:{path_or_pkg}"
        p = pathlib.Path(path_or_pkg)
        if level == 1:
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = p
            parts = rel.parts
            return f"dir:{parts[0] if len(parts) > 1 else '.'}"
        return f"file:{p.stem}"

    node_labels, node_ids = {}, {}
    edge_set = set()
    edge_lines = []

    def ensure_node(key, label, shape="normal", unresolved=False):
        if key not in node_ids:
            alias = alias_of(key, taken)
            node_ids[key] = alias
            node_labels[key] = (label, shape, unresolved)
        return node_ids[key]

    for src_file, dst, sym, kind in edges:
        src_key = node_key(str(src_file), True)
        src_label = src_file.stem if level != 1 else node_key(str(src_file), True).split(":", 1)[1]
        src_id = ensure_node(src_key, src_label)
        if kind == "internal" and dst:
            dst_key = node_key(str(dst), True)
            dst_label = dst.stem if level != 1 else node_key(str(dst), True).split(":", 1)[1]
            dst_id = ensure_node(dst_key, dst_label)
        elif kind == "unresolved":
            dst_key = f"unresolved:{sym}"
            dst_id = ensure_node(dst_key, sym, unresolved=True)
        else:
            pkg = sym.split(",")[0].split("/")[0] if level != 3 else sym
            dst_key = node_key(pkg or sym, False)
            dst_id = ensure_node(dst_key, pkg or sym, shape="ext")
        if src_id == dst_id:
            continue
        edge_key = (src_id, dst_id) if level != 3 else (src_id, dst_id, sym)
        if edge_key in edge_set:
            continue
        edge_set.add(edge_key)
        label = "" if level == 1 else sanitize_label(sym, 24)
        arrow = f"-->|{label}|" if (level == 3 and label) else "-->"
        edge_lines.append(f"  {src_id} {arrow} {dst_id}")

    for key, (label, shape, unresolved) in node_labels.items():
        nid = node_ids[key]
        label_s = sanitize_label(label, 30)
        if key.startswith("unresolved:"):
            lines.append(f"  {nid}{{{{{label_s}}}}}")
            lines.append(f"  %% unresolved: {label_s} -- import target not found on disk")
        elif key.startswith("pkg:"):
            lines.append(f"  {nid}([{label_s}])")
            lines.append(f"  %% external: {nid}")
        else:
            lines.append(f"  {nid}[{label_s}]")
    lines.extend(edge_lines)
    mermaid = "\n".join(lines)
    return mermaid, node_ids, edge_lines


# --------------------------------------------------------------------------
# flow: control flow inside one function/method
# --------------------------------------------------------------------------

def render_flow(proj, entry_comp, entry_method, level, entry_spec_label):
    steps = proj.get_steps(entry_comp, entry_method) if entry_comp else \
        (py_get_steps(_module_fn_as_component(proj, entry_method), entry_method, proj.components)
         if entry_method in proj.py_module_functions else None)
    taken = {}
    lines = ["flowchart TD", f"  %% diagram_from_code: kind=flow level={level} entry={entry_spec_label}"]
    start_id = alias_of("Start", taken)
    lines.append(f'  {start_id}(["Start: {sanitize_label(entry_spec_label, 30)}"])')
    if steps is None:
        end_id = alias_of("End", taken)
        lines.append(f'  {end_id}(["End"])')
        lines.append(f"  {start_id} --> {end_id}")
        lines.append("  %% unresolved: entry body could not be analysed")
        return "\n".join(lines), 2, []

    prev = start_id
    table = []
    n = 1
    for s in steps:
        if level == 1 and s.branch:
            continue  # level 1: outer shape only, no nested detail
        if level == 2 and s.internal:
            continue  # level 2: hide same-function internal recursion detail
        node_key = f"step{n}"
        nid = alias_of(node_key, taken)
        branch_lbl = s.branch[-1][1] if s.branch else None
        text = sanitize_label(s.text, 40)
        if s.kind == "raise" or s.is_error:
            lines.append(f'  {nid}[["{text}"]]')
        elif s.unresolved:
            lines.append(f'  {nid}{{{{"{text}"}}}}')
            lines.append(f"  %% unresolved: {text}")
        elif branch_lbl and s.branch[-1][0] in ("if", "else", "elif"):
            lines.append(f'  {nid}{{"{branch_lbl}: {text}"}}')
        else:
            lines.append(f'  {nid}["{text}"]')
        edge_label = f"|{sanitize_label(branch_lbl, 16)}|" if (level == 3 and branch_lbl) else ""
        lines.append(f"  {prev} -->{edge_label} {nid}")
        table.append({"step": n, "text": text, "branch": branch_lbl or "", "error": s.is_error})
        prev = nid
        n += 1
    end_id = alias_of("End", taken)
    lines.append(f'  {end_id}(["End"])')
    lines.append(f"  {prev} --> {end_id}")
    return "\n".join(lines), n + 1, table


def _module_fn_as_component(proj, name):
    f, node = proj.py_module_functions[name]
    comp = Component("__module__", f, "python")
    comp.methods = {name: node}
    comp.field_types = {}
    return comp


# --------------------------------------------------------------------------
# mermaid syntax validation
# --------------------------------------------------------------------------

def heuristic_validate(mermaid):
    lines = mermaid.splitlines()
    if not lines:
        return False, ["empty diagram"]
    head = lines[0].strip()
    problems = []
    if head not in ("sequenceDiagram", "flowchart LR", "flowchart TD", "graph LR", "graph TD"):
        problems.append(f"unrecognised diagram header: {head!r}")
    is_seq = head == "sequenceDiagram"
    declared = set()
    for i, raw in enumerate(lines[1:], start=2):
        line = raw.strip()
        if not line or line.startswith("%%") or line == "autonumber":
            continue
        if is_seq:
            pm = re.match(r"^(?:actor|participant)\s+(\w+)(?:\s+as\s+.+)?$", line)
            if pm:
                declared.add(pm.group(1)); continue
            mm = re.match(r"^(\w+)\s*(-->>|->>|-->|->|-x|--x)\s*(\w+)\s*:\s*.+$", line)
            if mm:
                for who in (mm.group(1), mm.group(3)):
                    if who not in declared:
                        problems.append(f"line {i}: {who!r} used before it was declared")
                continue
            if line.startswith("Note "):
                continue
            problems.append(f"line {i}: does not match participant/actor/message/Note grammar: {line!r}")
        else:
            if re.match(r"^\w+(\[.*\]|\(\[.*\]\)|\{.*\}|\{\{.*\}\}|\(.*\))\s*$", line):
                continue
            if re.match(r"^\w+\s*(-->|--x)\s*(\|[^|]*\|\s*)?\w+\s*$", line):
                continue
            problems.append(f"line {i}: does not match flowchart node/edge grammar: {line!r}")
    return (len(problems) == 0), problems


def mmdc_available():
    return shutil.which("mmdc") is not None or shutil.which("npx") is not None


def mmdc_validate(mermaid, timeout=45):
    tmpdir = tempfile.mkdtemp(prefix="diagram_from_code_")
    src = pathlib.Path(tmpdir) / "d.mmd"
    out = pathlib.Path(tmpdir) / "d.svg"
    src.write_text(mermaid)
    cmd = ["mmdc"] if shutil.which("mmdc") else ["npx", "-y", "@mermaid-js/mermaid-cli"]
    cmd += ["-i", str(src), "-o", str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ok = r.returncode == 0 and out.exists()
        detail = [] if ok else [(r.stderr or r.stdout or "mmdc failed").strip()[:400]]
        return ok, detail
    except Exception as e:
        return None, [f"mmdc unavailable/failed to run: {e}"]


def validate_mermaid(mermaid, prefer_mmdc=True):
    if prefer_mmdc and mmdc_available():
        ok, detail = mmdc_validate(mermaid)
        if ok is not None:
            return ok, "mmdc", detail
    ok, problems = heuristic_validate(mermaid)
    return ok, "heuristic", problems


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

LANG_SUPPORT = {
    "python": "properly supported (ast)",
    "ts": "heuristic (regex/brace-matching, no parser)",
    "go": "not analysed for call graphs (deps: file-level import scan only)",
}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--kind", choices=["sequence", "flow", "deps"], default="sequence")
    ap.add_argument("--level", type=int, choices=[1, 2, 3], default=2)
    ap.add_argument("--entry", default=None,
                     help="'Class.method' or 'function_name' to seed the trace. "
                          "Without it, entry points are inferred (route decorators, "
                          "main(), else the first public method/function found).")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-mmdc", action="store_true",
                     help="skip the mermaid-cli check even if npx/mmdc is on PATH; "
                          "use the stdlib heuristic validator instead")
    a = ap.parse_args()

    root = pathlib.Path(a.path)
    if not root.exists():
        print(f"no such path: {a.path}", file=sys.stderr)
        return 2

    files = find_source_files(root)
    total = len(files["python"]) + len(files["ts"]) + len(files["go"])
    if total == 0:
        print(f"no Python, TypeScript/JS, or Go source under {a.path} -- nothing to diagram")
        if files["other"]:
            print(f"({files['other']} other file(s) found but not in a supported language)")
        return 2

    proj = Project(root)

    entry_comp, entry_method, entry_label, entry_note = None, None, None, ""
    if a.entry:
        entry_comp, entry_method = proj.find_entry(a.entry)
        if entry_method is None:
            print(f"--entry {a.entry!r} not found among scanned symbols", file=sys.stderr)
            return 2
        entry_label = a.entry
    else:
        candidates = proj.infer_entries()
        if not candidates:
            print("could not infer an entry point (no route handlers, main(), or public "
                  "methods found) -- pass --entry Class.method explicitly", file=sys.stderr)
            return 2
        entry_comp, entry_method, why = candidates[0]
        entry_label = f"{entry_comp.name}.{entry_method}" if entry_comp else entry_method
        entry_note = f"entry inferred: {entry_label} ({why})"
        if len(candidates) > 1:
            entry_note += f"; {len(candidates) - 1} other candidate(s) not shown"

    warnings = []
    if a.kind == "sequence":
        mermaid, participants, msgs, steps_table = render_sequence(
            proj, entry_comp, entry_method, a.level, entry_label)
        node_count = len(participants) + len(msgs)
        extra = {"participants": len(participants), "messages": len(msgs),
                 "steps_table": steps_table if a.level == 3 else []}
    elif a.kind == "deps":
        mermaid, node_ids, edge_lines = render_deps(proj, a.level)
        node_count = len(node_ids) + len(edge_lines)
        extra = {"nodes": len(node_ids), "edges": len(edge_lines)}
    else:
        mermaid, node_count, table = render_flow(proj, entry_comp, entry_method, a.level, entry_label)
        extra = {"steps_table": table}

    ok, method, detail = validate_mermaid(mermaid, prefer_mmdc=not a.no_mmdc)

    langs_used = set()
    if files["python"]:
        langs_used.add("python")
    if files["ts"]:
        langs_used.add("ts")
    if files["go"]:
        langs_used.add("go")

    if a.json:
        result = {
            "kind": a.kind, "level": a.level, "path": str(root), "entry": entry_label,
            "entry_note": entry_note, "node_count": node_count,
            "language_support": {l: LANG_SUPPORT[l] for l in langs_used},
            "mermaid": mermaid,
            "syntax_check": {"ok": ok, "method": method, "detail": detail},
            **extra,
        }
        print(json.dumps(result, indent=2))
        return 0 if ok else 1

    print(f"diagram_from_code: kind={a.kind} level={a.level} path={a.path}")
    if entry_note:
        print(f"  {entry_note}")
    for l in sorted(langs_used):
        print(f"  language: {l} -- {LANG_SUPPORT[l]}")
    if files["go"] and a.kind != "deps":
        print("  note: Go files present but not analysed for this --kind")
    print()
    print("```mermaid")
    print(mermaid)
    print("```")
    if a.kind == "sequence" and a.level == 3 and extra["steps_table"]:
        print()
        print("| step | from | to | call | context |")
        print("|---|---|---|---|---|")
        for row in extra["steps_table"]:
            print(f"| {row['step']} | {row['from']} | {row['to']} | {row['call']} | {row.get('context','')} |")
    if a.kind == "flow" and extra.get("steps_table"):
        print()
        print("| step | text | branch |")
        print("|---|---|---|")
        for row in extra["steps_table"]:
            print(f"| {row['step']} | {row['text']} | {row['branch']} |")
    print()
    print(f"syntax check ({method}): {'OK' if ok else 'FAILED'}")
    if not ok:
        for d in detail[:10]:
            print(f"  {d}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
