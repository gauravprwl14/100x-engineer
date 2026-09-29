#!/usr/bin/env python3
"""Validate mermaid diagrams against this plugin's diagram discipline
(skills/diagramming/SKILL.md): the right type for the task, at one of three
mechanical detail levels, with no drift-breaking or placeholder content.

    check_diagrams.py <file-or-dir>              # validate every mermaid block found
    check_diagrams.py specs/login/spec.md --level 3   # force-check against level 3's rules

What this checks, and why each one is here:

  - diagram type is recognized (sequenceDiagram / flowchart|graph / stateDiagram(-v2)
    / classDiagram / erDiagram / C4Context|C4Container). An unrecognized block is
    almost always a copy-paste of the fence with no real diagram inside it.

  - SEQUENCE diagrams only: every participant is declared with `participant`/`actor`
    BEFORE it appears in a message, and every message arrow is one of
    -> --> ->> -->> -x --x -- the exact set scripts/design_drift.py's message regex
    recognizes. A participant that mermaid auto-creates from its first message (no
    explicit `participant` line), or a message using an arrow outside that set (e.g.
    the async `-)`), renders fine in mermaid but is INVISIBLE to design_drift.py's
    round-trip -- it will never be flagged as drifted because it was never read in
    the first place. `%% external:` participants are checked for typos the same way:
    an alias listed there that was never declared silently does nothing.

  - flowchart labels: an unquoted `ID[Label (with parens)]` is a documented mermaid
    parse hazard -- it must be `ID["Label (with parens)"]`.

  - no placeholder text survives (`TODO`, `<!-- ... -->`, `<...>`, a bare
    `<placeholder-looking-tag>`).

  - the diagram's LEVEL (declared with `%% level: 1|2|3` right after the diagram-type
    line, or forced with --level, or otherwise inferred from node count and reported)
    has its node budget respected: L1 <= 12 nodes, L2 <= 30 nodes, L3 uncapped but
    requires a numbered step table immediately below the diagram plus at least one
    shown branch/error path. Only a DECLARED or forced level is a hard gate on the
    node count -- an undeclared diagram is never failed for its size alone, but if it
    is big enough to infer as L3 it still owes L3's structural requirements, because
    size earns you those obligations whether you declared them or not.

This is a syntax + structure check, not a renderer. It does not catch every mermaid
parse error the real renderer would; it catches the failure modes that recur in this
plugin's own specs and that break scripts/design_drift.py's round-trip.

Exit 1 on any ERROR. Python stdlib only.
"""
import argparse, pathlib, re, sys

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__",
             ".next", "coverage", ".turbo"}

MERMAID_BLOCK = re.compile(r"```mermaid\s*\n(.*?)```", re.S)
LEVEL_DIRECTIVE = re.compile(r"%%\s*level\s*:\s*([123])")
EXTERNAL_DIRECTIVE = re.compile(r"%%\s*external\s*:\s*(.+)")

# --- diagram type detection -------------------------------------------------
TYPE_PATTERNS = [
    ("sequence", re.compile(r"^\s*sequenceDiagram\b", re.M)),
    ("state", re.compile(r"^\s*stateDiagram(?:-v2)?\b", re.M)),
    ("class", re.compile(r"^\s*classDiagram\b", re.M)),
    ("er", re.compile(r"^\s*erDiagram\b", re.M)),
    ("c4", re.compile(r"^\s*C4(?:Context|Container|Component|Dynamic|Deployment)\b", re.M)),
    ("flowchart", re.compile(r"^\s*(?:flowchart|graph)\s+(?:TD|TB|BT|RL|LR)\b", re.M)),
]

NODE_BUDGET = {1: 12, 2: 30, 3: None}  # None = uncapped; L3's obligation is structural

# --- placeholder text --------------------------------------------------------
PLACEHOLDER = re.compile(r"<!--.*?-->|\bTODO\b|\bFIXME\b|<\.\.\.>", re.S | re.I)
TEMPLATE_TAG = re.compile(r"<([a-zA-Z][a-zA-Z0-9_ -]{2,})>")
SAFE_HTML_TAGS = {"br", "sub", "sup", "b", "i", "u", "small", "del", "ins"}


def scan_placeholders(src):
    out = []
    for m in PLACEHOLDER.finditer(src):
        out.append(("ERROR", f"placeholder text left in diagram: {m.group(0)!r}"))
    for m in TEMPLATE_TAG.finditer(src):
        tag = m.group(1).strip().lower().rstrip("/")
        if tag not in SAFE_HTML_TAGS:
            out.append(("ERROR", f"template placeholder left in diagram: <{m.group(1)}>"))
    return out


# --- sequence diagrams (the type scripts/design_drift.py depends on) --------
# Identical to design_drift.py's PARTICIPANT/MESSAGE regexes on purpose: a form
# design_drift.py cannot parse is a form its round-trip cannot see.
SEQ_PARTICIPANT = re.compile(r"^\s*(actor|participant)\s+(\w+)(?:\s+as\s+(.+?))?\s*$")
SEQ_MESSAGE = re.compile(r"^\s*(\w+)\s*(-->>|->>|-->|->|-x|--x)\s*(\w+)\s*:\s*(.+?)\s*$")
SEQ_ARROW_HINT = re.compile(r"-{1,2}[>x)]|<-{1,2}")
SEQ_KEYWORDS = ("alt", "else", "opt", "par", "and", "critical", "option", "break",
                "loop", "end", "rect", "note", "activate", "deactivate",
                "autonumber", "title", "link", "box", "actor", "participant",
                "sequenceDiagram")
SEQ_BLOCK_KW = re.compile(r"^\s*(alt|opt|par|critical|break)\b", re.M)


def analyze_sequence(src):
    findings = []
    declared, seen = {}, set()
    external = set()
    for m in EXTERNAL_DIRECTIVE.finditer(src):
        external |= {x.strip() for x in m.group(1).split(",") if x.strip()}

    for ln in src.splitlines():
        pm = SEQ_PARTICIPANT.match(ln)
        if pm:
            declared[pm.group(2)] = pm.group(1) == "actor"
            seen.add(pm.group(2))
            continue
        mm = SEQ_MESSAGE.match(ln)
        if mm:
            for alias in (mm.group(1), mm.group(3)):
                if alias not in seen:
                    findings.append((
                        "ERROR",
                        f"participant '{alias}' used before a `participant`/`actor` "
                        f"declaration (in: {ln.strip()!r}) -- design_drift.py never "
                        f"reads an implicitly-created participant"))
                    seen.add(alias)
                    declared.setdefault(alias, False)
            continue
        stripped = ln.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        if any(stripped.split()[0] == k or stripped.startswith(k + " ") for k in SEQ_KEYWORDS):
            continue
        if SEQ_ARROW_HINT.search(stripped):
            findings.append((
                "ERROR",
                f"unrecognized sequence arrow or malformed message: {stripped!r} -- "
                f"only -> --> ->> -->> -x --x round-trip through design_drift.py"))

    for alias in external:
        if alias not in declared:
            findings.append((
                "ERROR",
                f"`%% external: {alias}` references a participant never declared "
                f"in this diagram"))

    nodes = len(declared)
    edges = sum(1 for ln in src.splitlines() if SEQ_MESSAGE.match(ln))
    has_branch = bool(SEQ_BLOCK_KW.search(src))
    return nodes, edges, findings, has_branch


# --- flowchart ----------------------------------------------------------------
FLOW_EDGE = re.compile(
    r"(\w+)(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})?\s*"
    r"(-{1,3}>|={1,3}>|-\.{1,3}->|--o|--x)\s*(?:\|[^|]*\|\s*)?(\w+)")
FLOW_NODE_DECL = re.compile(r"(\w+)\s*(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})")
FLOW_DECISION = re.compile(r"\w+\s*\{[^}]*\}")
UNQUOTED_PAREN_LABEL = re.compile(r'\w+\[(?!")([^\]"]*[()][^\]"]*)\]')


def analyze_flowchart(src):
    findings = []
    nodes = set()
    edges = 0
    for m in FLOW_EDGE.finditer(src):
        nodes.add(m.group(1)); nodes.add(m.group(3)); edges += 1
    for m in FLOW_NODE_DECL.finditer(src):
        nodes.add(m.group(1))
    for m in UNQUOTED_PAREN_LABEL.finditer(src):
        findings.append((
            "ERROR",
            f"label needs quoting -- parentheses inside an unquoted [...] label "
            f"break mermaid parsing: {m.group(0)!r} (use [\"...\"])"))
    if edges == 0:
        findings.append(("ERROR", "flowchart has no recognizable edges -- empty or malformed"))
    return len(nodes), edges, findings, bool(FLOW_DECISION.search(src))


# --- state ----------------------------------------------------------------
STATE_TRANS = re.compile(r"^\s*(\[\*\]|\w+)\s*-->\s*(\[\*\]|\w+)\s*(:.*)?$", re.M)
STATE_ERR = re.compile(r"\b(fail|error|reject|retry|timeout|cancel)\w*\b", re.I)


def analyze_state(src):
    findings = []
    nodes, out_degree, edges = set(), {}, 0
    for m in STATE_TRANS.finditer(src):
        a, b = m.group(1), m.group(2)
        if a != "[*]":
            nodes.add(a); out_degree[a] = out_degree.get(a, 0) + 1
        if b != "[*]":
            nodes.add(b)
        edges += 1
    if edges == 0:
        findings.append(("ERROR", "state diagram has no recognizable transitions "
                                   "(expected `A --> B` lines)"))
    has_branch = any(v >= 2 for v in out_degree.values()) or bool(STATE_ERR.search(src))
    return len(nodes), edges, findings, has_branch


# --- class / ER ----------------------------------------------------------------
CLASS_DECL = re.compile(r"^\s*class\s+(\w+)", re.M)
CLASS_REL = re.compile(r"(\w+)\s*(<\|--|\*--|o--|-->|\.\.>|\.\.\|>|--)\s*(\w+)")
ER_REL = re.compile(r"(\w+)\s+([|o{}]{1,2}--[|o{}]{1,2})\s+(\w+)\s*:\s*(.+)")


def analyze_class(src):
    findings = []
    nodes = set(CLASS_DECL.findall(src))
    edges = 0
    for m in CLASS_REL.finditer(src):
        nodes.add(m.group(1)); nodes.add(m.group(3)); edges += 1
    if not nodes and edges == 0:
        findings.append(("ERROR", "class diagram has no recognizable classes or relationships"))
    return len(nodes), edges, findings, False


def analyze_er(src):
    findings = []
    nodes = set()
    edges = 0
    for m in ER_REL.finditer(src):
        nodes.add(m.group(1)); nodes.add(m.group(3)); edges += 1
    if edges == 0:
        findings.append(("ERROR", "ER diagram has no recognizable relationships "
                                   "(expected `A ||--o{ B : label`)"))
    return len(nodes), edges, findings, False


# --- C4 ----------------------------------------------------------------
C4_NODE = re.compile(r"\b(?:Person|System|SystemDb|SystemQueue|Container|ContainerDb|"
                      r"ContainerQueue|Component|ComponentDb|Boundary|Enterprise_Boundary|"
                      r"System_Boundary|Container_Boundary)\w*\s*\(")
C4_EDGE = re.compile(r"\b(?:Rel|BiRel)\w*\s*\(")


def analyze_c4(src):
    findings = []
    nodes = len(C4_NODE.findall(src))
    edges = len(C4_EDGE.findall(src))
    if nodes == 0:
        findings.append(("ERROR", "C4 diagram has no recognizable Person()/System()/"
                                   "Container()/Component() declarations"))
    return nodes, edges, findings, False


ANALYZERS = {
    "sequence": analyze_sequence, "flowchart": analyze_flowchart,
    "state": analyze_state, "class": analyze_class,
    "er": analyze_er, "c4": analyze_c4,
}
BRANCH_REQUIRED_TYPES = {"sequence", "flowchart", "state"}


def diagram_type(src):
    for name, pat in TYPE_PATTERNS:
        if pat.search(src):
            return name
    return None


# --- level: declared / forced / inferred ----------------------------------
def evaluate_level(src, nodes, cli_level):
    findings = []
    m = LEVEL_DIRECTIVE.search(src)
    declared = int(m.group(1)) if m else None

    if cli_level is not None:
        level, source = cli_level, "cli"
        if declared is not None and declared != cli_level:
            findings.append(("INFO", f"diagram declares level {declared}; "
                                      f"--level {cli_level} overrides for this run"))
    elif declared is not None:
        level, source = declared, "declared"
    else:
        level = 1 if nodes <= NODE_BUDGET[1] else 2 if nodes <= NODE_BUDGET[2] else 3
        source = "inferred"
        findings.append(("INFO", f"no `%% level:` directive -- inferred level {level} "
                                  f"from {nodes} node(s); declare it to make the budget "
                                  f"a hard gate"))

    if source in ("cli", "declared"):
        budget = NODE_BUDGET[level]
        if budget is not None and nodes > budget:
            findings.append(("ERROR", f"level {level} allows <= {budget} nodes; diagram "
                                       f"has {nodes} -- split it or bump the level"))
    return level, source, findings


STEP_TABLE_ROW = re.compile(r"^\s*\|\s*(\d+)\s*\|", re.M)


def find_step_table(after_text, max_lines=100):
    lines = []
    for ln in after_text.splitlines()[:max_lines]:
        if ln.startswith("## "):
            break
        lines.append(ln)
    return [int(n) for n in STEP_TABLE_ROW.findall("\n".join(lines))]


def check_block(src, after_text, cli_level):
    dtype = diagram_type(src)
    if dtype is None:
        return dtype, None, 0, 0, [(
            "ERROR", "could not identify a diagram type (expected sequenceDiagram / "
                     "flowchart|graph / stateDiagram(-v2) / classDiagram / erDiagram / "
                     "C4Context|C4Container)")]

    findings = scan_placeholders(src)
    nodes, edges, type_findings, has_branch = ANALYZERS[dtype](src)
    findings += type_findings

    level, source, level_findings = evaluate_level(src, nodes, cli_level)
    findings += level_findings

    if level == 3:
        if dtype in BRANCH_REQUIRED_TYPES and not has_branch:
            findings.append(("ERROR",
                "level 3 requires at least one shown branch/error path -- an "
                "alt/opt/par/critical/break block for sequence, a decision {...} "
                "node for flowchart, or an error-like state for state -- none found"))
        steps = find_step_table(after_text)
        ok = steps and steps[0] == 1 and steps == sorted(set(steps)) and len(steps) >= 2
        if not ok:
            findings.append(("ERROR",
                "level 3 requires a numbered step table (`| 1 |`, `| 2 |`, ... "
                "ascending from 1) immediately below the diagram -- found none or "
                "malformed"))

    return dtype, level, nodes, edges, findings


def collect_files(target: pathlib.Path):
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*.md")
                  if not any(part in SKIP_DIRS for part in p.parts))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target")
    ap.add_argument("--level", type=int, choices=[1, 2, 3], default=None,
                     help="force this level's rules instead of the declared/inferred one")
    a = ap.parse_args()

    target = pathlib.Path(a.target)
    if not target.exists():
        print(f"no such file or directory: {a.target}", file=sys.stderr)
        return 2
    files = collect_files(target)

    total_blocks = total_errors = 0
    for f in files:
        text = f.read_text(errors="replace")
        blocks = list(MERMAID_BLOCK.finditer(text))
        if not blocks:
            continue
        print(f"\n{f}")
        for i, m in enumerate(blocks, 1):
            dtype, level, nodes, edges, findings = check_block(
                m.group(1), text[m.end():], a.level)
            total_blocks += 1
            errs = [x for x in findings if x[0] == "ERROR"]
            total_errors += len(errs)
            lvl_str = f"L{level}" if level else "?"
            status = "OK  " if not errs else "FAIL"
            print(f"  [{status}] block {i}: type={dtype or '?'} nodes={nodes} "
                  f"edges={edges} level={lvl_str}")
            for sev, msg in findings:
                print(f"      {sev:5} {msg}")

    if total_blocks == 0:
        print(f"no mermaid blocks found under {a.target}")
        return 0

    print(f"\ncheck_diagrams: {total_blocks} diagram(s) checked, {total_errors} error(s)")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
