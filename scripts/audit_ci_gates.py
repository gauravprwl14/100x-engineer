#!/usr/bin/env python3
"""Find checks that look like gates but cannot fail the build.

Motivated by a measured result: of 50 production Python repos, 36 configure static
type checking but only 27 let it gate CI -- six configure it in a way that provably
never blocks (research/31-findings-python-verification.md). A check that cannot fail
is worse than an absent one, because it buys false confidence.

    audit_ci_gates.py [path]
Exit 1 if any advisory-disguised-as-gate pattern is found.
"""
import re, sys, pathlib, argparse

# (pattern, severity, what it means)
ADVISORY = [
 (r"continue-on-error:\s*true", "HIGH",
  "step continues after failure - the check reports but cannot block"),
 (r"^\s*set \+e", "HIGH",
  "shell error-exit disabled - later commands' failures are swallowed"),
 (r"\|\|\s*true\b", "HIGH",
  "exit code forced to 0 - this command can never fail the job"),
 (r"\|\|\s*:\s*$", "HIGH", "exit code discarded via `|| :`"),
 (r"informational:\s*true", "HIGH",
  "coverage status is informational - looks like a gate, is not one"),
 (r"^\s*#.*(TODO|FIXME).{0,60}(add|enable|re-?enable).{0,30}"
  r"(mypy|pyright|test|lint|typecheck|coverage)", "MEDIUM",
  "a check the repo intends to add but has not"),
 (r"exit\s+0\s*$", "MEDIUM", "unconditional exit 0 at end of a check script"),
 (r"fail[-_]under\s*=\s*0\b", "HIGH", "coverage threshold of 0 - never fails"),
 (r"--exit-zero", "HIGH", "linter told to always exit 0"),
 (r"allow_failure:\s*true", "HIGH", "GitLab job allowed to fail"),
 (r"ignore[-_]failures?:\s*true", "HIGH", "failures explicitly ignored"),
 (r"soft_fail\s*=\s*true", "HIGH", "Buildkite soft-fail: job cannot block"),
 (r"\|\|\s*echo\b", "MEDIUM", "failure routed to an echo instead of a non-zero exit"),
 (r"warn_only\s*=\s*[Tt]rue", "MEDIUM", "tool configured to warn rather than fail"),
]
ADVISORY = [(re.compile(p, re.I | re.M), sev, why) for p, sev, why in ADVISORY]

CI_GLOBS = [".github/workflows/*.yml", ".github/workflows/*.yaml",
            ".gitlab-ci.yml", ".circleci/config.yml", "azure-pipelines.yml",
            ".buildkite/*.yml", "Jenkinsfile", "Makefile", "noxfile.py", "tox.ini",
            "build_tools/*.sh", "scripts/*.sh", "hack/*.sh", ".pre-commit-config.yaml",
            "pyproject.toml", "codecov.yml", ".codecov.yml", "package.json"]


ACTION_RX = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.M)
SHA_RX = re.compile(r"@[0-9a-f]{40}$")


def audit_pins(root):
    """Report GitHub Actions referenced by tag rather than a 40-char SHA.

    A tag is mutable: whoever controls the action can change what your workflow runs.
    Measured baseline: 2,869 of 4,958 external refs across 31 corpus repos (57.9%)
    are SHA-pinned, and the split is bimodal -- 13 repos are >=95% pinned, 8 are <=2%.
    """
    total = pinned = 0
    unpinned = []
    for p in list(root.glob(".github/workflows/*.yml")) + \
             list(root.glob(".github/workflows/*.yaml")) + \
             list(root.glob(".github/actions/*/action.yml")) + \
             list(root.glob(".github/actions/*/action.yaml")):
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for m in ACTION_RX.finditer(text):
            ref = m.group(1).strip().strip('"\'')
            if ref.startswith("./") or ref.startswith("docker://"):
                continue                       # local composite action: no third party
            total += 1
            if SHA_RX.search(ref):
                pinned += 1
            else:
                line = text[:m.start()].count("\n") + 1
                unpinned.append((f"{p.relative_to(root)}:{line}", ref))
    if total == 0:
        print("audit_ci_gates --pins: no external GitHub Actions references found")
        return 0
    pct = 100 * pinned / total
    print(f"action pinning: {pinned}/{total} SHA-pinned ({pct:.1f}%)   "
          f"corpus median cohorts: >=95% (13 repos) vs <=2% (8 repos)")
    for loc, ref in unpinned[:30]:
        print(f"  [unpinned] {loc}  {ref}")
    if len(unpinned) > 30:
        print(f"  ... {len(unpinned)-30} more")
    if unpinned:
        print("\nA tag is mutable. Pin any action used in a workflow that touches "
              "secrets or publishes artifacts.")
    return 1 if unpinned else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--pins", action="store_true",
                    help="audit GitHub Actions SHA-pinning instead of gate advisories")
    a = ap.parse_args()
    root = pathlib.Path(a.path).resolve()
    if a.pins:
        return audit_pins(root)

    files = []
    for g in CI_GLOBS:
        files.extend(p for p in root.glob(g) if p.is_file())
    # disabled workflows are their own finding
    disabled = [p for p in root.glob(".github/workflows/*") if p.is_file()
                and p.suffix not in (".yml", ".yaml")]

    if not files and not disabled:
        print(f"audit_ci_gates: no CI or build config found at {root}")
        return 0

    findings = []
    for p in files:
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        rel = p.relative_to(root)
        for rx, sev, why in ADVISORY:
            for m in rx.finditer(text):
                line = text[:m.start()].count("\n") + 1
                findings.append((sev, f"{rel}:{line}", why,
                                 re.sub(r"\s+", " ", m.group(0))[:80]))
    for p in disabled:
        findings.append(("HIGH", str(p.relative_to(root)),
                         "workflow file is disabled by extension - it does not run", p.name))

    order = {"HIGH": 0, "MEDIUM": 1}
    findings.sort(key=lambda f: order.get(f[0], 2))
    highs = sum(1 for f in findings if f[0] == "HIGH")

    print(f"audit_ci_gates: scanned {len(files)} config file(s) at {root}")
    if not findings:
        print("  no advisory-disguised-as-gate patterns found")
        return 0
    for sev, loc, why, snip in findings[:40]:
        print(f"[{sev:6s}] {loc}\n          {why}\n          > {snip}")
    if len(findings) > 40:
        print(f"  ... {len(findings)-40} more")
    print(f"\n{len(findings)} finding(s), {highs} HIGH.")
    print("Not every hit is a defect: `|| true` on a cleanup step is fine. The question "
          "each raises is whether a CHECK you rely on can actually fail the build.")
    return 1 if highs else 0


if __name__ == "__main__":
    sys.exit(main())
