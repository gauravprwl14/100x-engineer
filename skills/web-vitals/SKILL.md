---
name: web-vitals
description: >
  Use when building or reviewing any component that renders above the fold, adds
  a web font, ships client JS, adds an image, or wires up a new route — to keep
  Core Web Vitals a per-component decision instead of a Lighthouse run at the
  end of a quarter. Covers LCP/INP/CLS thresholds and what causes each at the
  component level, image and font loading rules, JS/hydration cost and
  `'use client'` boundaries, and lab-vs-field measurement. Owns BROWSER-side
  rendering metrics; does not own back-end latency budgets (see
  performance-budgets) or bundle-byte budgets (see typescript-verification rule
  6) — cross-references both rather than repeating them. Use PROACTIVELY before
  adding a hero image, a web font, or client-side data fetching above the fold.
---

# Web Vitals (Core Web Vitals)

Bundle-byte budgets are owned by `typescript-verification` (rule 6) and
back-end latency budgets by `performance-budgets` — this skill does not repeat
either. What's missing for a frontend-heavy stack is the browser-rendering
half: **LCP, INP, and CLS are decided component by component**, at the moment
you pick an image's loading strategy, a font's `display` value, or where a
`'use client'` boundary goes — not fixable by a script at the end. A build that
never measures field data and ships a Lighthouse 100 has measured the wrong
thing; see "Lab versus field" below.

## Trigger

**Fire when:** adding or changing an above-the-fold image, a web font, a route
that fetches data client-side, a `'use client'` boundary, or any code that runs
on first load/first interaction.

**Do not fire when:** a pure backend/API change with no rendered output, or a
change below the fold with no layout/JS impact (still worth a glance, not a
blocking gate).

## The three metrics

| metric | good threshold | measured as | what it means |
|---|---|---|---|
| **LCP** (Largest Contentful Paint) | ≤ **2.5s** | 75th percentile of real page loads | time until the largest above-the-fold element (usually the hero image or heading) is visible |
| **INP** (Interaction to Next Paint) | ≤ **200ms** | 75th percentile of real interactions | delay between a user's click/tap/keypress and the next visual update — **replaced FID as the responsiveness Core Web Vital on March 12, 2024** |
| **CLS** (Cumulative Layout Shift) | ≤ **0.1** | 75th percentile of real page loads | how much visible content moves around unexpectedly during load |

These are **field thresholds at the 75th percentile of real users**, not lab
numbers — `GoogleChrome/web-vitals` defines "good" as the rating a metric gets
only when the p75 value across real page loads is at or under the threshold.
A single fast lab run passing these numbers proves nothing about the users at
the 76th-99th percentile on a slow phone and a congested network.

## What causes each, per component

| metric | component-level cause |
|---|---|
| LCP | an unoptimized/oversized hero image; a render-blocking font on the LCP text; fetching above-the-fold data client-side instead of rendering it server-side |
| INP | a long task on the main thread (heavy computation, a big loop) inside an event handler; an expensive re-render triggered by one click; hydration cost — a large client component tree that must hydrate before it responds |
| CLS | an image with no reserved space (`width`/`height`/`aspect-ratio`); a banner/cookie-notice/ad injected after initial render; a late-loading web font that swaps to a different-metrics font; any content inserted above the fold after first paint |

## Rules

1. Set a budget per route before building it — target LCP/INP/CLS numbers,
   written down, same discipline as `performance-budgets` rule 1 for latency.
   A route with no stated budget silently inherits whatever the build produces.
   *Enforced by:* review

2. Every image ships `width`/`height`, `fill` (with a sized container), or
   `aspect-ratio` — no exceptions. Reserve the space before the image arrives,
   or CLS is guaranteed once it loads.
   *Enforced by:* `python3 scripts/a11y_check.py --only img-no-dimensions`

3. Use `priority`/eager loading (Next.js: `priority`, or `fetchPriority="high"`
   as of Next.js 16 — see Sources) on the one element that is actually the
   LCP candidate, and lazy-load everything else. Marking every image
   `priority` defeats the point: it competes with the real LCP element for
   bandwidth.
   *Enforced by:* review

4. Serve modern image formats (AVIF/WebP) where the pipeline supports it —
   `next/image` does this automatically; a hand-rolled `<img>` does not.
   *Enforced by:* review — cross-reference `reviewers/nextjs-react.md` row 13
   (`@next/next/no-img-element`) for the mechanical half of this

5. Set `font-display: swap` (or use `next/font`, whose default is already
   `swap`) so text renders in a fallback font instead of staying invisible
   while a custom font loads.
   *Enforced by:* review

6. Preload only the font actually used above the fold, and subset it to the
   character set you need. Preloading every font weight/subset "just in case"
   delays the one that matters.
   *Enforced by:* review

7. Keep the `'use client'` boundary at the leaf that needs interactivity, not
   the route root — every component inside a client boundary ships its JS to
   the browser and pays hydration cost before it can respond to input (INP).
   This is a performance decision wearing a syntax choice.
   *Enforced by:* review — see `reviewers/nextjs-react.md` failure mode #1 and
   its `grep -rn "^'use client'" app | wc -l` check; not repeated here

8. Fetch above-the-fold data on the server (server component `fetch`/`await`)
   rather than in a client `useEffect`. A client fetch means the browser must
   parse, hydrate, and run JS before the request even starts — that delay
   lands directly in LCP.
   *Enforced by:* review — see `reviewers/nextjs-react.md` failure mode #2

9. Budget and measure client JS per route, not just per bundle — the bytes
   that ship gate hydration time, which gates INP on first interaction.
   *Enforced by:* `npx size-limit` (owned by `typescript-verification` rule 6;
   cross-referenced, not duplicated here) or `npx next build` route-size table

10. Never trust a single Lighthouse run as ground truth. Measure field data
    (CrUX, RUM, or Vercel/Chrome UX report) before declaring a route fixed —
    lab and field disagree often enough that this is a distinct rule, not a
    restatement of rule 1.
    *Enforced by:* convention

## Verify

Diff-scoped where a checker exists; the rest is a measurement discipline no
script can fully replace.

```bash
# mechanical: CLS risk from undimensioned images (shared with the a11y checker)
python3 scripts/a11y_check.py --only img-no-dimensions --base origin/main

# client-JS-per-route -- the number that shows a 'use client' boundary crept up
npx next build 2>&1 | grep -A 20 "Route (app)"

# bundle budget, if configured (typescript-verification owns this)
npx size-limit

# lab proxy -- run against a PRODUCTION build, never `next dev`
npx next build && npx next start & npx lighthouse http://localhost:3000 --output=json --quiet

# field truth -- no CLI in this repo replaces this; use PageSpeed Insights,
# Chrome UX Report (CrUX), or your own RUM (web-vitals library) in production
```

Expected runtime: the two mechanical checks are seconds; `next build` +
Lighthouse is the slow step (tens of seconds to minutes) — run it before
claiming a change touching an above-the-fold image, a font, or a `'use
client'` boundary is done, since dev-mode numbers are not representative.

## Failure modes

This skill rejects:

- **A hero `<img>`/`Image` with no `width`/`height`/`fill`/`aspect-ratio`** —
  the layout jumps once it loads; guaranteed CLS.
- **Every image on a page marked `priority`** — defeats the purpose; the real
  LCP element now competes for the same bandwidth budget.
- **A client-side `useEffect` fetch for data needed on first paint** — LCP pays
  for the JS parse + hydrate + fetch waterfall that a server fetch skips.
- **`'use client'` on a route's `page.tsx`/`layout.tsx`** "to be safe" — every
  descendant now ships JS and hydrates, inflating INP for no interactive gain.
  See `reviewers/nextjs-react.md` failure mode #1 for the same defect from the
  correctness/architecture side.
- **A web font with no `font-display: swap`** — invisible text while the font
  loads (FOIT), directly hurting LCP on the text it's applied to.
  A late-swapping font with different metrics than the fallback — CLS as the
  text box resizes.
- **A route shipped with a Lighthouse 100 and no field-data check** — a lab
  score of 100 with bad field data means the lab conditions (fast machine, warm
  cache, no real network) were wrong for what real users experience; "lab
  passed" is not the same claim as "field is good."
- **No stated budget before the route is built** — the same failure
  `performance-budgets` rejects for latency, here applied to LCP/INP/CLS.

**Honest limitations:** `img-no-dimensions` is the only mechanically enforced
rule in this skill; the rest (font strategy, `'use client'` placement, lab-vs-
field discipline) need review or an actual Lighthouse/CrUX run — no static
checker can compute a real paint time or a real interaction delay from source
text alone.

## Scale

`solo`: rule 2 (mechanical, free) and rule 3 (name the one `priority` image) —
minutes to adopt, catches the most common AI-generated defect (every image
marked eager/priority, or none dimensioned).
`small-team (2-10)`: add 5, 6, 7, 8 — font and `'use client'` discipline start
mattering once more than one person adds components to the same route.
`org` / `high-blast-radius`: add 1, 9, 10 and real field-data monitoring
(CrUX/RUM in production) — at this scale a route regressing INP for a subset
of users is invisible without it.

## Sources

- LCP/INP/CLS thresholds (2500ms, 200ms, 0.1) and the "good"/"poor" boundary
  values: `GoogleChrome/web-vitals@main:src/onLCP.ts:37`
  (`LCPThresholds = [2500, 4000]`), `src/onINP.ts:37` (`INPThresholds = [200,
  500]`), `src/onCLS.ts:36` (`CLSThresholds = [0.1, 0.25]`).
- 75th-percentile-of-real-users methodology:
  `GoogleChrome/web-vitals@main:src/onINP.ts:60` ("will not affect your 75th
  percentile INP value..."); confirmed in prose on `web.dev/articles/inp`.
- INP replaced FID as a Core Web Vital on March 12, 2024: `web.dev/blog/inp-cwv`
  ("Update: As of March 12, 2024, Interaction to Next Paint (INP) is officially
  a Core Web Vital metric."); the library-level change is
  `GoogleChrome/web-vitals@main:CHANGELOG.md` v4.0.0 (2024-05-13), "Deprecate
  `onFID()`".
- `next/image` `priority`/loading defaults and the Next.js 16 `priority` →
  `preload` rename: `vercel/next.js@canary:docs/01-app/03-api-reference/02-
  components/image.mdx`.
- `next/font` defaults (`display: 'swap'`, `preload: true`, `subsets`):
  `vercel/next.js@canary:docs/01-app/03-api-reference/02-components/font.mdx`.
- `'use client'` boundary and client-fetch failure modes: `reviewers/nextjs-
  react.md` failure modes #1 and #2 (cited, not repeated) — including the
  `vercel/commerce` leaf-only `'use client'` measurement (15/65 files).
- Bundle-byte budgets, owned elsewhere: `skills/typescript-verification/SKILL.md`
  rule 6 (`TanStack/table` 30KB `size-limit` — 2 of 72 JS repos have any bundle
  budget at all).
- Back-end latency budgets, owned elsewhere: `skills/performance-budgets/SKILL.md`
  rule 1 (state a percentile budget before building).
- `img-no-dimensions` check: `SOURCE: original`, part of `scripts/a11y_check.py`
  (shared with `accessibility`, since dimension/alt are both per-`<img>`
  static-analysis checks on the same tag).
