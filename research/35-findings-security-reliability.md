# Security & Reliability Exemplars (D5/D6)

Scope: `research/00-signal-rubric.md` Part D5 (security) and D6 (operations), harvested from
`research/worklists/reliability.txt` (25 repos, admitted specifically for D5/D6 per Part F —
"we take the practice, not the language") plus 8 mandatory supplements. All repos were shallow-
cloned (`--depth 1`, sparse where noted) and read directly; no `gh api` was used. SHAs recorded
below are the commit each citation was read at. Absence is recorded as a finding, per Part G.6.

## Coverage (corpus vs supplements)

**Worklist (25/25 read):** discourse/discourse@3b6713e, nextcloud/server@c41a913, pnpm/pnpm@15a5da5,
clash-verge-rev/clash-verge-rev@0c7e0c8, swc-project/swc@0a69e04, envoyproxy/envoy@72e8b00,
mastodon/mastodon@35c3450, jdx/mise@498466b, kestra-io/kestra@c30e361, oxc-project/oxc@c6edde2,
forem/forem@18d50cb, ggml-org/llama.cpp@f00a64c, tauri-apps/tauri@d15cf9b, astral-sh/uv@877b153,
appwrite/appwrite@3b2a9c9, ClickHouse/ClickHouse@a25168f, astral-sh/ruff@fac9ad2,
valkey-io/valkey@ae819a9, biomejs/biome@af7825f, tursodatabase/turso@ca565db,
electron/electron@d58cb24, coollabsio/coolify@15909fa, block/goose@0193ffc (worklist lists this
as `aaif-goose/goose` — AAIF, "Agentic AI Foundation," is goose's governance body, not the GitHub
org; the repo is `block/goose`), grpc/grpc@9702cf9, SeleniumHQ/selenium@4732af1.

**Mandatory supplements (8/8 read):** sqlite/sqlite@86876d2 (GitHub mirror of the canonical Fossil
repo at sqlite.org/src), curl/curl@013c14a, openssl/openssl@1e36908, systemd/systemd@be1e78e,
php/php-src@24d002d, postgres/postgres@ad36e36, redis/redis@4cb007b, envoyproxy/envoy (already in
worklist — one repo satisfies both), google/oss-fuzz@2cc3fa4.

Depth was allocated by signal, not evenly: the six repos with the worklist's own D5/D6 sub-scores
of 3 (nextcloud, pnpm, envoy, kestra, valkey — see worklist header) plus mastodon, swc, uv,
appwrite, goose (D5+D6 ≥ 4) got full-text SECURITY.md reads, CI-workflow reads and repo-specific
follow-ups. The remaining 15 worklist repos got a fixed, mechanical probe (SECURITY.md presence,
CodeQL/Scorecard workflow presence, action-pinning ratio, Dependabot/Renovate presence) — this is
intentional: at 33 repos, uniform depth would mean no repo gets read closely enough to be useful.
sqlite and oss-fuzz got the deepest read of all, per the task brief's explicit weighting.

---

## SECURITY.md patterns (verbatim, cited)

Every one of the 12 repos checked in the deep tier has a `SECURITY.md`; only **grpc/grpc** among
those checked has one that's a pointer only (see below). Three patterns recur, in ascending order
of maturity:

**1. Pointer-only.** `postgres/postgres@ad36e36:.github/SECURITY.md`, in full:
> "For information about reporting security issues, see
> <https://www.postgresql.org/support/security/>."

Same shape at `astral-sh/uv@877b153:SECURITY.md`, which defers to an org-level policy
(`astral-sh/.github/SECURITY.md`) rather than repeating it. **Cheapest to write, and the most
common pattern below Tier-1 blast radius** — it costs one paragraph and a link, but it also means
the response SLA (if any) lives outside the repo and can't be checked mechanically.

**2. Reporting channel + supported-version table.** `redis/redis@4cb007b:SECURITY.md` is the
clearest example — a version table (8.10.x ✅ … <7.2.x ❌) plus scope caveats:
> "We generally backport security issues to a single previous major version, unless this is not
> possible or feasible with a reasonable effort." … "Vulnerability reports that rely on unsupported
> or uncommon environments (for example, 32-bit architectures, non-Linux operating systems, or
> outdated toolchains) may be considered out of scope."

`mastodon/mastodon@35c3450:SECURITY.md` and `kestra-io/kestra@c30e361:SECURITY.md` follow the same
shape with an explicit acknowledgement SLA — kestra: *"We'll acknowledge new reports within 2
business days"*; envoy (below) goes further with *"initial response within 1 business day."*

**3. Explicit threat model with in/out-of-scope reasoning.** This is the strongest pattern found
and it appears exactly where you'd predict — tools whose entire value proposition is "we don't
sandbox untrusted input, so don't report that as a bug." `pnpm/pnpm@15a5da5:SECURITY.md`:
> "pnpm's security boundary is **filesystem permissions**. We assume that the store directory, the
> project directory, `node_modules`, the lockfile, and pnpm's configuration files are only writable
> by parties the user already trusts. A report that assumes an attacker who already has write
> access to any of these locations is **out of scope**... The content-addressable store is not a
> security boundary against a write-capable local adversary. The integrity hashes recorded for each
> file live inside the store itself... Anyone who can modify a file in the store can also modify its
> recorded hash."

`swc-project/swc@0a69e04:SECURITY.md` states the identical idea for a compiler: *"SWC does not
support processing untrusted input and does not provide isolation, resource containment, or other
sandbox guarantees... If you operate SWC in a service that accepts input from untrusted users or
tenants, you are responsible for validating that input before passing it to SWC."* This pattern is
**the highest-value SECURITY.md content in the corpus** — it prevents the single most common
security-report failure mode (a "vulnerability" that's actually working as designed), and it's
free: no tooling required, just a paragraph naming the trust boundary and one worked example of
what's out of scope.

**The gold-standard full process** is `envoyproxy/envoy@72e8b00:SECURITY.md`, a ~350-line document
covering: a named Product Security Team drawn from `OWNERS.md`; a rotating "Fix Lead" role; a
three-tier disclosure ladder (main-branch-only bugs / point-release bugs / already-public bugs) with
different timelines per tier; and explicit numeric SLOs:
> "All reports to envoy-security@googlegroups.com will be triaged and have an initial response
> within 1 business day." … "Privately disclosed issues will be fixed or publicly disclosed within
> 90 days by the Envoy security team." … "Fuzz bugs are subject to a 90 day disclosure deadline." …
> "Three weeks notice will be provided to private distributors from patch availability until the
> embargo deadline."

It also runs a formal **Private Distributor List** with 10-slot end-user membership, an embargo
policy, and a required blameless retrospective within 1–3 days of every security release (citing
Google's SRE postmortem-culture doc). This is CNCF-project-scale process — see the scale synthesis
at the end for when it's worth copying.

`nextcloud/server@c41a913:SECURITY.md` adds a dimension the others don't: a published **threat
model** (`https://nextcloud.com/security/threat-model`) distinguishing vulnerability from "expected
behavior / accepted risk," plus a supported-version window stated in years (*"Nextcloud Server major
release versions are being supported with security updates for 1 year after their initial
release"*) and a bug-bounty program via HackerOne.

**Notable absence:** `sqlite/sqlite@86876d2` — the repo whose own testing culture is the strongest
in the corpus (see dedicated section below) — has **no `SECURITY.md`, no `.github/` directory at
all, and zero `.yml`/`.yaml` files anywhere in the tree.** The entire disclosure policy is three
sentences in `README.md`: report bugs with security implications by private email to one named
individual. No SLA, no supported-version policy, no CVE process. This is treated at length in the
SQLite section — it is not an oversight, it's what "verification so strong the process becomes
unnecessary" looks like, and it does not generalize.

---

## CI security scanning (configs quoted)

**CodeQL query-suite discipline is the sharpest split found.** `curl/curl@013c14a:.github/workflows/codeql.yml`
explicitly opts into the extended ruleset:
```yaml
- name: 'initialize'
  uses: github/codeql-action/init@db488ddef3bf6cb639b32c2e9a7c0a7ea8271d28 # v4.37.8
  with:
    languages: actions, python
    queries: security-extended
```
`redis/redis@4cb007b:.github/workflows/codeql-analysis.yml`, by contrast, runs the **default query
suite** (no `queries:` key at all) and the action itself is tag-pinned, not SHA-pinned:
```yaml
uses: github/codeql-action/init@v4
uses: github/codeql-action/autobuild@v4
uses: github/codeql-action/analyze@v4
```
`security-extended` adds lower-confidence/higher-recall queries (e.g. broader taint tracking) that
the default suite omits to keep false-positive rates low — using it is a deliberate trade toward
finding more, reviewing more. Of the repos checked for this specifically, only curl explicitly
declares it.

**CodeQL is far from universal even at 20k+ stars.** Only 5 of the 15 lightly-probed worklist repos
have a CodeQL workflow at all (forem, and — from the deeper tier — envoy, redis, valkey, appwrite).
ClickHouse, discourse, oxc, biome, electron, grpc, selenium, ruff, tauri, llama.cpp, turso, coolify,
clash-verge-rev all have **no CodeQL workflow** in `.github/workflows/`. This is a real finding, not
a probe artifact — GitHub Advanced Security is free for public repos, so the omission is a choice
(or an unpriorizited backlog item), not a cost barrier.

**Trivy for container/filesystem scanning**, quoted from `appwrite/appwrite@3b2a9c9:.github/workflows/security-scan.yml`:
```yaml
- name: Run Trivy vulnerability scanner on image
  uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0
  with:
    image-ref: 'appwrite_image:latest'
    format: 'sarif'
    severity: 'CRITICAL,HIGH'
- name: Upload Docker Image Scan Results
  uses: github/codeql-action/upload-sarif@e46ed2cbd01164d986452f91f178727624ae40d7 # v4.35.3
  with:
    sarif_file: 'trivy-image-results.sarif'
    category: 'trivy-image'
```
The pattern worth copying: Trivy scans **both** the built container image and the filesystem
(`scan-type: 'fs'`), and both results land in GitHub's native code-scanning UI via `upload-sarif` —
so a non-CodeQL tool's findings show up in the same PR-blocking surface as CodeQL's.

**OpenSSF Scorecard** appears in 4 of the deeply-read repos: `systemd/systemd@be1e78e:.github/workflows/scorecards.yml`,
`envoyproxy/envoy@72e8b00:.github/workflows/scorecard.yml`, `valkey-io/valkey@ae819a9:.github/workflows/scorecard.yml`,
`block/goose@0193ffc:.github/workflows/scorecard.yml`, and `electron/electron@d58cb24` (only repo
in the 15-repo light tier with one). All four upload SARIF and request `id-token: write` for the
OpenSSF badge. None of the other 20 repos checked run Scorecard in CI — the badge is opt-in and
uncommon even in this corpus. No repo's numeric Scorecard score was directly observable (requires
`gh api` or the deps.dev API, both unavailable this run); presence/absence of the workflow is the
only signal captured.

**Coverity** (closed-source static analysis, free for open source) appears at
`systemd/systemd@be1e78e:.github/workflows/coverity.yml`, `redis/redis@4cb007b:.github/workflows/coverity.yml`,
and `openssl/openssl@1e36908:.github/workflows/static-analysis-on-prem.yml` +
`.github/workflows/static-analysis.yml` — all C/C++ repos, consistent with Coverity's strength
being memory-safety analysis that CodeQL's C/C++ support historically covers less completely.

**Sanitizer builds as CI jobs**, not just fuzzing: `php/php-src@24d002d:.github/workflows/test-suite.yml`
runs a dedicated `ASAN`/`ALPINE_X64_ASAN_DEBUG_ZTS` matrix leg with
`CFLAGS="-fsanitize=undefined,address -fno-sanitize=function -DZEND_TRACK_ARENA_ALLOC"` on every
PR — this catches memory-safety regressions on the normal test path, before any fuzzer runs at all.
`systemd/systemd@be1e78e:.github/workflows/cifuzz.yml` runs a 3-way sanitizer matrix
(`address, undefined, memory`) specifically as short-duration CIFuzz jobs on every PR touching
`src/**` or `test/fuzz/**`.

---

## Supply-chain hardening, incl. action-SHA pinning counts

**The corpus-wide number:** across the 31 repos with at least one GitHub Actions workflow (2 of the
33 — sqlite and postgres's Cirrus-based CI — have none observable in this mirror), **2,869 of 4,958
external `uses:` action references (57.9%) are pinned to a full 40-character commit SHA** rather
than a mutable tag like `@v4`. The distribution is sharply bimodal, not evenly spread:

| Fully or near-fully SHA-pinned (≥95%) | Fully or near-fully tag-pinned (≤5%) |
|---|---|
| oxc-project/oxc — 215/215 (100%) | ClickHouse/ClickHouse — 0/534 (0%) |
| biomejs/biome — 198/198 (100%) | discourse/discourse — 0/43 (0%) |
| electron/electron — 152/152 (100%) | forem/forem — 0/35 (0%) |
| valkey-io/valkey — 153/153 (100%) | grpc/grpc — 0/2 |
| appwrite/appwrite — 110/110 (100%) | php/php-src — 0/34 (0%) |
| mastodon/mastodon — 59/59 (100%) | postgres/postgres — 0/7 |
| swc-project/swc — 121/121 (100%) | SeleniumHQ/selenium — 0/106 (0%) |
| astral-sh/uv — 548/587 (93%) | redis/redis — 1/68 (1%) |
| block/goose — 202/207 (98%) | coollabsio/coolify — 1/81 (1%) |
| nextcloud/server — 173/176 (98%) | tauri-apps/tauri — 2/128 (2%) |
| envoyproxy/envoy — 131/132 (99%) | tursodatabase/turso — 5/367 (1%) |
| jdx/mise — 143/151 (95%) | openssl/openssl — 22/171 (13%) |
| systemd/systemd — 43/49 (88%) | google/oss-fuzz — 0/25 (0%) |

Middling: pnpm/pnpm 189/234 (81%), astral-sh/ruff 131/142 (92%), curl/curl 114/138 (83%),
kestra-io/kestra 77/120 (64%), clash-verge-rev/clash-verge-rev 60/165 (36%), llama.cpp 19/248 (8%).

**This is a real, mechanically-checkable discriminator** — a mutable tag ref like
`@v4` can be repointed by the action author (voluntarily or via a compromised account) to ship
different code under the same version number without the consuming repo's approval; a 40-char SHA
cannot be silently repointed. The rubric asked to "count who pins" specifically because this is one
of the few supply-chain properties checkable with `grep` alone, no API required. The good actors
pair the SHA with a version comment for human readability —
`uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1` (curl, systemd, envoy all
use this exact format) — which Dependabot/Renovate can still parse and bump automatically; SHA-
pinning does not sacrifice update automation, contrary to the common objection.

**Release-artifact signing.** `astral-sh/uv@877b153:.github/workflows/sign-release-binaries.yml`
signs macOS and Windows release binaries with pinned tool versions and checksums, driven by a
`cargo-dist` release plan:
```yaml
- name: "Install uv"
  uses: astral-sh/setup-uv@bec219d24cd3e171d82865faccec33120bb574f4 # v10.1.0
  with:
    # renovate: datasource=github-release-attachments depName=astral-sh/uv
    version: "0.12.13"
    checksum: "745765a3b6e360ad76743599ae5c42e9278c7edf8bbff9fc76d05bf2623a04dd"
```
curl and openssl both PGP-sign release tarballs (documented in their release process pages, not
observable as a workflow file in this mirror). No repo in this corpus was found running
**cosign/sigstore** artifact signing or generating an **SLSA provenance** attestation in an
observable workflow — this is an absence finding across the whole D5/D6 corpus, not just a gap in
one repo. **SBOM generation** was likewise not found as an explicit CI step in any of the 33 repos
(several — nextcloud, envoy — ship container images that plausibly get SBOM'd by downstream distro
packaging, but that step is not in these repositories).

**Reproducible builds / hash-manifest integrity** — the one supply-chain mechanism SQLite does have,
described in the dedicated section below, is notably *not* signature-based: `sqlite/sqlite@86876d2:README.md`
uses a checked-in SHA3-256/SHA1 manifest of every source file, verified by `make verify-source`, with
an explicit caveat that it "detects accidental changes... but malicious changes could be hidden by
also modifying the makefiles" — an honest acknowledgment of the mechanism's limits.

---

## Fuzzing practice and the fuzz-finding-to-regression-test loop

**OSS-Fuzz scale**: `google/oss-fuzz@2cc3fa4` currently integrates **1,381 projects** (1,377 declare
a `main_repo`; 1,203 use libFuzzer, 321 AFL, and 280 `project.yaml` files enable the memory
sanitizer). Of the mandatory supplements, **curl, openssl, systemd, postgres (as `projects/postgresql`),
sqlite (as `projects/sqlite3`), and envoy** are all integrated. **`projects/redis` and
`projects/php-src` do not exist** in OSS-Fuzz (PHP is integrated separately as `projects/php`,
not `php-src`) — redis is a confirmed absence, despite being a 20k+-star, security-sensitive C
codebase with its own in-repo fuzz-adjacent test infrastructure.

**The integration contract is three files**: `project.yaml`, `Dockerfile`, `build.sh` per project.
`google/oss-fuzz@2cc3fa4:projects/sqlite3/project.yaml`:
```yaml
sanitizers: [address, memory, undefined]
fuzzing_engines: [afl, honggfuzz, libfuzzer]
```
`auto_ccs` in `project.yaml` doubles as the access-control list both for embargoed bug notifications
and for corpus download access — `projects/openssl/project.yaml` lists 15 `auto_ccs` including
`openssl-security@openssl.org`, wiring the fuzzer's findings directly into the security team's
inbox rather than a general bug tracker. `projects/systemd/build.sh` is one line —
`tools/oss-fuzz.sh` — meaning the build logic lives in the systemd tree itself rather than in
OSS-Fuzz's mirror, which OSS-Fuzz's own docs call the "ideal integration" end state (build logic
tracked and tested in the project's own CI, not duplicated in a second repo that can drift).

**Seed corpus from existing tests, at zero marginal cost.** `google/oss-fuzz@2cc3fa4:projects/sqlite3/Dockerfile`:
```dockerfile
RUN find $SRC/sqlite3 -name "*.test" | xargs zip $SRC/ossfuzz_seed_corpus.zip
```
This is a generally-applicable pattern independent of SQLite: a project's existing functional test
fixtures are a free, already-maintained fuzz seed corpus.

**Fuzz build hardens invariants ON, not off.** `google/oss-fuzz@2cc3fa4:projects/sqlite3/build.sh`
sets `-DSQLITE_DEBUG=1` in the fuzz build, which turns on SQLite's ~6,600 `assert()` calls — the
fuzzer is therefore checking internal invariants, not merely absence of a segfault. This is the
single highest-leverage, cheapest-to-copy idea in the fuzzing material: **enable your assertions in
the build that gets fuzzed**, regardless of whether they're compiled out of the release build.

**The fuzz-finding → regression-test loop, as OSS-Fuzz itself prescribes.**
`google/oss-fuzz@2cc3fa4:docs/advanced-topics/ideal_integration.md` states the contract directly:
> "The seed corpus should be available in revision control... It should be regularly extended with
> the inputs that (used to) trigger bugs and/or touch new parts of the code." … "Fuzz targets should
> be regularly tested (not necessarily fuzzed!) as a part of the project's regression testing
> process. One way to do so is to link the fuzz target with a simple standalone driver that runs the
> provided inputs, then use this driver with the seed corpus."

The two worked examples that doc cites are **SQLite's own fuzzcheck harness** and
`openssl/fuzz/test-corpus.c`. In SQLite concretely: a crash file found by dbsqlfuzz or OSS-Fuzz is
appended to an **in-tree corpus database** (`test/fuzzdata1.db`...`fuzzdata8.db`, 63 MB total,
committed to the repo) via one command documented in `sqlite/sqlite@86876d2:test/fuzzcheck.c`'s
header comment — `./fuzzcheck database.db --load-sql FILE...` — and from then on it replays on
every `make fuzztest`. **This is the entire loop in one sentence: commit the crash input as a
corpus entry, and make replaying the corpus a normal test-suite target** — no fuzzing
infrastructure is required to adopt this part; a bug reporter's repro file works exactly the same
way as a fuzzer's crash file.

`google/oss-fuzz@2cc3fa4:docs/advanced-topics/corpora.md` adds an important caveat: OSS-Fuzz keeps
its own daily backups of each project's corpus, downloadable via `gcloud storage cp`, but **that
corpus is Google's custody, not the project's** — a project that never commits its own crash inputs
back into its repo has a corpus it does not own and cannot easily replay outside the OSS-Fuzz
infrastructure. SQLite's in-tree `fuzzdata*.db` is exactly the fix for that gap.

**Disclosure SLA**, `google/oss-fuzz@2cc3fa4:docs/getting-started/bug_disclosure_guidelines.md`,
verbatim:
> "After notifying project authors, we will open reported issues to the public in 90 days, or after
> the fix is released (whichever comes earlier)... We have a 14-day grace period."

**Fuzz target counts in the worklist repos** (grep for files matching `fuzz` under a test/fuzz
directory, a mechanical lower bound, not an authoritative count): openssl 38 `fuzz/*.c` targets,
systemd 16 `test/fuzz/fuzz-*.c` targets, curl 0 observable in this sparse checkout (curl's fuzzer
lives in a separate `curl/curl-fuzzer` repo, referenced but not vendored). No fuzz targets were
found in mastodon, nextcloud, kestra, appwrite, or discourse — consistent with fuzzing being a
practice concentrated in parser/protocol-layer C/C++/Rust code, not in Ruby/PHP application
codebases, which is itself the expected shape and not a defect.

---

## Dependency policy

Dependabot and Renovate split roughly evenly across the corpus, with a meaningful minority running
**neither**:

- **Dependabot**: curl, openssl, systemd, redis, envoy, nextcloud, pnpm, kestra, valkey, mastodon
  (via `.github/renovate.json5` — see below, listed correctly there), goose, discourse, forem, electron, grpc.
- **Renovate**: clash-verge-rev, oxc, tauri, ruff, biome, selenium, mise, mastodon, swc.
- **Neither observed**: php-src, postgres, appwrite, llama.cpp, coolify, turso, ClickHouse.

`curl/curl@013c14a:.github/dependabot.yml` shows the more mature grouping/cooldown pattern:
```yaml
- package-ecosystem: 'pip'
  directories:
    - '.github/scripts'
    - 'tests'
  schedule:
    interval: 'monthly'
  cooldown:
    default-days: 7
    semver-major-days: 15
    semver-minor-days: 7
    semver-patch-days: 3
  groups:
    pip-dependencies:
      patterns:
        - '*'
```
The `cooldown` block delays a version bump PR by N days after release — scaled by how disruptive
the bump is (15 days for a major, 3 for a patch) — which absorbs the "day-one supply-chain
takeover" attack shape (a compromised package publishes a malicious point release; most projects'
automated bump PRs would land within hours) at zero developer cost. `redis/redis@4cb007b:.github/dependabot.yml`,
by contrast, is minimal — `github-actions`, weekly, no grouping, no cooldown.

**No repo in the deep-read tier was found requiring explicit human sign-off on new (as opposed to
bumped) dependencies as a distinct CI gate** — the closest observed is CODEOWNERS-gated review of
`.github/dependabot.yml`/`renovate.json` themselves (so changing the *policy* requires review, even
where an individual bump does not). This matches the corpus-wide finding from
`research/23-findings-antibloat-enforcement.md` that dependency-addition review is almost
universally a human-judgment (`CONTRIBUTING.md` prose), not mechanical, gate.

---

## AuthZ test patterns

This is, per the task brief, the area with the fewest visible conventions — and the corpus confirms
it. Two repos have genuinely strong, quotable patterns; most have none observable from outside.

**postgres/postgres@ad36e36** has the deepest authz-specific test suite found in the corpus:
`src/test/regress/sql/rowsecurity.sql` (2,640 lines) and `src/test/regress/sql/privileges.sql`
(2,245 lines) exist *purely* to test row-level-security and privilege-grant behavior. The pattern is
**multi-persona negative testing** — every test file creates several named roles with deliberately
different privilege levels and asserts what each one can and cannot see:
```sql
CREATE USER regress_rls_alice NOLOGIN;
CREATE USER regress_rls_bob NOLOGIN;
CREATE USER regress_rls_carol NOLOGIN;
CREATE USER regress_rls_dave NOLOGIN;
CREATE USER regress_rls_exempt_user BYPASSRLS NOLOGIN;
```
followed by hundreds of assertions of the shape "as alice, this query returns rows X,Y; as bob, the
same query returns nothing." This is directly transferable to any system with row-level or
role-based access control: **write the test as a fixed cast of named personas with different grants,
then assert the *difference* in what each persona can see for the same query/request** — a single
happy-path authz test (does the owner get access) never catches a scoping bug, because scoping bugs
are by definition about the *other* persona.

**redis/redis@4cb007b:tests/unit/acl.tcl** (1,901 lines) tests the ACL system with negative
assertions on error messages, not just allow/deny booleans:
```tcl
test {Usernames can not contain spaces or null characters} {
    catch {r ACL setuser "a a"} err
    set err
} {*Usernames can't contain spaces or null characters*}

test {New users start disabled} {
    r ACL setuser newuser >passwd1
    catch {r AUTH newuser passwd1} err
    set err
} {*WRONGPASS*}
```
The **"new users start disabled"** test is the pattern worth generalizing: it asserts a *secure
default* (a newly created principal has zero access until explicitly granted), which is the
single most common authz bug class in real systems — a new role/user/API key that's accidentally
usable before anyone intended it to be.

**Absence, everywhere else checked.** No dedicated authz test file/suite was found by name pattern
in nextcloud, mastodon, kestra, discourse, appwrite, or envoy within the sparse checkouts performed
(their authz logic is presumably tested inline within feature test suites rather than in a
dedicated permission-test file, which this probe — file-name-based, not full-suite-read — cannot
distinguish from true absence). This matches the task brief's framing: **authz testing is the most
commonly under-tested area in real systems**, and even in a corpus explicitly screened for security
practice, only 2 of 12 deeply-read repos have a *dedicated, named* authz test surface. The pattern
that does exist (postgres, redis) is not exotic — it is "test as multiple named personas with
different grants" and "assert secure-by-default" — and both are mechanically enforceable by any team
regardless of stack.

---

## Observability conventions

The strongest in-repo observability convention found is `kestra-io/kestra@c30e361:docs/architecture/METRICS_GUIDELINES.md`,
a Prometheus/Micrometer naming standard with a one-line thesis:
> "**Every Counter — without exception — MUST end in `.total`.** No Counter ships without it. No
> Gauge, Timer, or DistributionSummary ever uses `.total`. If you take one rule away from this
> document, take this one."

The document defines the metric-type → suffix mapping as a table (Counter → `.total`, Gauge → none,
Timer → `.duration`/unit, DistributionSummary → unit), a strict `<system>.<subject>.<qualifier>`
name ordering rule ("`controller.worker.active`, not `controller.active.worker`... makes related
metrics group together when the registry is sorted alphabetically"), and an explicit **cardinality
rule**:
> "Keep cardinality bounded. Every unique label-value combination is a separate time series. Avoid
> labels that take user-controlled or unbounded values (execution IDs, full URLs, free-form input)."

This is the exact failure mode that takes down Prometheus/metrics-backend clusters in production —
a label with unbounded cardinality (a user ID, a raw URL) silently multiplies time-series count
until the metrics backend falls over — stated as a rule with worked good/bad examples, not just
named as a concern.

`envoyproxy/envoy@72e8b00:docs/root/operations/stats_overview.rst` documents Envoy's stats surface
(exposed via `/stats`, shipped to a statsd cluster) but the naming convention itself lives in the
configuration reference per-subsystem rather than as a single style guide — a weaker pattern than
kestra's dedicated document, though the stats themselves (connection-pool, cluster, listener
counters) are extensively documented per-field.

**No repo in the deep-read tier had an explicit OpenTelemetry adoption document** (trace/span
naming conventions, in particular) discoverable by file search — OTel usage, where present, appears
to live in code (SDK imports, exporter config) rather than in a named convention doc, which this
probe would not surface without a full source read. This is recorded as an absence in the probed
surface, not a claim that none of these repos use OTel.

---

## SLOs and error budgets

**No repo in the corpus has a numeric SLO or error-budget document as a first-class file** (e.g. no
`SLO.md`, no `docs/error-budget.md`) in any of the 33 repos checked. The one place numeric
reliability targets appear in-repo is embedded inside the security-response process, not as a
standalone operational SLO: envoy's disclosure SLOs (1-business-day triage, 90-day fix, 3-week
distributor window — quoted above) and kestra's 2-business-day acknowledgement commitment are the
closest analogues, and both are *security* response-time commitments, not availability/latency SLOs
for the running service. This is consistent with the nature of what's in a public source
repository: **availability SLOs for a hosted service are an operational artifact of the company
running it, not of the open-source project**, so their absence from e.g. discourse, mastodon, or
kestra's *repos* is expected — those numbers live in status pages and internal runbooks that aren't
published to the codebase. This is worth stating plainly as a finding rather than treated as a gap
to be filled by invention: **a repo is not where SLOs live even for projects that clearly have
them.**

---

## Resilience patterns (quoted implementations)

`envoyproxy/envoy@72e8b00` documents its resilience mechanisms more completely, and more concretely,
than any other repo in the corpus, because circuit breaking, retries, and outlier detection are
literally Envoy's product surface rather than an internal implementation detail. Three patterns,
each with real defaults:

**Retry with fully-jittered exponential backoff**, `docs/root/configuration/http/http_filters/router_filter.rst`:
> "By default, Envoy uses a fully jittered exponential back-off algorithm for retries with a default
> base interval of 25ms. Given a base interval B and retry number N, the back-off for the retry is
> in the range [0, (2^N-1)B). For example, given the default interval, the first retry will be
> delayed randomly by 0-24ms, the 2nd by 0-74ms, the 3rd by 0-174ms, and so on. The interval is
> capped at a maximum interval, which defaults to 10 times the base interval (250ms)." … "The route
> timeout... **includes** all retries. Thus if the request timeout is set to 3s, and the first
> request attempt takes 2.7s, the retry (including back-off) has .3s to complete. This is by design
> to avoid an exponential retry/timeout explosion."

The second quote is the non-obvious, transferable rule: **retry budget must be a subset of the
overall request deadline, not additive to it** — a common bug is a retry policy that can multiply
total latency by (attempts × per-attempt timeout) with no outer bound.

**Circuit breaking as a resource limiter, not a state machine**, `docs/root/intro/arch_overview/upstream/circuit_breaking.rst`:
> "It's nearly always better to fail quickly and apply back pressure downstream as soon as
> possible... **Cluster maximum active retries**: the maximum number of retries that can be
> outstanding to all hosts in a cluster at any given time... In general we recommend using retry
> budgets; however, if static circuit breaking is preferred it should aggressively circuit break
> retries. This is so that retries for sporadic failures are allowed, but the overall retry volume
> cannot explode and cause large scale cascading failure."

Note Envoy's circuit breaker is deliberately simpler than the classic Hystrix-style closed →
open → half-open state machine — it's a set of independent connection/request/retry *count* limits
per cluster, which "fails open" (rejects new work) the moment a limit is hit, rather than tracking
failure rate over a rolling window.

**Outlier detection = passive health checking**, `docs/root/intro/arch_overview/upstream/outlier.rst`:
> "Outlier detection and ejection is the process of dynamically determining whether some number of
> hosts in an upstream cluster are performing unlike the others and removing them from the healthy
> load balancing set... Outlier detection is a form of *passive* health checking. Envoy also
> supports *active* health checking. *Passive* and *active* health checking can be enabled together
> or independently."

The active/passive distinction is the transferable idea for teams without a service mesh: **active
health checks cost the caller nothing extra to implement (poll a `/health` endpoint), but only
passive/outlier-based detection catches a backend that's healthy on `/health` but failing on real
traffic** — the two need to be run together, not treated as redundant.

**DB migration safety enforced mechanically at CI time**: `mastodon/mastodon@35c3450:Gemfile` pulls
in `gem 'strong_migrations'`, a static analyzer that fails CI on a specific list of unsafe Rails
migration patterns (adding a column with a non-null default on a large table without a backfill
step, renaming a column/table in a way that breaks in-flight deploys, adding an index without
`algorithm: :concurrently`, etc.) — this is the single most directly copyable zero-downtime-migration
enforcement mechanism found in the corpus, because it requires no process discipline, only a gem in
the Gemfile.

**Timeout/retry patterns not otherwise itemized in-repo**: no explicit "default HTTP client timeout"
convention document was found in mastodon, nextcloud, kestra, appwrite, or discourse — where these
exist they're presumably per-call-site configuration rather than a documented org-wide default,
which (as with the observability finding above) this file-search-based probe cannot distinguish
from true absence without a full source read.

---

## Release, rollback, and migration safety

**Envoy's stable-release branching model** (`envoyproxy/envoy@72e8b00:SECURITY.md`, referencing
`RELEASES.md`): security fixes get a point release created for **each currently supported minor
version** simultaneously, cherry-picked from the fix branch, with an explicit rule against editing
commits mid-cherry-pick ("Changes shouldn't be made to the commits even for a typo in the CHANGELOG
as this will change the git sha of the commits leading to confusion").

**Redis's supported-version + license-carveout mechanism** is a release-discipline pattern not seen
elsewhere in the corpus: `redis/redis@4cb007b:SECURITY.md` — *"For security vulnerability patches
released under Redis Open Source 7.4 and thereafter, Redis permits users of earlier versions (7.2
and prior) to access patches under the BSD3 license... instead of the full license requirements...
Security fixes are tested only against the specific versions for which they are provided.
Applicability or portability to other versions or forks has not been evaluated."* This is an
explicit, written refusal to promise backport correctness beyond the tested version — a useful
pattern for any project maintaining multiple release lines under different licenses/support tiers.

**Migration expand/contract discipline**: beyond mastodon's `strong_migrations` gem (above), no
repo in the deep-read tier had an explicit written expand/contract policy document (e.g. "always add
a column in one release, backfill in the next, drop the old column in a third"). The enforcement
found is entirely mechanical-linter-based (strong_migrations catches specific unsafe patterns) rather
than process-documented — which is arguably the stronger form (Part G.2: "no advice without a
command"), but it means the *policy* isn't independently discoverable without reading the linter's
rule list.

**Feature flags / progressive rollout**: not directly observable as a named subsystem in any of the
sparse checkouts performed (feature-flag systems are typically application code, not something
visible in a `.github`/`docs`/`SECURITY.md`-scoped probe) — recorded as an absence in the probed
surface rather than a claim.

**Canary/progressive delivery**: envoy's own product is a common substrate for canary analysis
(weighted cluster routing, `docs/root/intro/arch_overview/upstream/circuit_breaking.rst`'s
neighboring load-balancing docs) but Envoy's own release process does not itself use canary
deployment of Envoy — it uses the point-release-per-supported-branch model above.

---

## SQLite's testing culture: what transfers and what does not

SQLite (`sqlite/sqlite@86876d2`, GitHub mirror of the canonical Fossil repo at `sqlite.org/src`) is
the strongest verification culture in this corpus, and arguably in open source generally — but its
famous claims need separating from what this repo actually shows, because the two don't fully
match.

**Assertion density (measured directly, not the marketing number):** `src/*.c` totals 208,697
lines with **6,631 `assert()` call sites — one assertion per 31.5 lines of C**, concentrated far
more densely in the hottest subsystems: `src/vdbe.c` (the bytecode VM) has one assert per 13.5
lines; `src/btree.c` one per 15.8. Two coverage-instrumentation macro families exist alongside
plain asserts: `testcase()` (919 sites) exists purely to make a branch statistically countable for
MC/DC coverage tooling, and `ALWAYS()`/`NEVER()` (191 + 143 sites) mark branches the *compiler*
can't prove unreachable, so coverage tooling doesn't flag them as untested misses. `AGENTS.md`
states the convention directly: *"Assert liberally for invariants that must hold in correct code."*

**The famous test:source ratio does not check out as commonly quoted.** In-tree, `test/*.test` (Tcl
test scripts) totals 487,843 lines against 208,697 lines of `src/*.c` — a ratio of **~2.5:1**, not
the widely repeated "600:1" or "1000x" figure. That number counts **TH3**, SQLite's proprietary,
commercially-licensed test harness, which is entirely absent from this (or any public) repo — the
only occurrence of the string "TH3" anywhere in the tree is an unrelated mention in a doc file.
**Any team citing SQLite's test ratio as a benchmark is citing a number for a harness it cannot
inspect and, for most, cannot buy.** The honestly-citable, verifiable number is 2.5:1.

**Fault injection is the actual jewel, not the assert count.** `test/malloc_common.tcl` defines a
10-class fault matrix (OOM, I/O error, shared-memory error, can't-open, disk-full, interrupt — each
as transient/persistent variants), and `do_faultsim_test` **defaults to running the test body under
every fault class simultaneously**, iterating the injection point through the whole call sequence.
This appears at 299 call sites across the test suite, so one authored test effectively expands into
roughly nine fault-class variants × N injection points. This is what actually proves SQLite's claim
of "every error path unwinds cleanly" — not the assert count. **It's affordable specifically because
all memory allocation goes through one function (`sqlite3Malloc`) and all I/O through one VFS
abstraction** — a single chokepoint per fallible external effect is what makes fault injection a
~200-line harness instead of a per-call-site retrofit. This architectural precondition, not the
testing technique itself, is the thing to copy: **route every fallible external effect (HTTP calls,
disk writes, DB queries) through one seam in your own codebase, and the fault-injection harness
becomes cheap regardless of stack.**

**One blessed pre-commit command, with an honestly-scoped claim.** `main.mk:1868`:
```make
# This is the testing target preferred by the core SQLite developers.
# It runs tests under a standard configuration, regardless of how
# ./configure was run.  The devs run "make devtest" prior to each
# check-in, at a minimum.  Probably other tests too, but at least this
# one.
devtest: srctree-check sourcetest
	$(TCLSH_CMD) $(TOP)/test/testrunner.tcl mdevtest $(TSTRNNR_OPTS)
```
Two things worth copying beyond the command itself: it depends on `srctree-check` (a generated-file
drift check) as a **prerequisite**, not an afterthought, and the comment is honest about its own
limits ("Probably other tests too, but at least this one") rather than overclaiming completeness.

**Security process is the deliberate anti-model.** SQLite has no `SECURITY.md`, no CI security
scanning, no signing, no CVE process — the entire policy is one sentence naming one person's email.
This is not an oversight: it works *because* the project has zero third-party dependencies (nothing
to scan), ships as source the user compiles themselves, and the verification culture above makes
the vulnerability rate near-zero. **Every other project in this corpus has the inverse shape — many
dependencies, weaker verification — and needs the process SQLite skips.** Reading "SQLite doesn't
run CodeQL" as permission to skip it elsewhere is exactly the cargo-culting Part G.1 warns against.

**What transfers, by scale (see also the synthesis below):**
| Practice | Transfers to | Cost |
|---|---|---|
| Commit crash/bug-repro inputs as a permanent regression corpus, replayed in the normal test target | solo and up | hours |
| Seed a fuzz/regression corpus from existing test fixtures (`find *.test \| zip`) | solo | minutes |
| Route every fallible external effect through one seam → cheap fault injection | small-team up | the architectural discipline, not the harness, is the cost |
| Turn assertions ON in the fuzzed/CI build, not just debug builds | solo | one build flag |
| One documented, honestly-scoped pre-commit command | solo | an afternoon |

**What does not transfer:** the assertion density itself (a function of a frozen, 25-year,
single-author-designed C API surface — a product that pivots quarterly pays this as churn, not
safety); the 600:1 ratio (unverifiable, proprietary); MC/DC/100%-branch-coverage claims (rest on
`testcase()`/`ALWAYS`/`NEVER` annotation threaded through by the original authors — a multi-year
retrofit on an existing codebase); 58 build-configuration permutations (`test/permutations.test`,
sane only for a single-file C artifact with compile-time feature flags, combinatorially unworkable
against infrastructure a normal team doesn't control); and the absent security process, for the
reasons above.

---

## Synthesis: security baseline by scale (solo / small-team / org / high-blast-radius)

**Solo / hobby project with external users:**
- A `SECURITY.md` with, at minimum, a private reporting channel (GitHub Security Advisories cost
  nothing to enable) — the pointer-only pattern (postgres, uv) is sufficient at this scale.
- Dependabot on `github-actions` + your package ecosystem, no grouping needed yet.
- SHA-pin your GitHub Actions if the workflow has `secrets:` access or publishes artifacts; tag-
  pinning is an acceptable risk for a read-only CI job with no privileges.
- Commit crash/bug-repro inputs into your test suite the moment the first one happens (SQLite's
  cheapest, highest-leverage practice, and it costs nothing to start).

**Small team (2–10):**
- Add the explicit threat-model paragraph to `SECURITY.md` (pnpm/swc pattern) — cheap, and it
  eliminates the most common false-positive report category ("your tool executes code from an
  untrusted repo" when that's the documented design).
- CodeQL default suite on your primary language; `security-extended` once false-positive triage
  capacity exists to handle the extra volume.
- Renovate/Dependabot with cooldown days scaled by semver bump size (curl's pattern) — absorbs the
  "malicious point release lands within hours" attack shape for near-zero effort.
- Route your one or two most-used external-effect calls (HTTP client, DB layer) through a
  single wrapper — this is the precondition for cheap fault injection later, and it pays for itself
  in testability regardless of security posture.
- If you run Rails/Django-style migrations: adopt a static migration-safety linter
  (`strong_migrations` or equivalent) rather than a written policy nobody re-reads.

**Org (10+, multiple maintainers, sustained external adoption):**
- Full disclosure-SLA SECURITY.md with numeric response times (kestra's 2-business-day
  acknowledgement is a reasonable floor; envoy's 1-business-day is close to the ceiling of what's
  sustainable without a dedicated security team).
- OSS-Fuzz integration if you have any parser/protocol/format-handling surface in a memory-unsafe
  language — the three-file contract (`project.yaml`/`Dockerfile`/`build.sh`) is genuinely cheap
  relative to the bug classes it catches, and seeding the corpus from existing tests means there's
  no separate corpus-maintenance burden to start.
- Multi-persona authz tests (postgres's named-role pattern) for any RBAC/RLS surface — this is
  underinvested even in this screened corpus, so it is a place a smaller org can plausibly do better
  than the median 20k-star project.
- A metrics-naming convention document (kestra's `.total`-suffix rule is a good template) before
  cardinality problems appear in production, not after.

**High-blast-radius (CNCF-tier infrastructure, browser/OS-adjacent, or anything a large number of
downstream systems build on):**
- Envoy's full Product Security Team + rotating Fix Lead + Private Distributor List model — this is
  genuinely CNCF-scale process (dozens of named organizations, a 10-slot end-user allowance, yearly
  membership review) and would sink a small team; it exists because Envoy sits underneath other
  people's production traffic and a silent fix isn't an option.
- Fuzz target sanitizer coverage across address/undefined/memory, not just address — MSan in
  particular catches uninitialized-read bugs the others miss, and openssl marks it
  `experimental: true` (non-blocking) rather than skipping it, which is the right middle ground
  when MSan's false-positive rate on a large C codebase is still being tuned.
- Cherry-pick-without-commit-edit discipline across every supported release branch simultaneously
  (envoy's rule) — SHA-identity of a security-fix commit matters when downstream vendors are
  tracking specific commits, not just version tags.
- Signed release artifacts (uv's binary-signing workflow is the closest observed example of this in
  the corpus) — absent almost everywhere else checked, and the one supply-chain control this
  research found the fewest examples of despite it being explicitly asked for.

**What does not scale down, regardless of ambition:** SQLite's assertion density and 58-way build
permutation matrix (frozen, dependency-free, single-designed C core — a precondition, not a
technique); Envoy's full security org (a part-time volunteer team cannot staff a rotating Fix Lead);
and TH3-style proprietary/paid test harnesses (unverifiable and, for most teams, unbuyable). The
practices that *do* scale down to solo — commit-the-crash-input, one wrapper seam per external
effect, an honestly-scoped pre-commit command — are the ones worth actually adopting; the rest is
what "high-blast-radius" is tagged for.
