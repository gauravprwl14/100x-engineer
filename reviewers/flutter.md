# Flutter reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

Release-safety, size/perf-gate absence, and offline/migration correctness for this stack are
covered in `research/33-findings-mobile-verification.md` (`flutter/flutter`'s `.ci.yaml`
presubmit-false perf corpus, the "Ratchet Principle" for the native-plugin boundary, localsend's
clean N/A for local-DB migration). This file does not repeat those — it covers widget/code-level
review, grounded directly in `localsend/localsend` (production Dart/Flutter app, P2P file
transfer, `app/` module) and cross-checked against `AppFlowy-IO/AppFlowy` and the actual
`flutter_lints` package contents (`flutter/packages:packages/flutter_lints/lib/flutter.yaml`).

## Applies when
`pubspec.yaml` declares a `flutter:` SDK dependency; the diff touches `.dart` files under `lib/`.

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 | Static analysis clean | `flutter analyze` (or `dart analyze`) exits 0 | dead code, unawaited futures, missing `const`, unsafe `BuildContext` use |
| 2 | Formatting enforced | `dart format --set-exit-if-changed .` | unreviewable diffs, merge noise |
| 3 | Unit/widget tests pass | `flutter test` | regressions in widget build/lifecycle logic |
| 4 | `use_build_context_synchronously` is not suppressed anywhere new | `git diff \| grep "ignore: use_build_context_synchronously"` returns nothing new | a `BuildContext` used after an `await` on a widget that already unmounted |
| 5 | No `FutureBuilder`/`StreamBuilder` merged without an error branch | `git diff \| grep -A10 "FutureBuilder\|StreamBuilder"` reviewed for `snapshot.hasError` | unhandled exception crashes the widget subtree instead of showing an error state |

## Common AI failure modes in this stack
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | Uses a bare `setState()` at a high-level widget to react to a small state change | Works, and is the first pattern taught in every Flutter tutorial | review question: "does this `setState` rebuild widgets that don't depend on the changed value?" — no analyzer lint catches this, it's structural | `localsend/localsend` avoids this by routing cross-widget state through `refena_flutter` (its chosen state-management package) rather than lifting `setState` up the tree — scope rebuilds with a state-management package (`Consumer`/`Selector`/provider-equivalent) or `ValueListenableBuilder`, not a `setState` several levels above the widget that actually changed |
| 2 | Instantiates a controller, computes a value, or makes an HTTP call directly inside `build()` | Compiles; "looks like normal Dart code that happens to be in `build()`" | grep for `http.get(`/`Dio(`/`.new()` controller construction inside a `Widget build(BuildContext context)` method body — **no standard Flutter lint catches this**, confirmed absent from `flutter_lints`, `localsend`'s and `AppFlowy`'s `analysis_options.yaml` rule lists | `build()` re-runs on every rebuild (parent state change, hot reload, `MediaQuery` change, etc.) — move controller construction to `initState()`/a state-management provider, and HTTP/futures to `initState()` + cached `Future` field, never directly in `build()` |
| 3 | Constructs a widget without `const` at the call site (`Text('hi')` inside `build()` instead of `const Text('hi')`) | Renders identically either way, so it reads as a style nit rather than a real defect | **verified absence, not a default catch**: `flutter/packages@main:packages/flutter_lints/lib/flutter.yaml` — the package every `flutter create` project includes — ships only `prefer_const_constructors_in_immutables` (a *declaration*-site rule: it flags an unmarked-const constructor on an `@immutable` class, which mostly fires for custom `Widget` subclasses' own constructors). It does **not** ship `prefer_const_constructors`/`prefer_const_declarations`/`prefer_const_literals_to_create_immutables` — the *call*-site rules that would flag `Text('hi')` missing `const` in a `build()` method. Confirmed both `localsend/localsend:app/analysis_options.yaml` and `AppFlowy-IO/AppFlowy:frontend/appflowy_flutter/analysis_options.yaml` add neither rule on top of their `include: package:flutter_lints/flutter.yaml` | `flutter analyze` will **not** catch a missing `const` at a widget-construction call site out of the box — grep the diff for `return <Widget>(` / JSX-like nested widget literals without a leading `const`, or add `prefer_const_constructors`, `prefer_const_declarations`, `prefer_const_literals_to_create_immutables` to `analysis_options.yaml` explicitly (or adopt `package:very_good_analysis`, which enables `prefer_const_literals_to_create_immutables` — `VeryGoodOpenSource/very_good_analysis:lib/analysis_options.6.0.0.yaml:126`) so `dart fix --apply` can auto-fix it going forward |
| 4 | Renders a list with plain `ListView(children: [...])` instead of `ListView.builder` | Fine for a handful of items, identical code shape either way | grep `ListView(` vs `ListView.builder(` in the diff; `localsend/localsend`: 19 uses of `ListView(` vs. 5 of `ListView.builder(` in `app/lib` — most are legitimately small, fixed-size lists (settings screens, small device lists), which is why the ratio isn't itself damning | the review question is "is the item count bounded by app data (a handful of settings) or by user/network-generated content (files, messages, search results)?" — only the second case must use `.builder` (or `ListView.separated`) for lazy building; a fixed 3-item settings list does not need it |
| 5 | Creates a `TextEditingController`/`AnimationController`/`StreamSubscription` in `initState()` and never overrides `dispose()` | The leak is invisible until the screen is opened/closed repeatedly | grep controller/subscription instantiation vs. a `dispose()` override in the same class — **no standard analyzer lint enforces this pairing** (a real gap in `flutter_lints`); `localsend` is clean (7 files instantiate a controller, 11 define `dispose()`, a strict superset) — cite as the working convention, not proof the lint exists | every `Controller`/`AnimationController`/`StreamSubscription` field created in `initState()` must be released in a matching `dispose()`; this must be a manual review checklist item precisely because the tooling doesn't catch it |
| 6 | Uses `context` (for `Navigator.push`, `ScaffoldMessenger`, etc.) after an `await`, without checking `mounted` first | Works when the async call resolves fast, in dev, with a fast network | `use_build_context_synchronously` — confirmed present in `flutter/packages@main:packages/flutter_lints/lib/flutter.yaml:14`, the default lint set every `flutter create` project includes — is one of the few items on this list `flutter analyze` catches natively | `localsend` additionally shows 14 manual `if (mounted)`/`if (!mounted)` guards in `app/lib` beyond what the lint alone forces (the lint only fires on direct BuildContext use post-await, not on every unsafe pattern) — check `mounted` (StatefulWidget) or `context.mounted` (any BuildContext) immediately after any `await` before touching `context` |
| 7 | Ships a `FutureBuilder` with only a data/loading branch, no error branch | The happy path was the only path exercised during dev | grep `FutureBuilder`/`StreamBuilder` usage, check for `snapshot.hasError` | **real bug found in the corpus**: `localsend/localsend@HEAD:app/lib/pages/changelog_page.dart:17-31` — `FutureBuilder` checks `data.hasData` but never `data.hasError`, then force-unwraps `data.data!`; if `rootBundle.loadString()` throws, this crashes instead of showing an error state. Every `FutureBuilder`/`StreamBuilder` needs three branches: loading (`!snapshot.hasData`), error (`snapshot.hasError`), and data — not just the last two collapsed into one |
| 8 | Picks a state-management library by pattern-matching "what's popular" rather than the app's actual shape | Riverpod/Bloc/Provider are all defensible-sounding choices | review question: "does the chosen approach match the team's stated reason, or was it copied from a tutorial?" | real production counter-evidence: `localsend/localsend` uses `refena_flutter` + `routerino` (non-mainstream, same-author packages) while `AppFlowy-IO/AppFlowy` uses the mainstream combination `flutter_bloc` + `get_it` + `go_router` (`pubspec.yaml`) — both work at production scale, but a new project without a specific reason to deviate should default to the mainstream stack (below) rather than reinvent one |
| 9 | Calls a platform channel (`MethodChannel.invokeMethod`) with no `try`/`catch` for `PlatformException` | The call succeeds during manual testing on the dev device | grep `invokeMethod` vs. `try {`/`PlatformException` in the same file | **confirmed gap in the corpus**: `localsend/localsend@HEAD:app/lib/util/native/macos_channel.dart:11` and `ios_channel.dart:8` call `invokeMethod` with no surrounding `try`/`catch`; `android_channel.dart` has 9 `invokeMethod` calls but only 3 `try` blocks, and **none of the three channel files reference `PlatformException` by name at all** — every `invokeMethod` call needs a `try`/`catch` for `PlatformException` (missing native implementation, platform version mismatch, bad argument), not just a bare `await` |
| 10 | Builds a layout that only breaks at non-default text scale (accessibility large-text settings) | Never tested at anything but the default 100% system font scale | no automated coverage found in the corpus; review question: "does this widget still lay out correctly with `MediaQuery.textScalerOf(context)` at 1.5x–2x?" — golden tests with a forced `textScaler` are the mechanical answer but were not found in `localsend`'s or `AppFlowy`'s test suites | wrap risky rows/cards in a golden test that renders at `TextScaler.linear(2.0)`, or at minimum manually test with the device accessibility text-size slider maxed; don't assume `Expanded`/`Flexible` alone solves it — a `Row` with a fixed-width sibling still overflows |
| 11 | Wraps a `Text` widget in a `SizedBox(height: <fixed px>)` | Pixel-matches the design mock at 100% scale | grep `SizedBox(height:` / `SizedBox(width:` immediately wrapping a `Text` widget | a fixed-height box clips text the instant the user increases system font size; prefer `ConstrainedBox(constraints: BoxConstraints(minHeight: …))`, or no explicit height at all and let the row size to content |

## Edge cases routinely missed
| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|
| 1 | Cold start with no cached data and no network | Dev always has a warm cache | fresh install, airplane mode, launch app, check for a defined empty/error state rather than a spinner forever |
| 2 | Low-memory kill mid-navigation, then restore | Rarely triggered manually; requires OS memory pressure | Android: `adb shell am kill <package>` while backgrounded, then relaunch and verify navigation stack/scroll position restoration (or a defined "start fresh" fallback) |
| 3 | `BuildContext` used after the owning widget was removed from the tree during a rebuild triggered by the same async operation | Looks identical to the single-unmount case that `mounted` catches | a widget test that triggers a rebuild (not just an unmount) mid-`await` and asserts no exception |
| 4 | RTL locale mirrors icons/directional widgets incorrectly (e.g. a manually-positioned back-arrow `Icon(Icons.arrow_back)` instead of `Icons.arrow_back_ios` equivalents that flip automatically) | RTL rarely toggled in dev | run the widget test suite with `Directionality(textDirection: TextDirection.rtl, ...)` wrapping key screens |
| 5 | Timezone/DST change while app is backgrounded | Emulator clock rarely changes mid-session | change device timezone while backgrounded, foreground, verify any cached relative-time or scheduled-notification logic recomputes |
| 6 | Battery saver mode throttles background isolates/timers | Not observable without enabling the OS setting | enable battery saver on a real device and verify any periodic background work (sync, polling) degrades gracefully rather than silently stops with no user-visible state |
| 7 | Platform channel call made on a widget that gets disposed before the native side responds | The response usually arrives fast enough in dev to be invisible | dispose the widget immediately after firing the channel call (e.g. navigate away instantly) and confirm the response handler doesn't touch a disposed controller/context |
| 8 | Device rotation (or foldable fold/unfold) mid-async-operation triggers a full widget rebuild | Dev testing is almost always portrait-only | rotate the device mid-`await` and verify state isn't lost or duplicated |
| 9 | Large text scale + RTL combined overflow that neither alone triggers | Each is tested in isolation, if at all | golden test matrix crossing `TextScaler.linear(2.0)` × `TextDirection.rtl` for any screen with mixed fixed/flexible children |

## Approach selection
| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|
| State management | Riverpod / Bloc / Provider / setState only | domain complexity: how much cross-screen or async-derived state exists | **Riverpod for new projects** (compile-safe DI + state, testable, no `BuildContext` needed to read state); **Bloc for teams that want an explicit, testable event→state contract for complex business logic** — `AppFlowy-IO/AppFlowy` ships `flutter_bloc` (`^9.1.0`) at production scale, a defensible alternative default for domain-heavy apps. Plain `setState` is fine only for genuinely local, ephemeral widget state (an open/closed toggle) |
| Routing | `go_router` / raw `Navigator` 2.0 / a third-party router (`routerino`, etc.) | whether the app needs deep links / URL-based routing | **`go_router`** — official, declarative, handles deep links and nested navigation without hand-rolling `Navigator` 2.0's `RouterDelegate`/`RouteInformationParser`. `AppFlowy` uses it (`^14.2.0`); `localsend` uses a smaller custom router (`routerino`) — a valid choice for a simple, mostly single-screen-flow app, not a reason to deviate from `go_router` by default |
| Local database | Drift / Isar / sqflite / Hive | relational needs (joins, migrations) vs. simple key-value/object storage | **Drift** for anything relational with a real migration story (type-safe SQL, generates migration scaffolding); **Hive** or `shared_preferences` for flat key-value config only — `AppFlowy` uses `hive_flutter` for lightweight local cache/settings (its real data layer is a separate Rust core, not a Dart ORM); `localsend` has no local DB at all, a legitimate N/A for a P2P transfer tool with nothing to persist (consistent with `research/33`'s own finding on localsend) |
| Dependency injection | `get_it` / Riverpod-as-DI / manual singletons | whether the project already uses Riverpod for state | **If already on Riverpod, use Riverpod's own providers for DI — don't add `get_it` on top.** If using Bloc/Provider instead, default to `get_it` — `AppFlowy` uses exactly this combination (`get_it` `^8.0.3` alongside `flutter_bloc`) |

## Verify
```bash
# Static analysis — catches missing const, unsafe BuildContext, unawaited futures
flutter analyze

# Formatting — fails non-zero on any unformatted file
dart format --set-exit-if-changed .

# Unit + widget tests
flutter test

# Diff-scoped: confirm no new suppression of the one lint that catches async-context bugs
git diff --name-only | xargs -I{} grep -n "ignore: use_build_context_synchronously" {} 2>/dev/null

# Diff-scoped: flag any new FutureBuilder/StreamBuilder without an error branch
git diff -U15 -- '*.dart' | grep -B2 -A15 "FutureBuilder\|StreamBuilder" | grep -L "hasError"
```

## Sources
- `localsend/localsend@HEAD` — `app/analysis_options.yaml`, `app/pubspec.yaml`,
  `app/lib/pages/changelog_page.dart:17-31`, `app/lib/util/native/{ios,macos}_channel.dart`,
  `app/lib/util/native/channel/android_channel.dart`, grep counts across `app/lib`
- `AppFlowy-IO/AppFlowy@main` — `frontend/appflowy_flutter/pubspec.yaml`,
  `frontend/appflowy_flutter/analysis_options.yaml`
- `flutter/packages@main` — `packages/flutter_lints/lib/flutter.yaml` (default lint set contents)
- `dart-lang/lints@main` — `lib/recommended.yaml` (confirms no `prefer_const_*` rule in the base set)
- `VeryGoodOpenSource/very_good_analysis@main` — `lib/analysis_options.6.0.0.yaml:126`
- `research/33-findings-mobile-verification.md` — release safety, size/perf gate absence,
  Ratchet Principle, localsend's migration N/A (referenced, not repeated)
