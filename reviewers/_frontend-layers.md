# Frontend layers: the same component, badly layered then correctly layered

A before/after reference for `skills/frontend-architecture/SKILL.md`. Same
feature both times — an order checkout summary that fetches an order,
applies a promo code, and shows the total — so the difference is something
you can point at, not something you have to take on faith.

## Contents

| # | section | what it answers | size |
|---|---------|-----------------|------|
| 1 | [The layer contract, restated](#the-layer-contract-restated) | the three layers and the one allowed dependency direction | 12 lines |
| 2 | [Before: one file, three layers fused](#before-one-file-three-layers-fused) | what an AI-typical "just make it work" component looks like | 45 lines |
| 3 | [What's wrong, line by line](#whats-wrong-line-by-line) | which `fe_layers_check.py` rule catches each defect | 20 lines |
| 4 | [After: business layer](#after-business-layer) | pure, unit-testable pricing/validation rules, no React | 30 lines |
| 5 | [After: logic layer](#after-logic-layer) | the hook that owns fetching, storage, and orchestration | 30 lines |
| 6 | [After: presentation layer](#after-presentation-layer) | the component, now render-only | 25 lines |
| 7 | [Why this is worth the extra file](#why-this-is-worth-the-extra-file) | the concrete capability the split buys, not an abstract principle | 18 lines |
| 8 | [Sources](#sources) | what is grounded vs. this document's own synthesis | 10 lines |

## The layer contract, restated

| layer | files | owns | never contains |
|---|---|---|---|
| Presentation | `*.tsx` | props, view state (open/closed, hover, focus), JSX | I/O, money arithmetic, validation, storage access |
| Logic | `use*.ts` hooks | fetching, caching, form state, effects, subscriptions | JSX |
| Business | `.ts` in `domain/`/`lib/`/`core/`/`business/` | pure functions, types, pricing/eligibility/validation rules | any `react`/`next/*` import, any DOM global |

Dependency direction: **presentation → logic → business, never backwards.**
See `skills/frontend-architecture/SKILL.md` for the full contract and the
checker that enforces it; this file is examples only.

## Before: one file, three layers fused

```tsx
// src/components/OrderSummary.tsx -- everything in one component
import { useEffect, useState } from 'react';
import { z } from 'zod';

const promoSchema = z.object({ code: z.string().min(3) });

export function OrderSummary({ orderId }: { orderId: string }) {
  const [order, setOrder] = useState<{ subtotal: number } | null>(null);
  const [promoInput, setPromoInput] = useState('');

  useEffect(() => {
    fetch(`/api/orders/${orderId}`)
      .then((r) => r.json())
      .then(setOrder);
  }, [orderId]);

  if (!order) return <p>Loading…</p>;

  const savedCode = localStorage.getItem('promoCode') ?? '';
  const { code } = promoSchema.parse({ code: promoInput || savedCode });
  const discount = code === 'SAVE10' ? order.subtotal * 0.1 : 0;
  const tax = (order.subtotal - discount) * 0.08;
  const total = order.subtotal - discount + tax;

  return (
    <div>
      <input value={promoInput} onChange={(e) => setPromoInput(e.target.value)} />
      <p>Subtotal: {order.subtotal}</p>
      <p>Discount: {discount}</p>
      <p>Tax: {tax}</p>
      <p>Total: {total}</p>
    </div>
  );
}
```

This compiles, renders, and passes a manual click-through test. It also
cannot be unit-tested without a DOM and a network mock, cannot reuse the
discount rule anywhere else, and silently breaks if `localStorage` is
unavailable (SSR, a private-browsing edge case, a test runner).

## What's wrong, line by line

| defect | `fe_layers_check.py` rule | blocking? |
|---|---|---|
| `fetch(...).then(setOrder)` inside the component | `presentation-io` | yes |
| `localStorage.getItem('promoCode')` read directly | `presentation-storage-access` | advisory |
| `promoSchema.parse(...)` called inline in the component | `presentation-inline-validation` | advisory |
| `order.subtotal * 0.1`, `subtotal - discount + tax` — pricing math in JSX-adjacent code | `presentation-money-math` | yes |
| the whole fetch → validate → price pipeline runs on every render, untestable without mounting | `container-presenter-fused` (once this file grows) | advisory |

Every one of these is invisible in a code review that only asks "does it
render the right number" — the component *does* render the right number.
The defect is where the logic lives, not whether it currently works.

## After: business layer

```ts
// src/domain/pricing.ts -- pure, no React import, unit-testable with plain calls
import { z } from 'zod';

export const promoSchema = z.object({ code: z.string().min(3) });

export function applyDiscount(subtotal: number, code: string): number {
  return code === 'SAVE10' ? subtotal * 0.1 : 0;
}

export function computeTax(subtotal: number, discount: number): number {
  return (subtotal - discount) * 0.08;
}

export function computeTotal(subtotal: number, discount: number, tax: number): number {
  return subtotal - discount + tax;
}

export function validatePromoCode(raw: unknown): string {
  return promoSchema.parse(raw).code;
}
```

Every function here is `expect(applyDiscount(100, 'SAVE10')).toBe(10)` —
no render, no mock fetch, no DOM. This is also where `craft_check.py`'s
money-as-float rule applies once real currency is involved: these values
would become integer minor units in production code, not floats — that
shape rule belongs to `code-craft`, not duplicated here.

## After: logic layer

```ts
// src/hooks/useOrderSummary.ts -- orchestration: fetch, storage, business calls
import { useEffect, useState } from 'react';
import { applyDiscount, computeTax, computeTotal, validatePromoCode } from '../domain/pricing';

export function useOrderSummary(orderId: string) {
  const [order, setOrder] = useState<{ subtotal: number } | null>(null);

  useEffect(() => {
    fetch(`/api/orders/${orderId}`)
      .then((r) => r.json())
      .then(setOrder);
  }, [orderId]);

  function priceWithPromo(rawPromoInput: string) {
    if (!order) return null;
    const savedCode = localStorage.getItem('promoCode') ?? '';
    const code = validatePromoCode({ code: rawPromoInput || savedCode });
    const discount = applyDiscount(order.subtotal, code);
    const tax = computeTax(order.subtotal, discount);
    const total = computeTotal(order.subtotal, discount, tax);
    return { subtotal: order.subtotal, discount, tax, total };
  }

  return { order, priceWithPromo };
}
```

The fetch and the `localStorage` read are still here — that is correct.
This is the logic layer's job: know the transport, know the business layer,
never know JSX. `hook-renders-jsx` is the rule that keeps this file honest —
it fails the moment this hook is tempted to return a `<Spinner />`.

## After: presentation layer

```tsx
// src/components/OrderSummary.tsx -- render only
import { useState } from 'react';
import { useOrderSummary } from '../hooks/useOrderSummary';

export function OrderSummary({ orderId }: { orderId: string }) {
  const [promoInput, setPromoInput] = useState('');
  const { order, priceWithPromo } = useOrderSummary(orderId);

  if (!order) return <p>Loading…</p>;
  const pricing = priceWithPromo(promoInput);
  if (!pricing) return null;

  return (
    <div>
      <input value={promoInput} onChange={(e) => setPromoInput(e.target.value)} />
      <p>Subtotal: {pricing.subtotal}</p>
      <p>Discount: {pricing.discount}</p>
      <p>Tax: {pricing.tax}</p>
      <p>Total: {pricing.total}</p>
    </div>
  );
}
```

`promoInput` staying here is correct too — it is view state (what the user
has typed, not yet submitted), which the contract explicitly allows in the
presentation layer. The component now imports zero of: `fetch`, `zod`,
`localStorage`, or a pricing formula.

## Why this is worth the extra file

- **`applyDiscount`/`computeTax`/`computeTotal` are unit-tested directly** —
  no `render()`, no `act()`, no network mock. A pricing-rule change (a new
  promo tier, a tax-rate bump) is tested in milliseconds, not a browser.
- **`useOrderSummary` is reused** the moment a second surface needs the same
  order+promo logic (a checkout page and an order-confirmation email
  preview, say) without copying the fetch/validate/price pipeline.
- **`OrderSummary.tsx` is now a pure function of its hook's output** — a
  Storybook story or a snapshot test can render it with a fake `order`/
  `pricing` object and never touch `fetch` or `localStorage` at all.
- **The failure surfaces move to where they're cheapest to fix.** A wrong
  tax rate is now a one-line diff in `domain/pricing.ts` with a failing unit
  test pointing at it, not a bug report that starts with "the checkout page
  shows the wrong total."

## Sources

The layer contract, the checker, and the grounding citations (which real
repos separate this way, and how rare mechanical enforcement of it is) live
in `skills/frontend-architecture/SKILL.md`'s `## Sources` section — not
duplicated here. This file's before/after component is `SOURCE: original`,
written to make the contract visible rather than described.
