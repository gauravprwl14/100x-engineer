---
name: data-lifecycle
description: >
  Personal data, backups and deletion: delete account and GDPR erasure, retention, PII
  inventory, restoring backups in tested drills, RPO/RTO, point-in-time recovery, audit logs.
  Not for schema shape (→ data-modeling).
---

# Data lifecycle

Data outlives the code that wrote it. The failures here are slow and quiet: a
backup job that has run green for a year and cannot be restored, a deleted user
who is still in the search index and the analytics warehouse, a retention period
nobody chose. Google SRE's data-integrity chapter puts it in one line: "No one
really wants to make backups; what people really want are restores."

## Trigger

**Fire when:** adding a datastore (database, bucket, queue with retention, search
index, warehouse); a migration adds a column that identifies a person; writing
backup, restore, archival or purge jobs; implementing account deletion, data
export, or a privacy request; adding analytics or tracking.

**Do not fire when:** the change touches no persistent data. Schema shape itself
(types, keys, soft-delete columns) is `data-modeling`; release ordering of a
migration is `release-rollout`.

## Rules

1. **RPO and RTO are the owner's numbers: ask, never default.** How much data the
   business can lose (RPO) and how long it can be down (RTO) set the backup
   frequency, PITR and replica design. They are a class C decision
   (`docs/OPERATING-MODEL.md` §5); record the answer next to the datastore.
   *Enforced by:* review (asked as a blocking question, never assumed)

2. **A backup is proven only by a restore.** Schedule an automated restore into a
   scratch environment, check it (row counts, checksums, an application smoke
   query), and record how long it took against the RTO. A backup that has never
   been restored is a hypothesis.
   *Enforced by:* `grep -rliE 'restore' .github/workflows` (a drill job exists), then review of its last run

3. **Production datastores have point-in-time recovery, retained backups and
   deletion protection switched on explicitly.** Provider defaults are off:
   Terraform's `aws_db_instance` defaults `deletion_protection` to `false` and
   `backup_retention_period` to `0`; DynamoDB PITR defaults to `false`.
   *Enforced by:* `! grep -rnE 'deletion_protection(_enabled)?\s*=\s*false|skip_final_snapshot\s*=\s*true|backup_retention_period\s*=\s*0\b' --include='*.tf' .`, then review for attributes left unset

4. **Layer the defences: soft delete, then backups, then out-of-band
   validation.** User-initiated deletes are recoverable for a bounded window
   before a purge job hard-deletes; backups cover what soft delete cannot; a
   periodic validation job catches silent corruption before it ages out of the
   backups.
   *Enforced by:* review

5. **Every data class has a retention period and a job that enforces it.** How
   long is the owner's decision (class C: legal, contractual, product); the
   mechanism is yours: a TTL index, a bucket lifecycle rule, or a scheduled purge,
   with the period written next to it. "Forever" is a choice that must be stated.
   *Enforced by:* review

6. **Keep a PII inventory.** Each field holding personal data is listed with its
   class (identifier, contact, sensitive, financial), purpose, and every store
   it is copied to. A migration that adds a personal-data column updates the
   inventory in the same PR.
   *Enforced by:* review

7. **Erasure reaches every copy, not just the primary row.** One deletion
   workflow, idempotent and logged, removes or anonymises the subject in the
   primary database and its replicas, caches, search indexes, the analytics
   warehouse and event streams, object storage, logs that hold the payload, and
   third-party processors. GDPR Art. 17 requires erasure "without undue delay"
   and Art. 17(2) reaching copies; the UK ICO allows one month to respond. APPI
   Art. 35 (in force 1 April 2022) gives a similar right to cessation of use or
   deletion in Japan. A test creates a user, deletes them, and asserts absence
   in each store.
   *Enforced by:* review, plus that end-to-end deletion test in the suite

8. **Backups get the "beyond use" treatment, and restores replay deletions.**
   Backups usually cannot be edited, so erased records stay until the backup
   expires: keep backup retention short enough to defend, never restore a
   backup for any other purpose, and keep a deletion ledger (subject ids, not
   their data) that is re-applied after every restore so an erased person does
   not come back.
   *Enforced by:* review

9. **Analytics and tracking are opt-in.** No analytics or marketing event fires,
   and no identifier is stored, before the user consents; withdrawing consent
   stops collection and is honoured downstream.
   *Enforced by:* review

10. **Audit who touched whose data.** Admin access, exports, permission changes
    and erasures write an append-only audit record (actor, action, subject id,
    time) with its own retention, and it carries ids, not the personal data
    itself.
    *Enforced by:* review

## Verify

Seconds; most of this skill is review, and these show what can be checked.

```bash
# rule 3: protection explicitly switched off anywhere in Terraform
! grep -rnE 'deletion_protection(_enabled)?\s*=\s*false|skip_final_snapshot\s*=\s*true|backup_retention_period\s*=\s*0\b' --include='*.tf' .
# rule 3: which datastores turn on PITR -- compare against the list of datastores
grep -rnE 'point_in_time_recovery(_enabled)?|backup_retention_period' --include='*.tf' .
# rule 2: a scheduled restore drill exists
grep -rliE 'restore' .github/workflows
# rule 6 and 7: new personal-data columns in this diff, to check against the inventory
git diff origin/main...HEAD -- '*migrat*' | grep -niE '^\+.*(email|phone|address|birth|name|ip_addr)'
# rule 7: seed the erasure edge cases (every store a deleted user reached) into the spec
100x plan_feature new account-deletion --kind pii-compliance
```

The Terraform greps catch protection switched off, not protection never
switched on; an `aws_db_instance` with no `backup_retention_period` line has no
automated backups and no grep line to show it. Restore drills and erasure
coverage are only as real as the job's last green run.

## Failure modes

This skill rejects:

- **A nightly `pg_dump` to a bucket that has never been restored**, discovered
  during the incident to be zero bytes since a credentials rotation.
- **`skip_final_snapshot = true` and `deletion_protection = false` on the
  production RDS instance**: one mistaken `terraform destroy` is permanent.
- **"Delete account" that deletes the `users` row** while the user's profile
  stays in Elasticsearch, Redis, the BigQuery export and the CRM.
- **A restore from last week's backup** that silently resurrects every user who
  asked to be erased since.
- **A retention period of "keep everything"** that nobody decided, found in an
  audit.
- **An analytics SDK initialised on page load** before the consent banner is
  answered.
- **RPO/RTO invented by the implementer** ("hourly backups should be fine")
  instead of asked.

## Scale

**Every tier, `solo` included: rules 1, 3, 7, 9.** Explicit backups and deletion
protection cost one Terraform line; erasure is a legal duty wherever GDPR or
APPI applies, regardless of team size, and opt-in consent is the owner-approved
default. `small` (2-10): add 2, 5, 6: a scheduled restore drill, retention jobs,
a PII inventory. `growth` (org 10+):
add 4, 8, 10. `scale`: continuous automated restore testing and out-of-band
validation across every store, as the SRE chapter describes.

## Sources

- "No one really wants to make backups; what people really want are restores";
  soft deletion, backups and early detection as defence in depth; recover
  continuously to know you can: Google SRE book, ch. 26 "Data Integrity: What
  You Read Is What You Wrote" (https://sre.google/sre-book/data-integrity/).
- Right to erasure "without undue delay" and reaching "links to, or copy or
  replication of" the data: GDPR (Regulation (EU) 2016/679) Art. 17(1)–(2).
- Backups "beyond use" and the one-month response: UK ICO guidance, "Right to
  erasure" (https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/right-to-erasure/).
- Cessation of use or deletion of retained personal data: Act on the Protection
  of Personal Information (APPI) Art. 35, as amended in 2020, in force
  1 April 2022 (Japanese Law Translation, law 4241,
  https://www.japaneselawtranslation.go.jp/en/laws/view/4241/en).
- Provider defaults: `hashicorp/terraform-provider-aws@main:website/docs/r/db_instance.html.markdown`
  (`deletion_protection` default `false`, `backup_retention_period` default `0`),
  `website/docs/r/dynamodb_table.html.markdown` (PITR defaults to `false`);
  `hashicorp/terraform-provider-google@main:website/docs/r/sql_database_instance.html.markdown`
  (`point_in_time_recovery_enabled`).
- Opt-in analytics consent as the default: owner-approved, recorded in
  `scripts/data/baseline.json`.
- The erasure edge case seeded into specs ("Deleted user's PII persists ... in
  backups, caches, search indexes, or queued payloads"):
  `scripts/data/edge_cases_infra.json`, kind `pii-compliance`.
- Deletion ledger replayed after restore, and the tier mapping:
  `SOURCE: original`.
