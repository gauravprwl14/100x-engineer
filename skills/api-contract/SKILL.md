---
name: api-contract
description: >
  Use when designing or reviewing a public or internal API — REST, GraphQL, or
  gRPC — its versioning scheme, error responses, idempotency, pagination, PATCH
  semantics, or deprecation of a field or endpoint. Use PROACTIVELY before
  shipping a new endpoint, changing a response shape, or removing/renaming a
  field. Not for the database schema underneath it — that is data-modeling,
  though a schema decision (an exposed internal id, a nullable-as-state field)
  routinely becomes an API contract problem.
---

# API contract design

A published API is a promise made to code you don't control and often can't see
— a mobile app already in app-store review, a partner's batch job, a webhook
consumer nobody remembers exists. Breaking that promise is a product decision
with a blast radius, not a refactor. This skill is about which changes are
breaking (more of them than intuition suggests), and what a contract has to
state explicitly so the client isn't left inventing the parts you didn't write
down.

## Trigger

**Fire when:** adding, changing, or removing a field/endpoint/error code on an
API surface consumed outside the immediate PR; choosing a versioning scheme;
designing pagination, PATCH, idempotency, or error shape; deprecating anything.

**Do not fire when:** the change is to a genuinely private, same-deploy-unit
function call with no external or cross-service consumer.

## Rules

1. A breaking change is a product decision, not an engineering one. It ships
   with a stated reason, a migration path for consumers, and — for anything
   with external consumers — sign-off from whoever owns that relationship, not
   just a green CI run.
   *Enforced by:* review

2. Version at exactly one boundary, chosen deliberately: a URL path segment
   (`/v2/...`), a media-type parameter (`Accept:
   application/vnd.api+json;version=2`), or a dated/custom header — and never
   mix schemes within the same API. Redefining a field's meaning under an
   unchanged version number is the same breaking change as removing the field.
   *Enforced by:* convention (one versioning scheme per API surface; a reviewer
   rejects a PR introducing a second)

3. These are breaking, mechanically, full stop: adding a required field,
   narrowing a type (`string` → `enum`, nullable → non-nullable), removing or
   renaming a field or an enum value, changing a previously-stable error code,
   tightening validation on a field that used to accept more. Detect them on
   the schema diff, not by reading the PR.
   *Enforced by:* `python3 scripts/schema_check.py --base <ref>` for the
   DB/ORM layer the response is built from; for the wire format itself use
   whatever your stack actually emits — `oasdiff breaking base.yaml
   head.yaml` (OpenAPI), `buf breaking --against '.git#branch=main'`
   (protobuf/gRPC), `npx graphql-inspector diff old.graphql new.graphql`
   (GraphQL)

4. Evolve additively. New fields are optional with a sane default meaning when
   absent; clients are written as tolerant readers that ignore fields they
   don't recognize; no client `switch`/`match` on a response enum without a
   default arm, because a server-extensible enum is a type the client must
   treat as open, not closed.
   *Enforced by:* review

5. Errors are `application/problem+json` (RFC 9457): a stable, machine-readable
   `type` (or a `code` extension) the client branches its logic on, plus a
   human `title`/`detail` the client must never parse for meaning. A new
   failure condition ships a new `type`; a wording change to `detail` is never
   a breaking change and must never be load-bearing for a client either.
   *Enforced by:* `grep -rln "application/problem+json" src/` (Verify block)
   plus review for consistency across endpoints

6. Idempotency keys are required on every unsafe verb that creates a
   side-effect-bearing resource — a charge, a transfer, a notification send.
   State the key's lifetime (Stripe: effectively the life of the resource) and
   what a replay within that window returns: the original response, unchanged,
   never a second execution.
   *Enforced by:* review

7. Pagination is a contract, not an implementation detail. Prefer a cursor for
   anything that can mutate while being paged — offset pagination silently
   skips or repeats rows when the underlying set changes mid-page. Enforce a
   max page size server-side regardless of what the client asks for, and state
   the stability guarantee (or its explicit absence) in the docs.
   *Enforced by:* review

8. Name your PATCH semantics explicitly: JSON Merge Patch (RFC 7386 — absent
   key means unchanged, `null` means delete) or JSON Patch (RFC 6902 —
   explicit `op`/`path`/`value` operations). Whichever you pick, "field absent"
   and "field explicitly null" must survive deserialization as two different
   things, or PATCH cannot express a deletion.
   *Enforced by:* review

9. Timeout, retry, and backpressure behaviour are contract terms, written down
   — the server's own timeout, which verbs are safe to retry, what a 429/503
   means for backoff. An unstated timeout is not "flexible"; it is a term the
   client will invent by observing failures, and it will invent one you don't
   like.
   *Enforced by:* review

10. Contract tests run against a real or recorded provider (consumer-driven
    contract testing, or a recorded-fixture replay) as part of CI — not only
    unit tests against an in-process mock that can drift from the real
    response shape undetected.
    *Enforced by:* convention (the mechanical check varies per stack — Pact,
    Dredd, a recorded-fixture diff — pick one and wire it into required CI)

11. Every deprecation carries a stated, published window and a machine-readable
    signal — `Deprecation`/`Sunset` response headers (RFC 8594), or a
    dated/versioned identifier the client is already sending. "We'll remove it
    eventually" is not a deprecation policy; it's a promise nobody can plan
    against.
    *Enforced by:* `grep -rn "Sunset:\|Deprecation:"` (Verify block) + review

12. An API response shape is not obligated to mirror the table shape underneath
    it. A raw sequential id, a nullable-column-as-state field, or an internal
    enum leaking into a public response are schema decisions (see
    `data-modeling`) that become permanent API contract debt the moment a
    client depends on them.
    *Enforced by:* review

## Verify

```bash
# ~1s: DB/ORM layer breaking-change patterns underneath the API response
python3 scripts/schema_check.py --base origin/main --strict

# wire-format contract diff -- use whichever this repo actually emits
git diff --stat origin/main -- '*.proto' 'openapi*.yaml' 'openapi*.json' '*.graphql'
oasdiff breaking base-openapi.yaml openapi.yaml            # OpenAPI/REST
buf breaking --against '.git#branch=main'                   # protobuf/gRPC
npx graphql-inspector diff old.graphql new.graphql          # GraphQL

# error responses are structured, not a message string the client has to parse
grep -rln "application/problem+json" src/ 2>/dev/null \
  || echo "no problem+json responses found -- confirm errors are machine-readable"

# anything marked deprecated actually emits a machine-readable signal
grep -rn "Sunset:\|Deprecation:" src/ 2>/dev/null \
  || echo "no Sunset/Deprecation headers found -- deprecations are undiscoverable by clients"
```

## Failure modes

This skill rejects:

- **A required field added to an existing response** with no version bump —
  every client that validates against the old schema now fails.
- **An enum value removed** instead of deprecated — any client with an
  exhaustive `switch` now has an unreachable-in-theory branch that is reachable
  in practice, or throws.
- **A generic `500` with a human sentence in `message`** that the client has to
  regex-match to decide what to do — no stable `type`/`code` at all.
- **`POST /charges` with no idempotency key support** — a client-side retry on
  a network timeout double-charges.
- **Offset pagination on a list that receives concurrent writes** — a row
  inserted during iteration shifts every subsequent page, and a row gets
  skipped or duplicated with nobody noticing until a reconciliation job does.
- **A PATCH endpoint where "omit the field" and "send `null`" do the same
  thing** — there is no way to express "leave this alone" vs "clear this."
- **An endpoint with no documented timeout**, so every client picks its own and
  the actual behaviour under load is whatever the slowest client's guess was.
- **"This field is deprecated" with no date, no header, and no removal plan.**

**Honest limitations:**
- `schema_check.py` sees the DB/ORM layer, not the wire format. A hand-written
  serializer can still introduce a breaking response change with no
  corresponding schema change — the OpenAPI/protobuf/GraphQL diff tools named
  above are what actually cover the wire contract, and none of them ship in
  this repo; they are named, not vendored, per `research/01-skill-contract.md`
  ("no command may be aspirational" — if your stack lacks one, that absence is
  itself worth recording).
- Nothing here can tell you whether a breaking change was *worth* making, only
  whether it was labelled as one. Rule 1's sign-off is `Enforced by: review`
  for exactly that reason.

## Next

If the field or shape in question is a schema decision more than an API one —
an exposed internal id, a nullable field standing in for a status enum — read
`data-modeling` next; rule 12 here is the seam between the two skills. Log a
versioning or deprecation decision with `python3 scripts/decide.py new`. Run
`bloat_check.py` and `design_drift.py` as usual while implementing (see
`feature-planning`).

## Scale

`solo`: rules 1, 3, 5, 6 — the ones where getting it wrong turns into a support
ticket or a double-charge before anyone reviews it.
`small-team (2-10)`: add 2, 4, 11 — a second versioning scheme or an
undocumented deprecation is cheap to avoid and expensive to unwind once two
people are shipping against the same API independently.
`org (10+)`: add 7, 9, 10 — contract testing in CI and a documented
timeout/retry contract matter once the API has consumers you don't talk to
daily.
`high-blast-radius` (payments, partner integrations, anything with a mobile app
already in the field): numeric deprecation SLAs, not "eventually" — GitHub
supports a REST API version for 24 months after its successor ships, with
`Deprecation`/`Sunset` headers during the window; Stripe instead pins each
integration to the dated API version it started on indefinitely, so nothing
breaks until the customer explicitly opts into a new version. Pick one model
deliberately; both are real, and "no model" is not a third option.

## Sources

- RFC 9457 (obsoletes RFC 7807), "Problem Details for HTTP APIs":
  `www.rfc-editor.org/rfc/rfc9457.txt` — the `type`/`status`/`title`/`detail`/
  `instance` member definitions and, verbatim, "Consumers SHOULD NOT parse the
  `detail` member for information" (§3.1.4).
- PATCH semantics as three distinct, named content types (JSON Patch RFC 6902,
  JSON Merge Patch RFC 7386, and Kubernetes' own Strategic Merge Patch), and
  `null` being explicitly incompatible with JSON Merge Patch's delete
  semantics:
  `kubernetes/community@master:contributors/devel/sig-architecture/api-conventions.md`,
  "PATCH operations" and "Nullable" sections.
- DB-level idempotency (409 on duplicate create) and optimistic concurrency
  (`resourceVersion` → 409 on conflicting update) as the general pattern
  idempotency keys extend to the write path: same document, "Idempotency" and
  "Concurrency Control and Consistency" sections.
- Idempotency keys plus automatic network-retry-with-backoff since v13, and a
  major-version release pinned to a single dated API version with a published
  migration guide per breaking release: `stripe/stripe-node@master:README.md`,
  `stripe/stripe-node@master:CHANGELOG.md`.
- Real deprecation window, dated: "Node 16 support is deprecated and will be
  removed in the next scheduled major release (March 2026)" —
  `stripe/stripe-node@master:CHANGELOG.md`.
- Real deprecation window, GitHub's: API versions supported for 24 months
  after a newer version ships, `Deprecation` header per RFC 7231 and `Sunset`
  header per RFC 8594 during the closing-down window, `410 Gone` after:
  `github/docs@main:content/rest/about-the-rest-api/api-versions.md`.
- A public API description split into a stable artifact and one explicitly
  "subject to breaking changes on the `main` branch" — i.e., which parts of
  the contract are and aren't promises yet: `github/rest-api-description@main:README.md`.
- Idempotency-key/backoff/pagination/timeout enforcement implementation:
  `scripts/schema_check.py` (shared with `data-modeling`), `SOURCE: original`.
