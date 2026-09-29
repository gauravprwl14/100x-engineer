#!/usr/bin/env python3
"""Mechanically enforce research/01-skill-contract.md against every SKILL.md.

The plugin claims that advice without a runnable check is decoration. That claim
has to bind this plugin's own skills first, so this is the gate on our output.
Exit 1 on any ERROR. Run: python3 scripts/lint_skills.py
"""
import re, sys, pathlib

ALLOWED_FM = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
REQUIRED = ["## Trigger", "## Rules", "## Verify", "## Failure modes", "## Scale", "## Sources"]
MAX_LINES = 250
MAX_CONVENTION = 3
MIN_DESC = 120
CMD_START = ("python3", "bash", "npx", "npm", "yarn", "pnpm", "ruff", "mypy", "pytest",
             "mkdir", "test ", "grep", "find", "gofmt", "curl", "ls ", "printf",
             "go", "golangci-lint", "cargo", "git", "make", "./", "uv", "deptry",
             "vulture", "madge", "depcheck", "tsc", "eslint", "prettier", "sh ",
             "gradle", "xcodebuild", "fastlane", "cat", "echo", "diff-cover",
             "mutmut", "stryker", "knip", "semgrep", "trivy", "scorecard")


def section(body: str, heading: str) -> str:
    """Extract one '## heading' section, ignoring '## ' lines inside fenced blocks.

    A naive split breaks on heredocs and markdown examples that legitimately contain
    '## ' -- which is exactly what a Verify block writing a PR template looks like.
    """
    lines = body.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    except StopIteration:
        return ""
    out, fence = [], False
    for l in lines[start + 1:]:
        if l.lstrip().startswith("```"):
            fence = not fence
        elif not fence and l.startswith("## "):
            break
        out.append(l)
    return "\n".join(out)


errors, warns = [], []


def lint(path: pathlib.Path):
    rel = path.relative_to(pathlib.Path.cwd()) if path.is_absolute() else path
    def err(m): errors.append(f"{rel}: {m}")
    def warn(m): warns.append(f"{rel}: {m}")

    text = path.read_text()
    lines = text.splitlines()

    if not text.startswith("---"):
        err("missing YAML frontmatter"); return
    parts = text.split("---", 2)
    if len(parts) < 3:
        err("malformed frontmatter"); return
    fm, body = parts[1], parts[2]

    keys = re.findall(r"^([A-Za-z][\w-]*):", fm, re.M)
    for k in keys:
        if k not in ALLOWED_FM:
            err(f"frontmatter key '{k}' not in allowed set {sorted(ALLOWED_FM)}")
    for req in ("name", "description"):
        if req not in keys:
            err(f"frontmatter missing required key '{req}'")

    nm = re.search(r"^name:\s*(\S+)", fm, re.M)
    if nm:
        name = nm.group(1)
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
            err(f"name '{name}' is not kebab-case")
        if name != path.parent.name:
            err(f"name '{name}' != directory '{path.parent.name}'")

    dm = re.search(r"^description:\s*(>[-+]?\s*\n(?:\s+.*\n)+|.*)", fm, re.M)
    desc = re.sub(r"\s+", " ", (dm.group(1) if dm else "")).strip().lstrip("> ")
    if len(desc) < MIN_DESC:
        err(f"description is {len(desc)} chars, under the {MIN_DESC} minimum "
            f"(a vague description is why skills never fire)")
    if not re.search(r"\buse\b", desc, re.I):
        err("description must state when to use the skill (contract: retrieval key, not summary)")

    for sec in REQUIRED:
        if sec not in body:
            err(f"missing required section '{sec}'")

    if len(lines) > MAX_LINES:
        err(f"{len(lines)} lines exceeds the {MAX_LINES} cap — move detail to references/")

    conv = len(re.findall(r"\*Enforced by:\*\s*convention", body))
    if conv > MAX_CONVENTION:
        err(f"{conv} 'convention' rules exceeds the cap of {MAX_CONVENTION}")

    # every numbered rule needs an enforcement tag
    rules = re.findall(r"^\s*(\d+)\.\s", body, re.M)
    tags = len(re.findall(r"\*Enforced by:\*", body))
    if rules and tags < len(rules):
        err(f"{len(rules)} numbered rules but only {tags} 'Enforced by:' tags — "
            f"every rule needs one")

    if "## Verify" in body:
        vsec = section(body, "## Verify")
        cmds = [l.strip() for l in vsec.splitlines()
                if l.strip().startswith(CMD_START)]
        if not cmds:
            err("## Verify contains no runnable command (contract: >=1, no exceptions)")
        if "```" not in vsec:
            warn("## Verify has no fenced code block")

    if "## Sources" in body:
        ssec = body.split("## Sources", 1)[1]
        if not re.search(r"[\w.-]+/[\w.-]+", ssec) and "SOURCE: original" not in ssec:
            err("## Sources has no owner/repo citation and no 'SOURCE: original' label")

    if "## Failure modes" in body:
        fsec = section(body, "## Failure modes")
        if len(fsec.strip()) < 100:
            err("## Failure modes is too thin — if it rejects nothing, delete the skill")


def main():
    root = pathlib.Path("skills")
    if not root.exists():
        print("no skills/ directory"); return 0
    files = sorted(root.glob("*/SKILL.md"))
    if not files:
        print("no SKILL.md files found"); return 0
    for f in files:
        lint(f)
    for w in warns:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  ERROR {e}")
    print(f"\nlint_skills: {len(files)} skills, {len(errors)} errors, {len(warns)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
