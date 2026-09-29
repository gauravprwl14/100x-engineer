#!/usr/bin/env python3
"""Diff-scoped checks for the schema mistakes that don't show up until production.

Companion to bloat_check.py: that script catches AI-shaped code smells, this one
catches AI-shaped (and human-shaped) SCHEMA smells -- the ones that are cheap to
fix in a migration that hasn't shipped and expensive to fix once a table has rows.
Scoped to the diff so it is runnable against an existing, large schema, not just
a greenfield one.

Covers three shapes, on purpose (see the data-modeling skill's Honest limitations
for what is deliberately NOT covered):
  - SQL migrations (*.sql)          -- CREATE/ALTER/DROP TABLE, indexes, views
  - Prisma schemas (*.prisma)       -- model blocks, field/model attributes
  - Python ORM models (*.py)        -- Django-style and SQLAlchemy-style classes

    schema_check.py                        # check staged+unstaged vs HEAD
    schema_check.py --base origin/main
    schema_check.py --only money-float,tenant-index
    schema_check.py --strict            # treat advisory checks as failures too

Exit 1 if any blocking check finds a violation.
"""
import argparse, pathlib, re, subprocess, sys

MONEY_RX = re.compile(r"\b\w*(price|amount|total|balance|cost|fee|salary)\w*\b", re.I)
CURRENCY_RX = re.compile(r"\b\w*(currency|ccy|curr_code)\w*\b", re.I)
TENANT_NAMES = ("tenant_id", "tenantid", "org_id", "orgid", "account_id", "accountid")
CREATED_RX = re.compile(r"^(created_at|createdat|created_on|createdon|inserted_at|created)$", re.I)
SQL_FLOATY_RX = re.compile(r"\b(FLOAT4?|FLOAT8?|REAL|DOUBLE(\s+PRECISION)?)\b", re.I)
PRISMA_FLOATY_RX = re.compile(r"^Float$")
PY_FLOATY_RX = re.compile(r"\b(FloatField|Float)\b")


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed(base):
    """(added, modified) paths in the diff. Mirrors bloat_check.py's semantics."""
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--name-status", "--diff-filter=AM"] + rng)
    added, mod = [], []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        (added if parts[0].startswith("A") else mod).append(parts[-1])
    for p in sh(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        if p and p not in added:
            added.append(p)
    return added, mod


def added_line_numbers(path, base):
    """1-indexed line numbers in the CURRENT file content that this diff added.

    Used to gate every finding on 'did this diff introduce the thing', not 'does
    this pre-existing schema have the thing' -- the difference between a useful
    diff-scoped gate and a whole-repo scan that gets disabled on day one.
    """
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--unified=0"] + rng + ["--", path])
    if not out:
        try:
            n = len(pathlib.Path(path).read_text(errors="replace").splitlines())
        except OSError:
            return set()
        return set(range(1, n + 1))
    nums = set()
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", out, re.M):
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        nums.update(range(start, start + count))
    return nums


def read(path):
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except OSError:
        return ""


def any_added(spans, added_set):
    return any(l in added_set for l in spans)


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
    parts, depth, buf = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def sql_statements(text):
    """[(statement_text, start_line)], splitting on unquoted ';'."""
    stmts, buf = [], []
    start_line = line = 1
    in_str = False
    for ch in text:
        buf.append(ch)
        if ch == "\n":
            line += 1
        if ch == "'":
            in_str = not in_str
        if ch == ";" and not in_str:
            stmts.append(("".join(buf), start_line))
            buf = []
            start_line = line
    if "".join(buf).strip():
        stmts.append(("".join(buf), start_line))
    return stmts


def has_tenant_name(name):
    return name.lower().replace("-", "_") in TENANT_NAMES


# ---------------- SQL extraction ----------------

def extract_sql_facts(path, added_set):
    text = read(path)
    facts = []
    tables = {}  # table -> {"cols": {name: coldef}, "line": n, "added": bool}

    for stmt, start_line in sql_statements(text):
        s = stmt.strip()
        if not s:
            continue
        stmt_added = start_line in added_set

        m = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)[\"`]?\s*\(",
                       s, re.I)
        if m:
            table = m.group(1)
            body = paren_body(s, s.index("(", m.start()))
            cols = {}
            has_pk = False
            table_fks = []
            for part in split_top_level(body):
                if re.match(r"^\s*(PRIMARY\s+KEY|CONSTRAINT|FOREIGN\s+KEY|UNIQUE|CHECK)\b",
                            part, re.I):
                    if re.match(r"^\s*PRIMARY\s+KEY", part, re.I):
                        has_pk = True
                    fkm = re.search(r"FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+"
                                     r"[\"`]?(\w+)", part, re.I)
                    if fkm:
                        table_fks.append((fkm.group(1).split(",")[0].strip(" \"`"),
                                           fkm.group(2)))
                    continue
                cm = re.match(r"^[\"`]?(\w+)[\"`]?\s+([A-Za-z0-9_]+(?:\s*\([^)]*\))?)\s*(.*)$",
                               part.strip())
                if not cm:
                    continue
                name, coltype, rest = cm.group(1), cm.group(2), cm.group(3)
                rest_u = rest.upper()
                if "PRIMARY KEY" in rest_u:
                    has_pk = True
                cols[name] = {"type": coltype, "rest": rest_u, "rest_orig": rest}
            tables[table] = {"cols": cols, "line": start_line, "added": stmt_added}
            facts.append({"kind": "table_new", "file": path, "line": start_line,
                           "table": table, "has_pk": has_pk,
                           "has_created_at": any(CREATED_RX.match(c) for c in cols),
                           "is_tenant": any(has_tenant_name(c) for c in cols),
                           "cols": cols, "added": stmt_added})
            for name, c in cols.items():
                is_money = bool(MONEY_RX.search(name))
                facts.append({"kind": "column_in_new_table", "file": path, "line": start_line,
                               "table": table, "name": name, "type": c["type"],
                               "nullable": "NOT NULL" not in c["rest"],
                               "has_default": "DEFAULT" in c["rest"], "added": stmt_added,
                               "is_money": is_money,
                               "is_floaty": bool(SQL_FLOATY_RX.search(c["type"]))})
            money_cols = [n for n in cols if MONEY_RX.search(n)]
            if stmt_added and money_cols and not any(CURRENCY_RX.search(n) for n in cols):
                facts.append({"kind": "money_no_currency", "file": path, "line": start_line,
                               "table": table})
            for name, c in cols.items():
                rm = re.search(r"REFERENCES\s+[\"`]?(\w+)", c["rest_orig"], re.I)
                if rm:
                    facts.append({"kind": "fk", "file": path, "line": start_line,
                                   "table": table, "col": name, "ref_table": rm.group(1),
                                   "added": stmt_added})
            for col, ref_table in table_fks:
                facts.append({"kind": "fk", "file": path, "line": start_line,
                               "table": table, "col": col, "ref_table": ref_table,
                               "added": stmt_added})
            continue

        m = re.search(r"ALTER\s+TABLE\s+[\"`]?(\w+)[\"`]?\s+ADD\s+COLUMN\s+[\"`]?(\w+)[\"`]?"
                       r"\s+([A-Za-z0-9_]+(?:\s*\([^)]*\))?)\s*(.*)", s, re.I)
        if m:
            table, name, coltype, rest = m.groups()
            rest_u = (rest or "").upper()
            facts.append({"kind": "column_add", "file": path, "line": start_line,
                           "table": table, "name": name, "type": coltype,
                           "nullable": "NOT NULL" not in rest_u,
                           "has_default": "DEFAULT" in rest_u,
                           "added": stmt_added,
                           "is_money": bool(MONEY_RX.search(name)),
                           "is_floaty": bool(SQL_FLOATY_RX.search(coltype))})
            continue

        m = re.search(r"ALTER\s+TABLE\s+[\"`]?(\w+)[\"`]?\s+DROP\s+COLUMN\s+[\"`]?(\w+)",
                       s, re.I)
        if m:
            facts.append({"kind": "destructive", "file": path, "line": start_line,
                           "table": m.group(1), "what": f"DROP COLUMN {m.group(2)}",
                           "added": stmt_added})
            continue

        m = re.search(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?[\"`]?(\w+)", s, re.I)
        if m:
            facts.append({"kind": "destructive", "file": path, "line": start_line,
                           "table": m.group(1), "what": "DROP TABLE",
                           "added": stmt_added})
            continue

        m = re.search(r"ALTER\s+TABLE\s+[\"`]?(\w+)[\"`]?\s+ALTER(?:\s+COLUMN)?\s+"
                       r"[\"`]?(\w+)[\"`]?\s+(?:TYPE|SET\s+DATA\s+TYPE)\s+", s, re.I)
        if m:
            facts.append({"kind": "destructive", "file": path, "line": start_line,
                           "table": m.group(1), "what": f"ALTER COLUMN {m.group(2)} TYPE",
                           "added": stmt_added})
            continue

        m = re.search(r"CREATE\s+(UNIQUE\s+)?INDEX\s+[\"`]?\w+[\"`]?\s+ON\s+[\"`]?(\w+)[\"`]?"
                       r"\s*\(", s, re.I)
        if m:
            unique = bool(m.group(1))
            table = m.group(2)
            body = paren_body(s, s.rindex("(", 0, s.find(")", m.end()) + 1)
                               if ")" in s[m.end():] else s.index("(", m.end() - 1))
            cols = [c.strip(" \"`").split()[0] for c in split_top_level(body) if c.strip()]
            facts.append({"kind": "index_new", "file": path, "line": start_line,
                           "table": table, "cols": cols, "unique": unique,
                           "added": stmt_added})
            continue

        m = re.search(r"ALTER\s+TABLE\s+[\"`]?(\w+)[\"`]?\s+ADD\s+(?:CONSTRAINT\s+\w+\s+)?"
                       r"UNIQUE\s*\(([^)]*)\)", s, re.I)
        if m:
            cols = [c.strip(" \"`") for c in m.group(2).split(",") if c.strip()]
            facts.append({"kind": "index_new", "file": path, "line": start_line,
                           "table": m.group(1), "cols": cols, "unique": True,
                           "added": stmt_added})
            continue

        for fkm in re.finditer(r"REFERENCES\s+[\"`]?(\w+)", s, re.I):
            tbl_m = re.search(r"(?:ALTER\s+TABLE|CREATE\s+TABLE)\s+[\"`]?(\w+)", s, re.I)
            col_m = re.search(r"[\"`]?(\w+)[\"`]?\s+[A-Za-z0-9_]+[^,]*?REFERENCES", s, re.I)
            if tbl_m:
                facts.append({"kind": "fk", "file": path, "line": start_line,
                               "table": tbl_m.group(1),
                               "col": col_m.group(1) if col_m else "?",
                               "ref_table": fkm.group(1), "added": stmt_added})

        for vm in re.finditer(r"\bSELECT\s+\*", s, re.I):
            ln = start_line + s[:vm.start()].count("\n")
            facts.append({"kind": "select_star", "file": path, "line": ln,
                           "added": ln in added_set or stmt_added})

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
                             "line": ln}

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
            facts.append({"kind": "column_add" if not model_added else "column_in_new_table",
                           "file": path, "line": f["line"], "table": model, "name": name,
                           "type": f["type"], "nullable": f["optional"],
                           "has_default": "@default(" in f["attrs"], "added": f_added,
                           "is_money": is_money, "is_floaty": PRISMA_FLOATY_RX.match(f["type"]) is not None})
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
        a = added_line_numbers(p, base)
        if p.endswith(".sql"):
            facts += extract_sql_facts(p, a)
        elif p.endswith(".prisma"):
            facts += extract_prisma_facts(p, a)
        elif p.endswith(".py"):
            facts += extract_orm_facts(p, a)
    return facts


# ---------------- checks (operate on gathered facts) ----------------

def check_money_float(facts, **_):
    out = []
    for f in facts:
        if f["kind"] in ("column_add", "column_in_new_table") and f.get("added") \
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


def check_nullable_no_default(facts, **_):
    out = []
    for f in facts:
        if f["kind"] == "column_add" and f["added"] and f.get("nullable") \
           and not f.get("has_default"):
            out.append((f"{f['file']}:{f['line']}",
                        f"{f['table']}.{f['name']} added nullable with no default -- "
                        f"confirm the code path actually treats it as optional"))
    return out


def check_expand_contract(facts, **_):
    by_file = {}
    for f in facts:
        by_file.setdefault(f["file"], {"destructive": [], "additive": []})
        if f["kind"] == "destructive":
            by_file[f["file"]]["destructive"].append(f)
        elif f["kind"] in ("table_new", "index_new") and f.get("added"):
            by_file[f["file"]]["additive"].append(f)
        elif f["kind"] == "column_add" and f.get("added"):
            by_file[f["file"]]["additive"].append(f)
    out = []
    for file, d in by_file.items():
        if d["destructive"] and d["additive"]:
            whats = ", ".join(sorted({x["what"] for x in d["destructive"]}))
            out.append((file, f"destructive change ({whats}) mixed with an additive change "
                               f"in the same migration -- split into expand then contract"))
    return out


def check_fk_index(facts, **_):
    indexed_cols = {}  # (file, table) -> set of first-cols covered by an index
    for f in facts:
        if f["kind"] == "index_new" and f.get("cols"):
            indexed_cols.setdefault((f["file"], f["table"]), set()).add(f["cols"][0])
    out = []
    for f in facts:
        if f["kind"] != "fk" or not f.get("added"):
            continue
        if f.get("unindexed"):
            out.append((f"{f['file']}:{f['line']}",
                        f"FK {f['table']}.{f['col']} has no index=True"))
            continue
        covered = indexed_cols.get((f["file"], f["table"]), set())
        if f["col"] not in covered:
            out.append((f"{f['file']}:{f['line']}",
                        f"FK {f['table']}.{f['col']} -> {f['ref_table']} has no index "
                        f"on the referencing column"))
    return out


def check_tenant_index(facts, **_):
    tenant_tables = {}  # (file, table) -> True
    for f in facts:
        if f["kind"] == "table_new" and f.get("is_tenant"):
            tenant_tables[(f["file"], f["table"])] = True
    out = []
    for f in facts:
        if f["kind"] != "index_new" or not f.get("added"):
            continue
        key = (f["file"], f["table"])
        if key not in tenant_tables:
            continue
        cols_lower = [c.lower().strip(" \"'`") for c in f["cols"]]
        if not any(c in TENANT_NAMES for c in cols_lower):
            kind = "unique constraint" if f["unique"] else "index"
            out.append((f"{f['file']}:{f['line']}",
                        f"{kind} on tenant-scoped table {f['table']} omits the tenant "
                        f"column ({', '.join(f['cols'])}) -- cross-tenant leak"))
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
    "nullable-no-default": check_nullable_no_default,
    "expand-contract": check_expand_contract,
    "fk-index": check_fk_index,
    "tenant-index": check_tenant_index,
    "select-star": check_select_star,
}
ADVISORY = {"money-currency", "new-table-created-at", "nullable-no-default",
            "fk-index", "select-star"}


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

    added, mod = changed(a.base)
    relevant = [p for p in added + mod if p.endswith((".sql", ".prisma", ".py"))]
    if not relevant:
        print("schema_check: no SQL/Prisma/ORM changes to inspect")
        return 0

    facts = gather_facts(added, mod, a.base)

    hard = advisory = 0
    for n in names:
        try:
            res = CHECKS[n](facts)
        except Exception as e:
            print(f"  ! {n} errored: {type(e).__name__}: {e}", file=sys.stderr)
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
