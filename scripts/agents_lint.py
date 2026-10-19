#!/usr/bin/env python3
"""Check every agents/*.md against docs/OPERATING-MODEL.md and Claude Code's plugin-agent format.

An agent file that does not parse still loads, silently, with every field ignored, and a
`skills:` entry naming a skill that does not exist is skipped with only a debug-log
warning (https://code.claude.com/docs/en/sub-agents, "Preload skills into subagents").
Both failures are invisible at runtime, so they are caught here instead.

Exit 1 on any error. Run: python3 scripts/agents_lint.py [--root DIR]
"""
import argparse, json, pathlib, re, sys

# Plugin agents ignore these fields, so declaring one is a false promise in the file
# (https://code.claude.com/docs/en/plugins/components, "Frontmatter fields in plugin agents").
IGNORED_IN_PLUGIN = {"permissionMode", "hooks", "mcpServers", "initialPrompt"}
SUPPORTED = {"name", "description", "model", "effort", "maxTurns", "tools", "disallowedTools",
             "skills", "memory", "background", "omitClaudeMd", "isolation", "color", "experimental"}
KNOWN_TOOLS = {"Read", "Grep", "Glob", "Bash", "Edit", "Write", "NotebookEdit", "Skill",
               "WebFetch", "WebSearch", "Agent", "TodoWrite"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
# Roles the operating model marks "writes code? no": they judge others' work, and an agent
# that can edit what it reviews has stopped being independent.
READ_ONLY = {"requirements-analyst", "solution-architect", "code-reviewer",
             "security-reviewer", "independent-verifier"}
ENGINEERS = {"backend-engineer", "frontend-engineer", "mobile-engineer"}
ENGINEER_PHRASES = ("challenge the plan before implementing",
                    "if the plan cannot be executed as written, say so with a proposal")
TRIGGER = re.compile(r"\b(use (when|to|for|after|before)|use proactively|proactively)\b", re.I)
MIN_DESC, MAX_BODY = 120, 120


def parse_frontmatter(text):
    """Parse the YAML subset agent files use: scalars, folded `>` blocks, `- item` lists.

    The plugin depends on nothing but the standard library (AGENTS.md rule 12), so no PyYAML.
    """
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, text
    fm, body = text[4:end], text[end + 4:].lstrip("\n")
    data, key = {}, None
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            data[key] = "" if val in (">", ">-", "|", "|-") else val
            continue
        if key is None or not line.strip():
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item:
            data[key] = (data[key] if isinstance(data[key], list) else []) + [item.group(1).strip()]
        elif isinstance(data[key], str):
            data[key] = (data[key] + " " + line.strip()).strip()
    return data, body


def roster(root):
    """Agent names from the first column of the §1 table of the operating model."""
    om = (root / "docs" / "OPERATING-MODEL.md").read_text()
    sec = om.split("## 1. Roles", 1)[-1].split("\n## 2.", 1)[0]
    names = re.findall(r"^\|\s*([a-z][a-z-]+)\s*\|", sec, re.M)
    return {n for n in names if n != "agent"}


def lint(root, pending):
    errors, missing_pending = [], []
    plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text())["name"]
    files = sorted((root / "agents").glob("*.md"))
    for f in files:
        rel = f.relative_to(root)
        def err(msg): errors.append(f"{rel}: {msg}")
        data, body = parse_frontmatter(f.read_text())
        if data is None:
            err("no parseable frontmatter (the agent would load with every field ignored)")
            continue
        for k in data:
            if k in IGNORED_IN_PLUGIN:
                err(f"field '{k}' is ignored for plugin agents")
            elif k not in SUPPORTED:
                err(f"unknown frontmatter field '{k}'")
        if data.get("name") != f.stem:
            err(f"name {data.get('name')!r} != filename {f.stem!r}")
        desc = data.get("description", "")
        if len(desc) < MIN_DESC:
            err(f"description is {len(desc)} chars, under {MIN_DESC}")
        if not TRIGGER.search(desc):
            err("description has no trigger phrase ('Use when/to/for', 'PROACTIVELY')")
        tools = data.get("tools", "")
        tools = tools if isinstance(tools, list) else [t.strip() for t in tools.split(",") if t.strip()]
        if not tools:
            err("no tools list (an omitted list inherits every tool)")
        for t in tools:
            if t not in KNOWN_TOOLS:
                err(f"unknown tool '{t}'")
        if f.stem in READ_ONLY and WRITE_TOOLS & set(tools):
            err(f"read-only role has write tools: {sorted(WRITE_TOOLS & set(tools))}")
        skills = data.get("skills", [])
        if isinstance(skills, str):
            skills = [skills] if skills else []
        for s in skills:
            if not s.startswith(plugin + ":"):
                err(f"skill '{s}' is not namespaced '{plugin}:<skill>'")
            bare = s.split(":", 1)[-1]
            if not (root / "skills" / bare / "SKILL.md").is_file():
                if bare in pending:
                    missing_pending.append(f"{rel}: {bare}")
                else:
                    err(f"skill '{bare}' does not exist under skills/")
        if "OPERATING-MODEL.md" not in body:
            err("body does not reference OPERATING-MODEL.md")
        if "§3" not in body:
            err("body does not reference the §3 report")
        if "100x baseline show" not in body:
            err("body does not run `100x baseline show`")
        low = re.sub(r"\s+", " ", body.lower())
        if f.stem in ENGINEERS:
            for p in ENGINEER_PHRASES:
                if p not in low:
                    err(f"engineer body lacks '{p}'")
        n = len(body.splitlines())
        if n > MAX_BODY:
            err(f"body is {n} lines, over {MAX_BODY}")
    have, want = {f.stem for f in files}, roster(root)
    for n in sorted(want - have):
        errors.append(f"agents/: roster agent '{n}' (OPERATING-MODEL §1) has no file")
    for n in sorted(have - want):
        errors.append(f"agents/{n}.md: not in the OPERATING-MODEL §1 roster")
    return files, errors, missing_pending


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="plugin root (default: current directory)")
    ap.add_argument("--pending", default="",
                    help="comma-separated skills being built elsewhere; a miss is reported "
                         "separately but still fails")
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    if not (root / "agents").is_dir():
        print("no agents/ directory"); return 1
    files, errors, pend = lint(root, {s for s in a.pending.split(",") if s})
    for e in errors:
        print(f"  ERROR {e}")
    for p in pend:
        print(f"  MISSING-PENDING-SKILL {p}  (in flight in another branch; resolves on merge)")
    print(f"\nagents_lint: {len(files)} agents, {len(errors)} errors, "
          f"{len(pend)} pending-skill misses")
    return 1 if errors or pend else 0


if __name__ == "__main__":
    sys.exit(main())
