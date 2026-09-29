# Mobile Verification, Release Safety, and Anti-Bloat: Deep Read

Scope per `research/00-signal-rubric.md` Part D and Part G, and the mobile-specific brief in
`research/worklists/mobile.txt`. This document answers one question the web-focused findings
cannot: **what does a platform with no hotfix require that a web app does not?** Every claim
below is `owner/repo@sha:path`. Absence is recorded as a finding, not silently dropped.

31 repos were deep-read: 11 corpus repos (all that passed the admission gates — see rubric v4)
plus 20 named below-gate supplements. All clones were shallow (`--depth 1 --filter=blob:none`,
or `--shallow-since` for commit-velocity counts on supplements), extracted, and deleted.

**0 of 31 mobile repos have a hard, failing binary-size gate in CI; per-schema-version migration
tests are the most consistent practice found anywhere in the study.**

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [Coverage](#coverage) | why the true corpus is 11 repos, not 30 (the admission-gate definition problem), plus 20 below-gate supplement repos probed and reported honestly against the star/commit thresholds | 76 lines |
| 2 | [The prove-it command, per repo/platform](#the-prove-it-command-per-repoplatform) | the literal command per repo/platform, plus the finding that 7 of 31 repos run real CI on something other than GitHub Actions — a probe reading only `.github/workflows` misjudges a quarter of this corpus | 46 lines |
| 3 | [On-device test strategy: what runs when](#on-device-test-strategy-what-runs-when) | the four recurring patterns for splitting fast host tests from slow device/emulator tests, and why real third-party device farms are rarer than CI presence would suggest | 69 lines |
| 4 | [Release safety: staged rollout, kill switches, crash gates — THE CENTREPIECE](#release-safety-staged-rollout-kill-switches-crash-gates--the-centrepiece) | **the document's own flagged centrepiece**: staged-rollout percentages and kill-switch mechanisms, plus the finding that a hard numeric crash-rate CI gate exists in zero of 31 repos — it's always delegated to the store's own vitals system | 96 lines |
| 5 | [Binary size budgets (verbatim configs)](#binary-size-budgets-verbatim-configs) | headline: nobody enforces a hard byte budget in CI across all 31 repos — measurement tooling is common, a failing gate is not | 47 lines |
| 6 | [Startup and perf regression gates](#startup-and-perf-regression-gates) | the same measured-not-gated pattern for startup/jank regressions: benchmarking tooling exists widely but is kept off the PR-blocking path | 46 lines |
| 7 | [Offline/sync/local-migration correctness](#offlinesynclocal-migration-correctness) | **the study's most consistent finding**: one test file per numbered schema migration, converged on independently by 4 repos, plus the single confirmed gap (ProtonMail, no migration test harness) | 90 lines |
| 8 | [Cross-platform bridge safety and OTA discipline](#cross-platform-bridge-safety-and-ota-discipline) | Expo's and Bluesky's anti-bricking OTA mechanisms (fingerprint gating, rollback-only-before-`CONTENT_APPEARED`) against Flutter/NativeScript/Ionic's structurally different or absent equivalents | 71 lines |
| 9 | [Agent instruction files in mobile repos](#agent-instruction-files-in-mobile-repos) | corrects the brief's own hypothesis — 21 of 31 repos have an AI-agent instruction file, including a mechanically CI-enforced AI-authorship policy (nextcloud/android) and several verbatim human-in-the-loop rules | 96 lines |
| 10 | [Synthesis: three stacks](#synthesis-three-stacks) | minimum-viable vs. strongest-justified practices, split by native Android / native iOS / cross-platform, each tagged to the team size where it starts paying for itself | 87 lines |
| 11 | [What mobile needs that web does not](#what-mobile-needs-that-web-does-not) | seven itemized mobile-specific requirements, each paired with the exact failure mode it prevents — the "so what" summary for a web engineer new to mobile | 47 lines |

---

## Coverage

### Why the corpus is 11, not 30

`research/00-signal-rubric.md` v4 explains this directly: three successive attempts at a
mechanical "is this a mobile repo" rule failed (topic leakage in both directions — `appwrite`
declares `flutter` because it ships an SDK, `react-hook-form` declares `react-native` because it
*supports* it). The final rule is `primaryLanguage ∈ {Swift, Kotlin, Dart, Objective-C}` plus a
5-entry hand-maintained exception list for the canonical cross-platform frameworks. Applied
against the 20k-star / 250-commits-per-year / 24-month-age gates, **11 repos** pass. That
scarcity is reported as a finding about the mobile open-source ecosystem, not papered over.

### Corpus (11) — passed all admission gates

| repo | stars | lang | score | tier | SHA (short) |
|---|--:|---|--:|---|---|
| expo/expo | 52,475 | TypeScript | 12 | T2 | `cfbcecd` |
| NativeScript/NativeScript | 25,653 | TypeScript | 11 | T2 | `a032c22` |
| react/react-native | 126,753 | C++ | 9 | T3 | `efc5161` |
| localsend/localsend | 92,882 | Dart | 9 | T3 | `6f6cd3e` |
| ionic-team/ionic-framework | 52,686 | TypeScript | 9 | T3 | `879e91d` |
| flutter/flutter | 179,133 | Dart | 8 | T3 | `43596b3` |
| onevcat/Kingfisher | 24,404 | Swift | 6 | T3 | `a821446` |
| lysine-dev/okhttp | 47,077 | Kotlin | 5 | T3 | `40a3b87` |
| signalapp/Signal-Android | 29,400 | Kotlin | 5 | T3 | `6151a52` |
| swiftlang/swift | 70,434 | Swift | 4 | T3 | `f82565a` |
| ReVanced/revanced-manager | 29,659 | Kotlin | 4 | T3 | `2a88257` |

Two corpus members need a caveat, stated plainly rather than hidden:
- **`lysine-dev/okhttp`** is not a distinct project. The tree, README, and Maven coordinates
  (`com.squareup.okhttp3:okhttp`) are verbatim `square/okhttp`; the tip commit at clone time was
  authored by `renovate[bot]`. Findings under this name describe square/okhttp's own practice as
  vendored here, not `lysine-dev`'s engineering.
- **`swiftlang/swift`** is the Swift language/compiler toolchain, not a shipped mobile app. It
  has no release-rollout, crash-budget, binary-size, or OTA story by construction — those fields
  are marked N/A rather than absent.

### Supplements (20) — BELOW-GATE, named in the brief, probed for star/commit honesty

These are real production apps with millions of users that fell short of the 20k-star or
250-commit/yr gate. Every row below states the actual numbers found — no repo is presented as
having passed a gate it did not.

| repo | stars | commits/12mo | authors/12mo | note |
|---|--:|--:|--:|---|
| signalapp/Signal-iOS | 12,253 | 3,162 | 30 | |
| mozilla-mobile/firefox-ios | 13,050 | 2,877 | 133 | |
| mozilla-mobile/firefox-android | 1,840 | n/a | n/a | **archived June 2024** — dev moved to Mozilla's internal Mercurial monorepo |
| wordpress-mobile/WordPress-iOS | 3,906 | 821 | 21 | |
| wordpress-mobile/WordPress-Android | 3,153 | 832 | 19 | |
| duckduckgo/iOS → duckduckgo/apple-browsers | 1,949 (old, deprecated) / 257 (successor) | — | — | old repo redirects, no longer accepts contributions since Feb 2025 |
| duckduckgo/Android | 4,835 | 2,637 | 44 | |
| mattermost/mattermost-mobile | 2,728 | 442 | 59 | |
| element-hq/element-android | 3,728 | 148 | 10 | |
| element-hq/element-ios | 1,841 | 161 | 26 | |
| bluesky-social/social-app | 18,311 | 1,832 | 69 | closest to the gate — 18.3k stars |
| home-assistant/iOS | 2,364 | 1,363 | 27 | commit count inflated by Lokalise l10n bot |
| thunderbird/thunderbird-android | 14,048 | 4,482 | 95 | commit count likely inflated by Weblate bot |
| ProtonMail/proton-mail-android | 1,727 | not obtained | not obtained | shallow-since clone failed (git error); not guessed |
| wikimedia/apps-ios-wikipedia → wikimedia/wikipedia-ios | 3,450 | 4,901 | 43 | mandated name 404s; actual repo renamed |
| wikimedia/apps-android-wikipedia | 3,030 | 716 | 14 | |
| owncloud/android | 4,170 | 607 | 20 | |
| nextcloud/android | 5,604 | 4,005 | 36 | |
| Automattic/pocket-casts-android | 2,842 | 1,186 | 24 | |
| Automattic/pocket-casts-ios | 1,825 | 7,160 | 37 | |

`signalapp/Signal-Android` from the mandated supplement list is already in the corpus (it passed
the gates); it is not double-counted.

**Honesty note carried forward from the rubric:** every mobile finding below draws on a thinner
evidentiary base than the JS/TS or Python clusters. Where a supplement is the *only* source for a
practice (e.g. Bluesky's OTA fingerprint gate), that is flagged explicitly rather than presented
as corpus-wide convention.

---

## The prove-it command, per repo/platform

The single command a contributor (or agent) runs to prove a mobile change is good — literal, not
paraphrased.

| repo | prove-it command |
|---|---|
| expo/expo | `et check-packages` (build+typecheck+lint+test via expotools); native: `et native-unit-tests --platform ios\|android` |
| NativeScript/NativeScript | `npx nx run core:test` (unit); `npx nx run apps-automated:ios\|:android` (on-device) |
| ionic-team/ionic-framework | `npm test` = `npm run test.spec && npm run test.e2e` (Stencil + Playwright) |
| react/react-native | `yarn test <path>` (Jest); `yarn fantom <path>` (native integration); `yarn lint --max-warnings 0`; `yarn flow-check` |
| flutter/flutter | not GHA — LUCI via `.ci.yaml` (7,856 lines, 490 targets); `dev/bots/test.dart` per shard |
| localsend/localsend | `fvm flutter analyze && fvm flutter test`; `cargo test --features full && cargo clippy --features full` |
| onevcat/Kingfisher | `bundle exec fastlane tests` (all platforms); `bundle exec fastlane lint` |
| lysine-dev/okhttp (=square/okhttp) | `./gradlew check -PgraalBuild=true -x jvmTest ...`; `./gradlew test allTests -Ptest.java.version=<8\|24\|25>` |
| signalapp/Signal-Android | `./gradlew ciRemote` (PR fast path) / `./gradlew qaRemote` (main/8.x, full lint) |
| swiftlang/swift | `utils/build-script --release-debuginfo`, then `utils/run-test --lit ... <target-dir>` |
| ReVanced/revanced-manager | `./gradlew assembleRelease --no-daemon` — **this is the entire PR gate; no test task exists** |
| signalapp/Signal-iOS | `Scripts/build-and-test.sh` → `xcodebuild ... build test` on simulator |
| mozilla-mobile/firefox-ios | `fxios test` (wraps `xcodebuild build-for-testing -scheme Fennec -target Client`) |
| wordpress-mobile/WordPress-iOS | `xcodebuild ... -testPlan WordPressUnitTests test` — AGENTS.md: "Do not use `swift test`" |
| wordpress-mobile/WordPress-Android | `./gradlew checkstyle`; `./gradlew detekt` |
| duckduckgo/apple-browsers (iOS) | `xcodebuild test -scheme "iOS Browser" ... -test-iterations 3 -retry-tests-on-failure` |
| duckduckgo/Android | `./gradlew spotlessCheck`; `./gradlew jvm_tests -Pddg.di=<AnvilDagger\|Metro>` (run twice, once per DI framework mid-migration) |
| mattermost/mattermost-mobile | `npm run check-test` (= lint && tsc && test) |
| element-hq/element-android | `./gradlew knitCheck ktlintCheck detekt`; `./gradlew unitTestsWithCoverage` |
| element-hq/element-ios | `fastlane test` (2 schemes, slather coverage) |
| bluesky-social/social-app | `pnpm lint && pnpm typecheck && pnpm test`; native: `pnpm lint-native` (swiftlint+ktlint) |
| home-assistant/iOS | `bundle exec fastlane lint`; `bundle exec fastlane test` |
| thunderbird/thunderbird-android | `./gradlew testsOnCi --parallel`; `./gradlew lint spotlessCheck detekt dependencyGuard` |
| ProtonMail/proton-mail-android | GitLab CI: `./gradlew multiModuleDetekt`; `./gradlew -Pci --console=plain allTest` |
| wikimedia/wikipedia-ios | `xcodebuild test -scheme "Wikipedia"` (matrixed across 3 schemes) |
| wikimedia/apps-android-wikipedia | `./gradlew clean ktlint assembleAlphaRelease lintAlphaRelease testAlphaDebugUnitTest --no-daemon` — one line is both the PR gate and the release build |
| owncloud/android | `./gradlew testDebugUnitTest testMdmDebugUnitTest --continue`; `./gradlew :owncloudData:connectedAndroidTest`; `./gradlew detekt` (maxIssues:0) |
| nextcloud/android | `./gradlew check` family; full emulator+server integration via `garm.yml` |
| Automattic/pocket-casts-android | `./gradlew :app:testDebugUnitTest`; `./gradlew :app:connectedDebugAndroidTest`; `./gradlew spotlessCheck` |
| Automattic/pocket-casts-ios | `make build_staging`; `make test_staging`; `make lint_changed` |

**Pattern worth naming:** 7 of 31 repos (flutter, ProtonMail, mattermost, Automattic ×2,
WordPress ×2) run their real CI on something other than GitHub Actions (LUCI, GitLab CI,
Buildkite). A probe that only reads `.github/workflows` — the R3 lesson from
`research/00-signal-rubric.md` — would misjudge nearly a quarter of this corpus as
CI-less.

---

## On-device test strategy: what runs when

The mobile-specific failure mode web does not have: a "full test suite" that requires an
emulator/simulator/device is slow and flaky, so every serious mobile repo makes an explicit,
visible tradeoff about what blocks a PR versus what runs later. Four patterns recur:

**1. Split by layer, not by "all or nothing."** Nearly every repo separates fast host-JVM/host-OS
unit tests (Robolectric, XCTest, JVM) — always on PR — from slower instrumented/device tests,
which are gated more selectively:
- `thunderbird/thunderbird-android@358014f:.github/workflows/build-android.yml` — unit tests
  (Robolectric) run on every PR; **no `connectedAndroidTest` job found anywhere** in the sampled
  workflows. Only build-verification jobs (`assemble`, `checkFossReleaseBadging`).
- `NativeScript/NativeScript@a032c22:AGENTS.md` states outright that its unit layer "cannot
  exercise real native APIs" and mandates a second, on-device suite (`apps/automated`) for
  anything touching native runtime — that suite runs on **every PR**, both platforms
  (`.github/workflows/apps_automated_android.yml`, api-level 35; `apps_automated_ios.yml`, on a
  WarpBuild macOS runner).
- `owncloud/android@a8a55568:.github/workflows/android-instrumented-data-tests.yml` runs Room
  migration instrumented tests on every `pull_request` — no nightly tier at all.

**2. Nightly/scheduled full runs, PR runs are a fast subset.**
- `mozilla-mobile/firefox-ios@1510b181` splits `UnitTest.xctestplan` (every PR) from
  `firefox-ios-ui-tests.yml`, which is **`workflow_dispatch`-only** — a real UI-test pass never
  runs automatically on a PR, only on manual trigger or (implicitly) scheduled jobs.
- `bluesky-social/social-app@0f0f523:.github/workflows/nightly-e2e.yml` — Maestro E2E is
  **nightly-only** (`cron: '0 4 * * *'`, 120-min timeout on `macos-26-xlarge`), explicitly
  excluded from the PR path.
- `duckduckgo/Android@194ca33` splits its E2E fleet into a **blocking full suite** and a
  **non-blocking suite** run separately at night (`e2e-nightly-full-suite.yml` vs
  `e2e-nightly-non-blockers-suite.yml`) — so flaky/slow E2E does not gate every release, but
  still runs continuously.
- `expo/expo@cfbcecd:.github/workflows/test-suite-nightly.yml` (`cron: 0 10 * * SAT`) runs the
  full suite against React Native's nightly build; `fingerprint.yml` runs daily on a 3-OS matrix.
- `wordpress-mobile/WordPress-iOS@514f5b0:.buildkite/nightly.yml` runs an **AI-agent-driven E2E
  suite** ("🤖 AI E2E Tests", 60-min timeout) nightly against a Jetpack build — distinct from the
  human-authored UI tests, itself a novel mobile-specific test-authorship pattern.

**3. Real device farms are rare — most "device" testing is emulator/simulator.** Of 31 repos,
only two use a genuine third-party device lab:
- `ProtonMail/proton-mail-android@7ff6a12:.gitlab-ci.yml` — **three distinct Firebase Test Lab
  jobs** (UI smoke, per-feature, full instrumentation), each with `--num-flaky-test-attempts=1`.
- `duckduckgo/Android@194ca33` — Flank-orchestrated Firebase Test Lab
  (`./gradlew runFlankAndroidTests --no-configuration-cache`).
- `react/react-native@efc5161:.github/workflows/maestro-cloud-rntester.yml` — Maestro Cloud on
  **real hardware** (`device-model: iPhone-17-Pro`, `device-os: iOS-26-2`), but only on PRs
  originating from the repo itself (forks and dependabot excluded — cost control for a paid
  device farm), plus pushes to main.

Everyone else (expo, NativeScript, element-android, owncloud, nextcloud, wikipedia-android,
Signal-Android's benchmark modules) uses GitHub-Actions-hosted emulators/simulators, not a farm.
This is itself a finding: **device-farm adoption in mobile OSS is much rarer than CI presence
would suggest** — running an emulator in CI is cheap; a real-hardware farm is not, and most
projects accept the emulator/simulator gap in coverage rather than pay for it.

**4. Two flake-control patterns worth stealing**, both from `react/react-native@efc5161`:
- A **3-attempt retry ladder where only the final attempt sets `fail-on-error: true`**
  (`test_e2e_android_rntester`, `_retry_1`, `_retry_2`) — earlier attempts are informational.
- **Per-flow state resume**: the job downloads the previous run's `results.json` and skips
  already-passed flows, so a retry only re-runs what actually failed
  (`.github/workflows/test-all.yml:166-190,364-385`).

**Nextcloud's integration matrix deserves separate mention** because it tests something no other
repo in this study does: real client↔server compatibility. `nextcloud/android@67227403:
.github/workflows/garm.yml` boots a Dockerized Nextcloud server across three server versions
(`stable22`, `stable35`, `master`) crossed with a KVM Android emulator, points the app at the
server via `10.0.2.2`, and runs the sync suite against it — on every PR.

---

## Release safety: staged rollout, kill switches, crash gates — THE CENTREPIECE

This is the section the brief calls "the big one," and the evidence justifies that: mobile
cannot hotfix. A bad build is live for days pending app-store review, so every mature repo builds
a release pipeline whose entire purpose is to limit blast radius *before* a bug can be fixed
server-side.

### The sharpest numeric artifacts found

**DuckDuckGo Android's canary is the most conservative rollout percentage found anywhere in the
study:**
```ruby
rollout: '0.000001', # ie. 0.0001%
```
`duckduckgo/Android@194ca33:fastlane/Fastfile:68` — six orders of magnitude smaller than a
typical "10% canary." Paired with `release_blocking_checks.yml`, a reusable workflow that reruns
the full nightly test suite against the exact release commit and **auto-files Asana
release-blocker tasks on failure** (`create_asana_tasks: true` by default).

**WordPress-Android's rollout is a scheduled, Play-vitals-aware ladder:**
```ruby
PRODUCTION_ROLLOUT_INITIAL_FRACTION = '0.10'
PRODUCTION_ROLLOUT_STEPS = [0.25, 0.50, 0.75]  # then 100%
```
`wordpress-mobile/WordPress-Android@58dd61e:fastlane/lanes/promote.rb:64-95`. A scheduled
`advance_production_rollout` lane bumps the percentage Monday–Friday, never on a weekend, and
**reads Google Play's live `TrackRelease.status`** — if Play itself has auto-halted the rollout
(`halted`, triggered by policy or vitals/crash-rate regression) or a human paused it, the job
**refuses to resume it**: "never resumes a rollout a developer paused." WordPress and Jetpack
apps must be in the same rollout state or the job aborts with a mismatch error. This is the
single most complete automated staged-rollout system found in the study.

**Automattic (Pocket Casts) runs the same shape on both platforms, adapted to each store's native
mechanism.** Android: a validated fastlane lane —
```ruby
UI.user_error!('percent parameter must be between 0.0 and 1.0') if percent.to_f.negative? || percent.to_f > 1
```
`Automattic/pocket-casts-android@eeb9d1ce:fastlane/Fastfile:345-365`, triggered by an internal
"ReleasesV2" tool via Buildkite, plus a **dedicated hotfix track**
(`new-hotfix-release.yml`/`finalize-hotfix-release.yml`) distinct from the normal pipeline. iOS
uses Apple's own mechanism directly: `phased_release: true`
(`Automattic/pocket-casts-ios@1311cb71:fastlane/Fastfile:1654`) — Apple's native 7-day
1%→2%→5%→10%→20%→50%→100% ramp, auto-halting on App Store Connect's own crash/rating signals.
Same Buildkite pipeline shape on both platforms: code-freeze → beta → hotfix-or-publish.

`wikimedia/wikipedia-ios@599e4a6:fastlane/Fastfile:127-147` and
`duckduckgo/apple-browsers@ebf6c7c:iOS/fastlane/Fastfile:567` also both set `phased_release:
true` — this is the default "if you do nothing else" iOS mechanism, and three unrelated
supplement repos converge on it independently.

### Kill switches and remote config

**Signal-Android's remote-config system is the deepest kill-switch implementation found:**
`keyvalue/RemoteConfigValues.java` + `util/RemoteConfig.kt` fetch every 2 hours
(`FETCH_INTERVAL = 2.hours`) with an internal QA override screen
(`InternalRemoteConfigScreen.kt`) to flip flags before wide rollout
(`signalapp/Signal-Android@6151a52`). This is the mechanism by which a bad code path gets
disabled *without* a Play Store update — the actual answer to "mobile cannot hotfix."

**Mozilla's Nimbus SDK** is a shared kill-switch/experimentation layer across both
`mozilla-mobile/firefox-ios@1510b181:firefox-ios/nimbus.fml.yaml` and
`mozilla-mobile/firefox-android@fe8a71cd:fenix/app/nimbus.fml.yaml` — one platform, reused across
products, rather than each app inventing its own.

**home-assistant/iOS's TestFlight-gating discipline is process, not infrastructure:** every
beta-gated feature must ship with "a parallel draft PR that removes the gate," so a full public
rollout becomes a one-click merge rather than a code change under time pressure
(`home-assistant/iOS@0d29893:AGENTS.md`).

**expo's rollout mechanism is EAS Update**, built for its cross-platform users, not for the Expo
Go app itself: `eas update --rollout-percentage=10` progresses to 100, with
`eas update:revert-update-rollout` as the rollback lever, and an explicit rule that a rollout
must finish before a new update on the same runtime version can publish, "to prevent accidentally
clobbering the rollout" (`expo/expo@cfbcecd:docs/pages/eas-update/rollouts.mdx`). Notably, the
repo's *own* pre-release safety net has **decayed**: `verify_upload_to_staging` in
`fastlane/Fastfile:263-285` was clearly meant to block a production upload for a version that
hadn't been verified on staging, but the lane body is now just
`UI.message "Skipping staging verification step"` — a real, dated example of a gate rotting in
place, worth citing as a failure mode rather than a success.

### The absence pattern

Across the 31 repos, **staged/phased rollout percentage was ABSENT (defaults to 100% push) in**:
`element-hq/element-android@08dc499` (no rollout arg to `upload_to_play_store`),
`element-hq/element-ios@7ba8beb` (no phased-rollout param on App Store submission),
`mattermost/mattermost-mobile@bc03c18` (track-based alpha/beta, no fractional rollout),
`thunderbird/thunderbird-android@358014f` (track-based internal/beta/production, no
`userFraction`), `owncloud/android@a8a55568` (no Fastfile lanes at all), and
`ProtonMail/proton-mail-android@7ff6a12` (not found in the probed `.gitlab-ci.yml`; publish step
likely lives in an unprobed deploy pipeline). Numeric crash-rate CI gates were **not found as a
hard number in any repo in this study** — the operative gate is consistently *delegated* to the
store's own vitals system (Google Play's `halted` status, Apple's phased-release auto-pause) or
to an external ticketing loop (DuckDuckGo's Asana auto-file), never a repo-local threshold.

---

## Binary size budgets (verbatim configs)

**The headline finding: nobody enforces a hard byte budget in CI.** Across all 31 repos, size is
either *measured and reported* or *documented as unmeasurable in-repo* — never a failing check.

- **Signal-Android has the closest thing to a size gate, and it is advisory only.**
  `.github/workflows/diffuse.yml` builds `assemblePlayProdRelease` for both the PR base and head,
  diffs them with `usefulness/diffuse-action`, and posts the APK size/method-count delta as a
  **PR comment** — no failing threshold (`signalapp/Signal-Android@6151a52`).
- **Flutter measures size exhaustively but gates nothing.** `dev/devicelab/lib/tasks/perf_tests.dart:1703-2200`
  runs `CompileTest`, emitting `release_size_bytes` and per-component breakdowns
  (`app_framework_uncompressed_bytes`, `Flutter.framework` size) across 20 `*__compile` tasks —
  `hello_world_android`, `basic_material_app_{android,ios,macos,win}`, and an
  `imitation_game_flutter` vs `imitation_game_swiftui` comparison. These are dashboard metrics
  (`benchmarkScoreKeys`), and **every one of them is `presubmit: false`**
  (`flutter/flutter@43596b3:.ci.yaml:5210-5230`) — regression detection is dashboard-plus-revert,
  not a failing PR check.
- **Expo's own documentation explicitly declines to set a repo-side number:** "The only truly
  accurate way to see what your final app size will be shipped to users is to upload your app to
  the stores and download it on a physical device"
  (`expo/expo@cfbcecd:docs/pages/distribution/app-size.mdx`), alongside a real SDK 49→50 table
  showing a 66 MB→168 MB APK while the actual Play Store download stayed ~27 MB — a useful
  concrete illustration of why raw APK size is the wrong metric to gate on for a debug-heavy
  build.
- **DuckDuckGo Android has a real gate — but it is a shape check, not a byte budget:**
  `scripts/check_elf_alignment.sh` runs against the built APK
  (`duckduckgo/Android@194ca33:.github/workflows/ci.yml:284-290`), verifying native-library 16KB
  page-size alignment — a real Google Play rejection cause on newer Android, and the only
  APK-shape CI assertion found in the corpus, but it does not bound size.
- **Ionic ships the sharpest anti-bloat check in the group, as a test rather than a budget:**
  `test.treeshake` (`node scripts/treeshaking.js dist/index.js`) and `test.lazy-imports`
  (`node scripts/verify/lazy-imports.js`) assert *structural* size discipline —
  dead code and eager imports fail the build — without ever asserting a byte number
  (`ionic-team/ionic-framework@879e91d:core/package.json`).
- **No hits at all** for `size-limit`/`bundlesize`/`bundlewatch`/equivalent in: NativeScript,
  react-native, localsend, Kingfisher, WordPress (either platform), mattermost, element (either
  platform), bluesky, owncloud, nextcloud, Automattic (either platform), Signal-iOS, home-assistant/iOS.

**Why this matters for the anti-bloat thesis:** mobile is supposed to be the sharpest place to
find size enforcement, because the consequence (download size, install failures, store rejection)
is directly user-visible in a way that a web bundle is not. The finding is the opposite of what
was expected: **measurement is common, enforcement is almost absent.** The closest thing to a
real gate anywhere in the study is DuckDuckGo's ELF-alignment shape check, which polices a
correctness property, not a size number.

---

## Startup and perf regression gates

The same measured-not-gated pattern repeats for startup/jank regressions.

- **Expo has the module but no runner.** `apps/bare-expo/macrobenchmark/src/main/java/.../StartupBenchmark.kt`
  uses `MacrobenchmarkRule`, `StartupTimingMetric`, `StartupMode.COLD`, 5 iterations
  (`expo/expo@cfbcecd`). **No workflow in the 54-file `.github/workflows/` directory invokes it**
  — the benchmark exists, is presumably run by hand, and is not part of CI.
- **Signal-Android has dedicated `baseline-profile/`, `microbenchmark/`, and `benchmark/` Gradle
  modules** (the full androidx.benchmark family) but it was not confirmed whether they run as a
  blocking gate versus manual/nightly invocation (`signalapp/Signal-Android@6151a52`).
- **firefox-android (archived) had the most concrete "startup budget as CI-runnable benchmark"
  pattern found:** a dedicated `fenix/benchmark/` module —
  `BaselineProfilesStartupBenchmark.kt`, `MacroBenchmarkRule.kt`,
  `StartupOnlyBaselineProfileGenerator.kt` — plus a `nightly` build variant with its own baseline
  profiles directory (`mozilla-mobile/firefox-android@fe8a71cd`). It is frozen mid-2024, but the
  pattern is worth taking regardless of the repo's current status.
- **DuckDuckGo Android runs perf benchmarks, but strictly off the hot path:**
  `build-benchmark-nightly.yml` and `nightly-perf-benchmark.yml` are both scheduled, never
  PR-blocking (`duckduckgo/Android@194ca33`).
- **Bluesky has real perf tooling (`flashlight`) but it is a manual/scripted measurement, not a
  gate:** `flashlight test --testCommand "pnpm perf:test" --duration 150000` produces
  `.perf/results.json`, invoked via `pnpm perf:test:measure`, never wired to fail CI
  (`bluesky-social/social-app@0f0f523:package.json`).
- **Flutter has the largest perf corpus in the entire study — ~200 `*_perf__timeline_summary` /
  `*__e2e_summary` devicelab tasks** covering jank and frame timing
  (`android_view_scroll_perf`, `animated_blur_backdrop_filter_perf`,
  `complex_layout_scroll_perf__devtools_memory`) — **every one is `presubmit: false`**
  (`flutter/flutter@43596b3:.ci.yaml`). Regression detection is the same dashboard-plus-revert
  model as size.
- **ABSENT entirely** (no macrobenchmark/baseline-profile/perf-regression artifact found) in:
  NativeScript, ionic, react-native, localsend, Kingfisher, okhttp, WordPress (either platform),
  element (either platform), mattermost, home-assistant/iOS, thunderbird-android, ProtonMail,
  wikipedia (either platform), owncloud, nextcloud, Automattic (either platform).

**The pattern across both size and perf is the same shape:** the tooling to measure regressions
exists in a meaningful fraction of mature mobile repos, but it is consistently kept *off* the PR
critical path — either not wired into any workflow at all, or deliberately scheduled/post-submit.
The working theory these repos have converged on independently is: **device-dependent perf and
size measurements are too noisy or too slow to gate a PR, so they are tracked as trends and acted
on via revert, not blocked at merge time.** This is a legitimate, repeated engineering decision,
not an oversight — but it means "we have a Macrobenchmark module" is not itself evidence of an
enforced budget, and a skill written for this space should say so explicitly.

---

## Offline/sync/local-migration correctness

This is the deepest and most consistent finding in the whole study: **local database schema
migration is the single most-tested mobile-specific failure mode**, far more than release safety
or size. The reason is obvious once stated — a bad migration bricks an app on every device that
already has data, with no way to intervene before the user opens it.

### The strongest convention: one test file per numbered migration

Four independent repos converged on the identical pattern — a dedicated instrumented/unit test
per schema version, named after the migration it covers:

- **`signalapp/Signal-Android@6151a52`** —
  `app/src/test/java/.../database/helpers/migration/V322_NormalizeStickerTableTest.kt`,
  `V287_FixInvalidArchiveStateTest.kt`, `V298_DoNotBackupReleaseNotesTest.kt`,
  `V288_AddQuoteTargetContentTypeColumnTest.kt`, `V324_MoveGroupV1StorageIdsToUnknownIdsTest.kt` —
  the sharpest, most extensive local-DB-migration test discipline found in the entire study.
- **`owncloud/android@a8a55568`** — `MigrationToDB28Test.kt` … `MigrationToDB36Test.kt`
  under `owncloudData/src/androidTest/java/.../roommigrations/`, each exercising a real
  `Migration_NN.kt`.
- **`nextcloud/android@67227403`** — a dedicated `migrations/` package (`MigrationsManager`,
  `MigrationsDb`, `MigrationError`) plus numbered `Migration88to89.kt` … `Migration99to100.kt`,
  each with an instrumented test.
- **`wikimedia/apps-android-wikipedia@12796d0`** — `UpgradeFromPreRoomTest.kt`, a dedicated
  instrumented test verifying correct migration for users upgrading from the pre-Room (raw
  SQLite) schema into Room — precisely the failure class the brief names ("local DB migration
  bugs brick apps").

### Migration correctness as a live-schema-tracking artifact, not just a test

`signalapp/Signal-iOS@06fb42bb:SignalServiceKit/Storage/Database/GRDBSchemaMigrator.swift` +
`.../tests/Storage/Database/GRDBSchemaMigratorTest.swift` runs `migrateDatabase(...)` end-to-end
and extracts the resulting SQL schema; **CI uploads the normalized `schema.json` as a build
artifact on every run**, so schema drift is visible in every PR diff, not just caught by a
pass/fail test.

### A live migration, still in flight, with a safety flag

`home-assistant/iOS@0d29893` is mid-migration from Realm to GRDB in production. The completion
flag has a max-attempt fallback and a dedicated test
(`RealmToGRDBMigrationCompletionTests`) that verifies the flag **only** reports "completed" after
the importer actually finished — protecting the legacy store from deletion mid-migration. This is
the only example in the study of a migration-in-progress caught mid-flight with its own
regression test for the migration's *own* completion-tracking logic, not just the schema change.

### Decoupled migration engines

Two repos separate "migration" from the ORM's own migration mechanism entirely:
- **`element-hq/element-android@08dc499`** — Realm DB with explicit versioned migration classes
  **per store**: `RealmSessionStoreMigration.kt`, `RealmCryptoStoreMigration.kt` (the E2EE key
  store), `AuthRealmMigration.kt`, `GlobalRealmMigration.kt`.
- **`Automattic/pocket-casts-android@eeb9d1ce`** — `VersionMigrationsWorker` +
  `VersionMigrationsWorkerTest.kt` runs app-data migrations as a **WorkManager job**, deliberately
  decoupled from Room's own migration mechanism.
- **`duckduckgo/Android@194ca33`** — a whole family of migration *plugins*
  (`GpcMigrationPlugin.kt`, `LocationPermissionMigrationPlugin.kt`,
  `MigrationLifecycleObserver.kt`) plus numbered Room migrations
  (`WideEventsMigration1To2.kt`, `WideEventsMigration2To3.kt`) — a generalized
  migration-plugin architecture, not one-off ORM callbacks.

### Cross-app migration (the hardest version of this problem)

`wordpress-mobile/WordPress-iOS@514f5b0` migrates users **between** the WordPress and Jetpack
apps' separate local stores, not just between schema versions of one app —
`ContentMigrationCoordinator.swift` + `ContentMigrationCoordinatorTests.swift`,
`JetpackNotificationMigrationService.swift` + test, a root `MIGRATIONS.md` doc. This is Core Data
migration treated as a first-class, independently tested subsystem.

### Sync correctness, not just schema

`mattermost/mattermost-mobile@bc03c18:CLAUDE.md` states a hard rule for its dual-WatermelonDB
sync layer: **"Sync handlers must handle the full lifecycle: create, update, AND delete... Never
write a sync handler that only creates/updates."** — a concrete, named correctness requirement
for the offline-sync failure mode, not just a schema-migration one.

### The negative finding, stated plainly

`ProtonMail/proton-mail-android@7ff6a12:app/build.gradle.kts` and
`AppDatabaseMigrations.kt` implement explicit `androidx.room.migration.Migration` steps — but
**no dedicated `MigrationTest` file was found**. The migrations are hand-written but not
harnessed with Room's `MigrationTestHelper`. Given the strength of the convention everywhere else
in this section, this is a genuine gap, not just an unprobed area — worth citing as a
counter-example in any skill built from this evidence.

**Localsend is the one clean N/A**: a P2P file-transfer app with no server-backed sync or local
DB migration story to test (`localsend/localsend@6f6cd3e`); its own correctness surface is
protocol-level cancellation safety (drop guards), not database migration.

---

## Cross-platform bridge safety and OTA discipline

This section only applies to the 5 cross-platform-framework corpus repos plus the RN/Expo-based
supplements (mattermost-mobile, bluesky). Native-only repos are correctly N/A and are not
re-listed here.

### OTA is where the real no-hotfix engineering concentrates

**Expo has the most complete anti-brick OTA correctness suite found anywhere in the study.**
Maestro e2e flows explicitly named `basic_rollback`, `basic_updateInvalidHash`,
`basic_updateInvalidAssetHash`, `basic_updateOldCommitTime`, `assetRecovery_restoreAssetFiles`,
`errorRecovery_*`, and — the sharpest pair — **`brickingDisabled_runUpdate` /
`brickingDisabled_jsReloadUpdate`**
(`expo/expo@cfbcecd:packages/expo-updates/e2e/fixtures/project_files/maestro/tests/`). The
documented rollback rule is the load-bearing safety property: roll back **only** if the fatal
error arrives *before* `CONTENT_APPEARED`, because "this can be dangerous if your new update has
modified persistent state in a non-backwards compatible way… After this point `expo-updates` will
only fix forward and will not roll back" (`docs/pages/eas-update/error-recovery.mdx`). This is
the correct, hard version of "when is it safe to auto-rollback an OTA update" — after the app has
started mutating local state, it is not.

**Bluesky's OTA gate is fingerprint-based and it is the centerpiece supplement finding of the
whole study.** `.github/workflows/bundle-deploy-eas-update.yml` computes a fingerprint of the
native module surface before every OTA push; if the fingerprint or `package.json` version has
drifted since the last recorded baseline, the pipeline **forces a full native rebuild instead of
an OTA push** — preventing a JS/native ABI mismatch from a hot-reloaded bundle. Production OTA
updates additionally require explicit numeric `iosBuildNumber`/`androidVersionCode` inputs bound
to the specific native build they target, entered manually — "Production OTAs are bound to the
specific native build they target." The fingerprint baseline only advances after **both**
platforms' native builds succeed, recorded as a 90-day GitHub Actions artifact, replacing a prior
`actions/cache` approach that "silently froze" and stopped shipping updates without anyone
noticing (`bluesky-social/social-app@0f0f523`).

**Mattermost-mobile deliberately has no OTA at all**, despite running React Native's New
Architecture (`RCT_NEW_ARCH_ENABLED=1`): no CodePush/EAS Update reference anywhere in the repo —
native-store-only distribution (`mattermost/mattermost-mobile@bc03c18`).

### Codegen and bridge type safety

**React Native's own repo has the strongest bridge-type-safety story, because it is the framework
that generates the bridge every RN app relies on.** JS specs (`Native*.js`,
`*NativeComponent.js`) generate native counterparts at build time, and **CI validates committed
snapshots of every public surface**: `ReactNativeApi.d.ts` (TypeScript API),
`ReactAndroid/api/ReactAndroid.api` (Android ABI), and six C++ snapshots under
`scripts/cxx-api/api-snapshots/`, checked by `yarn cxx-api-validate` in
`validate-cxx-api-snapshots.yml`. The rule is explicit: "Never hand-edit generated output —
change the source and regenerate. CI validates the committed snapshots."
(`react/react-native@efc5161`). This is the same golden-file discipline the web anti-bloat
findings document (`research/23-findings-antibloat-enforcement.md`) recommends for TypeScript
public-API surfaces (`api-extractor`), independently arrived at for a native bridge.

**NativeScript has no codegen at all — bridge safety is a hand-maintained convention, enforced
by review, not by a tool.** Platform-specific files (`foo.ios.ts` / `foo.android.ts`), a shared
`foo-common.ts`, and a **hand-written** `foo.d.ts`, with the explicit rule "keep both platform
files in parity, and update the neighboring `.d.ts` whenever a public API changes"
(`NativeScript/NativeScript@a032c22:AGENTS.md`). This is a real, working bridge-safety pattern for
a smaller team without the resources to build codegen — the mechanical enforcement is simply
absent and the rule relies entirely on human review.

**Flutter has no OTA mechanism at all**, structurally — it is AOT-compiled, so there is no
JS-bundle-over-the-wire layer to update. Its bridge-safety concern is instead the platform-channel
boundary at the Gradle-plugin layer, governed by "The Ratchet Principle"
(`flutter/flutter@43596b3:packages/flutter_tools/gradle/AGENTS.md`) — see the agent-instruction
section below.

**Ionic has no codegen and no OTA**: Capacitor is detected at runtime
(`core/src/utils/native/capacitor.ts`), not generated at build time
(`ionic-team/ionic-framework@879e91d`).

---

## Agent instruction files in mobile repos

The brief hypothesized mobile might be behind web here. **It is not — the finding is the
opposite.** Across the 31 repos deep-read, **21 have some form of AI-agent instruction file**
(AGENTS.md, CLAUDE.md, `.cursor/rules`, or equivalent) — roughly two-thirds, a materially higher
presence rate than a naive prior would predict for a platform assumed to be behind web tooling.

**Present (21):** expo, NativeScript, react-native, localsend, flutter (Gemini-flavored),
Kingfisher, firefox-ios, WordPress-iOS, WordPress-Android, duckduckgo/apple-browsers (iOS),
duckduckgo/Android, mattermost-mobile, bluesky-social/social-app, home-assistant/iOS,
thunderbird-android, wikipedia-ios, apps-android-wikipedia, owncloud/android, nextcloud/android,
pocket-casts-android, pocket-casts-ios.

**Absent, checked at root and standard paths (10):** ionic-framework (the *only* cross-platform
framework in the corpus with nothing), lysine-dev/okhttp (mirror, not a distinct project so
unsurprising), signalapp/Signal-Android, swiftlang/swift, ReVanced/revanced-manager,
signalapp/Signal-iOS, firefox-android (archived mid-2024, predates the convention),
element-hq/element-android, element-hq/element-ios, ProtonMail/proton-mail-android.

### Verbatim excerpts worth harvesting

**A convergent single-source-of-truth pattern**: multiple repos independently made `CLAUDE.md` a
one-line pointer (`@AGENTS.md`) rather than a duplicate — `mozilla-mobile/firefox-ios@1510b181`,
`bluesky-social/social-app@0f0f523`, `nextcloud/android@67227403`,
`Automattic/pocket-casts-android@eeb9d1ce`, `owncloud/android@a8a55568` (byte-identical rather
than a pointer — same effect, different mechanism). This avoids the two-files-drift failure mode
by construction.

**"Run it and prove it, or say you didn't" is the single most repeated mobile-specific
rule**, appearing independently in three unrelated repos:
- `expo/expo@cfbcecd:.claude/CLAUDE.md` — "Passing tests and `et check-packages` are not enough
  for changes that have to be seen running... run the change in `apps/bare-expo` on a simulator or
  emulator before calling it done... If no simulator or emulator is available, or a platform could
  not be run, say so in the Test Plan instead of claiming the change is verified."
- `react/react-native@efc5161:AGENTS.md` — "give the exact commands you ran and their results,
  plus screenshots or a video for user-interface changes. **Say which checks you could not run.**"
- `signalapp/Signal-iOS@06fb42bb:.github/PULL_REQUEST_TEMPLATE.md` — a manual "tested on these
  devices" checklist, mechanically weaker but the same intent.

**Mechanically enforced AI-authorship policy — the strongest D3 artifact in the whole study**:
`nextcloud/android@67227403:.github/workflows/ai-policy.yml` greps PR commit trailers for known
coding-agent identities (Claude, Copilot, Codex, Devin, Cursor, Windsurf, Amazon Q, Gemini Code
Assist, OpenHands, SWE-agent, etc.), auto-labels the PR "AI assisted" if an `Assisted-by:` trailer
is found, and **fails the build (`exit 1`) if an agent appears in `Signed-off-by:`**, because DCO
sign-off "must only be attested by a human contributor." This is a `research/01-skill-contract.md`
`Enforced by: <command>` rule in production, not honor-system prose — a rarity even in the web
corpus.

**Explicit human-in-the-loop policies, stated as hard rules, not aspirations:**
- `home-assistant/iOS@0d29893:AI_POLICY.md` — "Autonomous contributions are not accepted: a human
  must review, understand, and be able to explain every change before it is submitted."
- `localsend/localsend@6f6cd3e:AGENTS.md` — "LocalSend disallows AI generated contributions unless:
  they are bug fixes or very small or you prove your expertise in your field."

**Governance controls, not just style rules** — a rare example of an agent-facing file that
grants or withholds merge authority: `Automattic/pocket-casts-android@eeb9d1ce:
.agents/skills/self-approve-pr/SKILL.md` — "Self-approval is a trust mechanism for small, safe
changes made by engineers who own this platform... The PR author must match [the authenticated gh
user]... user must be a member of the Android team... A web or iOS engineer making a drive-by
Android change is exactly who the human-review rule is for."

**A named architectural doctrine for the highest-risk boundary in a build system:**
`flutter/flutter@43596b3:packages/flutter_tools/gradle/AGENTS.md` — **"The Ratchet Principle":**
"All newly introduced tasks, properties, build logic, and modified lines must strictly comply with
these rules. No Automatic Legacy Refactoring: Pre-existing code that violates target
architectural guidelines... should **not** be automatically refactored within an unrelated PR to
prevent scope explosion, high review burden, and regression risks" — with the explicit
instruction to surface adjacent violations to the user rather than silently fixing or skipping
them. The same file bans a specific unsafe pattern outright: "Never use raw wildcard casts (e.g.,
`as NamedDomainObjectContainer<Any>`) or `@Suppress("UNCHECKED_CAST")`. Unchecked casts conceal
breaking changes across AGP versions."

**Context-budget discipline written *for* the agent, not the human reader:**
`duckduckgo/apple-browsers@ebf6c7c:AGENTS.md` — "This repo-level file is for team-shared
conventions only... **Do not read any other files in `.cursor/rules` unless requested
explicitly**" — an explicit token-budget rule embedded in the instruction file itself.

**Privacy-specific correctness rules for AI-generated telemetry code** (a mobile-and-privacy
combination not seen in the web corpus): `duckduckgo/Android@194ca33:CLAUDE.md` — "No PII. Never
emails, names, account IDs, usernames or phone numbers... No URLs, domains or page titles... No
correlation IDs... Bucket numeric values. Exact durations, byte counts and item counts fingerprint
users; send ranges... Bounded enums over free-form strings." The same repo runs a family of
**AI-agent-authored maintenance automations already live in CI** —
`android-maintenance-worker.md`/`.lock.yml`, `drift-audit.md`/`.lock.yml`,
`workflow-failure-classifier.md`/`.lock.yml` — dependency-drift audits and CI-failure triage run
by agents, not just static instructions consumed by them.

**Skills-as-symlinks, a repeated packaging pattern**: `NativeScript/NativeScript@a032c22` and
`flutter/flutter@43596b3` both make `.claude/skills` a **symlink** to a canonical
`.agent/skills`/external skills directory rather than a duplicate tree.
`home-assistant/iOS@0d29893` goes further: `.cursorrules` and `.windsurfrules` are also symlinks
to `AGENTS.md`, and `.claude/skills -> ../.agents/skills` — one file, four tool-specific access
paths.

---

## Synthesis: three stacks

Per `research/01-skill-contract.md` `## Scale`, every practice below is tagged with the team size
where it starts paying for itself. "Minimum viable" is the floor below which the evidence in this
study says a shipping mobile app is flying blind; "strongest justified" is the ceiling observed in
production, not an aspirational ideal.

### Native Android

**Minimum viable (solo / small-team, 2–10):**
- Unit tests on the JVM (Robolectric where native APIs are touched) as the PR gate — every repo
  in this study that has tests at all has this layer. `Enforced by: ./gradlew test`.
- At least one Room/SQLite migration test per schema version, following the
  `owncloud/android`/`nextcloud/android`/`Signal-Android` convention — this is the single
  highest-value practice found in the entire mobile study relative to its cost. `Enforced by: an
  instrumented test per `Migration_NN`.`
- Lint/static analysis with zero tolerance (`detekt` at `maxIssues: 0`, as in
  `owncloud/android@a8a55568`) — cheap, catches real bugs, no infrastructure cost.
- A remote-config or feature-flag mechanism for anything genuinely risky, even a crude one — this
  is the actual answer to "mobile can't hotfix," and it is available to a two-person team via a
  hosted remote-config service, not just Signal's bespoke system.

**Strongest justified (org, 10+, high blast radius — millions of users):**
- Signal-Android's per-migration-test-file convention, taken to its full extent, plus schema-diff
  tracking as a build artifact (Signal-iOS's `schema.json`, ported to Room's schema export).
- WordPress-Android's scheduled, Play-vitals-aware staged-rollout ladder
  (`10%→25%→50%→75%→100%`, refusing to resume a halted rollout) — this is infrastructure only
  worth building once release volume and blast radius justify automating what a human otherwise
  does manually in the Play Console.
- A dedicated hotfix pipeline, separate from the normal release train (Automattic's
  `new-hotfix-release.yml` pattern) — pays for itself once a single incident-driven release has
  ever collided with an in-flight normal release.
- Device-farm instrumented testing (Firebase Test Lab via Flank, as in `duckduckgo/Android`) —
  genuinely useful, but the cost (money, CI time) only clears the bar once a real device-fragmentation
  bug has actually shipped.
- A mechanically enforced AI-authorship gate (`nextcloud/android`'s `ai-policy.yml`) — worth
  adopting the moment a team is large enough that "who reviewed this" stops being self-evident.

### Native iOS

**Minimum viable:**
- XCTest unit tests on simulator as the PR gate (universal in this study).
- `PrivacyInfo.xcprivacy` per target/extension — Apple requires this for App Store submission as
  of 2024; its **absence** in `Kingfisher` (a widely-used SDK) and `home-assistant/iOS` is a real
  compliance gap, not a stylistic choice, and costs nothing to fix.
- `phased_release: true` in the App Store submission lane — this is Apple's own free 7-stage
  rollout, requires one line of fastlane config, and three unrelated supplements
  (`wikipedia-ios`, `duckduckgo/apple-browsers`, `pocket-casts-ios`) converge on it independently.
  There is no excuse for a solo iOS developer not to enable it.

**Strongest justified:**
- WordPress-iOS's cross-app Core Data migration discipline (`ContentMigrationCoordinator` +
  tests, a root `MIGRATIONS.md`) — only relevant once an org ships more than one app sharing user
  data.
- home-assistant/iOS's live-migration completion-flag pattern (Realm→GRDB, tested for the flag's
  own correctness, not just the schema) — the right template for any org mid-migration between
  local-storage engines in a shipped app.
- UI-test tiering by cadence (firefox-ios's `Smoketest`/`FullFunctionalTestPlan`/manual-dispatch
  split) — worth the workflow complexity once UI-test runtime starts exceeding what a PR can wait
  for.

### React Native / Expo / Flutter (cross-platform)

**Minimum viable:**
- Jest/unit tests at the JS layer plus lint/typecheck, gating every PR (universal).
- A native-fingerprint check before any OTA push, at minimum a manual verification step — Bluesky's
  automated version is the ceiling, but even a documented manual checklist beats nothing, because
  the failure mode (JS/native ABI mismatch from a stale bundle) is silent and catastrophic.
- `phased_release`/staged-rollout on the native store side even for a cross-platform app — the
  OTA layer does not replace native-store release safety, it adds to it; Bluesky and expo both
  still ship through native-store review for anything touching native modules.

**Strongest justified:**
- Expo's full OTA correctness suite — fingerprinting, rollback-only-before-`CONTENT_APPEARED`,
  explicit anti-bricking e2e flows — this is genuinely hard to build and only pays for itself once
  an app has real OTA-dependent users who cannot be asked to reinstall.
- React Native's own codegen + committed-API-snapshot discipline (`cxx-api-validate`,
  `ReactAndroid.api`, `ReactNativeApi.d.ts`) — appropriate for a framework whose bridge every
  downstream app depends on; a single-app team consuming RN does not need to rebuild this, but
  should treat a break in RN's own snapshot validation as a signal to pin versions carefully.
- Flutter's "Ratchet Principle" for the native-plugin boundary — the right doctrine for any team
  maintaining a native bridge that many other teams build on, where an over-eager agent
  "helpfully" refactoring adjacent legacy code is a bigger risk than the change actually
  requested.

---

## What mobile needs that web does not

Itemized, each with the failure mode it exists to prevent (per `research/00-signal-rubric.md`
Part G rule 1 — no cargo-culting without the problem it solves):

1. **A staged/percentage rollout mechanism, because there is no hotfix.** A web deploy is
   reversible in minutes; a mobile release is live for days pending store review. Every mature
   repo in this study builds or borrows a mechanism (Play's `userFraction`, Apple's
   `phased_release`, EAS Update's `rollout-percentage`) specifically to bound the population
   exposed to a bug before it can be pulled. **Failure mode prevented:** a bug reaching 100% of
   users before anyone notices.

2. **A remote-config/feature-flag kill switch independent of the release pipeline.** Signal's
   2-hour-fetch remote config and Mozilla's Nimbus exist because disabling a broken feature must
   not require going through app-store review again. **Failure mode prevented:** being stuck with
   a broken feature live for the days it takes a new build to clear review.

3. **Local database migration testing, per schema version, as a named convention.** Four
   independent repos converged on "one test file per migration." A migration bug on a web
   service is a rollback; a migration bug on a mobile device with the user's only copy of local
   data is data loss with no recovery path. **Failure mode prevented:** bricking or
   data-corrupting an already-installed app on upgrade.

4. **A privacy manifest per build target (`PrivacyInfo.xcprivacy`) — store-mandated, not
   optional.** No web equivalent exists because there is no app-store gate for a website.
   **Failure mode prevented:** App Store rejection, or (as found in Kingfisher and
   home-assistant/iOS) silent non-compliance with a requirement the team may not have noticed
   applies to them.

5. **A native-fingerprint or ABI-compatibility gate before any over-the-air JS bundle push.**
   Web has no analogue to "the client's compiled native code and the server-pushed JS must agree
   on an interface" — a web page and its backend are always deployed together or the browser just
   re-fetches everything. **Failure mode prevented:** shipping a JS bundle that calls a native
   method the installed binary doesn't have, silently crashing every affected user.

6. **Real device/emulator instrumented tests as a distinct, separately-gated tier from unit
   tests.** A web unit test with a mocked DOM is a reasonable proxy for browser behavior; a
   mobile unit test with mocked native APIs (as NativeScript states outright) categorically
   cannot exercise real platform behavior. **Failure mode prevented:** shipping code that passes
   every unit test but crashes on real hardware because of a platform API quirk no mock captures.

7. **A store-review-cycle-aware release cadence (code-freeze → beta → hotfix-or-publish), not a
   continuous-deploy pipeline.** Automattic and WordPress run the identical pipeline shape on both
   platforms because the constraint (review latency, phased rollout, no instant rollback) is the
   same regardless of app. Web CI/CD has nothing structurally equivalent to a code freeze imposed
   by a third party's review queue. **Failure mode prevented:** shipping a release train with no
   coordinated point to pull a bad change before it reaches the store queue.
