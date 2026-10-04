#!/usr/bin/env python3
"""Mechanically enforce research/01-skill-contract.md against every SKILL.md.

The plugin claims that advice without a runnable check is decoration. That claim
has to bind this plugin's own skills first, so this is the gate on our output.
Exit 1 on any ERROR, 2 when there is no SKILL.md to lint.
Run: python3 scripts/lint_skills.py [--root DIR]  (default root: this plugin)

Description rules are tuned for a crowded listing, not for this plugin alone. Installed
beside ~400 other skills, the harness showed many of ours NAME-ONLY: descriptions were
dropped once the listing budget ran out, and any one description is cut at 1,536 chars.
So a description is capped (MAX_DESC, an error) and must name what fires it early: the
first TRIGGER_WINDOW chars should share at least one noun with the skill's own
`**Fire when:**` paragraph (a warning). That check is a heuristic -- a lowercase word
match of 4+ letters with a trailing "s" stripped, minus a stoplist of generic words -- so
it catches a description that opens with throat-clearing ("Use when writing or reviewing
any...") and cannot judge whether the noun it finds is the right one.
"""
import argparse, re, sys, pathlib

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent

ALLOWED_FM = {"name", "description", "license", "allowed-tools", "metadata", "compatibility",
              "when_to_use", "argument-hint", "disable-model-invocation", "user-invocable",
              "model", "context", "agent", "paths"}
REQUIRED = ["## Trigger", "## Rules", "## Verify", "## Failure modes", "## Scale", "## Sources"]
MAX_LINES = 250
MAX_CONVENTION = 3
MIN_DESC = 120
MAX_DESC = 300          # hard cap; the house style aims at <= 250
TRIGGER_WINDOW = 100
GENERIC = set("""when what with that this from into your their there which where while about
after before every other them they than then also only just like such some more most much
many each both have does done used using user users code file files work change changes
changing write writing review reviewing build building add adding make making new any one
two need needs asked asking task tasks thing things something someone being been were
will would should could start started about across without within someone's""".split())
CMD_START = ("100x", "python3", "bash", "npx", "npm", "yarn", "pnpm", "ruff", "mypy", "pytest",
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


def nouns(text):
    """Heuristic content words: 4+ letters, trailing 's' stripped, generic words removed."""
    words = (w.lower().rstrip(".-") for w in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{3,}", text))
    return {w[:-1] if w.endswith("s") and len(w) > 4 else w
            for w in words if w not in GENERIC}


def fire_nouns(trigger_section):
    """Words of the '**Fire when:**' paragraph only; 'Do not fire' names anti-triggers."""
    m = re.search(r"\*\*Fire when:\*\*(.*?)(?:\n\s*\n|\*\*Do not fire|$)",
                  trigger_section, re.S)
    return nouns(m.group(1)) if m else set()


def lint(path: pathlib.Path):
    try:
        rel = path.resolve().relative_to(pathlib.Path.cwd())
    except ValueError:
        rel = path
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
    if len(desc) > MAX_DESC:
        err(f"description is {len(desc)} chars, over the {MAX_DESC} cap (a long description "
            f"is dropped or cut first when many plugins share the skill listing)")
    fire = fire_nouns(section(body, "## Trigger"))
    head = nouns(desc[:TRIGGER_WINDOW])
    if fire and not (head & fire):
        warn(f"first {TRIGGER_WINDOW} chars of the description share no noun with "
             f"'**Fire when:**' — front-load what fires the skill")

    for sec in REQUIRED:
        if sec not in body:
            err(f"missing required section '{sec}'")

    if len(lines) > MAX_LINES:
        err(f"{len(lines)} lines exceeds the {MAX_LINES} cap — move detail to references/")

    conv = len(re.findall(r"\*Enforced by:\*\s*convention", body))
    if conv > MAX_CONVENTION:
        err(f"{conv} 'convention' rules exceeds the cap of {MAX_CONVENTION}")

    # Every numbered rule needs an enforcement tag. Scoped to the Rules section:
    # other sections legitimately use numbered lists that are not rules.
    rules_sec = section(body, "## Rules")
    rules = re.findall(r"^\s*(\d+[a-z]?)\.\s", rules_sec, re.M)
    tags = len(re.findall(r"\*Enforced by:\*", rules_sec))
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
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(PLUGIN_ROOT),
                    help="plugin root holding skills/ (default: this plugin, wherever it "
                         "is run from)")
    root = pathlib.Path(ap.parse_args().root) / "skills"
    # Nothing to lint is a failure, not a pass: run from the wrong directory, the
    # old cwd default reported success on zero skills.
    if not root.is_dir():
        print(f"lint_skills: no skills/ directory under {root.parent} -- nothing was "
              f"linted", file=sys.stderr); return 2
    files = sorted(root.glob("*/SKILL.md"))
    if not files:
        print(f"lint_skills: no */SKILL.md under {root} -- nothing was linted",
              file=sys.stderr); return 2
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
