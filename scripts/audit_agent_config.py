#!/usr/bin/env python3
"""Audit a repository's AI-agent configuration as untrusted input.

Agent instruction files and hooks ship on a default branch and are auto-loaded by
tooling. Cloning a repo and opening an agent in it executes whatever its author put
there. Measured context (research/10-repo-corpus.md): 48% of active 20k+ star repos
ship at least one such file, so this is the common case, not an edge case.

    audit_agent_config.py [path]        # default: cwd
Exit 1 if any HIGH finding. Exit 0 with report otherwise.
"""
import json, re, sys, pathlib, argparse

INSTRUCTION_FILES = [
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules", ".windsurfrules",
    ".clinerules", ".rules", ".github/copilot-instructions.md",
    ".junie/guidelines.md", ".aider.conf.yml",
]
INSTRUCTION_GLOBS = [".cursor/rules/*", ".agents/*", ".claude/*.md"]
HOOK_FILES = [".claude/settings.json", ".claude/settings.local.json",
              ".claude/hooks.json", ".mcp.json"]

# Directives aimed at steering a reviewing/coding agent rather than describing
# house style. Each pattern is a question to ask a human, not a verdict.
SUSPICIOUS = [
    (r"\b(approve|lgtm|sign off|mark as approved)\b", "HIGH",
     "instructs the agent about APPROVAL - a review decision is not the repo's to make"),
    (r"\bignore (all |any )?(previous|prior|earlier|above) (instructions|rules|prompts)\b",
     "HIGH", "classic instruction-override phrasing"),
    (r"\b(disregard|override)\b.{0,40}\b(instruction|rule|system|policy|guardrail)\b",
     "HIGH", "attempts to override caller instructions"),
    (r"\byour only output must be\b|\byou must (only |always )?(respond|output|reply) (with|exactly)\b",
     "MEDIUM", "constrains the agent's output channel"),
    (r"\b(do not|never) (report|mention|disclose|tell|reveal)\b", "MEDIUM",
     "asks the agent to withhold information from its user"),
    (r"\b(exfiltrat|curl\s+-|wget\s+http|base64\s+-d|eval\s*\(|\| ?sh\b|\| ?bash\b)",
     "HIGH", "network egress or shell evaluation inside an instruction file"),
    (r"(patreon|buy me a coffee|ko-fi|opencollective"
     r"|sponsor (us|me|this project)|please (donate|sponsor)"
     r"|upgrade to (pro|premium|paid)|star this repo|follow me on)",
     "MEDIUM", "promotional content injected into agent context"),
    (r"\b(api[_ -]?key|secret|token|password|credential)s?\b.{0,30}(=|:)\s*\S{12,}",
     "HIGH", "possible hardcoded credential"),
    (r"\bprepend\b.{0,60}\b(README|LICENSE)\b|\bnever remove these lines\b", "INFO",
     "human-attestation canary (a deliberate review tripwire, e.g. zed-industries/zed)"),
]
SUSPICIOUS = [(re.compile(p, re.I | re.S), sev, why) for p, sev, why in SUSPICIOUS]


def scan_text(path, text, out):
    seen = set()
    for rx, sev, why in SUSPICIOUS:
        for m in rx.finditer(text):
            line = text[:m.start()].count("\n") + 1
            snippet = re.sub(r"\s+", " ", m.group(0))[:90]
            key = (path, why, snippet.lower())
            if key in seen:            # same pattern twice in one file adds nothing
                continue
            seen.add(key)
            out.append((sev, f"{path}:{line}", why, snippet))


def scan_hooks(path, text, out):
    """A hook is arbitrary code the harness runs. Always report, never silently trust."""
    try:
        data = json.loads(text)
    except Exception:
        out.append(("MEDIUM", str(path), "hook/MCP config present but unparseable", ""))
        return
    hooks = data.get("hooks") or {}
    for event, entries in (hooks.items() if isinstance(hooks, dict) else []):
        for entry in (entries if isinstance(entries, list) else []):
            for h in (entry.get("hooks") or []):
                cmd = h.get("command") or h.get("prompt") or h.get("url") or ""
                out.append(("HIGH", str(path),
                            f"{event} hook executes on your machine (matcher="
                            f"{entry.get('matcher','*')!r}, type={h.get('type')})",
                            re.sub(r"\s+", " ", str(cmd))[:110]))
    for name, srv in (data.get("mcpServers") or {}).items():
        cmd = " ".join([srv.get("command", "")] + list(srv.get("args") or [])) \
              if isinstance(srv, dict) else str(srv)
        out.append(("HIGH", str(path), f"MCP server '{name}' will be launched",
                    cmd[:110]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--quiet", action="store_true", help="only print findings")
    a = ap.parse_args()
    root = pathlib.Path(a.path).resolve()
    out, found_files = [], []

    targets = []
    for rel in INSTRUCTION_FILES + HOOK_FILES:
        p = root / rel
        if p.is_file():
            targets.append((rel, p))
    for g in INSTRUCTION_GLOBS:
        for p in sorted(root.glob(g)):
            if p.is_file():
                targets.append((str(p.relative_to(root)), p))

    for rel, p in targets:
        found_files.append(rel)
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        if rel in HOOK_FILES:
            scan_hooks(rel, text, out)
        else:
            scan_text(rel, text, out)

    if not found_files:
        if not a.quiet:
            print("audit_agent_config: no agent configuration found — nothing auto-loads")
        return 0

    if not a.quiet:
        print(f"audit_agent_config: {len(found_files)} agent config file(s) in {root}")
        for f in found_files:
            print(f"  - {f}")
        print()

    order = {"HIGH": 0, "MEDIUM": 1, "INFO": 2}
    out.sort(key=lambda r: order.get(r[0], 3))
    highs = sum(1 for r in out if r[0] == "HIGH")
    for sev, loc, why, snip in out:
        print(f"[{sev:6s}] {loc}\n          {why}")
        if snip:
            print(f"          > {snip}")
    print(f"\n{len(out)} finding(s): {highs} HIGH. "
          f"{'REVIEW BEFORE TRUSTING THIS REPO.' if highs else 'No HIGH findings.'}")
    print("Every finding is a question for a human, not a verdict. Legitimate repos "
          "trip these patterns (e.g. a deliberate review canary, or a documented "
          "Copilot opt-out).")
    return 1 if highs else 0


if __name__ == "__main__":
    sys.exit(main())
