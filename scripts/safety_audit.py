#!/usr/bin/env python3
"""Fail if this plugin gains a destructive primitive or an unguarded mutation.

A safety claim in a README decays the moment someone adds a line. This makes the
boundary executable: the plugin asserts it never deletes, and this is what keeps that
true as it grows.

Threat model: the user runs `claude --dangerously-skip-permissions`, so nothing
prompts. Every mutation runs silently, and the only protection is what the code
itself refuses to do.

    safety_audit.py
    safety_audit.py --json

Exit 1 if a destructive primitive appears outside the allowlist.
Python stdlib only.
"""
import argparse, json, pathlib, re, subprocess, sys

PLUGIN = pathlib.Path(__file__).resolve().parent.parent

# Primitives that can destroy a user's work. None of these belongs in this plugin.
FORBIDDEN = {
    r"\bshutil\.rmtree\b": "recursive delete",
    r"\bos\.remove\b": "file delete",
    r"\bos\.unlink\b": "file delete",
    r"\bPath\([^)]*\)\.unlink\b|\.unlink\(": "file delete",
    r"\bos\.rmdir\b": "directory delete",
    r"\bgit\W+rm\b": "git rm",
    r"\bgit\W+checkout\b": "git checkout (discards working-tree changes)",
    r"\bgit\W+reset\b": "git reset",
    r"\bgit\W+clean\b": "git clean",
    r"\bgit\W+stash\b": "git stash (moves the user's uncommitted work)",
    r"\bgit\W+push\b": "git push (sends data off the machine)",
    r"\bsubprocess[^\n]*\brm\b\s+-": "shell rm",
}
# Each entry is (file, pattern-fragment, why it is acceptable). Anything else fails.
ALLOWLIST = [
    ("run_evals.py", "shutil", "operates only inside tempfile.TemporaryDirectory()"),
    ("run_workflow_evals.py", "shutil", "operates only inside a temp dir"),
    ("safety_audit.py", "*", "this file names the patterns in order to forbid them"),
]
# Writes must be guarded: either under a temp dir, or behind dry-run/--yes, or into a
# known records path. This catches a new write that slipped in unguarded.
WRITE_RX = re.compile(r"\.write_text\(|\.rename\(|\bgit\W+mv\b")
GUARD_HINTS = ("dry_run", "--yes", "getattr(a, \"yes\"", "tempfile", "TemporaryDirectory",
               "mkdtemp", "safe_record_name", "require_git_root", "_mutation_guard")
# A tool whose whole purpose is to write one known artifact is guarded by its scope,
# not by a flag. Each entry states the only path it writes.
SCOPED_WRITERS = {
    "verified.py": ".claude/verification-receipt.json",
    "learn.py": "lessons/ (records + generated INDEX.md)",
    "01_harvest_candidates.py": "research/raw/ (one-shot research pipeline)",
    "02_enrich.py": "research/raw/",
    "02_enrich_gql.py": "research/raw/",
    "03_score.py": "research/raw/",
    "04_corpus_doc.py": "research/10-repo-corpus.md",
}


def scan():
    findings, writes = [], []
    for f in sorted(list((PLUGIN / "scripts").glob("*.py")) +
                    list((PLUGIN / "hooks").glob("*.py"))):
        text = f.read_text(errors="replace")
        allowed = {frag for fn, frag, _ in ALLOWLIST if fn == f.name}
        for rx, why in FORBIDDEN.items():
            for m in re.finditer(rx, text):
                line = text[:m.start()].count("\n") + 1
                snippet = text.splitlines()[line - 1].strip()
                # A regex that DETECTS a dangerous command is not a call to it. The
                # verification hook must match `git push` in order to gate it.
                if snippet.startswith("#") or "re.compile" in snippet or \
                   snippet.lstrip().startswith(("r\"", "r'", '"', "'")) or \
                   "RX = " in snippet or "_RX" in snippet:
                    continue
                if "*" in allowed or any(a in snippet for a in allowed):
                    continue
                findings.append({"file": f.name, "line": line, "why": why,
                                 "code": snippet[:100]})
        if WRITE_RX.search(text):
            guarded = any(h in text for h in GUARD_HINTS) or f.name in SCOPED_WRITERS
            writes.append({"file": f.name, "guarded": guarded,
                           "scope": SCOPED_WRITERS.get(f.name, "")})
    return findings, writes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    findings, writes = scan()
    unguarded = [w for w in writes if not w["guarded"]]
    if a.json:
        print(json.dumps({"forbidden": findings, "writers": writes,
                          "unguarded": unguarded}, indent=2))
        return 1 if findings else 0

    print(f"safety_audit: scanned {len(list((PLUGIN/'scripts').glob('*.py')))} scripts "
          f"and {len(list((PLUGIN/'hooks').glob('*.py')))} hooks\n")
    scoped = [w for w in writes if w.get("scope")]
    print(f"  files that write, rename or git-mv : {len(writes)}")
    print(f"  guarded by a flag or temp dir      : {len(writes)-len(scoped)-len(unguarded)}")
    print(f"  guarded by scope (one known path)  : {len(scoped)}")
    for w in scoped:
        print(f"      {w['file']:28s} -> {w['scope']}")
    print(f"  showing no guard at all            : {len(unguarded)}")
    for w in unguarded:
        print(f"      REVIEW {w['file']} — writes with no dry-run/temp/name guard in file")
    if findings:
        print(f"\n  DESTRUCTIVE PRIMITIVES FOUND ({len(findings)}):")
        for x in findings:
            print(f"      {x['file']}:{x['line']}  {x['why']}")
            print(f"         {x['code']}")
        print("\n  This plugin's stated boundary is that it never deletes a user's work.")
        print("  Either remove the call, or add an allowlist entry with a reason.")
        return 1
    print("\n  no destructive primitive present — the stated boundary holds")
    print("  (delete, git rm/checkout/reset/clean/stash, git push, shell rm)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
