#!/usr/bin/env python3
"""Diff-scoped application-security checks for skills/app-security/SKILL.md.

Same plumbing shape as scripts/a11y_check.py: only lines the current diff touched
are reported, --base/--only/--strict/--list, Python stdlib only.

Detection is regex with one hop of taint tracking (a variable assigned from the
request, then used in a sink, in the same file). It is not a data-flow analyser:
taint that crosses a function or file boundary is invisible to it, and it trusts
any allowlist or sanitiser it can see by name. It under-fires on purpose; run a
real SAST suite (CodeQL, Semgrep) beside it. tests/test_appsec_check.sh pairs
every detection with a clean form that must not be flagged.

    appsec_check.py                     # all checks vs HEAD
    appsec_check.py --base origin/main
    appsec_check.py --only ssrf,sql-concat
    appsec_check.py --strict            # advisory findings also fail
    appsec_check.py --list

Blocking: ssrf, mass-assignment, unsafe-html, sql-concat, hardcoded-secret.
Advisory: dto-spread-into-orm, nest-controller-no-guard.
Test and fixture paths are skipped. Exit 1 on a blocking finding (any finding
under --strict); exit 2 outside a git repository or with an unresolvable --base.
"""
import argparse, math, re, subprocess, sys, pathlib, collections

from _mutation_guard import enter_git_root

CODE_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".py")
SKIP_RX = re.compile(
    r"(?:^|/)(?:__tests__|__mocks__|tests?|spec|fixtures?|testdata|e2e|mocks?)/"
    r"|\.(?:test|spec|stories)\.[a-z]+$|(?:^|/)test_[^/]+\.py$|_test\.py$"
    r"|\.(?:example|sample|template)(?:\.[a-z]+)?$"
    r"|(?:^|/)(?:package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|uv\.lock)$")
BINARY_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
              ".woff", ".woff2", ".ttf", ".mp4", ".mov", ".jar", ".so", ".dylib")

RULE = {
    "ssrf": "rule 8, OWASP API7:2023 Server Side Request Forgery",
    "mass-assignment": "rule 4, OWASP API3:2023 Broken Object Property Level Authorization",
    "dto-spread-into-orm": "rule 4, OWASP API3:2023 (allowlist the writable fields)",
    "unsafe-html": "rule 10, OWASP XSS Prevention Cheat Sheet (output encoding)",
    "sql-concat": "rule 12, OWASP Query Parameterization Cheat Sheet",
    "hardcoded-secret": "rule 11, secrets never in code (gitleaks rule ids aws-access-token, private-key)",
    "nest-controller-no-guard": "rule 6, OWASP API5:2023 Broken Function Level Authorization",
}


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def changed(base):
    rng = [base] if base else ["HEAD"]
    files = []
    for line in sh(["git", "diff", "--name-status", "--diff-filter=AM"] + rng).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            files.append(parts[-1])
    for p in sh(["git", "ls-files", "--others", "--exclude-standard"]).splitlines():
        if p and p not in files:
            files.append(p)
    return [f for f in files if not SKIP_RX.search(f)]


def touched_lines(path, base):
    rng = [base] if base else ["HEAD"]
    out = sh(["git", "diff", "--unified=0"] + rng + ["--", path])
    if not out:
        return None
    lines = set()
    for l in out.splitlines():
        if l.startswith("@@"):
            m = re.search(r"\+(\d+)(?:,(\d+))?", l)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                lines |= set(range(start, start + count))
    return lines


def overlaps(touched, ln):
    return touched is None or ln in touched


def read(path):
    try:
        return pathlib.Path(path).read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return None


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def call_args(text, open_idx):
    """Text inside the parenthesis at open_idx, balanced across (), [], {}."""
    depth, i, quote = 0, open_idx, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i]
        i += 1
    return text[open_idx + 1:]


def first_arg(args):
    depth, quote = 0, None
    for i, c in enumerate(args):
        if quote:
            if c == quote and args[i - 1] != "\\":
                quote = None
        elif c in "'\"`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            return args[:i].strip()
    return args.strip()


def code_files(files):
    for p in files:
        if p.endswith(CODE_EXT):
            text = read(p)
            if text is not None:
                yield p, text


# --- taint: request input, one hop ------------------------------------------
TAINT_SRC = (r"\b(?:req|request|ctx\.request|ctx)\.(?:body|query|params|args|form|json|"
             r"GET|POST|data|values)\b|\bevent\.(?:body|queryStringParameters|pathParameters)\b"
             r"|\brequest\.get_json\(")
TAINT_SRC_RX = re.compile(TAINT_SRC)
ASSIGN_RX = re.compile(r"(?:\b(?:const|let|var)\s+)?(\{[^{}=]*\}|[A-Za-z_$][\w$]*)\s*=(?!=)\s*([^\n;]*)")
NEST_PARAM_RX = re.compile(r"@(?:Body|Query|Param)\([^)]*\)\s*([A-Za-z_$][\w$]*)")


def tainted_names(text):
    names = set(NEST_PARAM_RX.findall(text))
    for m in ASSIGN_RX.finditer(text):
        lhs, rhs = m.group(1), m.group(2)
        if not TAINT_SRC_RX.search(rhs) and not any(re.search(rf"\b{re.escape(n)}\b", rhs) for n in names):
            continue
        if lhs.startswith("{"):
            names |= {re.split(r"[:=]", n)[-1].strip() for n in lhs.strip("{} ").split(",") if n.strip()}
        else:
            names.add(lhs)
    return {n for n in names if n and re.fullmatch(r"[A-Za-z_$][\w$]*", n)}


def is_tainted(expr, names):
    return bool(TAINT_SRC_RX.search(expr)) or any(re.search(rf"(?<![\w.$]){re.escape(n)}\b", expr) for n in names)


# --- ssrf ------------------------------------------------------------------
HTTP_CALL_RX = re.compile(
    r"\b(?:fetch|axios(?:\.(?:get|post|put|patch|delete|head|request))?|got(?:\.(?:get|post|put|patch|delete))?"
    r"|https?\.(?:get|request)|requests\.(?:get|post|put|patch|delete|head|request)"
    r"|httpx\.(?:get|post|put|patch|delete|request)|urlopen|\$fetch|ky(?:\.(?:get|post))?)\s*\(")
ALLOWLIST_RX = re.compile(r"(?i)allow[_-]?list|allowed[_-]?(?:hosts?|domains?|origins?|urls?)|safe[_-]?list|whitelist|isAllowed(?:Url|Host)")
FIXED_HOST_RX = re.compile(r"""^(?:[`'"]https?://[^/$`'"{]+/|`\$\{\s*(?:[A-Z][A-Z0-9_]*|this\.\w+|config\.[\w.]+|(?:base|api)Url)\s*\}/|f["']https?://[^/{"']+/)""")


def check_ssrf(files, base):
    out = []
    for p, text in code_files(files):
        if ALLOWLIST_RX.search(text):
            continue
        names = tainted_names(text)
        touched = touched_lines(p, base)
        for m in HTTP_CALL_RX.finditer(text):
            arg = first_arg(call_args(text, m.end() - 1))
            if not arg or FIXED_HOST_RX.match(arg):
                continue
            # an options object passes the URL as a `url:` property
            url_prop = re.search(r"\burl\s*:\s*([^,}]+)", arg)
            target = url_prop.group(1) if arg.startswith("{") and url_prop else arg
            if not is_tainted(target, names):
                continue
            ln = line_of(text, m.start())
            if overlaps(touched, ln):
                out.append((f"{p}:{ln}", f"outbound request to a URL from request input "
                            f"({target.strip()[:50]}) with no host allowlist in this file [{RULE['ssrf']}]"))
    return out


# --- mass assignment ---------------------------------------------------------
BODY = r"(?:req|request|ctx\.request)\.body\b(?!\s*\.)"
OBJ_ASSIGN_RX = re.compile(r"\bObject\.assign\s*\(\s*[\w$.]+\s*,\s*" + BODY)
ORM_CALL_RX = re.compile(
    r"\.(?:create|update|save|insert|upsert|merge|build|set|findOneAndUpdate|updateOne|updateMany"
    r"|findByIdAndUpdate|bulkCreate|createMany|updateById|patch)\s*\(")
DATA_BODY_RX = re.compile(r"\bdata\s*:\s*" + BODY)
SPREAD_BODY_RX = re.compile(r"\.\.\.\s*" + BODY)
DIRECT_BODY_RX = re.compile(r"^\s*" + BODY + r"\s*$")
SPREAD_DTO_RX = re.compile(r"\.\.\.\s*(?:this\.)?([A-Za-z_$]*[dD]to)\b(?!\s*\.)")


def check_mass_assignment(files, base, want_dto=False):
    out = []
    for p, text in code_files(files):
        touched = touched_lines(p, base)
        hits = []
        if not want_dto:
            hits += [(m.start(), "Object.assign() of req.body onto an entity copies every client field")
                     for m in OBJ_ASSIGN_RX.finditer(text)]
        for m in ORM_CALL_RX.finditer(text):
            args = call_args(text, m.end() - 1)
            if want_dto:
                d = SPREAD_DTO_RX.search(args)
                if d:
                    hits.append((m.start(), f"...{d.group(1)} spread into {m.group(0)[:-1].strip()}"
                                 f"() writes every DTO field -- name the writable fields"))
                continue
            if DATA_BODY_RX.search(args) or SPREAD_BODY_RX.search(args) or DIRECT_BODY_RX.match(first_arg(args)):
                hits.append((m.start(), f"raw request body passed to {m.group(0)[:-1].strip()}() "
                             f"-- client chooses the columns (role, ownerId, price)"))
        seen = set()
        for idx, msg in hits:
            ln = line_of(text, idx)
            if ln in seen or not overlaps(touched, ln):
                continue
            seen.add(ln)
            rule = RULE["dto-spread-into-orm" if want_dto else "mass-assignment"]
            out.append((f"{p}:{ln}", f"{msg} [{rule}]"))
    return out


# --- unsafe html ------------------------------------------------------------
SANITIZE_RX = re.compile(r"(?i)\b(?:DOMPurify\.sanitize|sanitize(?:Html)?|purify|xss|escapeHtml|escape)\s*\(")
LITERAL_RX = re.compile(r"""^\s*(?:'[^']*'|"[^"]*"|`[^`$]*`)\s*$""")
DSIH_RX = re.compile(r"dangerouslySetInnerHTML\s*=\s*\{\{\s*__html\s*:\s*")
INNER_RX = re.compile(r"\.(?:innerHTML|outerHTML)\s*[+]?=\s*([^;\n]+)")
INSERT_RX = re.compile(r"\b(?:insertAdjacentHTML|document\.write(?:ln)?)\s*\(")
VHTML_RX = re.compile(r"""\bv-html\s*=\s*["']([^"']+)["']""")


def check_unsafe_html(files, base):
    out = []
    for p, text in code_files(files):
        touched = touched_lines(p, base)
        hits = []
        for m in DSIH_RX.finditer(text):
            expr = call_args(text, text.rfind("{", 0, m.end()))
            expr = re.sub(r"^\s*__html\s*:\s*", "", expr)
            hits.append((m.start(), "dangerouslySetInnerHTML", expr))
        for m in INNER_RX.finditer(text):
            hits.append((m.start(), m.group(0).split("=")[0].strip(), m.group(1)))
        for m in INSERT_RX.finditer(text):
            args = call_args(text, m.end() - 1)
            parts = [a for a in re.split(r",(?![^(]*\))", args)]
            hits.append((m.start(), m.group(0)[:-1], parts[-1] if parts else args))
        for m in VHTML_RX.finditer(text):
            hits.append((m.start(), "v-html", m.group(1)))
        for idx, sink, expr in hits:
            if LITERAL_RX.match(expr) or SANITIZE_RX.search(expr):
                continue
            ln = line_of(text, idx)
            if overlaps(touched, ln):
                out.append((f"{p}:{ln}", f"{sink} with a non-literal value ({expr.strip()[:40]}) "
                            f"and no sanitiser -- stored/reflected XSS [{RULE['unsafe-html']}]"))
    return out


# --- sql concatenation -------------------------------------------------------
SQL_WORD = r"(?i:\b(?:select|insert|update|delete|with|merge|replace)\b[\s\S]*\b(?:from|into|set|where|values|table)\b)"
SQL_SINK_RX = re.compile(
    r"(?:\.(?:query|raw|execute|executemany|exec|\$queryRawUnsafe|\$executeRawUnsafe)|\b(?:knex\.raw|sequelize\.query))\s*\(")
WHERE_SINK_RX = re.compile(r"\.(?:where|andWhere|orWhere|having)\s*\(")
TEMPLATE_INTERP_RX = re.compile(r"^`[^`]*\$\{[^`]*`$", re.S)
PY_INTERP_RX = re.compile(r"""^[fF][rR]?(?:"[^"]*\{[^"]*"|'[^']*\{[^']*')|^(?:"[^"]*"|'[^']*')\s*(?:%|\.format\s*\()""", re.S)
CONCAT_RX = re.compile(r"""(?:^(?:'[^']*'|"[^"]*"|`[^`]*`)\s*\+)|(?:\+\s*(?:'[^']*'|"[^"]*"|`[^`]*`)\s*$)""", re.S)
SQL_ASSIGN_RX = re.compile(r"(?:\b(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)")


def built_sql(expr):
    e = expr.strip()
    return bool(re.search(SQL_WORD, e)) and bool(
        TEMPLATE_INTERP_RX.match(e) or PY_INTERP_RX.match(e) or CONCAT_RX.search(e))


def check_sql_concat(files, base):
    out = []
    for p, text in code_files(files):
        touched = touched_lines(p, base)
        built = {m.group(1) for m in SQL_ASSIGN_RX.finditer(text) if built_sql(m.group(2))}
        for rx, need_sql in ((SQL_SINK_RX, True), (WHERE_SINK_RX, False)):
            for m in rx.finditer(text):
                arg = first_arg(call_args(text, m.end() - 1))
                if need_sql:
                    bad = built_sql(arg) or arg in built
                else:
                    bad = bool(TEMPLATE_INTERP_RX.match(arg.strip()))
                if not bad:
                    continue
                ln = line_of(text, m.start())
                if overlaps(touched, ln):
                    out.append((f"{p}:{ln}", f"SQL built from interpolated values passed to "
                                f"{m.group(0)[:-1].lstrip('.')}() -- bind parameters instead "
                                f"[{RULE['sql-concat']}]"))
    return out


# --- hardcoded secrets -------------------------------------------------------
# AWS and private-key shapes are gitleaks' own rules (config/gitleaks.toml ids
# aws-access-token, private-key); the generic rule is narrower than gitleaks'
# and adds an entropy floor so a 16-character English identifier is not a key.
AWS_RX = re.compile(r"\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b")
PEM_RX = re.compile(r"-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----")
GENERIC_RX = re.compile(
    r"""(?i)\b[\w-]*(?:api[_-]?key|secret|token|passw(?:or)?d)[\w-]*["']?\s*[:=]\s*["']([A-Za-z0-9/_+=.-]{16,})["']""")
# `user_password_input_1` is a name, not a key: words joined by _ - . with at most a short number.
WORDY_RX = re.compile(r"(?:[A-Za-z]{2,}|\d{1,3})(?:[_.-](?:[A-Za-z]{2,}|\d{1,3}))+")
PLACEHOLDER_RX = re.compile(r"(?i)example|changeme|placeholder|dummy|your[_-]|xxxx|redacted|<|\.\.\.|^\$\{|process\.env")


def entropy(s):
    c = collections.Counter(s)
    return -sum(v / len(s) * math.log2(v / len(s)) for v in c.values())


def check_hardcoded_secret(files, base):
    out = []
    for p in files:
        if p.endswith(BINARY_EXT):
            continue
        text = read(p)
        if text is None:
            continue
        touched = touched_lines(p, base)
        hits = []
        for m in AWS_RX.finditer(text):
            if not PLACEHOLDER_RX.search(m.group(1)):
                hits.append((m.start(), "AWS access key id"))
        for m in PEM_RX.finditer(text):
            hits.append((m.start(), "PEM private key block"))
        for m in GENERIC_RX.finditer(text):
            v = m.group(1)
            if PLACEHOLDER_RX.search(v) or not (re.search(r"\d", v) and re.search(r"[A-Za-z]", v)) \
                    or entropy(v) < 3.5 or WORDY_RX.fullmatch(v):
                continue
            hits.append((m.start(), "credential-looking literal"))
        seen = set()
        for idx, kind in hits:
            ln = line_of(text, idx)
            if ln in seen or not overlaps(touched, ln):
                continue
            seen.add(ln)
            out.append((f"{p}:{ln}", f"{kind} committed in source -- move it to the secret "
                        f"store and rotate it, it is already in history [{RULE['hardcoded-secret']}]"))
    return out


# --- nest controller without guard -------------------------------------------
def check_nest_guard(files, base):
    if sh(["git", "grep", "--untracked", "-lE", r"APP_GUARD|useGlobalGuards\s*\(", "--", "*.ts", "*.js"]).strip():
        return []
    out = []
    for p, text in code_files(files):
        m = re.search(r"@Controller\s*\(", text)
        if not m or "@UseGuards" in text:
            continue
        ln = line_of(text, m.start())
        if overlaps(touched_lines(p, base), ln):
            out.append((f"{p}:{ln}", "@Controller with no @UseGuards, and no APP_GUARD or "
                        "useGlobalGuards() anywhere in the repo -- every route is public "
                        f"unless something else authenticates it [{RULE['nest-controller-no-guard']}]"))
    return out


CHECKS = {
    "ssrf": (check_ssrf, True),
    "mass-assignment": (check_mass_assignment, True),
    "dto-spread-into-orm": (lambda f, b: check_mass_assignment(f, b, want_dto=True), False),
    "unsafe-html": (check_unsafe_html, True),
    "sql-concat": (check_sql_concat, True),
    "hardcoded-secret": (check_hardcoded_secret, True),
    "nest-controller-no-guard": (check_nest_guard, False),
}


def main():
    ap = argparse.ArgumentParser(description="Diff-scoped application-security checks.")
    ap.add_argument("--base", default=None, help="compare against this ref (default: HEAD)")
    ap.add_argument("--only", default=None, help="comma-separated subset of checks")
    ap.add_argument("--strict", action="store_true", help="advisory findings also fail")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for k, (_, blocking) in CHECKS.items():
            print(f"{k} ({'blocking' if blocking else 'advisory'}) -- {RULE[k]}")
        return 0
    names = [n.strip() for n in args.only.split(",")] if args.only else list(CHECKS)
    bad = [n for n in names if n not in CHECKS]
    if bad:
        print(f"unknown check(s): {', '.join(bad)}", file=sys.stderr)
        return 2
    if enter_git_root("appsec_check", args.base) is None:
        return 2
    files = changed(args.base)
    if not files:
        print("appsec_check: no changes to inspect")
        return 0

    hard = advisory = 0
    for n in names:
        fn, blocking = CHECKS[n]
        res = fn(files, args.base)
        if not res:
            continue
        print(f"\n[{'FAIL' if blocking else 'ADVISORY'}] {n}")
        for loc, msg in res[:12]:
            print(f"  {loc}: {msg}")
        if len(res) > 12:
            print(f"  ... {len(res) - 12} more")
        if blocking:
            hard += len(res)
        else:
            advisory += len(res)
    print(f"\nappsec_check: {len(files)} file(s) touched | {hard} blocking, {advisory} advisory"
          + (" (--strict: advisory findings fail)" if args.strict and advisory else ""))
    print("heuristic tool: one-hop taint, no data-flow analysis -- pair with CodeQL/Semgrep "
          "and a STRIDE pass (see skills/app-security/SKILL.md)")
    return 1 if hard or (args.strict and advisory) else 0


if __name__ == "__main__":
    sys.exit(main())
