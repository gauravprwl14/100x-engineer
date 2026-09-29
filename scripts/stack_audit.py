#!/usr/bin/env python3
"""Report which verification layers a project has, against the measured corpus baseline.

Baselines are adoption rates from research/3x-findings-*.md across the 223-repo
corpus -- not opinion. Absence of a layer is reported with how common that absence
actually is, so a gap can be judged rather than guessed at.

    stack_audit.py [path]
Exit 1 if a layer marked REQUIRED for the detected stack is missing.
"""
import json, re, sys, pathlib, argparse

# (layer, REQUIRED?, detection globs/files, content regex or None, corpus note)
PY = [
 ("formatter",  True,  ["pyproject.toml", "ruff.toml", ".ruff.toml", "setup.cfg"],
  r"\[tool\.ruff|ruff|black", "ruff is the modal formatter+linter in the corpus"),
 ("linter",     True,  ["pyproject.toml", "ruff.toml", ".ruff.toml", ".flake8", "setup.cfg"],
  r"\[tool\.ruff\.lint|\[tool\.ruff|flake8|pylint", "44% of corpus runs ruff and nothing more"),
 ("test runner",True,  ["pyproject.toml", "pytest.ini", "tox.ini", "noxfile.py", "setup.cfg"],
  r"pytest|\[tool\.pytest", "universal in corpus"),
 ("type checker",False,["pyproject.toml", "mypy.ini", ".mypy.ini", "pyrightconfig.json"],
  r"\[tool\.mypy|\[tool\.pyright|mypy|pyright|\bty\b|pyrefly",
  "58% of corpus has NONE; where present it is never advisory -- adopt and gate, or skip"),
 ("coverage gate",False,["pyproject.toml", ".coveragerc", "codecov.yml", ".codecov.yml"],
  r"fail[-_]under|\[tool\.coverage|codecov", "common but often advisory"),
 ("pre-commit", False, [".pre-commit-config.yaml"], None,
  "widely used; 30-hook setups are org-scale accretion, not a starting point"),
 ("lockfile",   True,  ["uv.lock", "poetry.lock", "requirements.txt", "Pipfile.lock",
                        "pdm.lock", "requirements.lock"], None, "uv is the fastest-growing"),
 ("property tests", False, ["pyproject.toml", "requirements.txt", "uv.lock", "poetry.lock"],
  r"hypothesis", "0 of 50 corpus repos use hypothesis -- largest unclaimed gap"),
 ("mutation tests", False, ["pyproject.toml", "requirements.txt", "uv.lock", "poetry.lock"],
  r"mutmut|cosmic-ray", "0 of 50 corpus repos -- the only proof a test can fail"),
 ("dead-code check", False, ["pyproject.toml", "requirements.txt", ".pre-commit-config.yaml"],
  r"vulture|deptry|\bERA\b|F401", "ruff F401/ERA covers most of this for free"),
]
JS = [
 ("typecheck config", True, ["tsconfig.json"], None, "baseline for any TS project"),
 ("strict mode",   True,  ["tsconfig.json"], r'"strict"\s*:\s*true', "the single highest-value flag"),
 ("linter",        True,  [".eslintrc", ".eslintrc.json", ".eslintrc.cjs", "eslint.config.js",
                           "eslint.config.mjs", "eslint.config.ts", "biome.json", "biome.jsonc"],
  None, "eslint or biome"),
 ("test runner",   True,  ["package.json", "vitest.config.ts", "vitest.config.js",
                           "jest.config.js", "jest.config.ts"], r"vitest|jest|mocha|node:test|ava", ""),
 ("e2e",           False, ["playwright.config.ts", "playwright.config.js", "cypress.config.ts",
                           "cypress.config.js"], None, "playwright dominates new adoption"),
 ("lockfile",      True,  ["package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
                           "bun.lock"], None, ""),
 ("dead-code check", False, ["knip.json", "knip.jsonc", ".knip.json", "package.json"],
  r"\bknip\b|ts-prune|depcheck", "knip is the strongest single tool here"),
 ("size budget",   False, [".size-limit.json", ".size-limit.js", "package.json"],
  r"size-limit|bundlewatch|bundlesize", "only meaningful for shipped bundles"),
 ("api surface",   False, ["api-extractor.json", "package.json"],
  r"api-extractor|attw|are-the-types-wrong|publint", "prevents silent public-API widening"),
 ("noUncheckedIndexedAccess", False, ["tsconfig.json"], r"noUncheckedIndexedAccess",
  "rare even in tier-1 repos; catches a real bug class"),
]
GO = [
 ("linter",      True,  [".golangci.yml", ".golangci.yaml", ".golangci.toml"], None,
  "golangci-lint is near-universal"),
 ("tests",       True,  ["go.mod"], None, "check for _test.go files separately"),
 ("race detector", False, ["Makefile", ".github"], r"-race",
  "notably absent even in large corpus repos"),
 ("fuzz targets", False, ["go.mod"], None, "check for func Fuzz* separately"),
 ("banned imports", False, [".golangci.yml", ".golangci.yaml"], r"depguard",
  "traefik and prometheus both ban pkg/errors for stdlib"),
 ("dependency drift gate", False, ["Makefile", ".github", "scripts"], r"go mod tidy",
  "canonical: go mod tidy then fail on a dirty tree"),
 ("codegen drift gate", False, ["Makefile", ".github", "scripts", "hack"],
  r"git diff --exit-code|verify-codegen|verify\.sh",
  "the kubernetes-lineage `make verify` pattern"),
]
UNIVERSAL = [
 ("CI", True, [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile", ".circleci",
               "azure-pipelines.yml", ".buildkite"], None, ""),
 ("CODEOWNERS", False, ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"], None,
  "granularity is a strong maturity signal"),
 ("SECURITY.md", False, ["SECURITY.md", ".github/SECURITY.md"], None,
  "the solo-scale security baseline is this plus dependabot"),
 ("dependency updates", False, [".github/dependabot.yml", ".github/dependabot.yaml",
                                "renovate.json", ".renovaterc.json", ".github/renovate.json"],
  None, ""),
 ("agent instructions", False, ["AGENTS.md", "CLAUDE.md", ".cursorrules", ".rules"], None,
  "48% of active 20k+ star repos have one; AGENTS.md is now canonical"),
]


def present(root, files, rx):
    for f in files:
        p = root / f
        if p.is_dir():
            if any(p.iterdir()):
                if rx is None:
                    return True, f
                for c in p.rglob("*"):
                    if c.is_file():
                        try:
                            if re.search(rx, c.read_text(errors="replace"), re.I):
                                return True, f"{f}/{c.name}"
                        except OSError:
                            pass
            continue
        if p.is_file():
            if rx is None:
                return True, f
            try:
                if re.search(rx, p.read_text(errors="replace"), re.I):
                    return True, f
            except OSError:
                pass
    return False, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--here", action="store_true",
                    help="audit the given path exactly; do not resolve to the git root")
    a = ap.parse_args()
    root = pathlib.Path(a.path).resolve()

    # In a monorepo, config lives at the repo root AND per package. Auditing a
    # subpackage reports false MISS for tsconfig/lockfile/CI, so resolve upward
    # unless the caller insists otherwise.
    if not a.here:
        probe = root
        while probe != probe.parent:
            if (probe / ".git").exists():
                if probe != root:
                    print(f"stack_audit: resolved to git root {probe}\n"
                          f"             (pass --here to audit {root} exactly)")
                root = probe
                break
            probe = probe.parent

    stacks = []
    def has_ext(ext, limit=4000):
        n = 0
        for q in root.rglob(f"*{ext}"):
            if any(part in {".git", "node_modules", ".venv", "venv", "dist", "build"}
                   for part in q.parts):
                continue
            return True
        return False
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists() or has_ext(".py"):
        stacks.append(("Python", PY))
    if (root / "package.json").exists():
        stacks.append(("JavaScript/TypeScript", JS))
    if (root / "go.mod").exists():
        stacks.append(("Go", GO))
    if not stacks:
        print(f"stack_audit: no Python/JS/Go project detected at {root}")
    stacks.append(("Universal", UNIVERSAL))

    missing_required = 0
    for label, layers in stacks:
        print(f"\n=== {label} ===")
        for name, req, files, rx, note in layers:
            ok, where = present(root, files, rx)
            tag = "ok  " if ok else ("MISS" if req else "gap ")
            if not ok and req:
                missing_required += 1
            detail = f"({where})" if ok and where else ""
            print(f"  [{tag}] {name:26s} {detail}")
            if not ok and note:
                print(f"         corpus: {note}")

    # counts that need a filesystem sweep rather than a config file
    if any(s[0] == "Go" for s in stacks):
        fz = len(list(root.rglob("*_test.go")))
        fuzz = sum(1 for p in root.rglob("*_test.go")
                   if re.search(r"^func Fuzz", p.read_text(errors="replace"), re.M))
        print(f"\n  go test files: {fz}   fuzz targets: {fuzz}")

    print(f"\nstack_audit: {missing_required} required layer(s) missing")
    return 1 if missing_required else 0


if __name__ == "__main__":
    sys.exit(main())
