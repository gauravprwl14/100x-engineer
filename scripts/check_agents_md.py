#!/usr/bin/env python3
"""Check an AGENTS.md against the measured practice of 48 production repos.

Patterns and frequencies come from research/21-findings-agent-instruction-corpus.md
(61 repos probed, 48 with at least one agent instruction file). Every check below
corresponds to a rule observed in real repos, with the repo count recorded.

    check_agents_md.py [path]
Exit 1 if a rule marked REQUIRED is missing.
"""
import re, sys, pathlib, argparse

# (label, REQUIRED, regex, repos-observed, why it matters)
CHECKS = [
 ("named prove-it command", True,
  r"```[\s\S]{0,400}?(pnpm|npm|yarn|bun|make|uv|cargo|go |\./gradlew|pytest|ruff|"
  r"tox|nox|just|bazel|xcodebuild)[^\n]*\n[\s\S]{0,400}?```|`[^`\n]{0,60}"
  r"(test|check|verify|lint|typecheck|build)[^`\n]{0,40}`",
  "30+", "the most common rule in the corpus: one named command proves the change works"),
 ("scope discipline", True,
  r"(scoped?|unrelated|drive-?by|focused)\b[\s\S]{0,80}(diff|change|refactor|file|format)"
  r"|keep (each )?(change|diff)s? (focused|scoped|small)",
  "12+", "prevents the agent widening a diff with opportunistic edits"),
 ("prefer editing over creating", False,
  r"prefer (editing|extending|modifying)[\s\S]{0,60}(existing|current)"
  r"|(avoid|don'?t|do not) creat(e|ing) (new |many )?(files?|small files)",
  "8+", "the primary anti-bloat rule in agent instructions"),
 ("generated-code prohibition", False,
  r"(never|do ?n[o']t|avoid)[\s\S]{0,40}(hand-?edit|edit|modify)[\s\S]{0,40}generated"
  r"|generated[\s\S]{0,30}(do not edit|don'?t edit|never edit)",
  "10+", "hand-edited generated files are silently reverted by the next regen"),
 ("dependency-addition rule", False,
  r"(dependenc|package|crate|module)[\s\S]{0,90}(check|existing|alternative|before adding|"
  r"never add|do not add|avoid adding)",
  "8+", "checking for an existing alternative before adding a dependency"),
 ("comment discipline", False,
  r"comments?[\s\S]{0,60}(why|not the what|non-?obvious)"
  r"|(avoid|no|don'?t)[\s\S]{0,30}comments?[\s\S]{0,40}(summari[sz]|restat|narrat|obvious)",
  "15+", "the single most frequent style rule in the corpus"),
 ("no suppression of checks", False,
  r"(never|do ?n[o']t|avoid)[\s\S]{0,50}(suppress|@ts-ignore|# type: ignore|"
  r"eslint-disable|#\[allow|noqa|silence)",
  "6+", "suppressing the type-checker hides the bug the checker found"),
 ("no AI attribution / no process leakage", False,
  r"(co-?author|attribution|generated with|Claude Code)[\s\S]{0,60}(never|do not|don'?t|no)"
  r"|(never|do not|don'?t)[\s\S]{0,60}(co-?author|attribution|generated with)"
  r"|(do not|don'?t|never)[\s\S]{0,60}(leak|mention)[\s\S]{0,60}"
  r"(conversation|prompt|iteration|tool usage|session)",
  "8+", "keeps process narration out of permanent commit history"),
 ("numeric budget", False,
  r"(>|<|under|exceed|max(imum)?|no more than|cap(ped)? at|target)\s*~?\d{2,}\s*"
  r"(lines?|loc|files?|kb|mb|chars?)",
  "5+", "a number is enforceable; 'keep it small' is not"),
 ("narrowest-check-first guidance", False,
  r"(narrowest|fastest|quickest)[\s\S]{0,60}(command|check|first)"
  r"|before broadening|then broaden",
  "6+", "a fast first gate is the one that actually gets run"),
 ("nested/local override note", False,
  r"(directory|package|sub-?dir|nested|closest)[\s\S]{0,80}(AGENTS\.md|own [A-Z]+\.md)"
  r"|closest applicable",
  "5+", "monorepos need local overrides or the root file becomes wrong everywhere"),
 ("defers to authoritative docs", False,
  r"(summari[sz]es?|does not replace|defer to|authoritative|source of truth)"
  r"[\s\S]{0,100}(CONTRIBUTING|docs?/|documentation|[\w/.-]+\.md)"
  r"|prefer authoritative",
  "6+", "prevents the file drifting from the real docs it duplicates"),
]
CHECKS = [(l, r, re.compile(p, re.I), n, w) for l, r, p, n, w in CHECKS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".")
    a = ap.parse_args()
    root = pathlib.Path(a.path).resolve()

    agents = next((root / n for n in ("AGENTS.md", ".github/AGENTS.md") if (root / n).is_file()), None)
    claude = next((root / n for n in ("CLAUDE.md", ".claude/CLAUDE.md") if (root / n).is_file()), None)

    if not agents and not claude:
        print("check_agents_md: no AGENTS.md or CLAUDE.md found.\n"
              "  48% of active 20k+ star repos have one; AGENTS.md is now the canonical\n"
              "  filename (research/10-repo-corpus.md). Consider adding one.")
        return 1

    if not agents and claude:
        print("[WARN] CLAUDE.md exists but AGENTS.md does not.\n"
              "       AGENTS.md is canonical in the corpus (412 repos vs 290), and 23 of 28\n"
              "       CLAUDE.md files are pointers to it. Prefer AGENTS.md as the real file.")
        agents = claude

    text = agents.read_text(errors="replace")
    lines = text.splitlines()
    print(f"check_agents_md: {agents.relative_to(root)} ({len(lines)} lines)")

    # CLAUDE.md should be a pointer, not a duplicate (23 of 28 in corpus)
    if claude and agents != claude:
        ctext = claude.read_text(errors="replace")
        if len(ctext.splitlines()) > 12 and "AGENTS.md" not in ctext:
            print("[WARN] CLAUDE.md is a second full document, not a pointer.\n"
                  "       23 of 28 CLAUDE.md files in the corpus are pointers "
                  "(`@AGENTS.md` or a symlink).\n"
                  "       Two documents drift; one does not.")
        else:
            print("  ok   CLAUDE.md is a pointer to AGENTS.md (matches 82% of corpus)")

    missing_required = 0
    for label, required, rx, n, why in CHECKS:
        if rx.search(text):
            print(f"  ok   {label}")
        else:
            tag = "MISS" if required else "gap "
            if required:
                missing_required += 1
            print(f"  [{tag}] {label}  (observed in {n} corpus repos)")
            print(f"         {why}")

    # structure, not length, tracks quality in the corpus
    heads = len(re.findall(r"^#{2,3}\s", text, re.M))
    if len(lines) > 120 and heads < 5:
        print(f"[WARN] {len(lines)} lines with only {heads} section headings.\n"
              "       Corpus finding: quality tracks STRUCTURE, not length. kubernetes "
              "(38 lines)\n       and appwrite (308 lines) are both high-density; "
              "unstructured length is the problem.")

    print(f"\ncheck_agents_md: {missing_required} required pattern(s) missing")
    return 1 if missing_required else 0


if __name__ == "__main__":
    sys.exit(main())
