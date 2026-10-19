#!/usr/bin/env python3
"""Diff-scoped checks for the schema mistakes that don't show up until production.

Companion to bloat_check.py: that script catches AI-shaped code smells, this one
catches AI-shaped (and human-shaped) SCHEMA smells -- the ones that are cheap to
fix in a migration that hasn't shipped and expensive to fix once a table has rows.
Scoped to the diff so it is runnable against an existing, large schema, not just
a greenfield one.

Covers these shapes, on purpose (see the data-modeling skill's Honest limitations
for what is deliberately NOT covered):
  - SQL migrations (*.sql)          -- CREATE/ALTER/DROP/RENAME TABLE, indexes, views
  - JS/TS migrations                -- SQL passed to any `<receiver>.query(...)` /
                                       `.raw(...)` outside down(), run through the SQL checks
  - TypeORM entities (@Entity)      -- @Column float/double/real types (money-float only)
  - Prisma schemas (*.prisma)       -- model blocks, field/model attributes
  - Python ORM models (*.py)        -- Django-style and SQLAlchemy-style classes

    schema_check.py                        # check staged+unstaged vs HEAD
    schema_check.py --base origin/main
    schema_check.py --only money-float,tenant-index
    schema_check.py --strict            # treat advisory checks as failures too

Exit 1 if any blocking check finds a violation; exit 2 outside a git repository,
with an unresolvable --base, or when a changed file cannot be read.
"""
import argparse, bisect, pathlib, re, subprocess, sys

from _mutation_guard import changed_files, diff_rev, enter_git_root, path_args, unreadable

MONEY_RX = re.compile(r"\b\w*(price|amount|total|balance|cost|fee|salary)\w*\b", re.I)
CURRENCY_RX = re.compile(r"\b\w*(currency|ccy|curr_code)\w*\b", re.I)
TENANT_NAMES = ("tenant_id", "tenantid", "company_id", "companyid", "organization_id",
                "organizationid", "org_id", "orgid", "account_id", "accountid",
                "workspace_id", "workspaceid")
CREATED_RX = re.compile(r"^(created_at|createdat|created_on|createdon|inserted_at|created)$", re.I)
SQL_FLOATY_RX = re.compile(r"\b(FLOAT4?|FLOAT8?|REAL|DOUBLE(\s+PRECISION)?)\b", re.I)
PRISMA_FLOATY_RX = re.compile(r"^Float$")
PY_FLOATY_RX = re.compile(r"\b(FloatField|Float)\b")
# Optionally schema-qualified, optionally quoted identifier; captures the bare name.
NAME = r'["`]?(?:\w+["`]?\.["`]?)?(\w+)["`]?'
# CONCURRENTLY and NOT VALID exist only in Postgres. A file with none of these
# MySQL/SQLite markers is treated as Postgres so the lock advisories can fire.
NON_PG_RX = re.compile(r"`|\bENGINE\s*=|\bAUTO_?INCREMENT\b|\bUNSIGNED\b|\bALGORITHM\s*=|"
                       r"\bLOCK\s*=\s*NONE\b", re.I)
SERIAL_RX = re.compile(r"^(SMALL|BIG)?SERIAL\d?$", re.I)
JS_EXTS = (".ts", ".js", ".mjs", ".cjs")
# Any receiver, not a fixed list of names: TypeORM's up() names its QueryRunner
# whatever the author likes (`up(q: QueryRunner)`), and a name list silently skipped
# every migration that did not use the conventional one. Only migration files are
# parsed with this, and only literal arguments are taken as SQL.
JS_SQL_CALL_RX = re.compile(r"(?<![\w$.])[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*"
                            r"\s*\.\s*(?:query|raw)\s*\(")
JS_DOWN_RX = re.compile(r"\bfunction\s+down\s*\(|"
                        r"\b(?:async\s+)?down\s*\([^)]*\)\s*(?::\s*[\w<>\[\]]+\s*)?\{|"
                        r"\bdown\s*[:=]\s*(?:async\s+)?(?:function\b[^{]*\{|(?:\([^)]*\)|\w+)\s*=>)")
TYPEORM_FLOAT = r"""['"`](?:float[48]?|double(?:\s+precision)?|real)['"`]"""


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed(base):
    """(added, modified) paths in the diff; see _mutation_guard.changed_files."""
    return changed_files(base, "schema_check")


def added_line_numbers(path, base):
    """1-indexed line numbers in the CURRENT file content that this diff added.

    Used to gate every finding on 'did this diff introduce the thing', not 'does
    this pre-existing schema have the thing' -- the difference between a useful
    diff-scoped gate and a whole-repo scan that gets disabled on day one.
    """
    rng = [diff_rev(base)]
    out = sh(["git", "diff", "--unified=0"] + rng + path_args(path))
    if not out:
        return set(range(1, len(read(path).splitlines()) + 1))
    nums = set()
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", out, re.M):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        nums.update(range(start, start + count))
    return nums


def read(path):
    # No fallback: an unreadable changed file is reported by main() as exit 2,
    # never parsed as empty and passed.
    return pathlib.Path(path).read_text(errors="replace")


def any_added(spans, added_set):
    return any(l in added_set for l in spans)


def is_js_migration(path):
    p = pathlib.PurePosixPath(path)
    if p.suffix not in JS_EXTS or p.name.endswith(".d.ts"):
        return False
    return (any(part.lower() in ("migrations", "migration") for part in p.parts[:-1])
            or "Migration" in p.name or re.match(r"\d+[-_]", p.name) is not None)


def is_schema_file(path):
    if path.endswith((".sql", ".prisma", ".py")) or is_js_migration(path):
        return True
    return path.endswith(JS_EXTS) and "@Entity" in read(path)


# ---------------- structural parsing helpers ----------------

def paren_body(s, open_idx):
    """Text between the '(' at open_idx and its matching ')', balanced."""
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return s[open_idx + 1:i]
    return s[open_idx + 1:]


def split_top_level(s, sep=","):
    parts, depth, buf, in_str = [], 0, [], False
    for ch in s:
        if ch == "'":
            in_str = not in_str
        elif not in_str and ch == "(":
            depth += 1
        elif not in_str and ch == ")":
            depth -= 1
        if ch == sep and depth == 0 and not in_str:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def sql_statements(text):
    """[(statement_text, start_line)], splitting on unquoted ';'.

    start_line is the line of the statement's first token: anchoring it to the
    previous ';' reported every finding one line early. Comments are skipped so
    an apostrophe in one cannot flip the string state for the rest of the file.
    """
    stmts, buf = [], []
    line, start_line = 1, None
    in_str = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if not in_str and text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if not in_str and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            nl = text.count("\n", i, j)
            buf.append("\n" * nl)
            line += nl
            i = j
            continue
        if ch == "\n":
            line += 1
        elif start_line is None and not ch.isspace():
            start_line = line
        if ch == "'":
            in_str = not in_str
        buf.append(ch)
        if ch == ";" and not in_str:
            stmts.append(("".join(buf).strip(), start_line or line))
            buf, start_line = [], None
        i += 1
    if "".join(buf).strip():
        stmts.append(("".join(buf).strip(), start_line or line))
    return stmts


def has_tenant_name(name):
    return name.lower().strip(" \"'`").replace("-", "_") in TENANT_NAMES


def line_of(s, part, cursor, start_line):
    """(line, new_cursor) of `part` inside statement `s`, searching from cursor."""
    pos = s.find(part, cursor)
    if pos < 0:
        return start_line, cursor
    return start_line + s[:pos].count("\n"), pos + len(part)


# ---------------- SQL extraction ----------------

def alter_action_facts(base, table, existing, action, postgres):
    """Facts for one comma-separated action of an ALTER TABLE statement."""
    a, u = action.strip(), action.upper()

    def fact(kind, **kw):
        return dict(base, kind=kind, table=table, **kw)

    def destructive(what):
        return [fact("destructive", what=what)] if existing else []

    m = re.match(r"ADD\s+(?:CONSTRAINT\s+" + NAME + r"\s+)?FOREIGN\s+KEY\s*\(([^)]*)\)\s*"
                 r"REFERENCES\s+" + NAME, a, re.I)
    if m:
        return [fact("fk", col=m.group(2).split(",")[0].strip(" \"`"), ref_table=m.group(3),
                     constraint_on_existing=existing, not_valid="NOT VALID" in u,
                     postgres=postgres)]
    m = re.match(r"ADD\s+(?:CONSTRAINT\s+" + NAME + r"\s+)?UNIQUE(?:\s+(?:INDEX|KEY))?"
                 r"(?:\s+" + NAME + r")?\s*\(([^)]*)\)", a, re.I)
    if m:
        return [fact("index_new", cols=[c.strip(" \"`") for c in m.group(3).split(",") if c.strip()],
                     unique=True)]
    m = re.match(r"ADD\s+(?:INDEX|KEY)(?:\s+" + NAME + r")?\s*\(([^)]*)\)", a, re.I)
    if m:
        return [fact("index_new", cols=[c.strip(" \"`") for c in m.group(2).split(",") if c.strip()],
                     unique=False)]
    if re.match(r"ADD\s+(CONSTRAINT|PRIMARY|CHECK|EXCLUDE|INDEX|KEY|UNIQUE|FOREIGN|FULLTEXT|"
                r"SPATIAL)\b", a, re.I):
        return []
    m = re.match(r"ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)[\"`]?\s+"
                 r"([A-Za-z0-9_]+(?:\s*\([^)]*\))?)\s*(.*)$", a, re.I | re.S)
    if m:
        name, coltype, rest = m.groups()
        ru = rest.upper()
        nullable = "NOT NULL" not in ru and "PRIMARY KEY" not in ru
        has_default = "DEFAULT" in ru
        implicit = bool(SERIAL_RX.match(coltype)) or "GENERATED" in ru
        out = [fact("column_add", name=name, type=coltype, nullable=nullable,
                    has_default=has_default, is_money=bool(MONEY_RX.search(name)),
                    is_floaty=bool(SQL_FLOATY_RX.search(coltype)),
                    needs_backfill_value=existing and not nullable and not has_default
                    and not implicit)]
        rm = re.search(r"REFERENCES\s+" + NAME, rest, re.I)
        if rm:
            out.append(fact("fk", col=name, ref_table=rm.group(1)))
        return out
    if re.match(r"DROP\s+(CONSTRAINT|PRIMARY|INDEX|KEY|FOREIGN|CHECK|PARTITION|DEFAULT)\b", a, re.I):
        return []
    m = re.match(r"DROP\s+(?:COLUMN\s+)?(?:IF\s+EXISTS\s+)?[\"`]?(\w+)", a, re.I)
    if m:
        return destructive(f"DROP COLUMN {m.group(1)}")
    m = re.match(r"RENAME\s+(?:TO|AS)\s+" + NAME, a, re.I)
    if m:
        return destructive(f"RENAME TABLE TO {m.group(1)}")
    if re.match(r"RENAME\s+(CONSTRAINT|INDEX|KEY)\b", a, re.I):
        return []
    m = re.match(r"RENAME\s+(?:COLUMN\s+)?[\"`]?(\w+)[\"`]?\s+TO\s+[\"`]?(\w+)", a, re.I)
    if m:
        return destructive(f"RENAME COLUMN {m.group(1)} TO {m.group(2)}")
    m = re.match(r"CHANGE\s+(?:COLUMN\s+)?[\"`]?(\w+)[\"`]?\s+[\"`]?(\w+)", a, re.I)
    if m and m.group(1).lower() != m.group(2).lower():
        return destructive(f"RENAME COLUMN {m.group(1)} TO {m.group(2)}")
    m = re.match(r"ALTER\s+(?:COLUMN\s+)?[\"`]?(\w+)[\"`]?\s+(?:SET\s+DATA\s+)?TYPE\b", a, re.I)
    if m:
        return destructive(f"ALTER COLUMN {m.group(1)} TYPE")
    return []


def extract_sql_facts(path, added_set, text=None):
    text = read(path) if text is None else text
    facts = []
    postgres = not NON_PG_RX.search(text)
    # A table created in this same file is empty when the rest of the file runs,
    # so dropping, locking or backfilling it is not a production hazard.
    created = {m.group(1).lower() for m in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + NAME, text, re.I)}

    for stmt, start_line in sql_statements(text):
        s = stmt.strip()
        if not s:
            continue
        stmt_added = start_line in added_set

        m = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + NAME + r"\s*\(", s, re.I)
        if m:
            table = m.group(1)
            body = paren_body(s, m.end() - 1)
            cols = {}
            has_pk = False
            table_fks, uniques, pks = [], [], []
            cursor = m.end()
            for part in split_top_level(body):
                ln, cursor = line_of(s, part, cursor, start_line)
                if re.match(r"^\s*(PRIMARY\s+KEY|CONSTRAINT|FOREIGN\s+KEY|UNIQUE|CHECK)\b",
                            part, re.I):
                    pkm = re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", part, re.I)
                    if pkm:
                        has_pk = True
                        pks.append([c.strip(" \"`") for c in pkm.group(1).split(",")])
                    fkm = re.search(r"FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+" + NAME,
                                    part, re.I)
                    if fkm:
                        table_fks.append((fkm.group(1).split(",")[0].strip(" \"`"),
                                          fkm.group(2), ln))
                    um = re.match(r"^\s*(?:CONSTRAINT\s+" + NAME + r"\s+)?UNIQUE\s*\(([^)]*)\)",
                                  part, re.I)
                    if um:
                        uniques.append(([c.strip(" \"`") for c in um.group(2).split(",")], ln))
                    continue
                cm = re.match(r"^[\"`]?(\w+)[\"`]?\s+([A-Za-z0-9_]+(?:\s*\([^)]*\))?)\s*(.*)$",
                              part.strip(), re.S)
                if not cm:
                    continue
                name, coltype, rest = cm.group(1), cm.group(2), cm.group(3)
                rest_u = rest.upper()
                if "PRIMARY KEY" in rest_u:
                    has_pk = True
                    pks.append([name])
                elif re.search(r"\bUNIQUE\b", rest_u):
                    uniques.append(([name], ln))
                cols[name] = {"type": coltype, "rest": rest_u, "rest_orig": rest, "line": ln}
            facts.append({"kind": "table_new", "file": path, "line": start_line,
                          "table": table, "has_pk": has_pk,
                          "has_created_at": any(CREATED_RX.match(c) for c in cols),
                          "is_tenant": any(has_tenant_name(c) for c in cols),
                          "cols": cols, "added": stmt_added})
            for name, c in cols.items():
                facts.append({"kind": "column_in_new_table", "file": path, "line": c["line"],
                              "table": table, "name": name, "type": c["type"],
                              "nullable": "NOT NULL" not in c["rest"],
                              "has_default": "DEFAULT" in c["rest"], "added": stmt_added,
                              "is_money": bool(MONEY_RX.search(name)),
                              "is_floaty": bool(SQL_FLOATY_RX.search(c["type"]))})
            money_cols = [n for n in cols if MONEY_RX.search(n)]
            if stmt_added and money_cols and not any(CURRENCY_RX.search(n) for n in cols):
                facts.append({"kind": "money_no_currency", "file": path, "line": start_line,
                              "table": table})
            for name, c in cols.items():
                rm = re.search(r"REFERENCES\s+" + NAME, c["rest_orig"], re.I)
                if rm:
                    facts.append({"kind": "fk", "file": path, "line": c["line"],
                                  "table": table, "col": name, "ref_table": rm.group(1),
                                  "added": stmt_added})
            for col, ref_table, ln in table_fks:
                facts.append({"kind": "fk", "file": path, "line": ln,
                              "table": table, "col": col, "ref_table": ref_table,
                              "added": stmt_added})
            for ucols, ln in uniques:
                facts.append({"kind": "index_new", "file": path, "line": ln, "table": table,
                              "cols": ucols, "unique": True, "added": stmt_added})
            for pcols in pks:
                facts.append({"kind": "pk_index", "file": path, "line": start_line,
                              "table": table, "cols": pcols})
            continue

        m = re.match(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?" + NAME + r"\s+(.*)$",
                     s, re.I | re.S)
        if m:
            table = m.group(1)
            existing = table.lower() not in created
            cursor = m.start(2)
            for action in split_top_level(m.group(2).rstrip().rstrip(";")):
                ln, cursor = line_of(s, action, cursor, start_line)
                base = {"file": path, "line": ln, "added": stmt_added}
                facts += alter_action_facts(base, table, existing, action, postgres)
            continue

        m = re.match(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(.+?)(?:\s+(?:CASCADE|RESTRICT))?\s*;?$",
                     s, re.I | re.S)
        if m:
            for raw in m.group(1).split(","):
                nm = re.match(r"\s*" + NAME, raw)
                if nm and nm.group(1).lower() not in created:
                    facts.append({"kind": "destructive", "file": path, "line": start_line,
                                  "table": nm.group(1), "what": "DROP TABLE",
                                  "added": stmt_added})
            continue

        m = re.match(r"RENAME\s+TABLE\s+" + NAME + r"\s+TO\s+" + NAME, s, re.I)
        if m:
            if m.group(1).lower() not in created:
                facts.append({"kind": "destructive", "file": path, "line": start_line,
                              "table": m.group(1), "what": f"RENAME TABLE TO {m.group(2)}",
                              "added": stmt_added})
            continue

        m = re.match(r"CREATE\s+(UNIQUE\s+)?INDEX\s+(CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
                     r"(?:" + NAME + r"\s+)?ON\s+(?:ONLY\s+)?" + NAME +
                     r"(?:\s+USING\s+\w+)?\s*\(", s, re.I)
        if m:
            table = m.group(4)
            body = paren_body(s, m.end() - 1)
            cols = [c.strip(" \"`").split()[0] for c in split_top_level(body) if c.strip()]
            facts.append({"kind": "index_new", "file": path, "line": start_line,
                          "table": table, "cols": cols, "unique": bool(m.group(1)),
                          "added": stmt_added, "create_index": True,
                          "concurrently": bool(m.group(2)), "postgres": postgres,
                          "existing_table": table.lower() not in created})
            continue

        for vm in re.finditer(r"\bSELECT\s+\*", s, re.I):
            ln = start_line + s[:vm.start()].count("\n")
            facts.append({"kind": "select_star", "file": path, "line": ln,
                          "added": ln in added_set or stmt_added})

    return facts


# ---------------- JS/TS extraction (TypeORM / Knex / Sequelize) ----------------

def js_skip_braces(src, i):
    """Index just past the '}' matching the '{' at src[i], skipping literals."""
    depth, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"`":
            i, _ = js_literal(src, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def js_literal(src, i):
    """(end_index, text) for the string/template literal opening at src[i].

    Escapes that would be newlines become spaces and ${...} interpolations become
    a placeholder carrying the interpolation's own newlines, so every line of the
    extracted SQL stays on the same line number as in the source file.
    """
    q, j, n, out = src[i], i + 1, len(src), []
    while j < n:
        c = src[j]
        if c == "\\" and j + 1 < n:
            nxt = src[j + 1]
            out.append(" " if nxt in "ntr" else nxt)
            j += 2
            continue
        if c == q:
            return j + 1, "".join(out)
        if q == "`" and src.startswith("${", j):
            end = js_skip_braces(src, j + 1)
            out.append("__expr__" + "\n" * src.count("\n", j, end))
            j = end
            continue
        out.append(c)
        j += 1
    return n, "".join(out)


def js_inert_ranges(src):
    """Sorted (start, end) spans of comments and literals, where a call is not code."""
    ranges, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
        elif src[i] in "'\"`":
            j, _ = js_literal(src, i)
        else:
            i += 1
            continue
        ranges.append((i, j))
        i = j
    return ranges


def js_down_ranges(src):
    """Spans of down()/rollback bodies. A rollback is supposed to drop what up()
    added, so checking it would flag every reversible migration as destructive."""
    out = []
    for m in JS_DOWN_RX.finditer(src):
        k = m.end()
        if src[k - 1] == "{":
            out.append((m.start(), js_skip_braces(src, k - 1)))
            continue
        if src[m.start():k].lstrip().startswith("function"):
            b = src.find("{", k)
            if b >= 0:
                out.append((m.start(), js_skip_braces(src, b)))
            continue
        while k < len(src) and src[k].isspace():
            k += 1
        if k < len(src) and src[k] == "{":
            out.append((m.start(), js_skip_braces(src, k)))
            continue
        depth, j = 0, k
        while j < len(src):
            c = src[j]
            if c in "'\"`":
                j, _ = js_literal(src, j)
                continue
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
                if depth < 0:
                    break
            elif c in ",;" and depth == 0:
                break
            j += 1
        out.append((m.start(), j))
    return out


def js_call_sql(src, i):
    """(sql, start_index) for literal argument(s) at src[i:], joined across '+'.
    None when the argument is not a literal (a variable or builder call)."""
    n, pieces, start, last_end = len(src), [], None, None
    while True:
        while i < n and src[i].isspace():
            i += 1
        if i >= n or src[i] not in "'\"`":
            break
        end, text = js_literal(src, i)
        if start is None:
            start = i
        else:
            pieces.append("\n" * src.count("\n", last_end, i) or " ")
        pieces.append(text)
        last_end = i = end
        while i < n and src[i].isspace():
            i += 1
        if i < n and src[i] == "+":
            i += 1
            continue
        break
    return ("".join(pieces), start) if start is not None else (None, None)


def js_migration_sql(src):
    """Source-shaped text holding only the SQL passed to the migration's query
    calls outside down(), each terminated with ';'. Each fragment sits on its
    original line, so diff gating and reported lines are the .ts/.js file's own."""
    inert = js_inert_ranges(src)
    starts = [a for a, _ in inert]
    down = js_down_ranges(src)
    lines = [""] * (src.count("\n") + 1)
    for m in JS_SQL_CALL_RX.finditer(src):
        p = m.start()
        k = bisect.bisect_right(starts, p) - 1
        if (k >= 0 and p < inert[k][1]) or any(a <= p < b for a, b in down):
            continue
        sql, at = js_call_sql(src, m.end())
        if sql is None:
            continue
        ln = src.count("\n", 0, at)
        parts = sql.split("\n")
        for off, piece in enumerate(parts):
            lines[min(ln + off, len(lines) - 1)] += " " + piece
        lines[min(ln + len(parts) - 1, len(lines) - 1)] += " ;"
    return "\n".join(lines)


def extract_js_migration_facts(path, added_set):
    return extract_sql_facts(path, added_set, js_migration_sql(read(path)))


def extract_typeorm_entity_facts(path, added_set):
    src = read(path)
    if "@Entity" not in src:
        return []
    inert = js_inert_ranges(src)
    starts = [a for a, _ in inert]
    classes = [(m.start(), m.group(1)) for m in re.finditer(r"\bclass\s+(\w+)", src)]
    facts = []
    for m in re.finditer(r"@Column\s*\(", src):
        k = bisect.bisect_right(starts, m.start()) - 1
        if k >= 0 and m.start() < inert[k][1]:
            continue
        args = paren_body(src, m.end() - 1)
        after = m.end() + len(args) + 1
        pm = re.match(r"\s*(?:@\w+\s*(?:\([^)]*\))?\s*)*(?:(?:public|private|protected|readonly|"
                      r"declare|override)\s+)*(\w+)\s*[!?]?\s*:", src[after:])
        if not pm:
            continue
        prop = pm.group(1)
        colname = re.search(r"""\bname\s*:\s*['"`](\w+)['"`]""", args)
        floaty = bool(re.match(r"\s*" + TYPEORM_FLOAT, args, re.I)
                      or re.search(r"\btype\s*:\s*" + TYPEORM_FLOAT, args, re.I))
        first = src.count("\n", 0, m.start()) + 1
        last = src.count("\n", 0, after + pm.end()) + 1
        owner = [nm for pos, nm in classes if pos < m.start()]
        facts.append({"kind": "entity_column", "file": path, "line": first,
                      "table": owner[-1] if owner else "?", "name": prop,
                      "added": any_added(range(first, last + 1), added_set),
                      "is_money": bool(MONEY_RX.search(prop)
                                       or (colname and MONEY_RX.search(colname.group(1)))),
                      "is_floaty": floaty})
    return facts


# ---------------- Prisma extraction ----------------

def extract_prisma_facts(path, added_set):
    text = read(path)
    facts = []
    for mm in re.finditer(r"model\s+(\w+)\s*\{([^}]*)\}", text, re.S):
        model = mm.group(1)
        body = mm.group(2)
        model_line = text[:mm.start()].count("\n") + 1
        model_added = model_line in added_set

        field_lines, model_attr_lines = [], []
        for i, raw in enumerate(body.splitlines()):
            ln = model_line + i
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            if line.startswith("@@"):
                model_attr_lines.append((line, ln))
            else:
                field_lines.append((line, ln))

        fields = {}
        for line, ln in field_lines:
            fm = re.match(r"^(\w+)\s+(\w+)(\[\])?(\?)?\s*(.*)$", line)
            if not fm:
                continue
            name, ftype, optional, attrs = fm.group(1), fm.group(2), fm.group(4), fm.group(5)
            fields[name] = {"type": ftype, "optional": bool(optional), "attrs": attrs,
                            "line": ln, "list": bool(fm.group(3))}

        has_pk = any("@id" in f["attrs"] for f in fields.values()) or \
            any(re.search(r"@@id\(", l) for l, _ in model_attr_lines)
        has_created_at = any(n.lower() in ("createdat", "created_at") for n in fields)
        tenant_field = next((n for n in fields if has_tenant_name(n)), None)

        facts.append({"kind": "table_new", "file": path, "line": model_line,
                      "table": model, "has_pk": has_pk, "has_created_at": has_created_at,
                      "is_tenant": tenant_field is not None, "added": model_added,
                      "cols": fields})

        for name, f in fields.items():
            f_added = f["line"] in added_set
            is_money = bool(MONEY_RX.search(name))
            has_default = "@default(" in f["attrs"]
            # List and @relation fields are relations, not columns, so they never
            # need a backfill value.
            needs_value = (not model_added and not f["optional"] and not has_default
                           and not f["list"] and "@relation" not in f["attrs"])
            facts.append({"kind": "column_add" if not model_added else "column_in_new_table",
                          "file": path, "line": f["line"], "table": model, "name": name,
                          "type": f["type"], "nullable": f["optional"],
                          "has_default": has_default, "added": f_added,
                          "is_money": is_money, "is_floaty": PRISMA_FLOATY_RX.match(f["type"]) is not None,
                          "needs_backfill_value": needs_value})
            if "@unique" in f["attrs"] and tenant_field and name != tenant_field:
                facts.append({"kind": "index_new", "file": path, "line": f["line"],
                              "table": model, "cols": [name], "unique": True,
                              "added": f_added})
            rel = re.search(r"@relation\(\s*fields:\s*\[([^\]]+)\]", f["attrs"])
            if rel:
                facts.append({"kind": "fk", "file": path, "line": f["line"], "table": model,
                              "col": rel.group(1).split(",")[0].strip(), "ref_table": f["type"],
                              "added": f_added})

        for line, ln in model_attr_lines:
            um = re.search(r"@@(unique|index)\(\s*\[([^\]]+)\]", line)
            if um:
                cols = [c.strip() for c in um.group(2).split(",")]
                facts.append({"kind": "index_new", "file": path, "line": ln,
                              "table": model, "cols": cols,
                              "unique": um.group(1) == "unique", "added": ln in added_set})

        # money without a currency companion field, only when the money field is new
        money_new = [n for n, f in fields.items()
                     if MONEY_RX.search(n) and f["line"] in added_set]
        has_currency = any(CURRENCY_RX.search(n) for n in fields)
        if money_new and not has_currency:
            facts.append({"kind": "money_no_currency", "file": path,
                          "line": fields[money_new[0]]["line"], "table": model})

    return facts


# ---------------- Python ORM extraction (Django / SQLAlchemy style) ----------------

def logical_lines(text):
    """Join physical lines inside unbalanced parens so a multi-line field def is
    matchable with a single-line regex, while remembering which original line
    numbers each logical line spans (needed to gate on the diff)."""
    result, buf, spans, depth = [], [], set(), 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        if depth == 0 and buf:
            result.append((" ".join(buf), frozenset(spans)))
            buf, spans = [], set()
        buf.append(raw)
        spans.add(lineno)
        depth = max(0, depth + raw.count("(") - raw.count(")"))
    if buf:
        result.append((" ".join(buf), frozenset(spans)))
    return result


def extract_orm_facts(path, added_set):
    text = read(path)
    if "models.Model" not in text and "Column(" not in text and "declarative_base" not in text \
       and ") as Base" not in text and "Base):" not in text and "(Base)" not in text:
        return []
    facts = []
    lines = logical_lines(text)
    i = 0
    while i < len(lines):
        line, spans = lines[i]
        cm = re.match(r"^\s*class\s+(\w+)\s*\(([^)]*)\)\s*:", line)
        if not cm:
            i += 1
            continue
        name, bases = cm.group(1), cm.group(2)
        is_django = "Model" in bases
        is_sa = "Base" in bases and not is_django
        if not (is_django or is_sa):
            i += 1
            continue
        class_added = any_added(spans, added_set)
        j = i + 1
        body = []
        while j < len(lines):
            bl, bspans = lines[j]
            if re.match(r"^class\s+\w+", bl):
                break
            body.append((bl, bspans))
            j += 1

        cols = {}
        has_created_at = False
        has_pk_field = False
        tenant_field = None
        for bl, bspans in body:
            fm = re.match(r"^\s*(\w+)\s*=\s*(models\.\w+|db\.Column|Column)\s*\(", bl)
            if not fm:
                continue
            fname, ctor = fm.group(1), fm.group(2)
            if CREATED_RX.match(fname):
                has_created_at = True
            if has_tenant_name(fname):
                tenant_field = fname
            open_idx = bl.index("(", fm.end() - 1)
            args = paren_body(bl, open_idx)
            if "primary_key=True" in args or ctor.endswith("AutoField"):
                has_pk_field = True
            nullable = "null=True" in args or "nullable=True" in args
            has_default = "default=" in args
            is_floaty = bool(PY_FLOATY_RX.search(ctor)) or bool(PY_FLOATY_RX.search(args))
            cols[fname] = {"line": min(bspans), "spans": bspans, "nullable": nullable,
                           "has_default": has_default, "is_floaty": is_floaty,
                           "is_fk": "ForeignKey(" in args, "fk_indexed": "index=True" in args,
                           "unique": "unique=True" in args}

        has_pk = has_pk_field or is_django  # Django always has an implicit auto PK
        facts.append({"kind": "table_new", "file": path, "line": min(spans), "table": name,
                      "has_pk": has_pk, "has_created_at": has_created_at,
                      "is_tenant": tenant_field is not None, "added": class_added,
                      "cols": cols})

        for fname, c in cols.items():
            f_added = any_added(c["spans"], added_set)
            is_money = bool(MONEY_RX.search(fname))
            facts.append({"kind": "column_add" if not class_added else "column_in_new_table",
                          "file": path, "line": c["line"], "table": name, "name": fname,
                          "type": "?", "nullable": c["nullable"], "has_default": c["has_default"],
                          "added": f_added, "is_money": is_money, "is_floaty": c["is_floaty"]})
            if c["is_fk"] and is_sa and not c["fk_indexed"]:
                facts.append({"kind": "fk", "file": path, "line": c["line"], "table": name,
                              "col": fname, "ref_table": "?", "added": f_added,
                              "unindexed": True})
            if c["unique"] and tenant_field and fname != tenant_field:
                facts.append({"kind": "index_new", "file": path, "line": c["line"],
                              "table": name, "cols": [fname], "unique": True, "added": f_added})

        money_new = [n for n, c in cols.items() if MONEY_RX.search(n) and any_added(c["spans"], added_set)]
        has_currency = any(CURRENCY_RX.search(n) for n in cols)
        if money_new and not has_currency:
            facts.append({"kind": "money_no_currency", "file": path,
                          "line": cols[money_new[0]]["line"], "table": name})

        i = j
    return facts


# ---------------- fact gathering ----------------

def gather_facts(added, mod, base):
    facts = []
    for p in added + mod:
        if not is_schema_file(p):
            continue
        a = added_line_numbers(p, base)
        if p.endswith(".sql"):
            facts += extract_sql_facts(p, a)
        elif p.endswith(".prisma"):
            facts += extract_prisma_facts(p, a)
        elif p.endswith(".py"):
            facts += extract_orm_facts(p, a)
        elif is_js_migration(p):
            facts += extract_js_migration_facts(p, a)
        else:
            facts += extract_typeorm_entity_facts(p, a)
    return facts


# ---------------- checks (operate on gathered facts) ----------------

def check_money_float(facts, **_):
    out = []
    for f in facts:
        if f["kind"] in ("column_add", "column_in_new_table", "entity_column") and f.get("added") \
           and f.get("is_money") and f.get("is_floaty"):
            out.append((f"{f['file']}:{f['line']}",
                        f"{f['table']}.{f['name']} is money-shaped and FLOAT/REAL/DOUBLE -- "
                        f"use integer minor units or a decimal/numeric type"))
    return out


def check_money_currency(facts, **_):
    out = []
    for f in facts:
        if f["kind"] == "money_no_currency":
            out.append((f"{f['file']}:{f['line']}",
                        f"{f['table']} has a money-shaped column with no companion "
                        f"currency column/field visible in this diff"))
    return out


def check_new_table_pk(facts, **_):
    out = []
    for f in facts:
        if f["kind"] == "table_new" and f["added"] and not f["has_pk"]:
            out.append((f"{f['file']}:{f['line']}",
                        f"table/model {f['table']} has no primary key"))
    return out


def check_new_table_created_at(facts, **_):
    out = []
    for f in facts:
        if f["kind"] == "table_new" and f["added"] and not f["has_created_at"]:
            out.append((f"{f['file']}:{f['line']}",
                        f"table/model {f['table']} has no created_at-equivalent column"))
    return out


def check_not_null_no_default(facts, **_):
    out = []
    for f in facts:
        if f["kind"] == "column_add" and f.get("added") and f.get("needs_backfill_value"):
            out.append((f"{f['file']}:{f['line']}",
                        f"{f['table']}.{f['name']} added NOT NULL with no DEFAULT to an "
                        f"existing table -- fails on any table that already has rows; add it "
                        f"nullable or with a DEFAULT, backfill, then SET NOT NULL"))
    return out


def check_expand_contract(facts, **_):
    additive_files = {f["file"] for f in facts if f.get("added") and (
        f["kind"] in ("table_new", "index_new", "column_add"))}
    out = []
    for f in facts:
        if f["kind"] != "destructive" or not f.get("added"):
            continue
        msg = (f"destructive change ({f['what']} on {f['table']}) -- code from the previous "
               f"deploy still reads the old shape while this one rolls out: expand (add the new "
               f"shape), migrate readers and backfill, then contract in a later deploy once "
               f"nothing references it")
        if f["file"] in additive_files:
            msg += "; also mixed with an additive change in the same migration -- split them"
        out.append((f"{f['file']}:{f['line']}", msg))
    return out


def index_covers(cols, col):
    """Whether an index serves lookups on col: col leads it, or col directly
    follows a tenant column. The tenant-first composite that tenant-index asks
    for already serves every tenant-scoped join on the FK; demanding a second
    FK-leading index would make the two rules contradict each other."""
    cols = [c.lower().strip(" \"'`") for c in cols]
    col = col.lower()
    return bool(cols) and (cols[0] == col or (len(cols) > 1 and cols[1] == col
                                              and has_tenant_name(cols[0])))


def check_fk_index(facts, **_):
    indexes = {}  # (file, table) -> [cols, ...]
    for f in facts:
        if f["kind"] in ("index_new", "pk_index") and f.get("cols"):
            indexes.setdefault((f["file"], f["table"].lower()), []).append(f["cols"])
    out = []
    for f in facts:
        if f["kind"] != "fk" or not f.get("added"):
            continue
        if f.get("unindexed"):
            out.append((f"{f['file']}:{f['line']}",
                        f"FK {f['table']}.{f['col']} has no index=True"))
            continue
        if not any(index_covers(c, f["col"])
                   for c in indexes.get((f["file"], f["table"].lower()), [])):
            out.append((f"{f['file']}:{f['line']}",
                        f"FK {f['table']}.{f['col']} -> {f['ref_table']} has no index "
                        f"on the referencing column"))
    return out


def check_fk_not_valid(facts, **_):
    out = []
    for f in facts:
        if f["kind"] == "fk" and f.get("added") and f.get("constraint_on_existing") \
           and f.get("postgres") and not f.get("not_valid"):
            out.append((f"{f['file']}:{f['line']}",
                        f"FK {f['table']}.{f['col']} -> {f['ref_table']} added to an existing "
                        f"table without NOT VALID -- validation scans the whole table while "
                        f"blocking writes; add it NOT VALID, then VALIDATE CONSTRAINT separately"))
    return out


def check_index_concurrently(facts, **_):
    out = []
    for f in facts:
        if f["kind"] == "index_new" and f.get("create_index") and f.get("added") \
           and f.get("postgres") and f.get("existing_table") and not f.get("concurrently"):
            out.append((f"{f['file']}:{f['line']}",
                        f"CREATE INDEX on existing table {f['table']} without CONCURRENTLY -- "
                        f"blocks writes for the whole build; use CREATE INDEX CONCURRENTLY "
                        f"(outside a transaction)"))
    return out


def _tenant_scope(facts):
    tenant_tables = {(f["file"], f["table"].lower()) for f in facts
                     if f["kind"] == "table_new" and f.get("is_tenant")}
    fk_cols = {(f["file"], f["table"].lower(), f["col"].lower()) for f in facts
               if f["kind"] == "fk"}
    return tenant_tables, fk_cols


def check_tenant_index(facts, **_):
    tenant_tables, _ = _tenant_scope(facts)
    out = []
    for f in facts:
        if f["kind"] != "index_new" or not f.get("added") or not f["unique"]:
            continue
        if (f["file"], f["table"].lower()) not in tenant_tables:
            continue
        if not any(has_tenant_name(c) for c in f["cols"]):
            out.append((f"{f['file']}:{f['line']}",
                        f"unique constraint on tenant-scoped table {f['table']} omits the "
                        f"tenant column ({', '.join(f['cols'])}) -- cross-tenant leak"))
    return out


def check_tenant_lookup_index(facts, **_):
    tenant_tables, fk_cols = _tenant_scope(facts)
    out = []
    for f in facts:
        if f["kind"] != "index_new" or not f.get("added") or f["unique"] or not f["cols"]:
            continue
        key = (f["file"], f["table"].lower())
        if key not in tenant_tables or any(has_tenant_name(c) for c in f["cols"]):
            continue
        # An index leading with an FK column exists for joins and cascades, which
        # the FK value already scopes; it is not a tenant lookup path.
        if key + (f["cols"][0].lower().strip(" \"'`"),) in fk_cols:
            continue
        out.append((f"{f['file']}:{f['line']}",
                    f"lookup index on tenant-scoped table {f['table']} ({', '.join(f['cols'])}) "
                    f"omits the tenant column -- tenant-scoped queries cannot use it fully; "
                    f"lead with the tenant column"))
    return out


def check_select_star(facts, **_):
    out = []
    for f in facts:
        if f["kind"] == "select_star" and f.get("added"):
            out.append((f"{f['file']}:{f['line']}", "SELECT * in a migration or view"))
    return out


CHECKS = {
    "money-float": check_money_float,
    "money-currency": check_money_currency,
    "new-table-pk": check_new_table_pk,
    "new-table-created-at": check_new_table_created_at,
    "not-null-no-default": check_not_null_no_default,
    "expand-contract": check_expand_contract,
    "fk-index": check_fk_index,
    "fk-not-valid": check_fk_not_valid,
    "index-concurrently": check_index_concurrently,
    "tenant-index": check_tenant_index,
    "tenant-lookup-index": check_tenant_lookup_index,
    "select-star": check_select_star,
}
ADVISORY = {"money-currency", "new-table-created-at", "fk-index", "fk-not-valid",
            "index-concurrently", "tenant-lookup-index", "select-star"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="compare against this ref (default: HEAD)")
    ap.add_argument("--only", default=None, help="comma-separated subset of checks")
    ap.add_argument("--strict", action="store_true", help="treat advisory checks as failures")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k in CHECKS:
            print(f"{k}{' (advisory)' if k in ADVISORY else ''}")
        return 0

    names = [n.strip() for n in a.only.split(",")] if a.only else list(CHECKS)
    bad = [n for n in names if n not in CHECKS]
    if bad:
        print(f"unknown check(s): {', '.join(bad)}", file=sys.stderr)
        return 2

    if enter_git_root("schema_check", a.base) is None:
        return 2
    added, mod = changed(a.base)
    if unreadable(added + mod, "schema_check"):
        return 2
    try:
        relevant = [p for p in added + mod if is_schema_file(p)]
        if not relevant:
            print("schema_check: no SQL/Prisma/ORM changes to inspect")
            return 0
        facts = gather_facts(added, mod, a.base)
    except OSError as e:
        print(f"schema_check: cannot read {e.filename}: {e.strerror} -- nothing was "
              f"checked.", file=sys.stderr)
        return 2

    hard = advisory = 0
    for n in names:
        try:
            res = CHECKS[n](facts)
        except Exception as e:
            # A check that crashed has not passed; counting it as clean would
            # silently disable it.
            print(f"  ! {n} errored: {type(e).__name__}: {e}", file=sys.stderr)
            hard += 1
            continue
        if not res:
            continue
        res = sorted(set(res))
        adv = n in ADVISORY and not a.strict
        print(f"\n[{'ADVISORY' if adv else 'FAIL'}] {n}")
        for loc, msg in res[:12]:
            print(f"  {loc}: {msg}")
        if len(res) > 12:
            print(f"  ... {len(res) - 12} more")
        if adv:
            advisory += len(res)
        else:
            hard += len(res)

    print(f"\nschema_check: {len(relevant)} schema files touched | "
          f"{hard} blocking, {advisory} advisory")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
