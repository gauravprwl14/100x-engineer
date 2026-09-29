# React Native + Expo reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

Release-safety, OTA/native-fingerprint gating, staged rollout, and per-schema-version
migration testing for this stack are covered in `research/33-findings-mobile-verification.md`
(Bluesky's `bundle-deploy-eas-update.yml` fingerprint gate, Expo's OTA anti-brick e2e suite,
mattermost's WatermelonDB sync rule). This file does not repeat those — it covers
component/code-level review, grounded in `bluesky-social/social-app` (122MB, 3,327 `src/**/*.tsx`
files, production app at ~18k stars) and `expo/expo`.

## Applies when
`package.json` depends on `react-native` or `expo`; an `app.json`/`app.config.js` with an
`"expo"` key is present; the diff touches `*.tsx`/`*.jsx` files importing from `react-native`.

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 | TypeScript compiles clean | `npx tsc --noEmit` | runtime crash from a type-hole the JS thread doesn't catch |
| 2 | Lint passes with RN-aware rules | `npx eslint . --max-warnings 0` (or `oxlint` — see Verify) | inline styles, missing keys, raw text outside `<Text>` |
| 3 | Expo project health | `npx expo-doctor` | mismatched native module versions, invalid `app.json`, broken prebuild |
| 4 | No secret bundled under a public-prefixed env var | `grep -rn "EXPO_PUBLIC_.*\(KEY\|SECRET\|TOKEN\)" app.config.*` returns nothing | shipping an API secret readable in every installed app binary |
| 5 | No raw JSX text outside `<Text>` | project's own `avoid-unwrapped-text` rule, or `eslint-plugin-react-native`'s `no-raw-text` | red-screen crash on Android for a literal string in a `<View>` |

## Common AI failure modes in this stack
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | `FlatList` with no `keyExtractor` | List renders fine in dev with default index keys | `grep -n "<FlatList" -A5 <file> \| grep -L "keyExtractor"`. `bluesky-social/social-app` pairs every list: 23 files use `FlatList`, `keyExtractor` appears in 52 places (incl. `SectionList`) — but the convention is by habit, no lint enforces it (`react-native` plugin absent from `.oxlintrc.json`) | pass `keyExtractor` (stable id, never array index) on every `FlatList`/`SectionList`; for very large feeds (>500 items), prefer `@shopify/flash-list` — notably absent from Bluesky's own `package.json` despite the app's scale, a real gap worth flagging in review |
| 2 | Inline `style={{...}}` object literals in render | Reads identically to `StyleSheet.create` at the call site | `grep -c "style={{" <file>` vs `StyleSheet.create` usage. Bluesky: 235 inline-object occurrences vs 46 files using `StyleSheet.create` — inline literals are common even in a mature codebase; no `react-native/no-inline-styles` rule is enabled (`.oxlintrc.json` plugins are only `typescript, react, import`) | a new object literal is allocated every render and defeats `PureComponent`/`memo` bail-outs; move static styles to `StyleSheet.create`, pass computed values as `[styles.base, {opacity}]` arrays, not fresh objects |
| 3 | Expensive work (parsing, sorting, layout math) runs synchronously in an event handler or `useEffect` | Works fine on a simulator with no thrown frames | review question: "does this handler block for >16ms on a mid-tier Android device?"; `InteractionManager.runAfterInteractions` usage count is a proxy | Bluesky's own codebase uses `InteractionManager` in exactly **1** file across all of `src` — heavy work is instead pushed to Reanimated worklets (UI thread) or deferred with `requestAnimationFrame`. `InteractionManager` is effectively a dead pattern in modern RN; the current correct move is Reanimated worklets for animation-adjacent work and `runOnJS`/background threads (or a real queue) for everything else, not `InteractionManager` |
| 4 | Assumes `InteractionManager.runAfterInteractions` is the standard way to defer non-urgent work | It is the historically-documented RN pattern | same as above | don't default to it; verify what the target app already uses (worklets, `setTimeout(0)`, a task queue) and match the codebase's existing pattern rather than introducing a second deferral mechanism |
| 5 | `<Image source={{uri}}>` for remote images with no cache/resize policy | Renders correctly once | `grep -n "expo-image\|react-native-fast-image" package.json` | Bluesky ships `expo-image` (`package.json:207`), which caches to disk and supports `contentFit`/`placeholder` out of the box — default to `expo-image` over bare `Image` for any remote or user-generated image |
| 6 | `useEffect` starts a fetch/subscription with no cleanup | Compiles, works until the component unmounts mid-request | `grep -n "useEffect" -A8 <file>` and check for a returned cleanup fn or `AbortController`; ESLint `react-hooks/exhaustive-deps` catches the dependency-array half of this, not the cleanup half | Bluesky uses `AbortController` in 34 files — the working convention: create the controller inside the effect, `abort()` in the cleanup, and guard any state update after `await` with a `mounted`/`isCancelled` flag |
| 7 | Navigation params typed as `any` or left untyped | TypeScript doesn't complain because `any` suppresses it | `grep -rn ": any" **/*Navigator*.tsx`; check for a generated `ParamList` type | Bluesky types every route through `FlatNavigatorParams` (`src/routes.ts`, `src/lib/routes/types.ts`) and derives `AllNavigatableRoutes` from it — define one root `ParamList` type and thread it through every `useNavigation<NativeStackNavigationProp<ParamList>>()` call, don't inline `navigation.navigate('Screen', {...})` with untyped params |
| 8 | `AsyncStorage` used for anything beyond small key-value settings (feed cache, draft queue, growing lists) | AsyncStorage's API looks like a database (`getItem`/`setItem`) | `grep -rln "AsyncStorage" src`; check whether the same keys are read in a loop or the value is a growing JSON blob | Bluesky ships **both** `@react-native-async-storage/async-storage` (`2.2.0`) and `react-native-mmkv` (`^3.3.3`) — MMKV for hot-path synchronous state, AsyncStorage retained for slower/legacy paths. Default: MMKV for key-value, a real SQLite layer (`expo-sqlite`/`op-sqlite`/WatermelonDB) for anything relational or growing without bound — AsyncStorage does not belong in either of those roles |
| 9 | No offline queue for user-generated writes (posts, likes, uploads) | The happy-path network call works in review/demo | `grep -rin "outbox\|offline.*queue\|pending.*post" src` | grep across all of `bluesky-social/social-app` for an outbox/offline-queue pattern returns **zero hits** — a flagship social app with a "post" action appears to fail the write synchronously on network loss rather than queue it. Call this out explicitly in review rather than assuming a mature app already solved it: ask "what happens to this write if the network drops mid-request?" |
| 10 | Treats a "public" env var or a value in `app.config.js` as hidden from end users | It isn't referenced directly in a rendered screen | `grep -rn "EXPO_PUBLIC_" app.config.js`; then `unzip -p app.ipa main.jsbundle \| strings \| grep <value>` to prove it's readable | only `EXPO_PUBLIC_`-prefixed vars are inlined into the client JS bundle by Expo's own convention (confirmed via Bluesky's `app.config.js:21-23`, `process.env.EXPO_PUBLIC_ENV`) — but *everything* in the shipped bundle, prefixed or not, is extractable from the `.ipa`/`.apk` with zero effort. Any real secret (server API key, signing key) must never enter client code at all, must live server-side, and `EXPO_PUBLIC_*` is not a security boundary, only a bundling boundary |
| 11 | Assumes an OTA/EAS Update push can ship a native-module change | JS-only workflow, the update "just works" for JS-only diffs | before publishing an OTA update, diff the native module surface (new/changed native deps, `Podfile`/`build.gradle` changes) against the last native build; see `research/33-findings-mobile-verification.md` for the full mechanism — Bluesky's `bundle-deploy-eas-update.yml` fingerprints the native module surface and forces a full native rebuild on drift | treat any native-surface diff as blocking for OTA: ship a new native store build instead of pushing the change as an OTA update, and add a fingerprint-gate CI step (or the manual checklist in this file's Verify section) if one doesn't exist yet |
| 12 | Platform-divergent code written as inline `Platform.OS === 'ios' ? … : …` sprinkled through a component, with no `.ios.tsx`/`.android.tsx` split and no parity check | Passes review because both branches were eyeballed once | `grep -c "Platform.select\|Platform.OS ===" <file>`; count `.ios.tsx`/`.android.tsx` pairs | Bluesky uses `Platform.select` in only 2 files and has 4 `.ios.tsx`/4 `.android.tsx` pairs against 3,327 total `.tsx` files — platform branching is deliberately rare, and there is **no automated cross-platform parity test** found; `pnpm lint-native` (per research/33) lints native Swift/Kotlin syntax, not JS-level UI parity. Treat "does the iOS branch and Android branch actually do the same thing" as a manual review question — no tool catches drift here |
| 13 | Ignores safe-area/notch insets, hardcodes top/bottom padding | Looks right on the simulator used during development | `grep -rln "useSafeAreaInsets\|SafeAreaView" src` | Bluesky uses `react-native-safe-area-context` (`useSafeAreaInsets`/`SafeAreaView`) in 43 files — this is the expected default, not an edge case; any new full-screen view or floating action button needs it |
| 14 | Relies on `KeyboardAvoidingView` alone, or nothing, for a form under the keyboard | `KeyboardAvoidingView` covers the simple cases | `grep -c "KeyboardAvoidingView" src`; `grep -n "react-native-keyboard-controller" package.json` | Bluesky ships `react-native-keyboard-controller` (`1.21.9`) and uses it in 15 files, vs. bare `KeyboardAvoidingView` in only 4 — for anything beyond a single trivial text input, default to the controller library; `KeyboardAvoidingView`'s `behavior` prop is famously unreliable across iOS/Android and inside nested scroll views |
| 15 | Permission request fires once; denial (especially Android's "denied but can ask again" vs. "denied forever") is not distinguished | The happy-path grant flow was tested | `grep -n "canAskAgain\|PermissionStatus" <file>` | Bluesky's notification permission check (`src/lib/notifications/notifications.ts`) explicitly branches: `status === 'granted' \|\| (status === 'denied' && !canAskAgain)` — Android's `canAskAgain` stays `true` after a single soft-denial (documented in a code comment in that file) and only becomes `false` after a hard denial, which changes what UI to show. Any permission flow (camera, location, notifications) needs this three-state handling, not a binary granted/denied check |

## Edge cases routinely missed
| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|
| 1 | Cold start with an empty/corrupt MMKV or AsyncStorage store | Dev devices always have warm storage | boot the app after `adb shell pm clear` / deleting the app and reinstalling, not just reloading JS |
| 2 | OS kills the app mid-background-upload | Dev sessions rarely background the app for minutes | put the app in background, wait past the OS's background-execution budget, foreground and check the upload didn't silently vanish |
| 3 | Deep link opens a screen that requires auth, but the user isn't logged in | Deep links are tested from a logged-in session during dev | open the link cold, logged out, and confirm redirect-to-login-then-back, not a crash or blank screen |
| 4 | Push notification arrives while app is backgrounded on Android (vs. foregrounded) | Notification handler is usually tested foregrounded | trigger a push with the app backgrounded and killed, separately, on Android — the notification-tap handler path differs from the foreground handler |
| 5 | Text scaled to 200% (accessibility) overflows a fixed-height row | Dev always tests at 100% system font scale | set device text size to max and check every list row / button for clipped text |
| 6 | RTL layout (Arabic/Hebrew) mirrors incorrectly for a manually-positioned (not flex-based) element | RTL is rarely toggled during development | flip `I18nManager.forceRTL(true)` and screenshot-diff key screens |
| 7 | Flaky network mid-write (request sent, response lost) leads to a duplicate action on retry | Retry logic tested against 0% or 100% packet loss only | inject a slow/dropped-response network condition (Charles/dev-tools throttle) around a write, verify idempotency |
| 8 | Permission re-requested after being hard-denied on Android does nothing (OS silently ignores it) | Simulators/emulators reset permission state easily, masking this | hard-deny a permission, then re-trigger the request flow and confirm the app detects `canAskAgain === false` and routes to Settings instead of re-prompting |
| 9 | App-open while OTA update download is in progress | Only tested with a completed download | kill/reopen the app mid-OTA-download and confirm it doesn't get stuck on the old bundle indefinitely or crash |
| 10 | Timezone/DST change while app is backgrounded (e.g. flight, DST rollover) | Emulator clock rarely changes mid-session | change device timezone while app is backgrounded, foreground, verify any cached "relative time" (e.g. "2h ago") recomputes |

## Approach selection
| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|
| Managed vs. bare workflow | Expo managed / Expo prebuild (CNG) / fully bare (vendored `ios`/`android`) | whether the team needs a native module with no Expo config plugin | **Expo + `expo prebuild` (Continuous Native Generation)**. Bluesky's own `ios/`/`android/` dirs exist on disk but are `.gitignore`'d and regenerated via `EXPO_NO_GIT_STATUS=1 expo prebuild --clean` (`package.json:54`) — this is the real-world default at scale: get Expo's managed tooling and OTA path, drop to native config plugins (not a hand-vendored native project) when you need custom native code |
| State management | Zustand / Redux Toolkit / Context+reducer / TanStack Query only | how much of the state is server data vs. client-only UI state | **TanStack Query for all server state, Zustand for cross-screen client state, `useState`/`useReducer` for local-only state.** Note the real counter-evidence: Bluesky uses TanStack Query (`^5.96.2`) but no Zustand/Redux — client state is Context+reducer per feature. That's a defensible large-scale pattern too, but Zustand is less boilerplate for a new project and is the safer default recommendation |
| Navigation | React Navigation / Expo Router | whether the app needs deep, dynamic, file-based routing from day one, or has an existing imperative nav tree | **Expo Router for new projects** (file-based, first-class Expo integration, typed routes). Bluesky itself still uses React Navigation (`@react-navigation/native` `^7.1.33`) with a hand-rolled typed `Router` — a legitimate choice for a codebase that predates Expo Router's maturity, not evidence against Expo Router for a new build |
| Local storage | MMKV / AsyncStorage / SQLite (`expo-sqlite`, `op-sqlite`) / WatermelonDB | data shape: flat key-value vs. relational/growing | **MMKV for key-value/settings/hot state, a real SQLite layer for anything relational or unbounded.** AsyncStorage is legacy-compatibility only — Bluesky keeps it installed but has already migrated hot paths to MMKV |
| OTA strategy | EAS Update with fingerprint gate / CodePush / no OTA (native-store-only) | whether native modules change often, and whether the team can build the fingerprint-gate CI step | **EAS Update, gated by a native-fingerprint check before every OTA push** — see `research/33-findings-mobile-verification.md` for the full Bluesky/Expo mechanism; a manual "did any native dependency change since the last rebuild?" checklist is the minimum viable version if the CI step isn't built yet |

## Verify
```bash
# Type safety — no silent `any`-shaped runtime crash
npx tsc --noEmit

# Lint — RN-aware rules (bluesky uses oxlint; eslint is more common elsewhere)
npx eslint . --max-warnings 0
# or, if the project uses oxlint (bluesky-social/social-app):
npx oxlint --quiet src

# Expo project health: native module version mismatches, invalid app.json, broken prebuild
npx expo-doctor

# Native-boundary fingerprint before any OTA push — see research/33 for the full gate;
# minimum viable manual check:
git diff --name-only <last-ota-baseline>..HEAD -- '**/*.podspec' 'android/**/build.gradle*' package.json
# any hit here means: rebuild natively, do not push an OTA update

# Native lint, if the diff touches native modules (per research/33's prove-it command)
pnpm lint-native   # swiftlint + ktlint, bluesky-social/social-app convention
```

## Sources
- `bluesky-social/social-app@HEAD` — grep counts, `.oxlintrc.json`, `lint-rules/avoid-unwrapped-text.js`,
  `src/routes.ts`, `src/lib/notifications/notifications.ts`, `app.config.js`, `package.json`
- `expo/expo@HEAD` — `packages/expo-doctor/README.md`
- `research/33-findings-mobile-verification.md` — OTA fingerprint gate, staged rollout, migration
  testing (referenced, not repeated)
