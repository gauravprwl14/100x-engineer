---
name: dependency-vetting
description: >
  Use before running npm install, pnpm add, pip install, uv add, or poetry add for any
  new package, and when reviewing a diff that touches package.json, pyproject.toml,
  requirements.txt, or a lockfile. Validates a package against the npm and PyPI
  registries before it is adopted — deprecation, licence, maintainer count, install
  scripts, typosquatting, transitive tree size — so "trendy" means actively maintained
  and safe to depend on, not merely popular. Not for scanning dependencies already
  installed (see security-baseline) and not for deciding whether you need a dependency
  at all before checking the stdlib (see minimal-diff rule 2, which comes first).
---

# Dependency vetting

"Trendy" is a trap if read as *fashionable*. The worst case this skill exists to catch
is exactly that: a package with a slick README, one maintainer, and no release in 18
months — fashionable and unsafe at once. Read "trendy" as **actively maintained and
safe to depend on**. Popularity (downloads, stars) is corroborating evidence that a
maintained project has users; it is never the criterion that decides adoption.

`research/00-signal-rubric.md` Part A already encodes this distinction for the corpus
this plugin was built from — stars alone admit nothing; recency, contributor count,
licence and release cadence do the actual gating. `scripts/vet_dep.py` is that same
rubric run against a single candidate package instead of a GitHub repo.

## Trigger

**Fire when:** about to run an install command for a new package; reviewing a diff
that adds a line to `package.json`/`pyproject.toml`/`requirements.txt`; auditing an
existing manifest for drift.

**Do not fire when:** bumping an already-vetted dependency's patch version with no
new transitive deps (routine lockfile churn), or when the "dependency" is a first-party
workspace package.

## Check this first

The best vetting outcome is not needing the package. Before running `vet_dep.py`,
`minimal-diff` rule 2 already requires checking the stdlib and the existing dependency
list — `grep` `package.json`/`requirements.txt` for something that already does this,
and check the language's own stdlib (`node:util`, `pathlib`, `datetime`, `itertools`
cover a large share of what gets reached for as a dependency). Only once that check
says "we do need something new" does the rest of this skill apply.

## Rules

1. Check the stdlib and existing dependencies before adding anything new, and state
   what you checked (`minimal-diff` rule 2).
   *Enforced by:* review

2. Vet a new package before installing it; do not install on an `AVOID` verdict.
   *Enforced by:* `python3 scripts/vet_dep.py <pkg> && <install command>` — chained,
   so the install genuinely cannot run past a non-zero exit

3. Never install on a registry that could not be reached. A vetting tool that fails
   open — installs anyway when it cannot check — is worse than no tool.
   *Enforced by:* `scripts/vet_dep.py` exits 2 (non-zero) rather than defaulting to
   a pass when the registry is unreachable

4. Pin the resolved version in a committed lockfile, and give a brand-new release a
   cooldown before adopting it — curl scales its Dependabot cooldown by semver bump
   size (15 days major, 7 minor, 3 patch; `research/35-findings-security-reliability.md`).
   `vet_dep.py` flags any release under 7 days old for exactly this reason.
   *Enforced by:* `test -f package-lock.json -o -f pnpm-lock.yaml -o -f poetry.lock -o -f uv.lock`

5. Read the install-scripts and typosquat-distance lines in the report before
   installing — `postinstall` is arbitrary code execution at install time, not a
   detail to skim past.
   *Enforced by:* `python3 scripts/vet_dep.py <pkg>` reports both for every package

6. Weigh vendoring or hand-writing against the dependency honestly: a 12-line date
   formatter is cheaper to vendor than to depend on; a JSON schema validator or a TLS
   stack is not. "Write it yourself" is a comparison, not a default.
   *Enforced by:* review

7. Periodically check whether an installed dependency is still used, and remove it if
   not — adding a dependency is one line; nobody is assigned to remove it later.
   *Enforced by:* `npx depcheck` / `deptry .` / `npx knip` (per `minimal-diff` rule 2's
   own tool list)

8. In CI, vet the whole manifest, not just the package someone remembered to check by
   hand.
   *Enforced by:* `python3 scripts/vet_dep.py --check-manifest` — exits 1 if any
   direct dependency is `AVOID`

## What "trendy" should mean here

- **Maintained**: a publish in the last 18 months. Older is a flag, not an automatic
  rejection — a finished library (a date formatter, a small parser) is allowed to be
  finished. The question is whether it is finished or abandoned, and that needs a
  human glance at open issues, not just the date.
- **Multi-maintainer**: npm's `maintainers` field is publish-access accounts, not
  GitHub contributors — a project can look "single-maintainer" via the registry API
  while having many code contributors. The signal is real regardless: a single
  publish-access account is exactly the takeover surface that mattered in the
  `ua-parser-js` and `event-stream` compromises (`Added` — both are widely documented
  public incidents, not re-verified from primary sources in this pass).
- **Licensed**: missing or non-permissive blocks. You cannot establish the right to
  use or adapt unlicensed code.
- **Small transitive tree**: reported, not silently accepted — a one-file utility
  that pulls in 40 packages costs more at audit time than the code it replaces saved.
- **Resolvable repository**: a registry entry with no source link cannot be inspected
  before it is trusted.
- Popularity (downloads) is listed last on purpose: it corroborates that a maintained
  project has users. It never substitutes for the other four.

## Supply-chain risks this specifically checks

- **Typosquatting** — the package name is checked by edit distance against a short
  hand-list of well-known names (`scripts/vet_dep.py:POPULAR_NAMES`), the same
  "visible hand-list beats a fetched top-N" choice `research/00-signal-rubric.md` v4
  made for its mobile cluster. `cross-env` vs. the real 2017 `crossenv` typosquat is
  the canonical case (`Added`).
- **Single maintainer** — bus factor and account-takeover risk, flagged `REVIEW`,
  never blocking on its own (too many legitimate, healthy projects show a single
  npm publisher — see the live examples below).
- **Recently transferred package** — not mechanically detectable from a single
  registry snapshot; `vet_dep.py` cannot see ownership history, so this stays a
  human check: read the maintainer list's join dates and the changelog around any
  ownership change.
- **Install scripts** (`preinstall`/`install`/`postinstall`) — reported for every npm
  package, because a `postinstall` hook is exactly how the `ua-parser-js` 2021
  compromise shipped its payload (`Added`).

This is deliberately narrow. SHA-pinning CI actions, SAST, and SECURITY.md are
`security-baseline`'s territory; auditing a cloned repo's own agent config as a
supply-chain surface is `untrusted-agent-config`'s. This skill is the one gate that
sits between "we need a package" and "it's in the lockfile."

## Live examples (verified 2026-09-29 against the real registries)

| package | verdict | why |
|---|---|---|
| `expressjs/express` (npm) | ADOPT | 5 maintainers, MIT, published 2025-12-01 (~10mo old), no install scripts, repo resolves. 28 direct deps reported, not gated — a framework, not a utility. `Verified` |
| `request/request` (npm) | AVOID | registry `deprecated` field set: *"request has been deprecated, see .../issues/3142"*, last publish 2020-02-11. `Verified` |
| `lodash/lodash` (npm) | REVIEW | 1 maintainer in the registry `maintainers` field despite being actively published (2026-04-01) and 193M weekly downloads — the bus-factor flag fires independent of popularity, which is the point. `Verified` |
| `colinhacks/zod` (npm) | REVIEW | also 1 registry maintainer, 341M weekly downloads, MIT, active. Included to show the single-maintainer flag is common even among the most depended-on packages in the ecosystem, not a sign something is unusual. `Verified` |
| `webpack/webpack` (npm) | REVIEW | 8 maintainers, MIT, active — but 10.8 MB unpacked install size, above the 8 MB note threshold. `Verified` |
| `pydantic/pydantic` (pypi) | ADOPT | SPDX `MIT` via `license_expression`, published 2026-08-28, 3 runtime deps, source repo resolves. PyPI exposes no maintainer-role list (`author_email` lists 12 people here — a weaker proxy, reported as such). `Verified` |

## Verify

```bash
# vet one package (~1-2s, two network calls)
python3 scripts/vet_dep.py react
python3 scripts/vet_dep.py --registry pypi pydantic
python3 scripts/vet_dep.py left-pad --json

# vet everything currently in package.json / pyproject.toml (network, one call/dep)
python3 scripts/vet_dep.py --check-manifest

# prove the tool itself still works, no network required (~2s, fixture-backed)
bash tests/test_vet_dep.sh
```

## Failure modes

This skill rejects:

- **Installing a deprecated package because it still resolves.** `request` installs
  fine today; the registry has carried its deprecation notice since 2020.
- **A single-maintainer utility waved through because it's popular.** Popularity and
  bus factor are independent; 341M weekly downloads does not change who can push a
  malicious version.
- **A dependency added for something the stdlib already does** — the check this
  skill defers to `minimal-diff` rule 2, and the one this skill's own "check this
  first" section exists to keep from being skipped.
- **A brand-new release adopted same-day**, with no cooldown — exactly the window a
  compromised point release exploits.
- **A `postinstall` script nobody read.** The report names it; skimming past the
  REVIEW section is a process failure this skill can surface but not prevent.
- **A no-network run that silently "passes."** `vet_dep.py` exits 2 and prints
  "could not reach the registry, cannot vet" — it never defaults to ADOPT.

**Honest limitations:** the typosquat check is a short hand-list plus edit distance,
not a fetched top-10,000 — it catches `crossenv`-shaped names, not novel ones.
Repository "resolvability" is reported as present/absent only; this tool does not
fetch the repo URL to confirm it 200s. PyPI's JSON API has no maintainer-role list,
so the PyPI maintainer count is a weaker proxy (author/maintainer email addresses),
labelled as such in the output rather than presented as npm's real count.

## Scale

`solo`: rules 1, 2, 3 — the network-backed check before every install, at zero
process cost.
`small-team (2-10)`: add rule 8 as a required CI check on manifest changes, and rule
4's lockfile discipline.
`org (10+)`: `--check-manifest` output feeds an intake record (`decisions/`) rather
than living only in a terminal; add an SBOM cross-reference.
`high-blast-radius`: vendor small, security-sensitive utilities rather than
depending on them at all (rule 6), and consider a private registry mirror with its
own cooldown window ahead of curl's public one.

## Sources

- Admission-gate thinking reused rather than reinvented: `research/00-signal-rubric.md`
  Part A (stars/recency/contributors/licence/releases) and Part G anti-goals (no
  advice without a command; no unsourced claims).
- Mobile cluster's "visible hand-list beats a fetched top-N" precedent, applied here
  to the typosquat list: `research/00-signal-rubric.md` v4.
- curl's semver-scaled Dependabot cooldown: `research/35-findings-security-reliability.md`
  (`curl/curl@013c14a:.github/dependabot.yml`).
- Check-stdlib-first, and the dependency-policy tools reused in rule 7:
  `skills/minimal-diff/SKILL.md` rule 2.
- Threat-model framing (third-party config/code as supply chain, not incidental
  risk): `skills/untrusted-agent-config/SKILL.md`.
- CI/scanning/SHA-pinning ownership boundary: `skills/security-baseline/SKILL.md`.
- Registry data quoted in "Live examples": `registry.npmjs.org/express`,
  `registry.npmjs.org/request`, `registry.npmjs.org/lodash`, `registry.npmjs.org/zod`,
  `registry.npmjs.org/webpack`, `pypi.org/pypi/pydantic/json`, and
  `api.npmjs.org/downloads/point/last-week/<pkg>`, fetched 2026-09-29. `Verified`.
- `ua-parser-js` 2021 npm-account compromise, `event-stream` 2018 maintainer
  handoff/compromise, `cross-env`/`crossenv` 2017 typosquat: `Added` — widely
  reported public incidents, not re-verified against a primary advisory in this pass.
- `scripts/vet_dep.py`, its fixture-backed tests, and the tri-state ADOPT/REVIEW/AVOID
  verdict model: `SOURCE: original`.
