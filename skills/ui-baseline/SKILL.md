---
name: ui-baseline
description: >
  Page, screen, form, dashboard, table or layout: responsive to 320px, looks good on mobile,
  loading/empty/error states, touch targets, design tokens, form validation UX. Not for
  per-component a11y (→ accessibility).
---

# UI baseline

A screen that works only at 1440px with perfect data is a demo. What breaks in
production is the 320px phone, the German label, the slow network, the empty
list and the failed save. None of that needs a request in the spec. It is class A
in `docs/OPERATING-MODEL.md` §5: applied silently, listed as an assumption.
`100x baseline show --work <type> --tier <tier>` prints the full baseline for a
declared tier. Every rule below holds at every tier.

## Trigger

**Fire when:** adding or changing a page, screen, route, form, layout, modal,
table or dashboard widget; a request says "responsive", "mobile", "polish", or
"make it look good"; a component starts fetching or mutating data.

**Do not fire when:** the diff has no rendered UI (API, migration, CLI), or only
changes copy. Per-component accessibility (semantic elements, names, focus) is
`accessibility`'s job; WCAG 2.2 AA is the bar at every tier, and this skill does
not repeat those rules. Layering (which file fetches) is `frontend-architecture`.

## Rules

1. **Reflow at 320 CSS px with no horizontal scroll, mobile first.** Write the
   narrow layout as the base and widen it with `min-width` breakpoints; use
   fluid units (`%`, `fr`, `minmax`, `clamp`) over fixed widths. Never disable
   zoom (`user-scalable=no`, `maximum-scale` below 2), and never paper over an
   overflow with `overflow-x: hidden` on `body`. Data tables, which need two
   dimensions, may scroll inside their own container.
   *Enforced by:* `100x ui_baseline_check --only fixed-width,viewport-zoom,overflow-x-hidden`

2. **Touch targets: at least 24×24 CSS px on the web** (WCAG 2.2 SC 2.5.8, AA),
   **44×44 pt on iOS, 48×48 dp on Android**. Pad the hit area; the icon can stay
   small.
   *Enforced by:* review

3. **Leave room for translated text.** No fixed-width or fixed-height box around
   a label; let buttons and table headers wrap. W3C's figures: about 130% for
   strings over 70 characters, 200–300% for strings of 10 or fewer. Test with
   the longest locale, or with a pseudo-locale that pads every string.
   *Enforced by:* review

4. **Every data view has loading, empty, error and partial states.** Loading is
   a skeleton shaped like the content when the wait is visible; empty says what
   to do next; error says what failed and offers retry; partial (some widgets
   failed) degrades only the failed part. A blank screen is not a state.
   *Enforced by:* `100x ui_baseline_check --only fetch-no-states` (advisory), then review

5. **Mutations: optimistic only when reversible, always with rollback and
   retry.** Update the UI immediately for a cheap, likely-to-succeed action
   (toggle, rename), restore the previous value on failure, and tell the user.
   Payments, deletes and sends wait for the server. Double-submit is blocked
   while a request is in flight.
   *Enforced by:* review

6. **Form validation tells the user what and where.** Validate on blur and on
   submit, not on every keystroke. Describe each error in text next to its field
   (WCAG 3.3.1, A) with a fix when one is known (3.3.3, AA); on a failed submit,
   show an error summary at the top that links to each field and move focus to
   it. Keep what the user typed.
   *Enforced by:* review (labels and error association: `accessibility` rules 6–7)

7. **Colour, spacing and type come from the repo's tokens or theme, never raw
   values.** No `#hex`, `rgb()` or arbitrary `bg-[#…]` in a component when the
   repo has a token file. With no design system, define CSS custom properties
   once and reference them. Never adopt a UI library nobody asked for.
   *Enforced by:* `100x ui_baseline_check --only raw-color` (blocking when a token file exists)

8. **Honour `prefers-color-scheme` and `prefers-reduced-motion`.** Dark mode
   swaps tokens, not components; any motion beyond a fade has a reduced-motion
   path.
   *Enforced by:* `100x a11y_check --only animation-no-reduced-motion` (motion); review (colour scheme)

9. **Search before you build.** Before writing a Button, Modal, Table, DatePicker
   or EmptyState, search the repo and its design-system package for one; extend
   it rather than fork it. A second near-identical component is a defect.
   *Enforced by:* review — `git grep -nE "export (default )?(function|const) (Button|Modal|Dialog|Table|EmptyState)"`

10. **Public, indexable pages carry SEO meta:** a unique, descriptive `<title>`,
    a meta description, a canonical URL, and Open Graph tags when the page will
    be shared. Authenticated app screens skip this and send `noindex`.
    *Enforced by:* review

11. **Target Browserslist `defaults`** (`> 0.5%, last 2 versions, Firefox ESR,
    not dead`) unless the user named other devices, which is a class C question.
    *Enforced by:* `test -f .browserslistrc || grep -q '"browserslist"' package.json`

## Verify

Diff-scoped, about a second on a typical UI PR.

```bash
100x ui_baseline_check --list
100x ui_baseline_check --base origin/main            # blocking findings fail
100x ui_baseline_check --base origin/main --strict   # advisories fail too
100x a11y_check --base origin/main                   # WCAG 2.2 AA per component
test -f .browserslistrc || grep -q '"browserslist"' package.json

# what no static check sees, before merging a new screen:
#   1. DevTools device mode at 320px wide and at 400% zoom: no sideways scroll
#   2. throttle to Slow 4G, then force the API to fail and return []
#   3. switch the OS to dark mode and to reduced motion
```

`ui_baseline_check` reads source text. It cannot see a width computed at runtime,
a class built by `cn()`, or an overflow clipped by a parent; it skips widths
inside `min-width` media queries, print styles, tables, and blocks with a fluid
`max-width`. Its loading/error check only asks whether the component branches
on a state at all.

## Failure modes

This skill rejects:

- **`.page { width: 1200px }`** or `className="w-[1200px]"` with no breakpoint:
  a phone gets a sideways scroll on every page.
- **`<meta name="viewport" content="…, maximum-scale=1, user-scalable=no">`**:
  a low-vision user can no longer pinch to read.
- **`body { overflow-x: hidden }`** added to "fix" a stray scroll: the
  overflowing element is still cut off, now silently.
- **`const { data } = useQuery(…); return data.map(…)`**: blank while loading,
  a crash on error, nothing at all when the list is empty.
- **A delete button that removes the row optimistically and never restores it**
  when the request fails.
- **A form that turns fields red on submit with no text**, or validates the
  email on the first keystroke.
- **`color: '#3b82f6'` in a component** of a repo that has `theme.ts`: the next
  rebrand misses it.
- **A new `ConfirmDialog.tsx`** in a repo that already exports `Dialog`.

## Scale

**Every tier, `solo` included: all 11 rules.** Each is a correctness floor, not
a scale feature: a checkout that cannot be used on a phone is broken at any team
size, and WCAG 2.2 AA applies regardless. What scales is the manual pass:
`small-team (2-10)` adds the 320px, slow-network and dark-mode pass to review of
every new screen; `org (10+)` adds visual regression snapshots at narrow and wide
widths and a pseudo-locale build in CI.

## Sources

- WCAG 2.2, W3C Recommendation 12 December 2024 (https://www.w3.org/TR/WCAG22/):
  SC 1.4.10 Reflow (AA, 320 CSS px), SC 1.4.4 Resize Text (AA, 200%), SC 2.5.8
  Target Size (Minimum) (AA, 24×24 CSS px), SC 3.3.1 Error Identification (A),
  SC 3.3.3 Error Suggestion (AA).
- Zoom: W3C ACT rule b4f0c3 "Meta viewport allows for zoom"
  (https://www.w3.org/WAI/standards-guidelines/act/rules/b4f0c3/): fails on
  `user-scalable=no` or `maximum-scale` below 2.
- Native targets: Apple Human Interface Guidelines, Accessibility (44×44 pt,
  https://developer.apple.com/design/human-interface-guidelines/accessibility);
  Android Developers, "Make apps more accessible" (48dp×48dp,
  https://developer.android.com/guide/topics/ui/accessibility/apps).
- Text expansion: W3C Internationalization, "Text size in translation"
  (https://www.w3.org/International/articles/article-text-size), quoting IBM's
  English-to-European expansion table.
- User preferences: Media Queries Level 5, W3C Working Draft 19 February 2026,
  §12.1 `prefers-reduced-motion`, §12.5 `prefers-color-scheme`.
- Error summary that links to fields and takes focus:
  `alphagov/govuk-frontend@main:packages/govuk-frontend/src/govuk/components/error-summary/`.
- Browser target: `browserslist/browserslist@main:README.md`, the `defaults`
  query.
- SEO: Google Search Central, "Influencing your title links"
  (https://developers.google.com/search/docs/appearance/title-link): every page
  needs a descriptive, unique `<title>`.
- Owner-approved defaults (WCAG 2.2 AA at every tier, Browserslist `defaults`,
  the repo's own tokens, no unrequested UI library): `scripts/data/baseline.json`.
- The 400px fixed-width threshold, the state and token heuristics, and
  `scripts/ui_baseline_check.py`: `SOURCE: original`; false-positive controls in
  `tests/test_ui_baseline_check.sh`.
