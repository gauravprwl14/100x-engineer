---
name: accessibility
description: >
  Use when building or reviewing any interactive UI component — a button, a form
  field, a modal, a card with a click handler, a custom dropdown, an icon-only
  control, an image, a toast/async update — not as an end-of-project audit but
  as a check that runs on every component-touching diff. Covers semantic HTML
  vs div-soup, keyboard operability and focus indicators, accessible names,
  label/error association, alt text, WCAG 2.2 AA contrast and target-size
  numbers, focus management in modals and on route change, live regions, and
  prefers-reduced-motion. Extends the a11y failure modes already listed in
  reviewers/nextjs-react.md (row 16) with the per-component rules and a
  runnable checker; does not repeat that file's Next.js-specific rows. Use
  PROACTIVELY whenever a `.tsx`/`.jsx`/`.html` file adds or changes a clickable
  element, a form field, an image, or an animation.
---

# Accessibility

The canonical defect this skill exists to reject: `<div onClick={...}>` instead
of `<button>`. It looks identical sighted, and is completely absent to a
keyboard or screen-reader user — not focusable, not operable with Enter/Space,
not announced as a control at all. Accessibility is not a Lighthouse pass you
run before shipping; it is a property of the component, decided the moment you
pick which element to render, same as `reviewers/nextjs-react.md` row 16
already flags for this exact stack. This skill gives that row its own rules,
numbers, and a diff-scoped checker instead of one table row.

## Trigger

**Fire when:** writing or reviewing a component with a click handler, a form
field, a modal/dialog/drawer, an icon-only control, an `<img>`/`next/image`,
route-change logic, or any CSS animation/transition.

**Do not fire when:** the diff is pure backend/API code with no rendered markup,
or a copy/config-only change with no new element or interaction.

## Rules

1. Reach for the semantic element first. A `div`/`span`/`li` with `onClick` and
   no `role`/`tabIndex` is not a button — it's invisible to assistive tech.
   *Enforced by:* `python3 scripts/a11y_check.py --only onclick-non-interactive`

2. Every interactive element must be reachable and operable by keyboard alone
   (Tab to reach it, Enter/Space to activate it) — this is broader than any
   mechanical check catches, so verify it by hand.
   *Enforced by:* review

3. Never remove the default focus outline without a compliant replacement. A
   `:focus-visible` rule in the same file is the minimum bar.
   *Enforced by:* `python3 scripts/a11y_check.py --only outline-none-no-focus-visible`

4. Don't use a positive `tabIndex`. It reorders focus away from DOM order and
   breaks the mental model every screen-reader and keyboard user relies on.
   *Enforced by:* `python3 scripts/a11y_check.py --only positive-tabindex`

5. Every control needs an accessible name: visible text, `aria-label`, or
   `aria-labelledby`. An icon-only button with none of the three is unusable —
   a screen reader announces "button" with nothing else.
   *Enforced by:* `python3 scripts/a11y_check.py --only control-no-accessible-name`

6. Every form field needs a programmatic label: `id` paired with a `label
   htmlFor`, or `aria-label`/`aria-labelledby`. A placeholder is not a label —
   it disappears the moment the user types.
   *Enforced by:* `python3 scripts/a11y_check.py --only form-field-no-label`

7. Associate a field's error with the field via `aria-describedby`, and make
   sure it's actually announced (a `role="alert"`/live region, or the field
   re-focused with the error read). A red border with no text relationship is
   invisible to a screen-reader user.
   *Enforced by:* review

8. Every `<img>`/`next/image` needs a meaningful `alt`, or an explicit `alt=""`
   for a purely decorative image. Missing `alt` is a defect; empty `alt` is a
   decision — the checker treats them differently.
   *Enforced by:* `python3 scripts/a11y_check.py --only img-no-alt`

9. Never invent an `aria-*` attribute name. A typo (`aria-lable`) is silently
   ignored by assistive tech — no warning, no fallback, just missing metadata.
   *Enforced by:* `python3 scripts/a11y_check.py --only unknown-aria-attribute`

10. Meet WCAG 2.2 AA contrast: **4.5:1** for body text, **3:1** for large-scale
    text (≥18pt, or ≥14pt bold) and for UI-component/graphical boundaries. And
    color is never the only signal — pair it with an icon, text, or pattern.
    *Enforced by:* review

11. Trap focus inside a modal while it's open, restore focus to the trigger
    element on close, and move focus to the new content (usually an `h1` or
    the main landmark) on a client-side route change. None of this is free —
    React doesn't do it for you.
    *Enforced by:* review

12. Announce async updates a sighted user would notice visually (a toast, a
    save confirmation, a newly-loaded list) via a live region (`aria-live`,
    `role="status"`/`role="alert"`), or a screen-reader user never learns it
    happened.
    *Enforced by:* review

13. Respect `prefers-reduced-motion`. A parallax hero or a spinning loader
    with no reduced-motion guard can trigger vestibular symptoms, not just
    annoy.
    *Enforced by:* `python3 scripts/a11y_check.py --only animation-no-reduced-motion`

14. Meet the WCAG 2.2 target-size minimum: pointer targets at least **24×24
    CSS pixels**, or 24px of clear space around a smaller one (SC 2.5.8).
    Applies to icon buttons, close ("×") controls, and checkboxes alike.
    *Enforced by:* review

15. Treat automated tooling as a floor, not a pass. axe-core's own README
    states it finds **on average 57% of WCAG issues automatically** — the rest
    needs a keyboard-only pass and a screen-reader pass (VoiceOver/NVDA) before
    a component with real interaction ships.
    *Enforced by:* convention

## Verify

Diff-scoped; runs in well under a second on a typical component PR.

```bash
python3 scripts/a11y_check.py --list
python3 scripts/a11y_check.py --base origin/main
python3 scripts/a11y_check.py --base origin/main --strict   # advisories also fail

# just the four blocking checks
python3 scripts/a11y_check.py --only onclick-non-interactive,img-no-alt,form-field-no-label,control-no-accessible-name

# what no script can do -- run manually before merging a real interactive component
#   1. unplug the mouse: Tab through the component, Enter/Space to activate
#   2. turn on VoiceOver (Cmd+F5 on macOS) or NVDA, navigate the component
```

`a11y_check.py` is heuristic — regex plus a hand-rolled tag scanner, not a real
JSX/HTML parser (its own docstring says so). It cannot see runtime state: a
conditionally-applied `role`, whether an "icon" component secretly renders
text, whether a CSS class actually strips the focus ring in the browser. It
under-fires on ambiguous input by design — a missed violation is cheap, a false
positive is what gets a checker like this disabled. It complements, and does
not replace, `eslint-plugin-jsx-a11y` if your stack already runs one (Next.js
does, by default — see Sources) and an automated scan like `@axe-core/cli` or
`@axe-core/playwright`, which see the rendered DOM and catch classes this
static checker structurally cannot (computed contrast, actual focus order,
ARIA tree correctness).

## Failure modes

This skill rejects:

- **`<div onClick={...}>` instead of `<button>`** — the canonical defect: not
  focusable, not keyboard-operable, not announced as a control.
- **An icon-only `<button><TrashIcon /></button>` with no `aria-label`** — a
  screen reader announces "button", nothing else.
- **A form `<input>` with a placeholder and no `<label>`/`aria-label`** — the
  hint vanishes the instant the user starts typing, and it was never
  programmatically associated with the field in the first place.
- **`outline: none` shipped with no `:focus-visible` replacement** — every
  keyboard user loses the only signal of where focus is.
- **`<img src="...">` with no `alt`** — screen readers read the filename, or
  nothing.
- **A modal with no focus trap** — Tab walks the user out into page content
  behind a dialog they can't see is still "underneath."
- **A color-only status signal** (red text, no icon or label, for "invalid") —
  invisible to colorblind users and unannounced to screen readers.
- **An `aria-live` region missing from a toast/async-save component** — the
  update happens, and a screen-reader user has no idea.
- **A parallax/spin animation with no `prefers-reduced-motion` guard.**

**Honest limitations:** the checker is static-text heuristic, not a DOM
inspector — it cannot verify rules 2, 7, 10, 11, 12, or 14 mechanically. Those
need `review` or a runtime tool (axe, a keyboard pass, VoiceOver/NVDA). That
gap is real and is why rule 15 exists: 57% automated coverage means the other
43% is a human task, not a missing feature of this checker.

## Scale

`solo`: rules 1, 4, 5, 6, 8, 9 — fully mechanical, near-zero cost, catches the
defects a solo builder repeats across every new component.
`small-team (2-10)`: add 3, 13, and a keyboard-only pass before merging any new
interactive component (rule 15).
`org` / `high-blast-radius`: add 10, 11, 12, 14 and a scheduled screen-reader
pass; a public-facing org is also a legal-exposure surface (ADA/EN 301 549) —
that isn't this skill's claim to make, but the WCAG 2.2 AA numbers above are
the bar those regulations point to.

## Sources

- WCAG 2.2 success criteria, read directly from the spec source: `w3c/wcag@main`
  — `guidelines/sc/20/contrast-minimum.html` (1.4.3, 4.5:1 / 3:1 large text),
  `guidelines/sc/21/non-text-contrast.html` (1.4.11, 3:1 UI components),
  `guidelines/sc/20/use-of-color.html` (1.4.1), `guidelines/sc/20/focus-visible.html`
  (2.4.7), `guidelines/sc/22/target-size-minimum.html` (2.5.8, 24×24 CSS px).
- Automated-coverage figure: `dequelabs/axe-core@develop:README.md` — "With
  axe-core, you can find on average 57% of WCAG issues automatically."
- `mui/material-ui@master:packages/mui-material/src/Button/Button.test.js:1036`
  — a real production example of this skill's discipline: per-component tests
  named after WCAG success criteria (`2.1.2 No Keyboard Trap`, `2.4.3 Focus
  Order`), run in the component's own unit-test file on every CI run, not a
  separate end-of-pipeline audit.
- `vercel/next.js@canary:packages/eslint-config-next/package.json` —
  `eslint-plugin-jsx-a11y ^6.10.0` ships as a direct dependency of
  `eslint-config-next`, so any Next.js app using the default lint config gets
  baseline jsx-a11y rules without a separate decision.
- CI-gate adoption, measured this session against 9 corpus repos
  (`mui/material-ui`, `adobe/react-spectrum`, `vercel/next.js`,
  `bluesky-social/social-app`, `excalidraw/excalidraw`, `shadcn-ui/ui`,
  `calcom/cal.com`, `supabase/supabase`, `vercel/commerce`): **0 of 9** have a
  CI workflow file named for accessibility, axe, or Lighthouse. Where a11y
  testing exists at all, it's embedded in the framework default (jsx-a11y in
  `eslint-config-next`) or hand-written into a component's own test file (MUI),
  never a standalone audit job — the absence is the finding this skill acts on.
- `reviewers/nextjs-react.md` row 16 — the existing failure-mode entry this
  skill extends with concrete rules and a checker, not repeated verbatim here.
- ARIA attribute list (rule 9): `w3c/aria@main:index.html`, full states-and-
  properties index.
- `a11y_check.py`'s check shapes: `SOURCE: original`, built to detect exactly
  the failure classes named above; false-positive rate measured in
  `tests/test_a11y_check.sh`.
