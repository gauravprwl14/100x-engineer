#!/usr/bin/env bash
# Regression suite for schema_check.py. Asserts detection AND absence of false
# positives -- the clean-file counter-tests are the important half, since a
# false positive is what gets a schema gate turned off. Run: bash tests/test_schema_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
REPO="$WORK/repo"; OUT="$WORK/sc.out"
SC="$ROOT/scripts/schema_check.py"
mkdir -p "$REPO"; cd "$REPO"; git init -q; git config user.email t@t; git config user.name t
mkdir -p migrations
printf '# init\n' > README.md
git add -A; git commit -qm init

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [-- extra args]
  local exp="$1" label="$2"; shift 2
  python3 "$SC" --base HEAD "$@" >"$OUT" 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-55s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-55s exit exp=%s got=%s\n' "$label" "$exp" "$got"
       sed 's/^/       /' "$OUT"; fi
}
has() { grep -q -- "$1" "$OUT" && { PASS=$((PASS+1)); printf '  ok   %-55s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "NOT reported: $1"; sed 's/^/       /' "$OUT"; }; }
nothas() { grep -q -- "$1" "$OUT" && { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "false positive: $1"; sed 's/^/       /' "$OUT"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-55s\n' "no false positive: $1"; }; }
reset_repo() { rm -rf migrations src *.prisma *.py; mkdir -p migrations; git add -A >/dev/null 2>&1; git commit -qm reset --allow-empty >/dev/null 2>&1; }

# ============================================================ money-float
cat > migrations/001.sql <<'EOF'
CREATE TABLE payments (
    id BIGSERIAL PRIMARY KEY,
    amount_cents FLOAT NOT NULL,
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 1 "money-float: FLOAT amount column detected" --only money-float
has "amount_cents is money-shaped and FLOAT"
reset_repo

cat > migrations/002_clean.sql <<'EOF'
CREATE TABLE payments (
    id BIGSERIAL PRIMARY KEY,
    amount_cents NUMERIC(12,2) NOT NULL,
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 0 "money-float: NUMERIC amount column is clean" --only money-float
nothas "FLOAT"
reset_repo

cat > model_dirty.py <<'EOF'
from sqlalchemy import Column, Float, String
from sqlalchemy.orm import declarative_base
Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    price = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False)
    created_at = Column(String, nullable=False)
EOF
git add -A
expect 1 "money-float: SQLAlchemy Column(Float) detected" --only money-float
has "Order.price is money-shaped and FLOAT"
reset_repo

# ============================================================ money-currency
cat > migrations/003.sql <<'EOF'
CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    total_amount NUMERIC(12,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 0 "money-currency: no blocking exit (advisory only)" --only money-currency
has "no companion currency column"
reset_repo

cat > migrations/004_clean.sql <<'EOF'
CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    total_amount NUMERIC(12,2) NOT NULL,
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 0 "money-currency: companion currency column is clean" --only money-currency
nothas "no companion currency"
reset_repo

# ============================================================ new-table-pk
cat > migrations/005.sql <<'EOF'
CREATE TABLE audit_events (
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 1 "new-table-pk: table with no primary key detected" --only new-table-pk
has "audit_events has no primary key"
reset_repo

cat > migrations/006_clean.sql <<'EOF'
CREATE TABLE audit_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 0 "new-table-pk: table with a primary key is clean" --only new-table-pk
nothas "no primary key"
reset_repo

cat > schema_dirty.prisma <<'EOF'
model Widget {
  name String
}
EOF
git add -A
expect 1 "new-table-pk: Prisma model with no @id detected" --only new-table-pk
has "Widget has no primary key"
reset_repo

# ============================================================ new-table-created-at (advisory)
cat > migrations/007.sql <<'EOF'
CREATE TABLE sessions (
    id BIGSERIAL PRIMARY KEY,
    token TEXT NOT NULL
);
EOF
git add -A
expect 0 "new-table-created-at: advisory does not fail the build" --only new-table-created-at
has "sessions has no created_at-equivalent"
reset_repo

cat > migrations/008_clean.sql <<'EOF'
CREATE TABLE sessions (
    id BIGSERIAL PRIMARY KEY,
    token TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 0 "new-table-created-at: table with created_at is clean" --only new-table-created-at
nothas "no created_at-equivalent"
reset_repo

# ============================================================ not-null-no-default (blocking)
cat > migrations/009.sql <<'EOF'
ALTER TABLE payments ADD COLUMN status TEXT NOT NULL;
EOF
git add -A
expect 1 "not-null-no-default: NOT NULL without DEFAULT on existing table" --only not-null-no-default
has "payments.status added NOT NULL with no DEFAULT"
reset_repo

cat > migrations/010_clean.sql <<'EOF'
ALTER TABLE payments ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
EOF
git add -A
expect 0 "not-null-no-default: NOT NULL DEFAULT column is clean" --only not-null-no-default
nothas "added NOT NULL"
reset_repo

cat > migrations/011_clean.sql <<'EOF'
ALTER TABLE payments ADD COLUMN note TEXT;
EOF
git add -A
expect 0 "not-null-no-default: nullable without default is clean (harmless)" --only not-null-no-default
nothas "added NOT NULL"
reset_repo

cat > migrations/011b_clean.sql <<'EOF'
CREATE TABLE payments (id BIGSERIAL PRIMARY KEY);
ALTER TABLE payments ADD COLUMN status TEXT NOT NULL;
ALTER TABLE ledger ADD COLUMN seq BIGSERIAL NOT NULL;
ALTER TABLE ledger ADD COLUMN total_cents BIGINT NOT NULL GENERATED ALWAYS AS (a + b) STORED;
EOF
git add -A
expect 0 "not-null-no-default: new table / serial / generated column are clean" --only not-null-no-default
nothas "added NOT NULL"
reset_repo

cat > schema.prisma <<'EOF'
model Order {
  id String @id
}
EOF
git add -A; git commit -qm "existing prisma model"
cat > schema.prisma <<'EOF'
model Order {
  id String @id
  status String
  note String?
  kind String @default("std")
}
EOF
git add -A
expect 1 "not-null-no-default: required Prisma field added to existing model" --only not-null-no-default
has "Order.status added NOT NULL"
nothas "Order.note"
nothas "Order.kind"
reset_repo

# ============================================================ expand-contract (blocking)
cat > migrations/012.sql <<'EOF'
ALTER TABLE payments DROP COLUMN legacy_note;
ALTER TABLE payments ADD COLUMN note TEXT;
EOF
git add -A
expect 1 "expand-contract: drop+add mixed in one migration detected" --only expand-contract
has "destructive change"
has "mixed with an additive change"
reset_repo

cat > migrations/013_clean.sql <<'EOF'
ALTER TABLE payments ADD COLUMN note TEXT NOT NULL DEFAULT '';
EOF
git add -A
expect 0 "expand-contract: additive-only migration is clean" --only expand-contract
nothas "destructive change"
reset_repo

cat > migrations/014.sql <<'EOF'
ALTER TABLE payments DROP COLUMN legacy_note;
EOF
git add -A
expect 1 "expand-contract: standalone DROP COLUMN is blocked" --only expand-contract
has "DROP COLUMN legacy_note on payments"
has "expand (add the new shape), migrate readers"
nothas "mixed with an additive"
reset_repo

cat > migrations/014b.sql <<'EOF'
ALTER TABLE payments RENAME COLUMN note TO memo;
EOF
git add -A
expect 1 "expand-contract: standalone RENAME COLUMN is blocked" --only expand-contract
has "RENAME COLUMN note TO memo"
reset_repo

cat > migrations/014c.sql <<'EOF'
DROP TABLE IF EXISTS legacy_payments;
EOF
git add -A
expect 1 "expand-contract: standalone DROP TABLE is blocked" --only expand-contract
has "DROP TABLE on legacy_payments"
reset_repo

cat > migrations/014d.sql <<'EOF'
ALTER TABLE payments RENAME TO charges;
EOF
git add -A
expect 1 "expand-contract: table rename is blocked" --only expand-contract
has "RENAME TABLE TO charges"
reset_repo

cat > migrations/014e_clean.sql <<'EOF'
ALTER TABLE payments DROP CONSTRAINT payments_note_check;
ALTER TABLE payments ALTER COLUMN note DROP NOT NULL;
ALTER TABLE payments RENAME CONSTRAINT a TO b;
CREATE TABLE scratch (id BIGSERIAL PRIMARY KEY, tmp TEXT);
ALTER TABLE scratch DROP COLUMN tmp;
DROP TABLE scratch;
EOF
git add -A
expect 0 "expand-contract: constraint drops / same-file scratch table clean" --only expand-contract
nothas "destructive change"
reset_repo

cat > migrations/014f.sql <<'EOF'
ALTER TABLE payments DROP COLUMN legacy_note;
EOF
git add -A; git commit -qm "contract already shipped"
printf '\nALTER TABLE payments ADD COLUMN memo TEXT;\n' >> migrations/014f.sql
git add -A
expect 0 "expand-contract: pre-existing DROP not re-flagged by later edit" --only expand-contract
nothas "destructive change"
reset_repo

# ============================================================ fk-index
cat > migrations/015.sql <<'EOF'
CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 0 "fk-index: advisory does not fail the build" --only fk-index
has "customer_id -> customers has no index"
reset_repo

cat > migrations/016_clean.sql <<'EOF'
CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX invoices_customer_id_idx ON invoices (customer_id);
EOF
git add -A
expect 0 "fk-index: indexed FK is clean" --only fk-index
nothas "has no index"
reset_repo

# ============================================================ tenant-index (blocking, the cross-tenant leak)
cat > migrations/017.sql <<'EOF'
CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    key_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX api_keys_hash_uq ON api_keys (key_hash);
EOF
git add -A
expect 1 "tenant-index: unique index omitting tenant_id detected" --only tenant-index
has "cross-tenant leak"
reset_repo

cat > migrations/018_clean.sql <<'EOF'
CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    key_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX api_keys_hash_uq ON api_keys (tenant_id, key_hash);
EOF
git add -A
expect 0 "tenant-index: unique index including tenant_id is clean" --only tenant-index
nothas "cross-tenant leak"
reset_repo

cat > migrations/019_clean.sql <<'EOF'
CREATE TABLE plans (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX plans_name_uq ON plans (name);
EOF
git add -A
expect 0 "tenant-index: non-tenant table with unique index is clean" --only tenant-index
nothas "cross-tenant leak"
reset_repo

# ============================================================ fk-index: tenant-first composite
cat > migrations/024_clean.sql <<'EOF'
CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL,
    customer_id BIGINT REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX invoices_company_customer_idx ON invoices (company_id, customer_id);
EOF
git add -A
expect 0 "fk-index: tenant-first composite covers the FK" --only fk-index
nothas "has no index"
reset_repo

cat > migrations/025.sql <<'EOF'
CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    status TEXT NOT NULL,
    customer_id BIGINT REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX invoices_status_customer_idx ON invoices (status, customer_id);
EOF
git add -A
expect 0 "fk-index: non-tenant prefix does not cover the FK (advisory)" --only fk-index
has "customer_id -> customers has no index"
reset_repo

# ============================================================ fk-not-valid (advisory)
cat > migrations/026.sql <<'EOF'
ALTER TABLE orders ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) REFERENCES users(id);
EOF
git add -A
expect 0 "fk-not-valid: advisory does not fail the build" --only fk-not-valid
has "without NOT VALID"
expect 1 "fk-not-valid: fails under --strict" --only fk-not-valid --strict
reset_repo

cat > migrations/027_clean.sql <<'EOF'
ALTER TABLE orders ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) REFERENCES users(id) NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT orders_user_fk;
CREATE TABLE refunds (id BIGSERIAL PRIMARY KEY, order_id BIGINT);
ALTER TABLE refunds ADD CONSTRAINT refunds_order_fk FOREIGN KEY (order_id) REFERENCES orders(id);
EOF
git add -A
expect 0 "fk-not-valid: NOT VALID, or a table new in this file, is clean" --only fk-not-valid
nothas "without NOT VALID"
reset_repo

# ============================================================ index-concurrently (advisory)
cat > migrations/028.sql <<'EOF'
CREATE INDEX orders_status_idx ON orders (status);
EOF
git add -A
expect 0 "index-concurrently: advisory does not fail the build" --only index-concurrently
has "without CONCURRENTLY"
expect 1 "index-concurrently: fails under --strict" --only index-concurrently --strict
reset_repo

cat > migrations/029_clean.sql <<'EOF'
CREATE INDEX CONCURRENTLY IF NOT EXISTS orders_status_idx ON orders (status);
CREATE TABLE refunds (id BIGSERIAL PRIMARY KEY, status TEXT);
CREATE INDEX refunds_status_idx ON refunds (status);
EOF
git add -A
expect 0 "index-concurrently: CONCURRENTLY / new table is clean" --only index-concurrently
nothas "without CONCURRENTLY"
reset_repo

cat > migrations/030_clean.sql <<'EOF'
CREATE INDEX `orders_status_idx` ON `orders` (`status`);
EOF
git add -A
expect 0 "index-concurrently: MySQL-dialect file is not told to use it" --only index-concurrently
nothas "without CONCURRENTLY"
reset_repo

# ============================================================ tenant column names + FK-index exemption
for tcol in company_id organization_id org_id account_id workspace_id; do
cat > migrations/031.sql <<EOF
CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    $tcol BIGINT NOT NULL,
    key_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX api_keys_hash_uq ON api_keys (key_hash);
EOF
git add -A
expect 1 "tenant-index: $tcol recognised as the tenant column" --only tenant-index
has "cross-tenant leak"
reset_repo
done

cat > schema.prisma <<'EOF'
model Project {
  id        String @id
  companyId String
  slug      String @unique
}
EOF
git add -A
expect 1 "tenant-index: Prisma companyId + @unique slug detected" --only tenant-index
has "Project omits the tenant column"
reset_repo

cat > migrations/032.sql <<'EOF'
CREATE TABLE members (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A
expect 1 "tenant-index: column-level UNIQUE in CREATE TABLE detected" --only tenant-index
has "members omits the tenant column (email)"
reset_repo

cat > migrations/033_clean.sql <<'EOF'
CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, id)
);
CREATE INDEX invoices_customer_id_idx ON invoices (customer_id);
EOF
git add -A
expect 0 "tenant-index: plain FK index on tenant table not blocked" --only tenant-index,tenant-lookup-index --strict
nothas "cross-tenant leak"
nothas "lookup index"
reset_repo

cat > migrations/034.sql <<'EOF'
CREATE TABLE invoices (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX invoices_status_idx ON invoices (status);
EOF
git add -A
expect 0 "tenant-index: non-unique lookup index is not a leak" --only tenant-index
nothas "cross-tenant leak"
expect 0 "tenant-lookup-index: advisory reported for it" --only tenant-lookup-index
has "lookup index on tenant-scoped table invoices (status)"
reset_repo

# ============================================================ FK parsing + line numbers
cat > migrations/035.sql <<'EOF'
-- the owner's orders: an apostrophe here must not break statement splitting
CREATE TABLE orders (id BIGSERIAL PRIMARY KEY);

ALTER TABLE orders ADD CONSTRAINT orders_user_fk
    FOREIGN KEY (user_id) REFERENCES users(id);
EOF
git add -A
expect 0 "fk parsing: ALTER ... ADD CONSTRAINT FOREIGN KEY form" --only fk-index
has "FK orders.user_id -> users"
has "migrations/035.sql:4:"
nothas "orders.ALTER"
reset_repo

cat > migrations/036.sql <<'EOF'
CREATE TABLE a (id BIGSERIAL PRIMARY KEY);
CREATE TABLE b (
    id BIGSERIAL PRIMARY KEY,
    price FLOAT NOT NULL
);
EOF
git add -A
expect 1 "line numbers: finding points at the column's own line" --only money-float
has "migrations/036.sql:4:"
reset_repo

# ============================================================ JS/TS migrations (TypeORM / Knex)
cat > migrations/1700000000000-AddPrice.ts <<'EOF'
import { MigrationInterface, QueryRunner } from "typeorm";

export class AddPrice1700000000000 implements MigrationInterface {
    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "orders" ADD "price" double precision NOT NULL DEFAULT 0`);
        await queryRunner.query(`ALTER TABLE "orders" DROP COLUMN "legacy_total"`);
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "orders" ADD "legacy_total" integer`);
        await queryRunner.query(`ALTER TABLE "orders" DROP COLUMN "price"`);
    }
}
EOF
git add -A
expect 1 "ts migration: money-float in queryRunner.query detected" --only money-float
has "1700000000000-AddPrice.ts:5: orders.price is money-shaped"
expect 1 "ts migration: DROP COLUMN in up() detected" --only expand-contract
has "AddPrice.ts:6: destructive change (DROP COLUMN legacy_total"
nothas "DROP COLUMN price"
reset_repo

cat > migrations/1700000000001-Reversible.ts <<'EOF'
import { MigrationInterface, QueryRunner } from "typeorm";

export class Reversible1700000000001 implements MigrationInterface {
    public async up(queryRunner: QueryRunner): Promise<void> {
        // await queryRunner.query(`ALTER TABLE "orders" DROP COLUMN "old"`);
        await queryRunner.query(
            'ALTER TABLE "orders" ADD "amount_cents" bigint NOT NULL DEFAULT 0'
        );
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`ALTER TABLE "orders" DROP COLUMN "amount_cents"`);
    }
}
EOF
git add -A
expect 0 "ts migration: down() and commented-out calls are not flagged" --only expand-contract,money-float,not-null-no-default
nothas "destructive change"
nothas "money-shaped"
reset_repo

cat > migrations/20240101120000_drop_legacy.js <<'EOF'
exports.up = function (knex) {
  return knex.raw('ALTER TABLE orders ' +
    'DROP COLUMN legacy');
};
exports.down = function (knex) {
  return knex.raw('ALTER TABLE orders DROP COLUMN replacement');
};
EOF
git add -A
expect 1 "knex migration: knex.raw string concatenation parsed" --only expand-contract
has "DROP COLUMN legacy on orders"
nothas "replacement"
reset_repo

mkdir -p src
cat > src/report.service.ts <<'EOF'
export async function purge(queryRunner: any) {
  await queryRunner.query(`ALTER TABLE "orders" DROP COLUMN "legacy"`);
}
EOF
git add -A
expect 0 "ts: non-migration source file is not parsed as a migration" --only expand-contract
nothas "destructive change"
reset_repo

# ============================================================ TypeORM entity decorators
mkdir -p src
cat > src/order.entity.ts <<'EOF'
import { Column, Entity, PrimaryGeneratedColumn } from "typeorm";

@Entity()
export class Order {
  @PrimaryGeneratedColumn()
  id!: number;

  @Column('float')
  price!: number;

  @Column({ type: 'double precision', nullable: true })
  totalAmount?: number;

  @Column({ type: 'decimal', precision: 12, scale: 2 })
  shippingFee!: string;

  @Column('float')
  latitude!: number;
}
EOF
git add -A
expect 1 "typeorm entity: @Column float on money property detected" --only money-float
has "Order.price is money-shaped"
has "Order.totalAmount is money-shaped"
nothas "shippingFee"
nothas "latitude"
reset_repo

# ============================================================ select-star
cat > migrations/020.sql <<'EOF'
CREATE VIEW active_payments AS SELECT * FROM payments WHERE status = 'active';
EOF
git add -A
expect 0 "select-star: advisory does not fail the build" --only select-star
has "SELECT \* in a migration or view"
reset_repo

cat > migrations/021_clean.sql <<'EOF'
CREATE VIEW active_payments AS SELECT id, status FROM payments WHERE status = 'active';
EOF
git add -A
expect 0 "select-star: explicit column list is clean" --only select-star
nothas "SELECT \*"
reset_repo

# ============================================================ diff scoping: pre-existing schema is not re-flagged
cat > migrations/022_base.sql <<'EOF'
CREATE TABLE widgets (
    id BIGSERIAL PRIMARY KEY,
    price FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
EOF
git add -A; git commit -qm "pre-existing bad schema, already merged"
cat >> migrations/022_base.sql <<'EOF'

ALTER TABLE widgets ADD COLUMN sku TEXT NOT NULL DEFAULT '';
EOF
git add -A
expect 0 "diff-scoping: pre-existing FLOAT column not re-flagged by an unrelated later edit" --only money-float
nothas "price is money-shaped"
reset_repo

# ============================================================ --strict promotes advisories to failures
cat > migrations/023.sql <<'EOF'
CREATE TABLE sessions (
    id BIGSERIAL PRIMARY KEY,
    token TEXT NOT NULL
);
EOF
git add -A
expect 1 "strict mode: advisory (missing created_at) fails under --strict" --only new-table-created-at --strict
reset_repo

echo
echo "schema_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
