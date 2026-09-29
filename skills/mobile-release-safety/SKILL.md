---
name: mobile-release-safety
description: >
  Use when building, testing, or shipping mobile apps — native Android/iOS, React
  Native, Expo, or Flutter. Covers on-device test strategy, staged rollout and kill
  switches, local database migration testing, binary size budgets, and OTA update
  safety. Use PROACTIVELY before any mobile release, when changing a local DB
  schema, when adding an OTA/CodePush/EAS update, or when a mobile change touches
  the JS-to-native boundary.
---

# Mobile release safety

Mobile has one failure mode the web does not: **you cannot hotfix.** A bad build is
live for days behind store review, on devices you do not control, for users who may
never update. Every rule here follows from that.

Measured across 31 mobile repos (11 corpus + 20 named production apps including
Signal, Firefox, WordPress, DuckDuckGo, Bluesky, Nextcloud, Wikipedia).

## Trigger

**Fire when:** shipping a mobile release; changing a local DB schema or migration;
pushing an OTA update; touching the JS-native bridge; setting up mobile CI.

**Do not fire when:** changing only a web target in a cross-platform monorepo, or
editing docs/config with no shipped binary impact.

## Rules

1. Test every local DB migration against every prior schema version. One test file
   per version. A migration bug bricks the app with the user's data trapped inside,
   and no server-side fix reaches it.
   *Enforced by:* the per-version migration test suite in your test runner —
   `./gradlew test` / `xcodebuild test`

2. Never ship to 100% at once. Use a staged rollout and let store vitals halt it.
   *Enforced by:* `phased_release: true` in fastlane deliver (iOS — one line, free);
   a staged `rollout:` fraction in Play publishing (Android)

3. Treat a halted rollout as halted. Automation that resumes a rollout a human or
   the store paused defeats the entire mechanism.
   *Enforced by:* review

4. Before any OTA/EAS/CodePush push, fingerprint the native boundary. If native code
   changed, an OTA is invalid — ship a full build instead. A JS bundle against
   mismatched native modules crashes on launch.
   *Enforced by:*
   `find android ios -type f \( -name '*.gradle' -o -name '*.gradle.kts' -o -name 'Podfile.lock' -o -name '*.podspec' -o -name 'AndroidManifest.xml' \) 2>/dev/null | sort | xargs shasum | shasum`
   — compare against the value recorded for the currently-deployed bundle

5. Only auto-rollback an OTA update if the fatal error occurred *before* the app
   rendered content. After that point, state may already be mutated and reverting
   can corrupt it.
   *Enforced by:* review

6. Ship a remote kill switch for any risky feature, and verify it works before you
   need it. A flag you have never exercised is not a kill switch.
   *Enforced by:* an integration test that toggles the flag and asserts the feature
   goes dark

7. Measure binary size every build and fail on a budget you choose. Size is
   user-visible on mobile: download cost, install failures, uninstalls.
   *Enforced by:* a CI assertion on APK/IPA bytes — note that **0 of 31 repos
   surveyed have one**, so there is no industry default to copy; pick a number and
   ratchet it

8. Run fast unit tests (JVM/Robolectric, XCTest on simulator) on every PR; keep slow
   instrumented/device tests to a nightly or pre-release suite. A 40-minute PR gate
   gets bypassed.
   *Enforced by:* `./gradlew test` on PR, `./gradlew connectedAndroidTest` nightly

9. Declare privacy/permission manifests per target and keep them current — a store
   rejection is a shipping outage.
   *Enforced by:* `PrivacyInfo.xcprivacy` present per iOS target; Play data-safety
   declaration reviewed at release

## Verify

```bash
# --- Android ---
./gradlew lint test                       # fast, PR gate
./gradlew connectedDebugAndroidTest       # instrumented; nightly/pre-release
./gradlew :app:assembleRelease && ls -l app/build/outputs/apk/release/*.apk

# --- iOS ---
xcodebuild test -scheme <Scheme> -destination 'platform=iOS Simulator,name=iPhone 16'
bundle exec fastlane scan                 # if fastlane is configured
ls -l build/*.ipa

# --- React Native / Expo: native-boundary fingerprint before any OTA ---
find android ios -type f \( -name '*.gradle' -o -name '*.gradle.kts' \
  -o -name 'Podfile.lock' -o -name '*.podspec' -o -name 'AndroidManifest.xml' \) \
  2>/dev/null | sort | xargs shasum | shasum
# differs from the deployed bundle's recorded value => full build, NOT an OTA

# --- what this project is missing vs the corpus ---
python3 scripts/stack_audit.py .
python3 scripts/audit_ci_gates.py .       # mobile CI is where advisory gates hide

# --- bind the release checks to the exact code being shipped ---
python3 scripts/verified.py --name mobile-test -- ./gradlew test
```

## Failure modes

This skill rejects:

- **A schema change with no migration test for the previous version.** Per-version
  migration tests are the single most consistent practice found across the 31 repos
  — more consistent than release safety itself.
- **An OTA push after native code changed.** `bluesky-social/social-app` computes a
  native fingerprint and forces a full rebuild on drift; this was the sharpest
  cross-platform finding in the study.
- **A 100% release with no staged rollout**, when `phased_release: true` costs one
  line.
- **Automation that resumes a halted rollout.** `wordpress-mobile/WordPress-Android`
  runs the most complete ladder found (10→25→50→75→100) and explicitly refuses to
  resume a rollout Play or a human halted.
- **A size regression nobody notices** — universally measured, essentially never
  enforced, so it silently accumulates.
- **An untested kill switch.**

**Honest limitations:**
- **No repo enforces a numeric crash-rate gate directly.** All 31 delegate to store
  vitals (Play `halted`, Apple phased-release auto-pause). If you want a numeric
  crash budget you are building something the industry has not standardised.
- **Startup/perf budgets are measured, not enforced**, in essentially every repo.
- Mobile agent-instruction-file adoption lags web; there is less prior art to copy
  for AI-assisted mobile work than for backend or frontend.

## Scale

`solo`: rules 1, 2, 8 — a migration test and `phased_release: true` are near-free
and prevent the two unrecoverable failures.
`small-team (2-10)`: add 4, 6, 7.
`org` / `high-blast-radius`: add 3, 5, 9 and a vitals-aware automated ladder.
`DuckDuckGo` Android's initial canary is `0.0001%` — six orders of magnitude below a
typical 10% canary. That is an org-scale choice justified by blast radius, not a
default.

## Sources

- All 31 repos, the release-safety playbook, and the three per-platform stacks:
  `research/33-findings-mobile-verification.md`.
- `bluesky-social/social-app` — native-module fingerprint forcing full rebuild (rule 4).
- `expo/expo` `expo-updates` — the `CONTENT_APPEARED` anti-brick rule (rule 5).
- `wordpress-mobile/WordPress-Android` — vitals-aware staged ladder (rules 2, 3).
- `signalapp/Signal-Android`, `owncloud/android`, `nextcloud/android`,
  `wikimedia/apps-android-wikipedia` — per-schema-version migration tests (rule 1).
- `duckduckgo/Android` — 0.0001% canary and auto-filed release blockers.
- `wordpress-mobile/WordPress-iOS`, `home-assistant/iOS` — Core Data migration
  discipline and live-migration completion flags.
- The native-boundary fingerprint command in Verify: `SOURCE: original` — a portable
  equivalent of Bluesky's fingerprint, using only shasum and find.
