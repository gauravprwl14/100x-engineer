---
name: security-baseline
description: >
  Use when setting up or reviewing a project's security posture — SECURITY.md and
  disclosure policy, CI scanning with CodeQL or Semgrep, dependency update policy,
  GitHub Actions SHA-pinning, supply-chain hardening, fuzzing, or authorization
  tests. Also use when a bug or crash is found, to convert it into a permanent
  regression test. Use PROACTIVELY before publishing a repository, adding a
  dependency, or handling a vulnerability report.
---

# Security baseline

What 33 production repos (25 corpus + 8 canonical security cultures: sqlite, curl,
openssl, postgres, redis, envoy, php-src, systemd) actually do — tagged by the scale
at which each practice starts paying for itself.

## Trigger

**Fire when:** publishing a repo; writing or reviewing SECURITY.md; configuring
CodeQL/Semgrep/Dependabot/Renovate; adding CI that touches secrets or publishes
artifacts; handling a vulnerability report; turning a bug into a test.

**Do not fire when:** the change has no external surface and no dependency or CI
impact.

## The cheapest high-leverage practice

**Commit the reproduction as a permanent test.** When a bug, crash, or fuzz finding
appears, save the input that triggers it into the test suite so it is replayed
forever. SQLite and OSS-Fuzz doctrine converge on this independently, and it needs
no fuzzing infrastructure — a human bug report's repro file works exactly like a
fuzzer's crash file.

This is the one practice on this page that is equally correct for a solo project and
for CNCF-tier infrastructure.

## Rules

1. Ship a `SECURITY.md` with a private reporting channel before making a repo
   public. GitHub Security Advisories cost nothing to enable.
   *Enforced by:* `test -f SECURITY.md || test -f .github/SECURITY.md`

2. State your threat model in one paragraph — what is in scope and what is designed
   behaviour. This removes the largest category of false-positive reports ("your tool
   executes code from an untrusted repo" when that is the documented design).
   *Enforced by:* review

3. SHA-pin any GitHub Action in a workflow that touches `secrets:` or publishes
   artifacts. A tag is mutable; whoever owns the action can change what runs.
   *Enforced by:* `python3 scripts/audit_ci_gates.py --pins`

4. Turn every bug and crash repro into a committed test input on the day it is found.
   *Enforced by:* the repro file living in the test suite, replayed by the normal
   test command

5. Enable automated dependency updates, and scale the delay by semver bump size so a
   malicious point release does not land within hours of publication.
   *Enforced by:* `minimumReleaseAge` / cooldown settings in `renovate.json`, or
   Dependabot schedule + grouping

6. Run a SAST suite on your primary language. Start with CodeQL's default queries;
   move to `security-extended` only when you have triage capacity for the volume.
   *Enforced by:* a CodeQL workflow whose job is required, not `continue-on-error`

7. Test authorization with multiple personas, not one. Assert that role A **cannot**
   reach role B's data — a negative assertion, not just a positive one.
   *Enforced by:* per-role test cases in the test suite

8. Route external-effect calls (HTTP client, DB layer) through a single wrapper. This
   is the precondition for fault injection and for auditing egress, and it pays for
   itself in testability regardless of security posture.
   *Enforced by:* review

9. Lint database migrations for unsafe operations instead of writing a policy nobody
   re-reads.
   *Enforced by:* `strong_migrations` or the equivalent for your ORM, in CI

10. Verify your security checks actually gate. A scanner behind
    `continue-on-error: true` is a reporting tool, not a control.
    *Enforced by:* `python3 scripts/audit_ci_gates.py`

## Verify

```bash
# posture snapshot (~1s each)
python3 scripts/stack_audit.py .                    # SECURITY.md, dependabot, CODEOWNERS
python3 scripts/audit_ci_gates.py --pins .          # action SHA-pinning ratio
python3 scripts/audit_ci_gates.py .                 # do the security gates actually gate?
python3 scripts/audit_agent_config.py .             # agent-config supply-chain surface

# dependency vulnerability sweep -- use what your stack has
npm audit --audit-level=high
uv run pip-audit          # or: pip-audit
govulncheck ./...
cargo audit

# secrets that should never have been committed
git log --all --full-history -p | grep -nE '(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)' | head

# bind the security checks to the code being shipped
python3 scripts/verified.py --name audit -- npm audit --audit-level=high
```

## Failure modes

This skill rejects:

- **A public repo with no private reporting channel** — forcing reporters to file a
  public issue, which is a disclosure.
- **Tag-pinned actions in a secrets-bearing workflow.** Measured: 2,869 of 4,958
  external action references across 31 corpus repos are SHA-pinned (57.9%), and the
  distribution is bimodal — 13 repos ≥95% pinned (`oxc`, `biome`, `electron`,
  `valkey`, `appwrite`, `mastodon`, `swc` all at 100%) versus 8 at ≤2%
  (`ClickHouse` 0/534, `discourse` 0/43, `postgres`, `grpc`, `selenium` all 0).
  There is no middle; projects either adopted this or did not.
- **A fixed bug with no regression test.** The fix survives until someone refactors.
- **A scanner that cannot fail the build** (rule 10).
- **Authorization tested only from the happy path** — one admin persona asserting it
  *can* do things, with nothing asserting a lower-privilege persona *cannot*.

**Honest limitations, and one myth to stop repeating:**
- **SQLite's test:source ratio is ~2.5:1 in-repo, not the widely-cited 600:1.** That
  figure counts TH3, a proprietary harness absent from every public mirror, so it is
  not a citable benchmark and not a target you can reproduce.
- **Most of SQLite's culture does not transfer.** Its assertion density and
  branch-coverage discipline reflect a tiny, stable, extremely widely deployed C
  library maintained by a few people for decades. Take the repro-as-test loop
  (rule 4); leave the rest.
- **Multi-persona authz testing is underinvested even in this screened corpus** —
  which means a small team can plausibly do better than the median 20k-star project
  here.
- Envoy's Product Security Team, rotating Fix Lead and Private Distributor List are
  genuine CNCF-scale process and **would sink a small team**. Listed under Scale, not
  as a default.

## Scale

`solo`: rules 1, 4, 5, plus rule 3 only for secrets-bearing workflows.
`small-team (2-10)`: add 2, 6, 8, 9 — the threat-model paragraph and dependency
cooldown are near-free and remove whole categories of noise and risk.
`org (10+)`: add 7, 10, numeric disclosure SLAs (2 business days is a reasonable
floor; 1 day is near the ceiling without a dedicated security team), OSS-Fuzz if you
parse untrusted input in a memory-unsafe language, and a metrics-naming convention
before cardinality bites.
`high-blast-radius`: a formal security team, private distributor list, and
multi-sanitizer fuzzing (address + undefined + memory; MSan catches uninitialized
reads the others miss, and is reasonably run non-blocking while its false-positive
rate is tuned).

## Sources

- All counts, SECURITY.md patterns, scanning configs, the pinning distribution, the
  fuzz-to-regression loop, resilience patterns, and the scale synthesis:
  `research/35-findings-security-reliability.md` (33 repos, per-repo citations).
- Threat-model paragraph pattern: `pnpm/pnpm`, `swc-project/swc`.
- Dependency cooldown scaled by semver bump: `curl/curl`.
- Multi-persona authz tests: `postgres/postgres` named-role pattern.
- Disclosure SLAs: `kestra-io/kestra` (2 business days), `envoyproxy/envoy`
  (1 business day, full PST model).
- Repro-as-permanent-test: `sqlite/sqlite` (`fuzzcheck` + `make fuzztest`),
  `google/oss-fuzz` `ideal_integration.md`.
- Action-pinning audit implementation: `scripts/audit_ci_gates.py --pins`,
  `SOURCE: original`.
