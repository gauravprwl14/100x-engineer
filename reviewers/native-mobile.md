# Native Android + iOS reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

Room/Core Data/GRDB per-schema-version migration testing, staged rollout percentages,
remote-config kill switches, `PrivacyInfo.xcprivacy` absence, and size/perf-gate absence for this
stack are all covered in `research/33-findings-mobile-verification.md` — this file does not
repeat them. This file covers component/class-level code review, grounded directly in
`signalapp/Signal-Android`, `signalapp/Signal-iOS`, `mozilla-mobile/firefox-ios`, and
`duckduckgo/Android`.

Sections are split per platform; a diff usually only needs one.

---

## Applies when
Android: `build.gradle`/`build.gradle.kts` present with an `com.android.application`/`library`
plugin, diff touches `.kt`/`.java` under `src/main`.
iOS: `.xcodeproj`/`.xcworkspace`/`Package.swift` present, diff touches `.swift`.

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 (Android) | Unit tests pass | `./gradlew testDebugUnitTest` | regressions in business logic |
| 2 (Android) | Lint clean | `./gradlew lint` (or `ktlintCheck`/`detekt` if configured) | reflection/nullability/resource bugs |
| 3 (Android) | No new `.observe(this` inside a `Fragment` | `grep -n "\.observe(this" <changed Fragment files>` | LiveData observer outliving the Fragment's view, double-firing on the next view creation |
| 4 (iOS) | Tests pass on simulator | `xcodebuild test -scheme <Scheme> -destination 'platform=iOS Simulator,...'` | regressions caught only by exercising the real run loop |
| 5 (iOS) | SwiftLint clean | `swiftlint --strict` | style and a subset of correctness issues (whatever rules are enabled — see finding #11 below, this subset is smaller than it looks) |

---

## Android

### Common AI failure modes
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | Does file I/O, DB queries, or network calls on the main thread inside a click handler or `onCreate` | Works fine on a fast dev device, no visible jank in a quick test | `StrictMode` — `duckduckgo/Android@HEAD:app/src/main/java/com/duckduckgo/app/global/DuckDuckGoApplication.kt:169-190` configures `ThreadPolicy.Builder().detectDiskReads().detectDiskWrites().detectNetwork().penaltyLog().penaltyDropBox()` in debug builds, plus (API 31+) `VmPolicy.Builder().detectUnsafeIntentLaunch().penaltyDeath()` — this is a real, runnable detector, not a review question | wrap `BuildConfig.DEBUG`-gated `StrictMode` policies exactly this way if the project doesn't have them yet; any disk/network call not inside a coroutine dispatched to `Dispatchers.IO` will fire it immediately in a debug build |
| 2 | Registers a `LiveData`/`Flow` observer with `.observe(this, ...)` inside a `Fragment` | `this` type-checks as a `LifecycleOwner` (the Fragment itself implements it) | `grep -rn "\.observe(this" <Fragment files>` | Signal-Android's own codebase shows the working convention precisely: all 4 instances of `.observe(this` found repo-wide are inside **Activities** (`MainActivity.kt:290`, `RegistrationActivity.kt:47`, `AppSettingsActivity.kt:102`, `CustomExpireTimerSelectDialog.kt:42`), never a Fragment; Fragments use `.observe(viewLifecycleOwner, ...)` in 101 call sites. Using the Fragment's own lifecycle instead of its view's means the observer can fire after the view is destroyed but before the Fragment itself is (e.g. when the view is torn down by the back stack) — always use `viewLifecycleOwner` in a Fragment, `this` only in an Activity |
| 3 | Stores in-flight UI state in a plain `ViewModel` field with no `SavedStateHandle` | Survives simple config-change rotation testing (ViewModel itself survives that) | grep the touched `ViewModel` for a `SavedStateHandle` constructor param when it holds anything the user would be upset to lose | a bare `ViewModel` field is lost on **process death** (the OS killing the whole process under memory pressure while backgrounded — rotation alone does not kill it, which is why casual testing misses this). Anything representing in-progress user input (a draft, a scroll position, a multi-step form) needs `SavedStateHandle`, confirmed present in Signal-Android (15 files use it) but not automatic — it has to be threaded through explicitly per field |
| 4 | Calls `registerReceiver(...)` in `onCreate`/`onResume` without a matching `unregisterReceiver` in the paired lifecycle method | Works during the session it was registered in; the leak is invisible until the component is destroyed and recreated repeatedly | grep `registerReceiver(` vs `unregisterReceiver(` counts per file — Signal-Android: 17 `registerReceiver` call sites vs. 12 `unregisterReceiver`, a real imbalance worth walking through per-file (some are legitimately manifest-registered or registered once at Application scope, but the gap is a genuine review flag, not proven-safe) | every `registerReceiver` in an Activity/Fragment/Service needs a paired `unregisterReceiver` in the mirroring lifecycle callback (`onCreate`/`onDestroy`, `onStart`/`onStop`), or use `LocalBroadcastManager`/lifecycle-aware alternatives that don't need manual pairing |
| 5 | Adds a new model class that's only touched via reflection (Gson/Moshi deserialization, `Class.forName`) without a corresponding ProGuard/R8 `-keep` rule | Passes every test that runs on a debug build (R8 minification is release-only) | grep the new class name against `*.pro`/`proguard-rules.pro` files if it's touched by JSON deserialization, JNI, or reflection; the failure **only reproduces in a release build**, never in debug or unit tests | Signal-Android and DuckDuckGo/Android both maintain hand-written `proguard-rules.pro` with explanatory comments for exactly this class of bug (e.g. `duckduckgo/Android@HEAD:app/proguard-rules.pro` documents the JS-interface `-keepclassmembers` pattern) — any reflection-touched class needs an explicit keep rule, and this must be verified with an actual release-variant build/run, not just unit tests, because it is release-only by construction |
| 6 | Uses `Dagger`/`Hilt` reflexively for DI on a new module | It's the most commonly cited Android DI framework online | check what the rest of the codebase actually uses before introducing a second DI mechanism | real production counter-evidence: Signal-Android uses **manual DI** via a single `AppDependencies.kt` singleton object (`app/src/main/java/org/thoughtcrime/securesms/dependencies/AppDependencies.kt`) — no Dagger/Hilt anywhere in `app/build.gradle.kts`. DuckDuckGo/Android uses `dagger.android` **and** is mid-migration to `dev.zacsweers.metro` (confirmed via imports in `DuckDuckGoApplication.kt`, matching research/33's note that its test task runs twice, once per DI framework). Match whatever the existing codebase does; don't introduce Hilt into a manual-DI or Dagger-only codebase without a stated migration plan |
| 7 | Writes `suspend fun` and `Flow<T>` freely without checking who owns cancellation | Coroutines "just work" as long as the call compiles | review question: "if the calling `CoroutineScope` is cancelled mid-call (Activity destroyed), does this leave anything in an inconsistent state (partial write, held lock)?" | Signal-Android uses `suspend fun` in 131 files and `Flow<` in 140 — coroutines are the default async mechanism in this ecosystem (not RxJava/callbacks); scope new async work to `viewModelScope`/`lifecycleScope` so cancellation is automatic on destroy, and treat any coroutine that does a multi-step write (not a single atomic DB call) as needing explicit cleanup on cancellation |

### Verify
```bash
# Unit tests + lint (adjust module path as needed)
./gradlew testDebugUnitTest

# Static analysis (project-dependent: ktlint, detekt, or gradle's built-in lint)
./gradlew lint
./gradlew ktlintCheck    # if ktlint is configured (e.g. element-hq/element-android)
./gradlew detekt         # if detekt is configured

# Diff-scoped Fragment/LiveData lifecycle check
git diff --name-only -- '*Fragment*.kt' | xargs -I{} grep -Hn "\.observe(this" {} 2>/dev/null

# Diff-scoped receiver pairing check
git diff --name-only -- '*.kt' | xargs -I{} sh -c 'grep -q "registerReceiver(" "{}" && ! grep -q "unregisterReceiver(" "{}" && echo "{}: register with no unregister in file"'

# Release-only breakage: proguard/R8 keep-rule regressions only show up here
./gradlew assembleRelease
```

---

## iOS

### Common AI failure modes
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | Captures `self` strongly in an escaping closure (network completion handler, `DispatchQueue.main.async`, notification observer) | Works, no visible symptom until the owning object should have deallocated | SwiftLint's `weak_delegate` rule catches one narrow case; most retain cycles need a review question: "does this closure outlive `self`'s expected lifetime, and does it capture `self` strongly?" | Signal-iOS uses `[weak self]` in 479 places — the default, not the exception, for any closure stored or escaping beyond the current call frame. Every `Task { ... }`, completion handler, and long-lived closure capturing `self` needs `[weak self]` plus a `guard let self else { return }` unless the closure is provably synchronous/local |
| 2 | Updates UI (a `UILabel`, triggers a reload) from a background-dispatched completion handler with no hop back to main | Compiles; SwiftUI/UIKit don't always crash immediately on a background UI mutation, so it can ship silently broken | grep for UI mutation immediately following a background-queue callback with no `DispatchQueue.main.async`/`@MainActor` in between | Signal-iOS uses `DispatchQueue.main.async` 219 times and `@MainActor` 245 times — both patterns coexist; the correct move for new code is `@MainActor`-annotated methods/types over manual `DispatchQueue.main.async`, since the compiler enforces it instead of relying on the pattern being remembered every time |
| 3 | Adds a force unwrap (`value!`) for a value the model has (incorrectly) reasoned is always present | Type-checks, looks like every other line of Swift, and there is no default-enabled lint against it | **absence finding**: neither `signalapp/Signal-iOS`'s `.swiftlint.yml` (`Signal/.swiftlint.yml` — just `line_length: 200` and `disabled_rules: [file_length, todo]`) nor `mozilla-mobile/firefox-ios`'s far more thorough `only_rules:` allowlist enables `force_unwrapping` — firefox-ios explicitly lists `force_cast` and `force_try` as enabled but has `# - force_unwrapping` **commented out** (`.swiftlint.yml:61`). Two major production iOS codebases confirm this is not mechanically enforced anywhere in this corpus | this must be a manual review question — "can this value actually be nil/empty at this call site, and if so, what happens?" — not something `swiftlint --strict` will flag by default; a team that wants mechanical enforcement has to opt in explicitly via `opt_in_rules: [force_unwrapping]`, which neither reference repo does |
| 4 | Sprinkles `@MainActor` on a type or function reflexively "to fix a concurrency warning" without checking whether the caller is already off the main actor | Silences the Swift 6 concurrency-checker error | review question: "is this type/method actually UI-adjacent, or does `@MainActor` here just force every caller onto the main thread for no reason?" | over-applying `@MainActor` serializes unrelated background work onto the main actor and reintroduces the "blocking work on the main thread" bug via type annotation instead of an explicit `DispatchQueue` call — apply it to the smallest unit (the specific UI-touching method), not the whole type, unless the whole type is genuinely UI state |
| 5 | Calls `UIApplication.shared.beginBackgroundTask(...)` directly, with an easy-to-miss expiration handler, instead of reusing a shared wrapper | Looks like standard iOS background-task boilerplate | grep `beginBackgroundTask` and check for a paired `endBackgroundTask` in every exit path (success, error, early return) plus a non-empty expiration handler | Signal-iOS solved this by building a dedicated RAII-style wrapper, `OWSBackgroundTask` (`SignalServiceKit/Util/OWSBackgroundTask.swift`) — its own doc comment states the reasons: "Ensures completion block is called exactly once and on main thread... Ensures we properly handle the 'background task could not be created' case." Reuse (or build) a single wrapper type like this rather than hand-writing `begin`/`end` pairs at every call site — the failure mode is real enough that a major production app built dedicated infrastructure specifically to prevent it |
| 6 | Uses Combine for new async code because "that's the reactive-iOS pattern" | Combine is a well-known, documented Apple framework | check whether the codebase has already moved to `async`/`await` | Signal-iOS: only 15 files `import Combine` vs. 551 files using `async`/`await` syntax — Combine is legacy in this codebase, not the default for new code. Default to structured concurrency (`async`/`await`, `AsyncSequence`) for new asynchronous code unless the surrounding code is already Combine-based |

### Verify
```bash
# Simulator test run (adjust scheme)
xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=iPhone 16' build test

# Lint — note: only catches what's enabled. Check .swiftlint.yml's opt_in_rules /
# only_rules before trusting a clean run to mean "no force unwraps", "no retain cycles", etc.
swiftlint --strict

# Diff-scoped: new force unwraps introduced
git diff -U0 -- '*.swift' | grep -E '^\+' | grep -oE '[A-Za-z0-9_\)\]]\!' | grep -v '!='

# Diff-scoped: closures capturing self without [weak self]
git diff -U5 -- '*.swift' | grep -B5 '\bself\.' | grep -L "weak self"
```

---

## Sources
- `signalapp/Signal-Android@HEAD` — `app/src/main/java/org/thoughtcrime/securesms/dependencies/AppDependencies.kt`,
  grep counts across `app/src/main` for `.observe(`, `SavedStateHandle`, `registerReceiver`,
  `suspend fun`, `Flow<`
- `duckduckgo/Android@HEAD` — `app/src/main/java/com/duckduckgo/app/global/DuckDuckGoApplication.kt:169-190`
  (StrictMode config), `app/proguard-rules.pro`, `build.gradle` (spotless)
- `signalapp/Signal-iOS@HEAD` — `Signal/.swiftlint.yml`, `SignalServiceKit/Util/OWSBackgroundTask.swift`,
  grep counts for `[weak self]`, `DispatchQueue.main.async`, `@MainActor`, `import Combine`,
  `async`/`await`
- `mozilla-mobile/firefox-ios@HEAD` — `.swiftlint.yml` (`only_rules:` allowlist, `force_unwrapping`
  commented out)
- `research/33-findings-mobile-verification.md` — Room/Core Data migration testing, staged
  rollout, remote-config kill switches, `PrivacyInfo.xcprivacy` absence, prove-it commands
  (referenced, not repeated)
