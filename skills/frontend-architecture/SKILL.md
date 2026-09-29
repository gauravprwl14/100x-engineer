---
name: frontend-architecture
description: >
  Use when building or reviewing any React/TypeScript feature — a page, a form, a
  dashboard widget, a list with actions — to keep presentation, logic and business
  rules in separate files instead of one component. Fires on a new/changed `.tsx`
  component, a new `use*` hook, or any change touching money, tax, discount,
  validation, or a `fetch`/API call from inside a component. Covers what
  `code-craft` (function shape) and `reviewers/nextjs-react.md` (framework failure
  modes, server/client boundary, hydration) do not: WHICH FILE a piece of logic is
  allowed to live in, and which direction imports may point. Use PROACTIVELY before
  writing a component that fetches data, computes a total, or validates input.
---

# Frontend architecture

A React component that fetches, computes tax, and renders in one file is not one
defect — it is three defects wearing one file extension: it can't be unit-tested
without a DOM, it can't be reused with a different data source, and every future
change to the fetch logic risks breaking the markup next to it. This skill draws
the line mechanically: three layers, one allowed direction of dependency.

## Trigger

**Fire when:** writing or reviewing a `.tsx` component; adding a `use*` custom
hook; any diff touching money/tax/discount/validation/date computation in a
frontend file; a component grows a `useEffect` that fetches or transforms data.

**Do not fire when:** the change is markup-only styling (no new state, no new
data dependency), or the stack has no React/TSX in the diff — see
`reviewers/nextjs-react.md` for Next.js-specific server/client-boundary and
hydration failure modes, which this skill does not duplicate.

## The three layers

| layer | files | may contain | may NOT contain |
|---|---|---|---|
| **Presentation** | `*.tsx` components | props, local view state (open/closed, hover, focus), JSX | `fetch`/`axios`/`.then`, business rules, money/tax arithmetic, validation logic, date/timezone computation, retry logic, direct storage access, backend response shapes |
| **Logic** | `use*.ts` hooks | data fetching via a client, caching, form state, derived state, effects, subscriptions | JSX — a hook that renders is a component wearing a hook's name |
| **Business/domain** | plain `.ts` in `domain/`, `lib/`, `core/`, `business/` | pure functions, types, money/pricing/eligibility/validation rules, state machines | any `react`/`next/*` import, any DOM global (`window`, `document`, `localStorage`) |

Dependency direction: **presentation → logic → business, never backwards.** A
business module importing React is always a defect — it means domain logic
cannot be unit-tested without mounting a component. See
`reviewers/_frontend-layers.md` for the same component shown badly layered and
then correctly layered, so the difference is visible, not described.

## Rules

1. A `.tsx` component never calls `fetch`/`axios`/an API client method, and never
   embeds a raw backend URL. If a component needs data, it calls a hook that
   returns it.
   *Enforced by:* `python3 scripts/fe_layers_check.py --only presentation-io`
   (**blocking**)

2. A `.tsx` component never does arithmetic on a money/tax/discount identifier
   (`price`, `amount`, `total`, `tax`, `discount`, `fee`). If the UI needs a
   computed total, the business layer computes it and the component displays the
   result.
   *Enforced by:* `python3 scripts/fe_layers_check.py --only presentation-money-math`
   (**blocking**)

3. A business module (`domain/`, `lib/`, `core/`, `business/`) never imports
   `react`, `next/*`, or touches a DOM global. If it needs to, it is not a
   business module — move it.
   *Enforced by:* `python3 scripts/fe_layers_check.py --only business-imports-react`
   (**blocking**)

4. A `use*.ts` hook never returns JSX. A hook that renders has become a component
   with the wrong file suffix, and loses every benefit of being a hook (reuse
   across markup, easy mock in a non-DOM test).
   *Enforced by:* `python3 scripts/fe_layers_check.py --only hook-renders-jsx`
   (**blocking**)

5. A `useEffect` body that fetches, transforms, or subscribes belongs in a named
   hook, not inline in a component — a long inline effect is the leading
   indicator that logic never got extracted.
   *Enforced by:* `python3 scripts/fe_layers_check.py --only large-use-effect`
   (advisory, default 15 lines)

6. A component file should not simultaneously be long AND own more than a
   handful of `use*` calls — that shape is a container and a presenter fused
   into one file, and it is the single hardest shape to review or test.
   *Enforced by:* `python3 scripts/fe_layers_check.py --only container-presenter-fused`
   (advisory, default >200 lines and >3 `use*` calls)

7. A component never reads `localStorage`/`sessionStorage`/`document.cookie`
   directly — a hook wraps it, so the storage mechanism can be swapped or mocked
   without touching markup.
   *Enforced by:* `python3 scripts/fe_layers_check.py --only presentation-storage-access`
   (advisory)

8. A component that imports `zod`/`yup`/`joi` and calls `.parse`/`.validate`
   itself has put validation in the wrong layer — the schema and the parse call
   belong in the business layer; the component reads a validated value or an
   error the logic layer already produced.
   *Enforced by:* `python3 scripts/fe_layers_check.py --only presentation-inline-validation`
   (advisory)

9. Naming, function length, parameter count and general shape inside any of the
   three layers is `code-craft`'s job, not this skill's — apply both, don't
   duplicate one inside the other.
   *Enforced by:* convention (cross-reference to `skills/code-craft/SKILL.md`)

## Verify

```bash
# diff-scoped: safe on a large existing codebase (regex + brace balancing, ~1-2s)
python3 scripts/fe_layers_check.py                        # all checks vs HEAD
python3 scripts/fe_layers_check.py --base origin/main
python3 scripts/fe_layers_check.py --strict                # advisory findings also fail
python3 scripts/fe_layers_check.py --only presentation-io,business-imports-react
python3 scripts/fe_layers_check.py --effect-lines 20 --file-lines 250 --hook-calls 4

# the reference doc: the SAME component badly layered, then correctly layered
sed -n '1,80p' reviewers/_frontend-layers.md

# prove the checker itself works (49 assertions, ~24 clean-file false-positive
# checks — the important half, ~2s)
bash tests/test_fe_layers_check.sh
```

## Failure modes

This skill rejects:

- **`fetch('/api/orders').then(setOrders)` inside a component's `useEffect`** —
  presentation performing I/O; the component now can't be tested or reused
  without a network mock, and it has no cache/retry/dedupe story.
- **`const grandTotal = total + tax;` typed directly in JSX** — the tax rule now
  lives in a component and is untestable without mounting one; move it to
  `domain/pricing.ts`.
- **`domain/pricing.ts` importing `useState` "just to memoize a lookup table"** —
  the moment a business module imports React, it can no longer be unit-tested
  with plain function calls, which was the entire point of having the layer.
- **`useOrderData.ts` returning `<Spinner />` for the loading case** — a hook
  rendering markup; the loading UI now can't be swapped per screen without
  forking the hook.
- **A 340-line `Dashboard.tsx` with 7 `useState`/`useEffect`/`useMemo` calls
  inline** — container and presenter fused; nobody can review the data-fetching
  logic without also reading 300 lines of JSX, or vice versa.
- **A component reading `localStorage.getItem('token')` directly** — swapping
  storage (cookie, IndexedDB, a mock in tests) now requires touching every
  component that reads it, instead of one hook.

## Scale

`solo`: rules 1-4 (the blocking set) — the cost of an untestable component is
paid by the same person who wrote it, on the very next bug fix. `small-team
(2-10)`: add rules 5-8 — a second person now has to review the diff without
being able to ask the author "wait, why is tax computed here." `org (10+)`: this
becomes the boundary a mechanical linter should also enforce
(`eslint-plugin-boundaries`, `dependency-cruiser`) — see Sources for how rare
that actually is even at scale.

## Sources

- `owner/reactive-resume` (cited via `skills/typescript-verification/SKILL.md`,
  rule 5, and `research/30-findings-js-verification.md`) — the **only** repo in
  a 72-repo JS/TS corpus survey with a machine-enforced cross-package import
  boundary (Turborepo `boundaries` + Grit). Everyone else in that corpus
  documents layering intent in prose and lets it erode.
- `research/36-findings-antibloat-in-practice.md` §"Architectural boundary
  rules (verbatim)" — `eslint-plugin-boundaries` (the purpose-built tool for
  exactly this layer problem) has **zero** flagship adoption across 8 repos
  checked specifically for it (Ghost, backstage, nx, nuxt, ant-design, qwik,
  mermaid, Trilium). Real boundary enforcement, where it exists at all, is
  hand-rolled `dependency-cruiser`/`no-restricted-imports`, and it enforces
  *package*-level boundaries (frontend-to-server-via-proxy-only in
  `TryGhost/Ghost:.dependency-cruiser.cjs`), not the presentation/logic/business
  split *within* a single frontend app that this skill targets — that narrower
  boundary has **no purpose-built enforcement found anywhere in the survey**.
- Real presentation/logic/business splits, grounded via direct repository
  inspection: `supabase/supabase:apps/studio/data/` (a dedicated directory of
  `use*` React Query hooks — `projects/project-detail-query.ts` exports
  `useProjectDetailQuery`, `database/table-definition-query.ts` follows the
  same shape — wrapping every server call, kept separate from
  `apps/studio/components/`); `bluesky-social/social-app:src/state/` versus `src/view/` — an explicit,
  named top-level split (verified: both are real sibling directories under
  `src/`), not just an informal convention. Corrected on verification: `state/`
  is not universally JSX-free — most of it is plain `.ts` (`state/queries/*.ts`,
  `state/session/reducer.ts`, `session-core.ts`) but a handful of files
  (`state/a11y.tsx`) are React Context `Provider` components, which is a
  defensible fourth shape (a thin logic-layer wrapper that must be a component
  to use `createContext`) this skill's three-layer contract doesn't name
  separately — noted rather than papered over; `payloadcms/payload:packages/payload/package.json`
  — the core package (types, field validation, access-control logic) does
  **not** list `react` as a dependency at all, while `packages/ui` does; the
  split is enforced by *package* boundaries (a stronger mechanism than a lint
  rule, but only available because it is already a monorepo) rather than by
  a checked-in rule inside a single app.
- `TanStack/query:docs/framework/react/guides/queries.md` — corrected on
  verification: the docs' own minimal example calls `useQuery` directly
  inside `function App()`, not wrapped in a named hook, so "every example
  uses a custom hook" was wrong and is not claimed. What the docs *do*
  recommend for reuse is `docs/framework/react/guides/query-options.md`'s
  `queryOptions()` factory — a plain function (no React) that centralizes
  `queryKey`/`queryFn` outside the component, called as
  `useQuery(groupOptions(1))`. `supabase/supabase:apps/studio/data/projects/
  project-detail-query.ts` shows the stronger, further step production code
  actually takes: `export const useProjectDetailQuery = (...) => useQuery(...)`
  — the fetch itself is named and hook-wrapped, not just its options. Rules 1
  and 5 above make the supabase shape mechanical, not the bare docs example.
- `vercel/commerce` (cited fully in `reviewers/nextjs-react.md`) — `lib/`
  (business/data-shaping) kept separate from `components/`; no `.tsx` in
  `lib/`.
- `scripts/fe_layers_check.py`'s 8 diff-scoped checks and
  `tests/test_fe_layers_check.sh`'s 49 assertions (24 clean-file false-positive
  checks): `SOURCE: original` — no surveyed repo runs a purpose-built checker
  for this specific three-layer split; built because the survey found the gap,
  not a tool to match.
