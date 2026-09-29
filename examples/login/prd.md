# login — PRD

| field | value |
|---|---|
| kind | auth |
| stack | NestJS, Postgres, Redis |
| linked spec | [specs/login/spec.md](../../specs/login/spec.md) |
| created | 2026-09-29 |
| status | **ready** |

Worked example for `python3 scripts/prd.py`. It exists to show what a complete PRD
looks like above `specs/login/spec.md`, and to be the fixture `prd.py align` scores
against. Every table below is machine-audited by
`python3 scripts/prd.py audit examples/login`.

## 1. Problem

| field | answer |
|---|---|
| who has this problem | returning users of the product who already have an account |
| what they do today | nothing — there is no authenticated session; every request is anonymous, so any per-user feature (saved data, personalization, admin controls) is blocked on this shipping first |
| what "better" means, measurably | see Success metrics below |

Today the app cannot tell one visit from the next, so nothing that requires "this is
the same user as last time" can ship. Login is the smallest thing that unblocks all
of it, which is also why it is easy to over-scope — see Options analysis for what
this PRD deliberately does not try to solve at the same time.

## 2. Users

| # | segment | current workaround | why they would adopt this |
|---|---|---|
| U1 | returning users with an account | none — they cannot return to per-user state today | it is the only way to access anything tied to their account |
| U2 | on-call / security response | manually rotating credentials or taking the service down | immediate session revocation (password change, admin ban) instead of a full incident |

## 3. Success metrics

| # | metric | target (must include a number) | baseline | measurement method |
|---|---|---|---|---|
| M1 | Login success rate for well-formed email+password attempts | >=98% | N/A — new feature | login-attempt telemetry, with regressions caught by the integration test suite (spec V4) before they reach production |
| M2 | Session revocation SLA — logout, password change, or admin ban takes effect within one request | 100%, zero misses | N/A — new feature | `decide.py verify` re-checks the revocation assumption (spec V7, ADR-0001 A1) on every run; behaviour covered end-to-end pre-PR |
| M3 | OAuth sign-in completion rate (started vs. finished) | >=90% | N/A — new feature | verified against a real provider in the integration suite backed by redis session creation (spec V4) |

## 4. Constraints

| constraint | value |
|---|---|
| team size and skills | 2 backend engineers who already ship NestJS services; no dedicated security engineer |
| existing stack | NestJS, Postgres, Redis — Redis is assumed present in every deploy target (ADR-0001 assumption A2) |
| deadline | none hard-stated; product wants it ahead of a competitor's OAuth-only push |
| budget | no new paid infrastructure — must reuse the existing Redis cluster |
| compliance / regulatory | none named yet; password storage is built as if SOC2 applied (argon2id, no plaintext in logs — spec E24/E25) |
| what cannot change | the `/auth/*` route prefix is already referenced by the mobile client; the `users` table's primary key type |

## 5. Requirements

What the recommended solution must satisfy. This is what `prd.py align` checks
against `specs/login/spec.md`'s in-scope table.

| # | requirement | why it matters |
|---|---|---|
| R1 | Returning users can sign in with email and password and receive a session | the core ask — nothing else in this PRD matters if this does not work |
| R2 | A signed-in user can request logout on a single device or on all devices without affecting the others | single-device mental models under-serve anyone with two devices, which is most users |
| R3 | Session revocation is immediate on password change or an admin ban | a revocation that takes minutes is a security incident window, not a feature |
| R4 | Failed login attempts trigger throttling and temporary account lockout, matching brute-force protections | credential stuffing is the single most common attack on a login endpoint |
| R5 | Users can sign in via at least one OAuth provider in addition to local credentials | a meaningful fraction of the target users expect "sign in with Google" and will bounce without it |

## 6. Options analysis

Scored with the `approach-selection` rubric (`skills/approach-selection/SKILL.md`):
reversibility x3, blast radius x3, moving parts x2, already-in-use x2, exit cost x1,
fit x1, each 1-5. This section answers **build vs. buy vs. do nothing** — it does
NOT re-decide session mechanism, password hashing, or session storage; those are
spec-level decisions already recorded in `specs/login/spec.md` §5 and
[ADR-0001](../../decisions/ADR-0001-session-strategy-for-login.md). Re-deriving them
here would duplicate the spec layer this PRD feeds.

| # | option | pros | cons | reversibility x3 | blast radius x3 | moving parts x2 | already-in-use x2 | exit cost x1 | fit x1 | weighted score |
|---|---|---|---|---|---|---|---|---|---|---|
| O1 | Do nothing / smallest possible change | zero new moving parts; zero new blast radius; ships today | doesn't solve the problem — only choose this if the cost of the status quo is now acceptable, which is itself a decision worth recording | 5 | 5 | 5 | 5 | 5 | 1 | 56 |
| O2 | Build first-party session-based login in NestJS (opaque server session + Redis) | reuses the existing NestJS/Postgres/Redis stack; full control over UX, throttling, and revocation timing | the team owns the password-storage security surface (hashing, lockout tuning, breach response) forever | 3 | 3 | 2 | 4 | 2 | 5 | 37 |
| O3 | Delegate identity to a third-party provider (e.g. a hosted auth service) | no password-storage liability; MFA/SSO available later with no extra build | new paid vendor outside the "no new paid infra" constraint; adds a moving part (network hop, webhook sync) nobody on the team has operated | 2 | 4 | 1 | 1 | 1 | 4 | 27 |

## 7. Recommendation

| field | answer |
|---|---|
| chosen option | O2 — build first-party session-based login in NestJS |
| single deciding factor | the budget constraint rules out a new paid identity vendor, and O2 is the only option scoring well on already-in-use — the team ships NestJS/Redis today, which O3 cannot claim regardless of its lower operational risk on paper |
| what would change it | if compliance later requires enterprise SSO/SAML the team cannot reasonably build in-house (see Out of scope O4), O3 or a hybrid becomes the better score — that is a constraints-table change, not a re-litigation of this analysis |

## 8. Risks

| # | risk | likelihood (1-5) | impact (1-5) | L x I | mitigation |
|---|---|---|---|---|---|
| RI1 | Login success rate is lower than the 98% target because of unexpected friction (captcha, throttling false positives) | 2 | 3 | 6 | ship behind the `auth.v2_login` flag to a 5% cohort first; watch `login.e2e-spec.ts` and the throttle e2e pass rate before widening rollout |
| RI2 | Implementation estimate is wrong because the spec's 31 edge cases (specs/login/spec.md §7) surface more OAuth/session issues than scoped here | 3 | 2 | 6 | phase 1 ships email+password only (see Phasing); OAuth and lockout are separate phases with independent kill criteria, so scope growth in one does not block the others |
| RI3 | The existing codebase already has undocumented auth assumptions (e.g. routes that assume a dev-only bypass) that make O2 more expensive than the 37-point score assumed | 2 | 4 | 8 | run `scripts/decide.py trace` and grep the codebase for the current bypass before starting; §11 records what was found for this feature |

## 9. Phasing

Phase 1 is the smallest slice that proves the core assumption, not the smallest
slice of the full feature.

| # | phase | ships | proves | kill criteria |
|---|---|---|---|---|
| P1 | Phase 1 — core session (R1-R3) | `POST /auth/login`, `POST /auth/logout`, immediate revocation on password change / admin ban | that an opaque server session with Redis-backed revocation (ADR-0001) is fast and simple enough in production | login success rate <90% after two weeks at 5% cohort, or Redis is not reliably present in the deploy target (falsifies ADR-0001 A2) — stop and re-open the session-storage decision before phase 2 |
| P2 | Phase 2 — throttling and lockout (R4) | per-account and per-IP throttling, temporary lockout | that lockout stops credential stuffing without locking out real users | false-lockout rate >1% in the first week |
| P3 | Phase 3 — OAuth (R5) | Google sign-in | that the "identity source: both" decision (spec D5) is worth the added provider-adapter complexity | fewer than 5% of new logins use OAuth after a month — deprioritize further providers |

## 10. Out of scope

| # | explicitly out of scope |
|---|---|
| X1 | registration / signup |
| X2 | password reset and email verification |
| X3 | MFA / TOTP |
| X4 | SSO / SAML for enterprise tenants |
| X5 | device / session management UI |

## 11. Existing-code note

This PRD was written **after** `specs/login/spec.md` and `examples/login/src/*.ts`
already existed — reverse-engineered from the shipped spec and code rather than
preceding them, which is the common case in an existing codebase (see
`skills/solution-architecture/SKILL.md`, "Reverse-engineering a PRD from existing
code"). Each section above traces to something observable: the constraints reflect
what `examples/login/src/session.store.ts` and ADR-0001 already assume about Redis;
the requirements restate `specs/login/spec.md` §2's in-scope table in product terms;
Options O2/O3 reflect the stack actually running (NestJS, no identity vendor
integration present anywhere in the codebase).

The success metrics are the one section that is **not** reverse-engineered — they are
proposed, not measured. Nothing in `examples/login/src/*.ts` or
`specs/login/spec.md` emits the telemetry M1-M3 would need. That gap is real and is
exactly the divergence this tool is meant to surface: the spec was audited as
"ready" and the code passes its tests, but the product success criteria were never
instrumented. `prd.py align` cannot detect this particular gap — a metric with a
plausible-sounding measurement method still passes if the words match; only running
the measurement method and finding no data source would catch it. That limitation is
stated here rather than hidden.
