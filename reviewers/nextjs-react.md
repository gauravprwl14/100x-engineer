# Next.js + React reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

## Applies when
- `next` in `package.json` `dependencies`, or `next.config.{js,mjs,ts}` present.
- `app/` or `pages/` directory at a workspace root (App Router vs Pages Router — see below).
- `.tsx`/`.jsx` files importing `react` directly (plain React/Vite/CRA apps without
  `next`: apply the "Common AI failure modes" and "Edge cases" sections, skip the
  App Router / server-component rows in "Approach selection").

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|
| 1 | No TypeScript error on changed files | `npx tsc --noEmit` exits 0 | typed boundary silently defeated (see `any` row below) |
| 2 | No ESLint error/warning on changed files | `npx eslint <diff-files> --max-warnings=0` exits 0 | react-hooks and `@next/eslint-plugin-next` violations shipping |
| 3 | Production build succeeds | `npx next build` exits 0 | server/client boundary errors, missing `"use client"`, broken static generation only surface here, not in dev mode |
| 4 | `react-hooks/exhaustive-deps` clean or explicitly justified | `eslint` rule output; a suppressed dep needs an inline comment naming why | stale-closure bugs from a missing dependency |
| 5 | No `'use client'` at the top of a route's `page.tsx`/`layout.tsx` without justification | `grep -n "^'use client'" app/**/page.tsx app/**/layout.tsx` — each hit is a review question, not an auto-fail | whole subtree opted into client rendering by default |

## Common AI failure modes in this stack

| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|
| 1 | `'use client'` added to a page/layout, or to every new component by default, "to be safe" | client components are more forgiving of hooks/event handlers, so the model reaches for the directive whenever it needs interactivity anywhere in the tree | `grep -rn "^'use client'" app \| wc -l` vs total component count; `npx next build` output's route size table (client JS per route jumps); `@next/next/no-async-client-component` catches the worst case (async fn marked client) | push `'use client'` to the leaf that actually needs state/effects/events; keep `page.tsx`/`layout.tsx` server by default. Real example: `vercel/commerce` keeps `'use client'` on 15/65 `.tsx` files, all leaf interactive components (`cart-context.tsx`, `variant-selector.tsx`, `add-to-cart.tsx`) — never on `app/page.tsx`, `app/layout.tsx`, or `app/product/[handle]/page.tsx` |
| 2 | fetches data in a client component via `useEffect` + `useState` when the route is server-renderable | matches pre-App-Router React knowledge the model was trained on; "fetch in an effect" is the most common pattern in its corpus | grep for `useEffect(\s*\(\)\s*=>\s*{[^}]*fetch\(` in files under `app/`; bundle analysis shows a client-fetch waterfall (network tab: HTML loads empty, then a fetch fires) | fetch directly in the server component (`async function Page()`, `await fetch(...)`) unless the data is per-interaction (search-as-you-type, polling) — `vercel/commerce:app/product/[handle]/page.tsx` fetches server-side and streams via `Suspense`, no client fetch |
| 3 | no `Suspense` boundary around a slow data-dependent subtree, so one slow fetch blocks the whole page's first paint | works fine in dev with fast local data; the model doesn't have a slow-network signal to react to | grep for `async function Page` with no `<Suspense` anywhere in the same file or a sibling `loading.tsx`; Lighthouse TTFB/FCP gap | wrap the slow subtree: `<Suspense fallback={...}><SlowThing /></Suspense>`, or add `app/**/loading.tsx`. Real example: `vercel/commerce:app/search/layout.tsx` and `app/product/[handle]/page.tsx` both wrap variant/related-product fetches in `Suspense`; `app/search/loading.tsx` exists as the route-level fallback |
| 4 | `useEffect` recomputes a value from props/state that could be computed inline during render | "sync state with an effect" is the most-repeated wrong pattern in React's own training data (React docs literally have a page titled "You Might Not Need an Effect") | grep `useEffect` bodies that only call `setX(...)` derived from other state/props already in scope, with no subscription/DOM/network side effect | delete the effect, compute the value directly in the render body (or `useMemo` only if the computation is measured as expensive) |
| 5 | missing dependency array item, or dependency stuffed in to silence the linter (`eslint-disable-next-line react-hooks/exhaustive-deps`) | the model tried the naive dependency list, the linter flagged it, and the fastest way to a green check is a disable comment | `grep -rn "eslint-disable.*exhaustive-deps"`; each hit is a required review item, not automatically wrong | fix the actual staleness (move the value inside the effect, use a ref, or restructure) before suppressing; a disable comment must state why in the same line |
| 6 | one `useState` per form field instead of a single form object or `react-hook-form` | mirrors toy tutorial code; each field "obviously" needs its own state hook | count `useState` calls in a file with a `<form>`; >4 co-located `useState` calls feeding one submit handler is the signal | one object (`useState<FormState>` or `useReducer`) or `react-hook-form` + `zod`. `calcom/cal.com:apps/web/package.json` ships both `react-hook-form` and `zod` as direct deps, used throughout the booking forms |
| 7 | inline object/array/function literals passed as props to a `memo`-wrapped or list-rendered child every render | correct-looking JSX; the perf cost is invisible without a profiler | React DevTools Profiler "why did this render" flag; grep for `<Child prop={{` or `<Child onX={() =>` inside a component body (not inside `useMemo`/`useCallback`) | hoist the literal out of the render body, or wrap in `useMemo`/`useCallback` — but only after confirming the child is actually memoized and re-rendering matters |
| 8 | `useMemo`/`useCallback` wrapped around every value/function "for performance," with no measurement | matches a rule the model half-remembers ("memoize expensive things") without the actual criterion (is it expensive? does the child skip re-render because of it?) | grep count of `useMemo`/`useCallback` per file vs component complexity; each one adds a dependency-array bug surface for no measured benefit | remove unmeasured memoization; keep it only for (a) values passed to a memoized child, or (b) genuinely expensive computation confirmed via profiler |
| 9 | `key={index}` on a list that can reorder, filter, or have items removed | index keys "just work" in the model's mental model of keys as "a required prop," and the list renders correctly on first paint regardless | grep `key={i}` / `key={index}` next to `.map(`; cross-check whether the list's source data can reorder/filter (cart, sortable table, drag list) vs is static (nav menu, skeleton) | stable identity key (`item.id`, `product.handle`). Real counterexample found in `vercel/commerce:components/cart/modal.tsx:120` — a filtered, mutable cart line-item list keyed on `.map((item, i) => ... key={i})`; contrast the same repo's `components/layout/product-grid-items.tsx:13` which correctly keys a similarly-shaped list on `product.handle`. Index keys on genuinely static lists (`app/search/loading.tsx` skeleton rows) are not a bug — the review question is "can this list's order or membership change," not "is `index` present" |
| 10 | server-only env var (`DATABASE_URL`, API secret) referenced from a file that ends up in a client bundle | Next.js only prefixes public vars with `NEXT_PUBLIC_`; the model doesn't always track which file is server vs client-bounded once `'use client'` boundaries get sprinkled around | `next build` output doesn't flag this reliably — grep `process.env\.[A-Z_]+` in files with `'use client'` at the top, or in files imported by one, and check the var isn't `NEXT_PUBLIC_*`; `next-secure-headers`/`@next/eslint-plugin-next` doesn't catch this, treat as a manual review item | keep secrets in server components / route handlers / server actions only; pass only the derived, non-secret value down as a prop |
| 11 | `searchParams`/dynamic route params used unvalidated, cast with `as` instead of parsed | TypeScript's `as` cast satisfies the compiler, so the code "type-checks," and the happy path works in manual testing | grep `searchParams as \{` / `params as \{`; absence of a `zod`/`valibot` parse call before first use | parse with `zod` (`schema.safeParse(searchParams)`) and handle the failure case explicitly. Real counterexample: `vercel/commerce:app/search/page.tsx:15` does `const { sort, q: searchValue } = searchParams as { [key: string]: string }` — no validation, even in the official reference template, which is itself the finding: this failure mode ships in production-quality code, not just AI output |
| 12 | no `error.tsx` for a route segment, so one uncaught throw blanks the entire page (or the whole app, if no root `app/error.tsx` either) | App Router error boundaries are opt-in per-segment and easy to forget; the model writes the happy-path component and moves on | `find app -name page.tsx` vs `find app -name error.tsx` — segments with data fetching or client interactivity and no sibling `error.tsx` are a gap; `next build` does not warn about this | add `app/**/error.tsx` (and a root `app/error.tsx`) — `vercel/commerce:app/error.tsx` exists at the app root as the baseline |
| 13 | `<img>` instead of `next/image`, or `next/image` without `width`/`height`/`fill`, causing layout shift | `<img>` "just works" and is what the model's non-Next React training defaults to | `@next/next/no-img-element` ESLint rule (in `eslint-config-next`'s `core-web-vitals` preset) flags this directly; Lighthouse CLS score | use `next/image` with explicit dimensions or `fill` + a sized container |
| 14 | new component file created per small UI element (a `<Badge>`, a `<Spacer>`, a one-line wrapper) instead of inlining or extending an existing component | file-per-concept is a defensible pattern in isolation, and the model has no signal that this file will never be reused | no mechanical check exists in the wild for this — `research/36-findings-antibloat-in-practice.md` surveyed 46 production repos and found **zero repos with a CI-enforced "unnecessary new file" gate**; the only production mitigation found is a size-proxy convention (`calcom/cal.com:AGENTS.md`: *"Never create large PRs (>500 lines or >10 files) — split them instead"*), itself unenforced by tooling | treat as a review-only question: "is this exported and imported by more than the one call site it was extracted for?" If not, inline it. Do not expect a lint rule to catch this |
| 15 | API response typed `any`, or a hand-written interface that isn't validated against what the endpoint actually returns | fastest way to make `tsc` pass on a fetch result; the type "boundary" looks enforced because the file compiles | `grep -rn ": any" --include="*.ts" --include="*.tsx"`; `npx tsc --noEmit` with `noImplicitAny: true` catches implicit but not explicit `any`; `eslint` rule `@typescript-eslint/no-explicit-any` | derive the type from a runtime validator (`zod` schema + `z.infer`) so a shape mismatch fails at the network boundary, not silently downstream. Note: `vercel/next.js` itself ships with root `tsconfig.json` `"strict": false` (`research/30-findings-js-verification.md`) — don't assume a Next.js repo enforces strictness by default; check the actual flag |
| 16 | interactive element built as `<div onClick=...>` instead of `<button>`; modal built without a focus trap; icon-only control with no `aria-label` | visually identical to the correct element, and the model optimizes for "looks right" not "is operable without a mouse" | `eslint-plugin-jsx-a11y` (`no-static-element-interactions`, `click-events-have-key-events`, `no-noninteractive-tabindex`); manual/automated axe scan (`@axe-core/playwright`) | use semantic elements (`<button>`, `<a href>`); for custom modals use a library with focus-trap built in (Radix UI primitives, which `shadcn-ui/ui` builds on) or `focus-trap-react`; every icon-only control gets `aria-label` |

## Edge cases routinely missed

| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|
| 1 | Hydration mismatch (server-rendered HTML differs from first client render — e.g. `Date.now()`, `Math.random()`, locale-dependent formatting, or reading `window` during render) | works in dev with fast refresh masking the warning; only visible as a console error + visual flash | `npx next build && npx next start`, load the page with JS devtools console open — hydration warnings are dev/prod-build visible, not always caught by `next dev` alone |
| 2 | Missing/inconsistent loading, empty, and error states for the same data — a component handles the happy path and the error path but not "zero results" | the model writes the case it's prompted for (the demo data usually has results) | render the component/route with an empty array and with a rejected fetch, not just with sample data |
| 3 | Race condition on rapid navigation (user navigates away before a client fetch resolves, and the stale response still calls `setState` on the unmounted/replaced view) | passes every manual test because humans navigate slower than automated ones | rapid programmatic navigation in a Playwright test; check for `AbortController` cleanup in `useEffect` fetches |
| 4 | Optimistic update with no rollback path if the mutation fails | the optimistic-UI happy path is what gets built and demoed; the failure branch is an afterthought | force the mutation's server action / API route to reject in a test and assert the UI reverts |
| 5 | Double-submit on a form (user double-clicks submit, or resubmits on a slow network before the first request returns) | single click during manual testing never reproduces it | disable the submit button on pending state; test via two rapid `fireEvent.click` calls in RTL/Playwright |
| 6 | Back/forward-cache (bfcache) breaks a page that has an unclosed WebSocket/interval or reads stale client state on `pageshow` | Next.js apps with client-heavy state (websockets, timers) are the common victims; invisible without explicitly testing back-nav | Chrome DevTools "back/forward cache" test in the Application panel; Lighthouse bfcache audit |
| 7 | Stale data shown after a mutation (server action / API mutation succeeds but the list/detail view wasn't revalidated or refetched) | the mutation "worked" (200 response) so the task looks done; only a second view of the same data reveals staleness | after a mutation in a test, re-query the same route/component and assert the new value is visible, not just that the mutation call succeeded |
| 8 | Slow 3G / high-latency behavior not tested — spinners that never resolve, layout that assumes near-instant response | local dev network is effectively instant | Chrome DevTools network throttling ("Slow 3G"); `next build` + Lighthouse CI with a throttled profile |
| 9 | Offline behavior undefined — a fetch throws a generic network error with no user-facing message | offline isn't in the happy-path spec, so the model doesn't branch for it | DevTools "Offline" toggle during manual QA; assert a specific offline UI state, not a raw error boundary |
| 10 | RTL/i18n: layout assumes LTR text flow, or a `date`/`number` is formatted without `Intl`/the request locale | most training data and most manual QA is English/LTR | render the page with `dir="rtl"` and a non-`en-US` locale; snapshot test with `Intl.NumberFormat`/`Intl.DateTimeFormat` in a non-default locale |
| 11 | Timezone rendering: a server-rendered timestamp is formatted in the server's timezone, then hydrates to the browser's — mismatch, or silently wrong for the user | server and dev-machine timezone are often the same (UTC or the developer's local zone), hiding the bug until a real user in another timezone hits it | render with `TZ=<something-else>` on the server process and a different `Intl.DateTimeFormat` locale/timezone on the client in a test |
| 12 | Very long lists rendered without windowing/virtualization — fine at 20 items in the demo data, unusable at 5,000 | demo/seed data is always small | render with a large fixture list and measure paint/interaction time; check for `@tanstack/react-virtual` or equivalent on any list that can grow unbounded |
| 13 | Deep-link / hard refresh on a route whose UI state lives only in client state (not the URL) loses that state entirely | works during the session because the state was set by a client interaction, never round-tripped through a reload in testing | hard-refresh (`Cmd+R`) on the route mid-interaction and assert the important state either survives (via URL/localStorage) or degrades gracefully, not silently to a blank/default view |

## Approach selection

| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|
| Router | App Router vs Pages Router | new project vs existing codebase; App Router is where Next.js ships new features (Server Components, streaming, `loading.tsx`/`error.tsx`) | **App Router** for anything new. Stay on Pages Router only for an existing large codebase where migration cost isn't justified — `calcom/cal.com` still runs a hybrid (Pages Router legacy + App Router growth areas) at scale, which is the realistic middle state, not a clean either/or |
| Component default | server components vs client components | does the component need state, effects, browser APIs, or event handlers? | **server component by default**; add `'use client'` only at the leaf that needs interactivity, per the `vercel/commerce` pattern cited above (15/65 files, all leaves) |
| Data fetching | server component `fetch`/`await` vs TanStack Query vs SWR vs server actions | is the data needed on initial render (→ server fetch) or driven by client interaction/polling/optimistic updates (→ TanStack Query)? is it a mutation (→ server action)? | **server component fetch for initial/route data**, **TanStack Query for client-driven fetching** (search-as-you-type, polling, infinite scroll — `supabase/supabase:apps/studio` runs `@tanstack/react-query` `~5.83` as its primary client data layer), **server actions for mutations** from forms. Reach for SWR only if the codebase already has it — no corpus evidence found favoring it over TanStack Query for a new project |
| Client state | `useState`/Context vs Zustand vs Redux vs URL state | is the state server-derived (→ don't duplicate it client-side), shareable via link (→ URL state, `useSearchParams`/`nuqs`), or genuinely global client-only UI state? | **URL state for anything that should survive a refresh or be shareable** (filters, tabs, pagination); **`useState`/Context for local/small-tree state**; **Zustand for cross-tree client state that doesn't fit Context cleanly** (avoids the re-render-everything problem of a single large Context). Reach for Redux only if the team already has Redux expertise/tooling investment — no repo in the researched corpus adopted Redux fresh for a Next.js App Router project |
| Styling | Tailwind vs CSS Modules vs styled-components | team convention + whether runtime CSS-in-JS is acceptable under React Server Components (styled-components requires client-only usage under RSC) | **Tailwind** as the default — it's the dominant choice across the grounding repos (`shadcn-ui/ui`, `vercel/commerce`, `calcom/cal.com` all ship it) and has no RSC-compatibility caveat. CSS Modules is the fallback when a team wants zero build-time class-name magic. Avoid styled-components/Emotion in new App Router code — they need `'use client'` wrapping and a registry workaround to work under Server Components at all |
| Forms | `react-hook-form` + `zod` vs server actions with `useActionState` vs plain controlled state | complexity of client-side validation/UX (inline errors, multi-step) vs how much of the form is a simple POST-and-redirect | **`react-hook-form` + `zod`** for anything with real client-side validation UX — confirmed production pattern (`calcom/cal.com:apps/web/package.json` ships both). **Server actions + `useActionState`** for simple forms where a full round-trip per submit is acceptable and you want to avoid a client-validation library entirely. Avoid one-`useState`-per-field regardless of which of the two you pick |
| Auth | next-auth/Auth.js vs custom vs third-party (Clerk, Supabase Auth, WorkOS) | does the team need to own the session/token model, or is a hosted provider acceptable? | **Auth.js (next-auth)** as the default for a self-hosted, provider-agnostic setup; a **hosted provider** (Clerk, Supabase Auth) when time-to-ship matters more than owning the auth stack. Avoid hand-rolled session/JWT auth unless the team has specific requirements a library can't meet — it's the highest-blast-radius place to reinvent |
| Rendering | SSG vs SSR vs ISR vs client-only | how often does the data change, and does it need to be per-request-personalized? | **SSG/ISR by default for content that changes on a scale of minutes-to-days** (marketing pages, docs, product catalogs); **SSR for per-request personalized/auth-gated data**; **client-only rendering only for genuinely client-only surfaces** (a canvas editor, a dashboard behind auth that never needs to be crawled/shared). Don't default to SSR "to be safe" — it throws away the caching Next.js gives you for free |
| Testing | Vitest + RTL vs Playwright component testing vs e2e-only | unit/component logic (→ Vitest+RTL) vs full-stack user flows (→ Playwright e2e); Playwright component testing is a narrower, less-adopted middle option | **Vitest + React Testing Library for component/unit logic**, **Playwright for e2e flows** — this is the dominant combination measured across the 72-repo JS/TS corpus (`research/30-findings-js-verification.md`: vitest 40/72, playwright 16/72, both frequently in the same repo). Playwright component testing has real but much thinner adoption in the corpus; don't pick it over the two-tier default without a specific reason |
| Monorepo placement | single Next.js app vs `apps/<name>` in a Turborepo/Nx monorepo | more than one deployable surface (web app + admin + docs) sharing code | **single app** until there are genuinely 2+ deployables sharing a component/logic library; at that point, **Turborepo** — it's the dominant task-graph tool in the corpus for JS/TS monorepos (`research/30-findings-js-verification.md`: Turborepo 14/72 vs Nx 6/72 vs Lerna mostly legacy), and every grounding repo here that is a monorepo (`calcom/cal.com`, `payloadcms/payload`) uses it |

## Verify

```bash
# Type errors — run before anything else; catches boundary/prop-type breaks
npx tsc --noEmit

# Production build — the ONLY step that reliably surfaces missing 'use client',
# broken static generation, and server/client boundary violations
npx next build

# Lint, diff-scoped — includes @next/eslint-plugin-next (no-img-element,
# no-async-client-component, no-html-link-for-pages) and react-hooks/exhaustive-deps
# if eslint-config-next / eslint-plugin-react-hooks is installed
git diff --name-only --diff-filter=ACM origin/main -- '*.ts' '*.tsx' | xargs -r npx eslint --max-warnings=0

# Next's own lint wrapper (same rules, Next-aware defaults)
npx next lint

# Bundle size — per-route client JS, the number that catches "'use client' crept
# up the tree" concretely; compare before/after on the changed routes
npx next build 2>&1 | grep -A 20 "Route (app)"
# or, for a byte-budget gate (rare in the wild — TanStack/table and
# react-hook-form are the two production examples found; see research/30):
npx @next/bundle-analyzer

# Accessibility — automated pass, not a substitute for manual keyboard-only testing
npx playwright test --grep @a11y   # if an axe-core/playwright suite exists
# or, ad hoc against a running dev server:
npx @axe-core/cli http://localhost:3000

# E2E, if Playwright is present
npx playwright test

# Lighthouse against a production build (not `next dev` — dev-mode numbers are meaningless)
npx next build && npx next start & npx lighthouse http://localhost:3000 --output=json --quiet
```

Expected runtime: `tsc --noEmit` and diff-scoped `eslint` are seconds; `next build`
is the slow step (30s-5min depending on app size) — run it before claiming a change
that touches `'use client'` boundaries, data fetching, or routing is done, since it
is the only command in this list that actually exercises the server/client split.

## Sources
- `vercel/commerce@HEAD` (cloned `--depth 1 --filter=blob:none`, deleted after
  extraction): `'use client'` leaf-only pattern (15/65 `.tsx` files), `Suspense`
  usage (`app/product/[handle]/page.tsx`, `app/search/layout.tsx`),
  `app/error.tsx` + `app/search/loading.tsx` presence, unvalidated `searchParams`
  cast (`app/search/page.tsx:15`), `key={index}` on a mutable cart list
  (`components/cart/modal.tsx:120`) vs stable key on the product grid
  (`components/layout/product-grid-items.tsx:13`)
- `vercel/next.js@canary:packages/eslint-plugin-next/src/index.ts` — full rule
  list (`no-img-element`, `no-async-client-component`, `no-html-link-for-pages`,
  etc.) and their default severities
- `vercel/next.js@canary:tsconfig.json` — root `"strict": false`, cited via
  `research/30-findings-js-verification.md`
- `calcom/cal.com@main:apps/web/package.json` — `react-hook-form` + `zod` in
  production; `calcom/cal.com:AGENTS.md` PR-size convention, cited via
  `research/36-findings-antibloat-in-practice.md`
- `supabase/supabase@master:apps/studio/package.json` — `@tanstack/react-query
  ~5.83.0` as primary client data layer
- `shadcn-ui/ui@main:.eslintrc.json` — `next/core-web-vitals` + `turbo` +
  `prettier` + `tailwindcss` preset stack
- `research/30-findings-js-verification.md` — 72-repo JS/TS verification-stack
  measurement (test runners, linters, tsconfig strictness, coverage gates,
  monorepo tooling); not re-measured here, only cited
- `research/36-findings-antibloat-in-practice.md` — 46-repo anti-bloat
  measurement, specifically the failure-mode coverage table (row 1: "new file
  vs. edit" has zero mechanical coverage in any repo surveyed) and the
  architecture-boundary/size-budget findings (`TryGhost/Ghost`
  `.dependency-cruiser.cjs`, `nuxt/nuxt` `no-restricted-paths`,
  `TanStack/table` size-limit `30 KB`, `react-hook-form` bundlewatch `15.0 kB`)
- `SOURCE: original` — the "correct move" phrasing and the Approach-selection
  deciding factors are this document's synthesis, not lifted from a single
  cited repo, where no repo-specific citation is given inline
