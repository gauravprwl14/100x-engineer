#!/usr/bin/env bash
# Regression suite for schema_check.py. Asserts detection AND absence of false
# positives -- the clean-file counter-tests are the important half, since a
# false positive is what gets a schema gate turned off. Run: bash tests/test_schema_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
SC="$ROOT/scripts/schema_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p migrations
printf '# init\n' > README.md
git add -A; git commit -qm init

PASS=0; FAIL=0
expect() { # expect <0|1> <label> [-- extra args]
  local exp="$1" label="$2"; shift 2
  python3 "$SC" --base HEAD "$@" >/tmp/sc.out 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-55s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-55s exit exp=%s got=%s\n' "$label" "$exp" "$got"
       sed 's/^/       /' /tmp/sc.out; fi
}
has() { grep -q "$1" /tmp/sc.out && { PASS=$((PASS+1)); printf '  ok   %-55s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "NOT reported: $1"; }; }
nothas() { grep -q "$1" /tmp/sc.out && { FAIL=$((FAIL+1)); printf '  FAIL %-55s\n' "false positive: $1"; } \
        || { PASS=$((PASS+1)); printf '  ok   %-55s\n' "no false positive: $1"; }; }
reset_repo() { rm -f migrations/*.sql *.prisma *.py; git add -A >/dev/null 2>&1; git commit -qm reset --allow-empty >/dev/null 2>&1; }

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

# ============================================================ nullable-no-default
cat > migrations/009.sql <<'EOF'
CREATE TABLE payments (id BIGSERIAL PRIMARY KEY);
ALTER TABLE payments ADD COLUMN note TEXT;
EOF
git add -A
expect 0 "nullable-no-default: advisory does not fail the build" --only nullable-no-default
has "payments.note added nullable with no default"
reset_repo

cat > migrations/010_clean.sql <<'EOF'
CREATE TABLE payments (id BIGSERIAL PRIMARY KEY);
ALTER TABLE payments ADD COLUMN note TEXT NOT NULL DEFAULT '';
EOF
git add -A
expect 0 "nullable-no-default: NOT NULL DEFAULT column is clean" --only nullable-no-default
nothas "added nullable with no default"
reset_repo

cat > migrations/011_clean.sql <<'EOF'
CREATE TABLE payments (id BIGSERIAL PRIMARY KEY);
ALTER TABLE payments ADD COLUMN note TEXT DEFAULT 'n/a';
EOF
git add -A
expect 0 "nullable-no-default: nullable WITH default is clean" --only nullable-no-default
nothas "added nullable with no default"
reset_repo

# ============================================================ expand-contract
cat > migrations/012.sql <<'EOF'
ALTER TABLE payments DROP COLUMN legacy_note;
ALTER TABLE payments ADD COLUMN note TEXT;
EOF
git add -A
expect 1 "expand-contract: drop+add mixed in one migration detected" --only expand-contract
has "destructive change"
reset_repo

cat > migrations/013_clean.sql <<'EOF'
ALTER TABLE payments ADD COLUMN note TEXT NOT NULL DEFAULT '';
EOF
git add -A
expect 0 "expand-contract: additive-only migration is clean" --only expand-contract
nothas "destructive change"
reset_repo

cat > migrations/014_clean.sql <<'EOF'
ALTER TABLE payments DROP COLUMN legacy_note;
EOF
git add -A
expect 0 "expand-contract: drop-only (contract phase alone) is clean" --only expand-contract
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
