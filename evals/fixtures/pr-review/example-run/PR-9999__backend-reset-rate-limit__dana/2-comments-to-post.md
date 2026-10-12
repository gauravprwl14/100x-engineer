# PR 9999 — comments to post

> **In 10 seconds:** 4 comments for @dana: 2 inline, 2 general; 1 to ask someone else. Copy each **Paste this** box, or run `/pr-review post` to post A + B as one draft review only you can see. To change any of it first: `/pr-review adjust`.

Numbers match the action table in [README.md](README.md). Text in **Why (for you)** is for you, not the author.

## Quick index — by priority

Read top to bottom: what blocks the merge first, then what must be settled before rollout, then the rest. Comments with the same **Theme** overlap, so read them together and consider posting only the strongest one.

| Priority | # | Comment | Type | Severity | Theme | Related | Goes to |
|---|---|---|---|---|---|---|---|
| 1 · Blocks merge | [#1](#c1) | Cap is per sender IP, not per email address | issue | major | — | — | Inline |
| 2 · Before rollout | [#2](#c2) | How many API instances run in production? | question | major | — | — | Inline |
| 3 · Non-blocking | [#3](#c3) | Test the 4th call is refused | suggestion | minor | — | — | General comment |
| 3 · Non-blocking | [#4](#c4) | Small fixes, bundled (1) | nit | trivial | — | — | General comment |

## A) Line comments

Post inline on the changed line (Files changed tab), or let `post` do it.

<a id="c1"></a>
### 1 · issue (blocking) · inline on `limiter.ts` L10

**Where:** [`src/reset/limiter.ts` L10](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/limiter.ts#L10)

**Why (for you):** The issue is about flooding ONE inbox. Keyed on the IP, 2 IPs send 6 mails a minute to the same address.

**Paste this:**

> **issue (blocking):** The cap is keyed on the sender IP, so `--ips 198.51.100.7,203.0.113.9` still sends 6 mails a minute to `user@acme.test`; issue 9990 asks for 3 per address. Could we key it on the email instead?
>
> ```suggestion
>     const key = `reset:${email.toLowerCase()}`;
> ```

<sub>Change checked: applies cleanly — typecheck not run (no node_modules in the snapshot)</sub>

<a id="c2"></a>
### 2 · question (before rollout) · inline on `limiter.ts` L6

**Where:** [`src/reset/limiter.ts` L6](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/limiter.ts#L6)

**Why (for you):** Each server counts alone. With 4 servers the real cap is about 12 a minute, not 3. Fine for one server, wrong for many.

**Paste this:**

> **question (before rollout):** This `Map` lives in one process. If prod runs more than 1 instance (the LB spreads calls), the effective cap is 3 × instances. How many run today, and is a shared counter (e.g. Redis `INCR` with a 60 s TTL) planned before we turn this on?

## B) General PR comments

Post in the PR conversation (or the review summary); these are not on a changed line.

<a id="c3"></a>
### 3 · suggestion (non-blocking) · general PR comment · about `reset.controller.spec.ts` L4

**Where:** [`src/reset/reset.controller.spec.ts` L4](https://git.example.com/acme/widgets/blob/0a1b2c3d4e5f60718293a4b5c6d7e8f901234567/src/reset/reset.controller.spec.ts#L4) — not in this PR's diff, so it goes in the general comment

**Why (for you):** The only test checks the 1st call is allowed. Nothing proves the cap itself works.

**Paste this:**

> **suggestion (non-blocking):** The spec only checks that the 1st call passes. Could we add a case where the 4th call within 60 s returns `false`?
>
> ```diff
> --- a/src/reset/reset.controller.spec.ts
> +++ b/src/reset/reset.controller.spec.ts
> @@ -7,2 +7,8 @@
>    });
> +
> +  it('refuses the 4th call within 60 s', () => {
> +    const l = new ResetLimiter();
> +    [0, 1, 2].forEach((t) => l.allow('198.51.100.7', 'user@acme.test', t));
> +    expect(l.allow('198.51.100.7', 'user@acme.test', 3)).toBe(false);
> +  });
>  });
> ```

<sub>Change checked: applies cleanly — typecheck not run (no node_modules in the snapshot)</sub>

<a id="c4"></a>
### 4 · nit (non-blocking) · general PR comment

**Why (for you):** small things worth fixing but not worth a thread each; bundled into one comment.

- (1) Repo convention: no magic numbers. Named constants also make the cap easy to find.

**Paste this:**

> **nit (non-blocking):** A few small optional things:
>
> **(1)** Could `60000` and `3` become `WINDOW_MS` and `MAX_MAILS` constants? — `src/reset/limiter.ts` L11
>
> <details><summary>Proposed change</summary>
>
> ```diff
> --- a/src/reset/limiter.ts
> +++ b/src/reset/limiter.ts
> @@ -11,2 +11,2 @@
> -    const recent = (this.hits.get(key) ?? []).filter((t) => now - t < 60000);
> -    if (recent.length >= 3) return false;
> +    const recent = (this.hits.get(key) ?? []).filter((t) => now - t < WINDOW_MS);
> +    if (recent.length >= MAX_MAILS) return false;
> ```
>
> </details>

## C) Ask someone else

Not for the PR author: ask the named person, in the named place.

### 2 (also) · ask Infra on-call · Slack #infra

**Why (for you):** the answer to [#2](#c2) depends on Infra on-call, not only on the PR author.

**Say this to Infra on-call:**

> How many replicas does the `api` deployment run in production today (`kubectl get deploy api -o jsonpath='{.spec.replicas}'`)? We need it for the reset-mail cap in PR 9999.

## E) Praise (optional)

Goes at the top of the review summary when you post.

> **praise:** Nice that the refusal is a plain `429` — the UI follow-up can key on it directly.
