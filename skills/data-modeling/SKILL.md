---
name: data-modeling
description: >
  Use when designing or reviewing a database schema, ORM model, or migration —
  new tables, money/currency columns, soft delete, audit trails, state machines,
  multi-tenant tables, or PII columns. Use PROACTIVELY before writing a migration,
  a Prisma model, a SQLAlchemy/Django model, or a TypeORM entity, and when
  reviewing someone else's. Not for API request/response shape — that is
  api-contract, the schema's external face.
---

# Data modeling

A schema outlives the code that wrote it. The migration ships, the invariant it
should have enforced doesn't, and eighteen months later a backfill script, a
support engineer's console session, or a second service writes a row that the
application layer would never have allowed. This skill is about which decisions
belong in the schema itself, because those are the ones that survive the code
that made them.

## Trigger

**Fire when:** writing or reviewing a migration, a Prisma `model` block, a
SQLAlchemy/Django model, a TypeORM entity, or any DDL; adding a money, PII, or
tenant-scoped column; adding a nullable column to an existing table; designing
soft delete or an audit trail.

**Do not fire when:** the change is read-only (a query, a report) with no schema
impact, or the change is to the API layer only — that's `api-contract`.

## Rules

1. Money is an integer minor-unit count or a fixed-point decimal, **never** a
   float, and the currency travels in the same row as the amount — never a
   global default. Rounding direction and precision are a written decision, not
   an accident of the language's float implementation.
   *Enforced by:* `python3 scripts/schema_check.py --only money-float` (blocking),
   `--only money-currency` (advisory)

2. Invariants live in the schema — `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY`,
   exclusion constraints — not only in application code. Code-only uniqueness is
   a race; two concurrent inserts both pass the app-level check before either
   commits.
   *Enforced by:* review

3. Every new table has a primary key, and no public API response exposes a raw
   sequential/serial internal id — a bigserial id lets any client enumerate
   every row by incrementing it. Use UUIDv7 or ULID (time-ordered, so the
   primary-key index still clusters on insert, unlike UUIDv4 which scatters
   every write across the whole index) or a separate public identifier.
   *Enforced by:* `python3 scripts/schema_check.py --only new-table-pk` (blocking
   on missing PK); the id-exposure half is *Enforced by:* review

4. `created_at`/`updated_at` are conveniences, not an audit trail — they say
   *when*, never *who*, *what changed*, or *what it was before*. A real audit
   trail is its own immutable, append-only table (actor, action, before, after,
   timestamp) with different retention and tamper-evidence guarantees than
   application logs, which rotate and are not admissible as a record of intent.
   *Enforced by:* `python3 scripts/schema_check.py --only new-table-created-at`
   (advisory, presence only — it cannot check immutability)

5. A financial or otherwise regulator-visible record is not `UPDATE`d in place;
   model it as an append-only ledger of immutable postings, or as bi-temporal
   rows (valid-time vs transaction-time) if you must support "what did we
   believe on date X". An `UPDATE` on a balance is usually the modelling error
   that reconciliation later has to explain.
   *Enforced by:* review

6. Soft delete (`deleted_at`) is not an archive and is not free: every read path
   must remember to filter it, and a naive `UNIQUE` constraint now allows a live
   row to collide with a "deleted" one unless the constraint is made partial
   (`WHERE deleted_at IS NULL`). Move rows you don't need queried against to an
   archive table instead of flagging them in place.
   *Enforced by:* review

7. A nullable column is a smell, not a default. Ask what the `NULL` means before
   adding it: usually either two entities got merged into one table, or a state
   machine got flattened into a bag of optional fields. A field that's one of a
   mutually-exclusive set (a "union") should look like one — not four
   independently-nullable columns where only one is ever set.
   *Enforced by:* review

8. Enumerate legal states explicitly (a `CHECK`/enum constraint, not a free-text
   column), forbid illegal transitions in the database where the DB can express
   it, and never infer current state from a combination of nullable timestamp
   columns (`approved_at`, `rejected_at`, `cancelled_at` all `NULL` is not a
   state, it's an ambiguity waiting for a bug).
   *Enforced by:* review

9. Normalize by default. Denormalize only as a deliberate, written decision that
   names the invalidation cost — which write paths must now update two places,
   and how staleness will be detected.
   *Enforced by:* `python3 scripts/decide.py new "<denormalization>" --affects "<glob>"`
   (convention: reviewers reject an un-recorded denormalization on sight)

10. Every table that can be read by more than one tenant carries `tenant_id` (or
    equivalent), and every unique constraint and every index built for a lookup
    path includes it. A unique index that omits the tenant column is not just a
    missing optimization — it is a promise that no two tenants can ever collide
    on that value, which is almost never true and is a cross-tenant leak the
    day it's false.
    *Enforced by:* `python3 scripts/schema_check.py --only tenant-index` (blocking)

11. A foreign-key column has an index on the referencing side. Most databases do
    not create one automatically for you (Postgres/SQLAlchemy do not; Django's
    `ForeignKey` does).
    *Enforced by:* `python3 scripts/schema_check.py --only fk-index` (advisory)

12. A destructive change (`DROP COLUMN`, `DROP TABLE`, a narrowing `ALTER COLUMN
    ... TYPE`) never ships in the same migration as an additive one. Old code
    must be able to run against the new schema for the length of a deploy —
    expand in one migration, contract in a later one once nothing reads the old
    shape.
    *Enforced by:* `python3 scripts/schema_check.py --only expand-contract`
    (blocking)

13. PII columns are classified on the way in (what regulatory category, what
    residency requirement), and high-sensitivity fields are encrypted or
    tokenized at the field level, not just covered by disk-level encryption at
    rest. State explicitly how "right to erasure" is honored against anything
    append-only — you cannot delete a row from an immutable ledger without
    breaking the ledger's own invariant, so the honest answer is usually
    cryptographic erasure (destroy the key for that subject) or detach-and-
    tombstone (replace PII with a reference, keep the immutable amounts), not
    "we'll figure it out when Legal asks."
    *Enforced by:* review

## Verify

```bash
# diff-scoped, ~1s on a normal migration/schema diff
python3 scripts/schema_check.py --base origin/main
python3 scripts/schema_check.py --base origin/main --strict     # advisories fail too
python3 scripts/schema_check.py --list                          # see all checks

# record a denormalization or any other departure from the default
python3 scripts/decide.py new "Denormalize order totals" --affects "src/orders/**"

# if the stack has one, run its own migration linter too -- this tool is not a
# substitute for strong_migrations / squawk / django's makemigrations --check
```

## Failure modes

This skill rejects:

- **A `price`/`amount`/`balance` column typed `FLOAT`, `REAL`, or `DOUBLE`.**
  Floats cannot represent most decimal currency amounts exactly; the rounding
  error compounds silently until reconciliation fails.
- **A money column with no currency column next to it** — `amount: 500` means
  nothing without knowing if it's USD cents or JPY yen.
- **A new table with no primary key**, or one whose public API leaks a raw
  incrementing id.
- **A migration that drops a column and adds one in the same file** — the
  expand/contract violation that breaks the currently-running old code.
- **A unique index on a multi-tenant table that omits the tenant column** — two
  different tenants' data colliding on a "unique" value.
- **A foreign key with no index on the referencing column** — every cascade
  delete and every join on that FK does a sequential scan.
- **`approved_at`/`rejected_at`/`cancelled_at` all nullable on the same row**
  instead of a `status` enum — a state that has to be inferred is a state that
  gets inferred wrong.
- **Soft delete with a plain (non-partial) `UNIQUE` constraint** — a new "foo"
  can never be created again once one is soft-deleted.

**Honest limitations:**
- `schema_check.py` reads the diff, not the running database — it cannot see
  constraints that exist only via an ORM-level validator, and it cannot tell
  you whether a `CHECK` you added is the *right* invariant, only whether new
  tables/columns follow the shapes above.
- Tenant-index detection is scoped to a single migration/schema file — a new
  index added in a migration that does not also declare the table's tenant
  column will not be flagged, because the tool has no whole-schema context.
  This is a deliberate false-negative bias: the alternative is a whole-repo
  schema loader, which is out of scope for a diff-scoped stdlib tool.
- ORM coverage is SQL, Prisma, and Python (Django-style and SQLAlchemy-style)
  models. TypeORM, Sequelize, and Medusa-style JS/TS model files are not yet
  covered — absence, not a claim they're fine.

## Next

Read `api-contract` before the schema decisions above reach an API response —
an internal id exposed in a URL, or a nullable-field-as-state-machine leaking
into JSON, are both schema smells that become API contract problems the moment
a client depends on them. Log any departure from a default here with
`python3 scripts/decide.py new`. Run `bloat_check.py` and `design_drift.py` as
usual while implementing (see `feature-planning`).

## Scale

`solo`: rules 1, 3, 8, 12 — the ones a solo engineer has no reviewer to catch.
`small-team (2-10)`: add 2, 10, 11 — DB-level invariants and tenant isolation
stop being optional once more than one person writes migrations.
`org (10+)`: add 4, 5, 9 as reviewed process — the audit trail and ledger
modelling rules are cheap when designed in and expensive to retrofit onto a
table with production rows and five years of `UPDATE`s.
`high-blast-radius` (fintech, health, anything regulated): rule 13 is not
optional, and rule 5's bi-temporal / append-only guidance stops being "nice to
have" and starts being what a SOC 2 or PCI auditor will ask to see.

## Sources

- Money as `(Decimal, currency)`, never float:
  `beancount/beancount@master:beancount/core/amount.py` — `Amount` is a
  `NamedTuple[Decimal, str]`.
- Money as integer minor units with currency/precision travelling with the
  amount: `formancehq/ledger` README — postings use `"amount":100,
  "asset":"USD/2"`, an atomic multi-posting transaction model built on
  Postgres, programmable via the `numscript` DSL.
- Money as a fixed-point `bigNumber()` plus a separate `currency_code` column,
  and soft delete via a **partial** unique index (`where: "deleted_at IS
  NULL"`) rather than a plain one:
  `medusajs/medusa@develop:packages/modules/pricing/src/models/price.ts`.
- DB-level optimistic concurrency (`resourceVersion` → HTTP 409 on conflict)
  and name-idempotency (409 on duplicate create) as invariants enforced by the
  server, not the client:
  `kubernetes/community@master:contributors/devel/sig-architecture/api-conventions.md`,
  "Concurrency Control and Consistency" and "Idempotency" sections.
- "Think twice about `bool` fields... they eventually trend towards a small set
  of mutually exclusive options" — the nullable/boolean-as-flattened-state-
  machine smell, same document, "Constants" section.
- "Nullable... is not compatible with JSON merge patching" — why null and
  optional-with-default should not be conflated at a schema boundary, same
  document, "Nullable" section.
- Identity (UUIDv7/ULID vs bigserial, index locality, enumeration exposure),
  audit-trail-vs-log distinction, PII/erasure-vs-ledger tension, state-machine
  enumeration in `CHECK`/enum form: `SOURCE: original` — general database
  engineering practice, not tied to a single fetched repo.
- `supabase/supabase` was checked for a canonical multi-tenant RLS migration to
  cite directly; the specific paths probed returned 404 (repo restructured
  since indexing). Recorded as an absence rather than invented — see
  `research/00-signal-rubric.md` Part G.6.
