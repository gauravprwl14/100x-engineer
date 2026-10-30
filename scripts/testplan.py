#!/usr/bin/env python3
"""Turn a spec's acceptance criteria into a test plan, and prove every AC has a test.

    testplan.py new <root>/specs/tagging/spec.md [--out [<root>/specs/tagging/testplan.md]]
    testplan.py trace specs/tagging/spec.md --tests backend/test,frontend/e2e [--json]
    testplan.py matrix --work web-ui --tier small [--json]

The spec argument may be the file, its directory, `specs/<name>` under the records
root, or the bare feature name.

Criteria are parsed by _md.parse_criteria, the one parser prd.py, plan_feature.py and
plan_dag.py share: `AC-<n>: <outcome> (R<k>, S<k>)` lines in the spec's acceptance
criteria section.

Specs number their criteria `AC-<n>`; TESTS tag them `<feature>/AC-<n>`
(`test('tagging/AC-1 tags ten people', ...)`, `# tagging/AC-2`, `@tagging/AC-3`).
AC ids are only unique within one spec, so in a test tree shared by several features
a bare `AC-1` could belong to any of them. `trace` counts only tags for its own
feature (--feature, the spec's `| feature |` header field, else its directory name),
and lists bare `AC-<n>` tags as not counted, with a hint to namespace them.

`new` derives cases mechanically from each AC's wording (numbers become boundary
rows, ownership words become authz rows, state words become transition rows). It is
a first draft for a human to prune, not a substitute for reading the AC. Each
implicit-requirement row gets one case whose level comes from the baseline item
(LEVEL_BY_ID, or a `level` field in baseline.json), never from its evidence text;
ask.* rows and n/a(...), waived(...) or ASK rows get none. Each open §7 edge case
(status still to do, or covered) whose source is a screen family (scripts/data/edge_cases_ui.json) or
`role:<name>` gets case `TC-E<n>-1` tagged `<feature>/E<n>`; `--all-edge-cases`
includes every other source.

`trace` counts an AC as covered only when its tag appears in a TEST file (by name
pattern) outside a commented-out test or a skipped test; a skipped `describe` block,
`xdescribe`, `context.skip` or skipped Python class marks every test inside it.

Python stdlib only.
"""
import argparse, json, os, pathlib, re, sys

import _md as md
import _mutation_guard as mg
import _paths
from _md import parse_acs

# The prefix may itself contain hyphens (`web-ui.reflow-320`, `data-pipeline.*`); the
# lookbehind stops a search from starting mid-prefix and returning `ui.reflow-320`.
NFR_ID = re.compile(r"`?(?<![A-Za-z0-9_-])([a-z][a-z0-9-]*\.[a-z0-9][a-z0-9-]*)\b`?")
PLUGIN = pathlib.Path(__file__).resolve().parent.parent
DATA = PLUGIN / "scripts" / "data"

AUTO_OUT = "\0auto"

HOW_TO_WRITE = """\
no acceptance criteria found. Write each one on its own line, starting with a stable id:

    AC-1: A member can tag up to 10 people on a photo. (R1, S1)
    AC-2: Only the album owner can delete a tag. (R2, S2)

(`- **AC-1** ...` bullets and `| AC-1 | ... |` table rows are also read.)

One observable outcome per AC, numbered once and never renumbered — tests reference
the id under the feature's namespace (`test('tagging/AC-1 tags ten people', ...)`,
`# tagging/AC-2`, `@tagging/AC-3`), so renumbering silently breaks `testplan trace`.
A removed AC leaves a gap; its id is not reused."""


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def read_doc(path):
    p = pathlib.Path(path)
    if not p.is_file():
        print(f"testplan: {path}: no such file", file=sys.stderr)
        return None
    return p.read_text(errors="replace")


def resolve_doc(arg, verb):
    """The spec file an argument names: a path, a spec directory, `specs/<name>` under
    the records root, or a bare feature name (_md.find_record)."""
    repo, _ = _paths.git_root()
    records, _ = _paths.resolve(repo)
    p = md.find_record(arg, "specs", "spec.md", repo, records)
    if p is None:
        print(f"testplan {verb}: "
              + md.not_found(arg, "specs", "spec.md", records, lambda x: _paths.show(x, repo)),
              file=sys.stderr)
    return p


FEATURE_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def feature_of(path, text, override=None):
    """The namespace tests tag with, `<feature>/AC-<n>`: --feature, else the spec's
    `| feature |` header field, else its directory (specs/<feature>/spec.md), else
    the file stem. AC ids are only unique within one spec, so a bare `AC-1` in a
    shared test tree could belong to any feature."""
    p = pathlib.Path(path)
    name = (override or md.header_field(text, "feature").strip("`* ")
            or (p.parent.name if p.stem == "spec" and p.parent.name else p.stem))
    return name if FEATURE_RX.match(name) else None


SKIP_STATUS = re.compile(r"^\s*(n/a|waived|ask)\b", re.I)


def implicit_requirements(text):
    """Rows of the implicit-requirements table (the spec section whose heading contains
    'implicit' or is numbered 0b), as [(id, requirement, status)].

    `requirement` is the default/requirement column only, never the evidence column:
    evidence prose ("k6 run", "axe scan") is how a row was met, not what it requires,
    and classifying on it put health checks under axe and consent under k6. Status is
    "" when the table has no status column."""
    out, in_sec, seen, cols = [], False, set(), None
    for line in text.splitlines():
        if line.startswith("#"):
            h = line.lower()
            in_sec = "implicit" in h or re.match(r"^#+\s*(§\s*)?0b\b", h) is not None
            cols = None
            continue
        if not in_sec or not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or set("".join(cells)) <= set("-: "):
            continue
        m = NFR_ID.fullmatch(cells[0]) or NFR_ID.search(cells[0])
        if not m or re.fullmatch(r"\d+\.\d+", m.group(1)):
            if cols is None:
                cols = [c.lower() for c in cells]
            continue
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        names = cols or []

        def col(*want):
            for w in want:
                if w in names and names.index(w) < len(cells):
                    return cells[names.index(w)]
            return None

        req = col("default", "requirement")
        if req is None:
            req = cells[1] if len(cells) > 1 else ""
        out.append((m.group(1), req, col("status") or ""))
    return out


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------

UI_WORDS = re.compile(r"\b(page|screen|button|click|tap|display|shows?|sees?|form|modal|"
                      r"dialog|list|link|navigate|toast|banner|ui)\b", re.I)
AUTHZ_WORDS = re.compile(r"\b(only|owner|admin|administrator|permission|authori[sz]ed|role|"
                         r"member|signed[- ]in|logged[- ]in|tenant|company|private|forbidden)\b",
                         re.I)
STATE_WORDS = re.compile(r"\b(status|state|draft|published|pending|approved|rejected|"
                         r"cancel(?:led|ed)?|archived|deleted|active|inactive|expired|locked|"
                         r"moves? to|transitions?|becomes?|once)\b", re.I)
INPUT_WORDS = re.compile(r"\b(input|field|name|title|text|comment|list|upload|file|search|"
                         r"query|email|password|items?|characters?)\b", re.I)
MAX_RX = re.compile(r"\b(?:up to|at most|max(?:imum)?|no more than|not more than|less than|"
                    r"fewer than|within|limit(?:ed)? (?:of|to))\s+(\d+)|(?:<=|≤)\s*(\d+)", re.I)
MIN_RX = re.compile(r"\b(?:at least|min(?:imum)?|no fewer than|more than|greater than)\s+(\d+)|"
                    r"(?:>=|≥)\s*(\d+)", re.I)
BETWEEN_RX = re.compile(r"\bbetween\s+(\d+)\s+and\s+(\d+)", re.I)
TIME_RX = re.compile(r"\b(?:within|under|in less than|in under|at most)\s+(\d+)\s*"
                     r"(ms|milliseconds?|s|seconds?|minutes?|hours?|days?)\b", re.I)


def boundary_rows(text):
    """(value-description, expected) pairs per test-design rule 1: min-1/min/min+1,
    max-1/max/max+1."""
    rows, used = [], set()
    for n, unit in TIME_RX.findall(text):
        used.add(n)
        rows.append((f"elapsed time around {n} {unit} (fake clock or measured timestamps)",
                     f"completes in <= {n} {unit}; a result at {n} {unit} + 1 tick fails "
                     f"the AC. Never assert this with a sleep"))

    def add(v, exp):
        if v not in used:
            used.add(v)
            rows.append((v, exp))

    for a, b in BETWEEN_RX.findall(text):
        lo, hi = int(a), int(b)
        used.update({str(lo), str(hi)})
        for v, ok in ((lo - 1, False), (lo, True), (hi, True), (hi + 1, False)):
            rows.append((str(v), "accepted" if ok else "rejected with a validation error"))
    for m in MAX_RX.finditer(text):
        n = int(m.group(1) or m.group(2))
        if str(n) in used:
            continue
        add(str(n - 1), "accepted (max-1)")
        add(str(n), "accepted (max)")
        add(str(n + 1), "rejected with a validation error (max+1)")
    for m in MIN_RX.finditer(text):
        n = int(m.group(1) or m.group(2))
        if str(n) in used:
            continue
        add(str(n - 1), "rejected with a validation error (min-1)")
        add(str(n), "accepted (min)")
        add(str(n + 1), "accepted (min+1)")
    if not rows:
        for n in re.findall(r"\b(\d+)\s*(?:characters?|chars|items?|people|users|files?|"
                            r"photos?|mb|kb|gb|seconds?|minutes?|days?|%)", text, re.I):
            n = int(n)
            for v in (n - 1, n, n + 1):
                add(str(v), "confirm which side of the limit is allowed, then assert it")
    return rows


def cases_for(ac_id, text):
    n = ac_id.split("-")[1]
    ui = bool(UI_WORDS.search(text))
    cases = []

    def add(level, technique, given, expected):
        cases.append((level, technique, given, expected))

    add("e2e" if ui else "integration", "equivalence partition (valid)",
        "a representative valid input / actor for: " + text, "the outcome the AC states")
    add("unit" if not ui else "integration", "equivalence partition (invalid)",
        "an input from the invalid partition (wrong type, malformed, out of range)",
        "rejected with a specific error; no state change")
    for v, exp in boundary_rows(text):
        if v.startswith("elapsed"):
            add("integration", "boundary value (time budget)", v, exp)
        else:
            add("unit", "boundary value", f"value = {v}", exp)
    if INPUT_WORDS.search(text):
        add("unit", "boundary value (empty)", "empty / zero elements / whitespace only",
            "the AC's empty-case behaviour, asserted explicitly (not assumed 'small')")
    if AUTHZ_WORDS.search(text):
        add("integration", "negative / authz", "an actor WITHOUT the required role or ownership",
            "403 (or 404 to avoid disclosure); nothing changed")
        add("integration", "negative / authz (tenant)",
            "an actor from another tenant/company targeting this resource by id",
            "denied; the resource is not readable or writable across tenants")
    if STATE_WORDS.search(text):
        add("integration", "state transition (legal)", "the resource in the AC's starting state",
            "it moves to the AC's target state exactly once")
        add("integration", "state transition (illegal)",
            "the resource in a state the AC does not allow the action from",
            "rejected; state unchanged (e.g. act-after-delete, repeat transition)")
    return [(f"TC-{n}-{i}", ac_id) + c for i, c in enumerate(cases, 1)]


# How each kind of implicit requirement is tested: (level, how). `automated?` is "no"
# for review and manual-exploratory.
NFR_HOW = {
    "responsive": ("e2e", "responsive overflow at 320/768/1280 and 200% text "
                          "(templates/qa/responsive.spec.ts)"),
    "a11y": ("a11y", "axe scan, wcag2a/2aa/21aa/22aa (templates/qa/a11y.spec.ts) + manual "
                     "keyboard pass"),
    "a11y-mobile": ("a11y", "VoiceOver + TalkBack pass at max font scale, on the Maestro "
                            "flows"),
    "visual": ("visual", "toHaveScreenshot vs approved baseline, one per state and theme "
                         "(templates/qa/visual.spec.ts)"),
    "vitals": ("e2e", "field/lab web-vitals budget check (see the web-vitals skill)"),
    "load": ("load", "k6 with thresholds from the SLO (templates/qa/load.k6.js)"),
    "authz": ("integration", "negative authz: other role / other tenant denied, per endpoint"),
    "integration": ("integration", "integration test at the boundary asserting the stated "
                                   "behaviour, including the failure path"),
    "unit": ("unit", "unit tests on the values the requirement names (boundaries, zones, "
                     "encodings)"),
    "e2e": ("e2e", "end-to-end test of the journey on the matrix browsers "
                   "(100x testplan matrix)"),
    "mobile-e2e": ("e2e", "Maestro flow on the smallest and largest supported device and "
                          "the min supported OS"),
    "smoke": ("e2e", "post-deploy smoke (templates/qa/smoke.sh)"),
    "static": ("static", "a CI check that fails the build (linter, scanner or config "
                         "assertion); link the job"),
    "release": ("review", "release checklist item, exercised once in staging; link the run"),
    "review": ("review", "reviewer confirms it in the PR; not an automated test"),
}

# Every baseline id (scripts/data/baseline.json) by name. A `level` field on the
# baseline item, when present, wins; tests/test_testplan.sh fails when a baseline id
# is in neither place, so a new item cannot fall through to a keyword guess.
LEVEL_BY_ID = {
    "web-ui.reflow-320": "responsive", "web-ui.text-resize-200": "responsive",
    "web-ui.contrast-and-targets": "a11y", "web-ui.keyboard-focus-names": "a11y",
    "web-ui.view-states": "visual", "web-ui.core-web-vitals": "vitals",
    "web-ui.browser-target": "e2e", "web-ui.security-headers-csrf": "integration",
    "web-ui.design-tokens": "static", "web-ui.i18n-ready": "static",
    "web-ui.color-scheme": "visual", "web-ui.seo-meta": "integration",
    "web-ui.analytics-consent": "e2e",
    "mobile.touch-targets": "a11y-mobile", "mobile.font-scaling-labels": "a11y-mobile",
    "mobile.orientation-safe-areas": "mobile-e2e", "mobile.offline-flaky-network": "mobile-e2e",
    "mobile.crash-anr-thresholds": "release", "mobile.staged-rollout-kill-switch": "release",
    "mobile.privacy-manifest-permissions": "static", "mobile.min-os-device-matrix": "mobile-e2e",
    "api.authz-every-endpoint": "authz", "api.property-authz-mass-assignment": "authz",
    "api.boundary-validation": "integration", "api.resource-caps": "integration",
    "api.rate-limit": "integration", "api.problem-details-errors": "integration",
    "api.idempotency-timeouts-retries": "integration",
    "api.health-graceful-shutdown": "integration", "api.contract-checked-in": "static",
    "api.ssrf-guard": "integration", "api.inventory-deprecation": "review",
    "worker.idempotent-handler": "integration", "worker.retry-jitter-dlq": "integration",
    "worker.visibility-timeout": "integration", "worker.queue-alerts": "review",
    "worker.cron-overlap-timezone": "integration",
    "data-pipeline.rerunnable-partitions": "integration",
    "data-pipeline.schema-contract": "static", "data-pipeline.quality-assertions": "integration",
    "data-pipeline.late-data-watermarks": "integration", "data-pipeline.pii-lineage": "review",
    "cli.conventions": "integration", "cli.semver-changelog": "review",
    "cli.minimal-deps-lockfile": "static",
    "iac.no-public-data-encrypted": "static", "iac.least-privilege-iam": "static",
    "iac.backups-tested-restore": "release", "iac.remote-state-locking": "static",
    "iac.cost-tags-budgets": "static", "iac.multi-az": "release", "iac.multi-region": "release",
    "all.no-secrets-in-code": "static", "all.sast-deps-pinned-actions": "static",
    "all.sbom-provenance": "static", "all.threat-model-paragraph": "review",
    "all.pii-out-of-logs": "integration", "all.golden-signals-tracing": "review",
    "all.runbook-per-alert": "review", "all.tests-in-same-change": "review",
    "all.e2e-critical-journeys": "e2e", "all.visual-regression": "visual",
    "all.load-soak-spike": "load", "all.flags-tested-rollback": "release",
    "all.canary": "release", "all.small-changes": "review", "all.readme-adrs": "review",
    "all.time-unicode": "unit", "all.copyleft-review": "static",
    "all.wcag-aa-floor": "a11y", "all.audit-trail": "integration",
    "all.privacy-impact-assessment": "review", "all.encryption-in-transit": "static",
}

# For ids outside the baseline (a team's own rows). Tried against the id first, then
# the requirement text; whole words only, so "load only after consent" is not a load
# test and "label" inside "labelled" is not accessibility.
NFR_KEYWORDS = [
    (re.compile(r"\b(reflow|responsive|viewport|text-resize|320)\b", re.I), "responsive"),
    (re.compile(r"\b(wcag\w*|contrast|a11y|accessib\w*|keyboard|focus|screen-?reader|"
                r"aria|target-size)\b", re.I), "a11y"),
    (re.compile(r"\b(visual(-regression)?|screenshot|pixel|theme|dark mode)\b", re.I),
     "visual"),
    (re.compile(r"\b(lcp|inp|cls|web-?vitals|core-web-vitals)\b", re.I), "vitals"),
    (re.compile(r"\b(p9[059](-budget)?|latency|throughput|rps|load[- ]test\w*|soak|spike)\b",
                re.I), "load"),
    (re.compile(r"\b(authz|idor|tenant\w*|permission\w*|csrf|authori[sz]\w*)\b", re.I),
     "authz"),
    (re.compile(r"\b(smoke|health-?check)\b", re.I), "smoke"),
]


def _baseline():
    try:
        return {i["id"]: i for i in json.loads((DATA / "baseline.json").read_text())["items"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


BASELINE_BY_ID = _baseline()


def nfr_level(req_id, requirement):
    """The NFR_HOW key for a row: the baseline item's `level`, else LEVEL_BY_ID, else
    a whole-word keyword on the id, then on the requirement text; None when nothing
    fits (an exploratory charter)."""
    hint = BASELINE_BY_ID.get(req_id, {}).get("level")
    if isinstance(hint, str) and hint in NFR_HOW:
        return hint
    if req_id in LEVEL_BY_ID:
        return LEVEL_BY_ID[req_id]
    for text in (req_id.replace(".", " "), requirement):
        for rx, key in NFR_KEYWORDS:
            if rx.search(text):
                return key
    return None


def skip_reason(req_id, status):
    """Why a row gets no test case: ask.* items are questions, not behaviour, and an
    n/a(...), waived(...) or unanswered ASK row has nothing to test."""
    if req_id.startswith("ask."):
        return "a question"
    m = SKIP_STATUS.match(status or "")
    return m.group(1).lower() if m else None


def nfr_case(req_id, requirement, status=""):
    expected = requirement or "the baseline requirement"
    if expected.startswith("ASK:") and status:
        expected = status
    key = nfr_level(req_id, requirement)
    if key is None:
        return (f"TC-{req_id}-1", req_id, "manual-exploratory", "non-functional",
                "exploratory charter (templates/qa/exploratory-charter.md)", expected)
    level, how = NFR_HOW[key]
    return (f"TC-{req_id}-1", req_id, level, "non-functional", how, expected)


def _ui_kinds():
    try:
        return {k for k in json.loads((DATA / "edge_cases_ui.json").read_text())
                if not k.startswith("_")}
    except (OSError, ValueError):
        return set()


# Screen-behaviour families get a case by default; the universal and backend kinds are
# seeded on most specs and would grow every plan, so they wait for --all-edge-cases.
UI_KINDS = _ui_kinds()
E2E_SOURCES = {"destructive-action"}
OPEN_EDGE_STATUS = ("todo", "covered")
SUGGESTED = "_suggested:_ "
# #, source, edge case, why, status, test / reference (plan_feature new writes these)
EDGE_COLUMNS = 6


def select_edge_cases(text, every_source):
    """[(E<n>, source, what, test)] for open §7 rows (to do, or covered) whose
    source is a UI family or `role:<name>` (any source when `every_source`)."""
    out = []
    for r in md.rows_of(text, "| # | source | edge case |"):
        if len(r) < EDGE_COLUMNS or r[4].strip().lower() not in OPEN_EDGE_STATUS:
            continue
        src = r[1].strip()
        if every_source or src in UI_KINDS or src.startswith("role:"):
            test = r[5].strip()
            out.append((r[0].strip(), src, r[2].strip(),
                        test[len(SUGGESTED):] if test.startswith(SUGGESTED) else test))
    return out


def build_edge_case(feature, eid, source, what, test):
    is_role = source.startswith("role:")
    level = "e2e" if is_role or source in E2E_SOURCES else "component"
    return (f"TC-{eid}-1", f"{feature}/{eid}", level, "role" if is_role else "edge case",
            what, test)


def default_testplan(feature, repo):
    """(<root>/specs/<feature>/testplan.md, the legacy <root>/testplans/<feature>.md
    when one exists there, else None)."""
    records, _ = _paths.resolve(repo)
    legacy = records / _paths.LEGACY_TESTPLANS / f"{feature}.md"
    return (_paths.feature_dir(feature, repo) / "testplan.md",
            legacy if legacy.is_file() else None)


def esc(s):
    return str(s).replace("|", "\\|")


def cmd_new(a):
    src = resolve_doc(a.doc, "new")
    if src is None:
        return 2
    text = src.read_text(errors="replace")
    acs = parse_acs(text)
    if not acs:
        print(f"testplan new: {a.doc}: {HOW_TO_WRITE}", file=sys.stderr)
        return 1
    feature = feature_of(src, text, a.feature)
    if feature is None:
        print(f"testplan new: cannot derive a feature name from {a.doc} — pass "
              f"--feature <name> (letters, digits, . _ -)", file=sys.stderr)
        return 2
    rows = []
    for ac, t in acs.items():
        for cid, acid, level, tech, given, exp in cases_for(ac, t):
            rows.append((cid, f"{feature}/{acid}", level, tech, given, exp,
                         "no" if level == "manual-exploratory" else "yes", a.owner))
    nfr, skipped = [], []
    for rid, req, status in implicit_requirements(text):
        why = skip_reason(rid, status)
        if why:
            skipped.append(f"{rid} ({why})")
        else:
            nfr.append(rid)
            cid, rid, level, tech, given, exp = nfr_case(rid, req, status)
            rows.append((cid, rid, level, tech, given, exp,
                         "no" if level in ("manual-exploratory", "review") else "yes",
                         a.owner))
    edges = select_edge_cases(text, a.all_edge_cases)
    rows += [build_edge_case(feature, *e) + ("yes", a.owner) for e in edges]
    first = next(iter(acs))
    # The edge-case count is named only when there is one, so a spec without §7 UI or
    # role rows gets byte-for-byte the plan it got before.
    n_edges = f", {len(edges)} edge cases" if edges else ""
    out = [f"# Test plan — {feature}", "",
           f"Generated from `{a.doc}` by `100x testplan new`: {len(acs)} acceptance "
           f"criteria, {len(nfr)} implicit requirements{n_edges}, {len(rows)} cases. Rows are "
           "derived from the AC wording; prune duplicates and fill concrete values before "
           f"writing tests. Tag every test with its namespaced id (`{feature}/{first}`), "
           f"then prove coverage with `100x testplan trace {a.doc} --tests <dir>`.", "",
           "| case id | AC id | level | technique | input / precondition | expected | "
           "automated? | owner |",
           "|---|---|---|---|---|---|---|---|"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    if skipped:
        out += ["", f"No case for {len(skipped)} implicit-requirement row(s) with nothing "
                f"to test: {', '.join(skipped)}."]
    if not nfr and not skipped:
        out += ["", "No implicit-requirements table (a section headed 'implicit "
                "requirements' or '0b') was found, so no non-functional rows were added. "
                "Responsive, accessibility and performance cases still apply per "
                "`100x testplan matrix`."]
    doc = "\n".join(out) + "\n"
    repo, in_git = _paths.git_root()
    legacy = None
    if a.out == AUTO_OUT:
        target, legacy = default_testplan(feature, repo)
        a.out = str(_paths.show(target, pathlib.Path.cwd()))
    if a.out:
        p = pathlib.Path(a.out)
        if p.exists() and not a.force:
            print(f"testplan new: {a.out} exists (use --force)", file=sys.stderr)
            return 2
        if legacy is not None and not p.exists():
            here = _paths.show(legacy, pathlib.Path.cwd())
            print(f"testplan new: note: a test plan for {feature} exists at the legacy "
                  f"location {here}; plans now live beside the spec at {a.out}. Move it "
                  f"(`git mv {here} {a.out}`) to keep one copy"
                  + ("" if a.force else ", or pass --force to write a fresh one there"),
                  file=sys.stderr)
            if not a.force:
                return 2
        if a.dry_run:
            print(f"would write {a.out}: {len(rows)} cases for {len(acs)} ACs")
            return 0
        if mg.require_git_root(in_git, "testplan new --out", pathlib.Path.cwd()):
            return 2
        _paths.safe_write_text(p.resolve(), doc, repo, "testplan new --out")
        print(f"wrote {a.out}: {len(rows)} cases for {len(acs)} ACs")
    else:
        sys.stdout.write(doc)
    return 0


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------

TEST_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".kt", ".kts",
            ".swift", ".dart"}
TEST_NAME = re.compile(
    r"([._-](test|spec|e2e-spec|e2e)\.[a-z]+$)|(^test_.*\.py$)|(_test\.(py|go|dart)$)|"
    r"(Tests?\.(kt|kts|swift)$)|(\.cy\.[jt]sx?$)", re.I)
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "vendor", ".venv", "venv",
             "__pycache__", ".next", "coverage", "Pods", ".dart_tool"}
CODEY = re.compile(r"\b(test|it|describe|expect|assert\w*|testWidgets)(\.\w+)?\s*\(|"
                   r"^\s*(def test|async def test|func Test|fun |assert\s)|@Test\b|[;{}]\s*$")
SKIPPED = re.compile(r"\b(test|it|describe)\.(skip|fixme)\b|\bx(it|describe|test)\s*\(|"
                     r"@pytest\.mark\.skip|@unittest\.skip|\bt\.Skip\(|@Disabled|@Ignore|"
                     r"skip:\s*true")
# A skipped GROUP: everything inside its braces (C-like) or its indented body (Python)
# is skipped, however far below the opener a tagged test sits.
SKIP_BLOCK = re.compile(r"\b(describe|context|suite)\.(skip|fixme)\b|"
                        r"\bx(describe|context)\s*\(|^\s*@(Disabled|Ignore)\b")
PY_SKIP_DECORATOR = re.compile(r"^\s*@(pytest\.mark\.skip|unittest\.skip)")
PY_MODULE_SKIP = re.compile(r"^pytestmark\s*=.*\bpytest\.mark\.skip")
NS_TAG = re.compile(r"(?<![A-Za-z0-9_./-])@?([A-Za-z0-9][A-Za-z0-9._-]*)/AC-(\d+)(?![0-9])")
BARE_TAG = re.compile(r"(?<![A-Za-z0-9/])@?AC-(\d+)(?![0-9])")
STRING_RX = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")


def is_test_file(path):
    p = pathlib.Path(path)
    if p.suffix.lower() in (".yaml", ".yml"):
        return any(part in (".maestro", "maestro") for part in p.parts)
    return p.suffix.lower() in TEST_EXT and bool(TEST_NAME.search(p.name))


def comment_prefix(path):
    return "#" if path.endswith((".py", ".yaml", ".yml")) else "//"


def _brace_block(lines, start):
    """Line indexes from `start` to the line closing the first brace opened at or
    after it. String literals are blanked first so a '{' in a test title is not a
    block. An opener with no brace within 5 lines marks only itself."""
    depth, opened = 0, False
    for k in range(start, len(lines)):
        code = STRING_RX.sub("''", lines[k])
        for ch in code:
            if ch == "{":
                depth, opened = depth + 1, True
            elif ch == "}" and opened:
                depth -= 1
        if opened and depth <= 0:
            return range(start, k + 1)
        if not opened and k - start >= 5:
            break
    return range(start, start + 1)


def _indent(s):
    return len(s) - len(s.lstrip())


def _py_block(lines, start):
    """From a skip decorator to the end of the def/class it decorates (dedent)."""
    k = start
    while k < len(lines) and lines[k].lstrip().startswith("@"):
        k += 1
    if k >= len(lines):
        return range(start, len(lines))
    base, end = _indent(lines[k]), k
    for j in range(k + 1, len(lines)):
        if lines[j].strip() and _indent(lines[j]) <= base:
            break
        end = j
    return range(start, end + 1)


def skipped_lines(path, lines):
    out = set()
    if path.endswith(".py"):
        for k, line in enumerate(lines):
            if PY_MODULE_SKIP.match(line):
                return set(range(len(lines)))
            if PY_SKIP_DECORATOR.match(line):
                out.update(_py_block(lines, k))
        return out
    for k, line in enumerate(lines):
        if SKIP_BLOCK.search(STRING_RX.sub("''", line)):
            out.update(_brace_block(lines, k))
    return out


def live_tags(path, text):
    """[(feature, ac_num, lineno, kind)]: feature is None for a bare `AC-<n>` tag;
    kind is 'live' or 'skipped'.

    A comment run (consecutive comment lines, or a /* */ block) that contains code
    is a commented-out test: tags inside it do not count. A prose comment
    (`// covers tagging/AC-2`) does count."""
    lines = text.splitlines()
    pref = comment_prefix(path)
    c_like = pref == "//"
    dead = set()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if c_like and s.startswith("/*"):
            j = i
            while j < len(lines) and "*/" not in lines[j]:
                j += 1
            block = range(i, min(j, len(lines) - 1) + 1)
            body = [re.sub(r"^\s*(/\*+|\*+/?)", "", lines[k]) for k in block]
            if any(CODEY.search(b) for b in body):
                dead.update(block)
            i = j + 1
            continue
        if s.startswith(pref):
            j = i
            while j < len(lines) and lines[j].strip().startswith(pref):
                j += 1
            body = [lines[k].strip()[len(pref):] for k in range(i, j)]
            if any(CODEY.search(b) for b in body):
                dead.update(range(i, j))
            i = j
            continue
        i += 1
    group_skipped = skipped_lines(path, [lines[k] if k not in dead else ""
                                         for k in range(len(lines))])
    out = []
    for k, line in enumerate(lines):
        if k in dead:
            continue
        prev = lines[k - 1] if k else ""
        kind = ("skipped" if k in group_skipped or SKIPPED.search(line)
                or SKIPPED.search(prev) else "live")
        for m in NS_TAG.finditer(line):
            out.append((m.group(1), int(m.group(2)), k + 1, kind))
        for m in BARE_TAG.finditer(line):
            out.append((None, int(m.group(1)), k + 1, kind))
    return out


def walk_tests(dirs):
    for d in dirs:
        root = pathlib.Path(d)
        if root.is_file():
            yield root
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = [x for x in dn if x not in SKIP_DIRS]
            for f in fn:
                yield pathlib.Path(dp) / f


def cmd_trace(a):
    src = resolve_doc(a.doc, "trace")
    if src is None:
        return 2
    text = src.read_text(errors="replace")
    acs = parse_acs(text)
    if not acs:
        print(f"testplan trace: {a.doc}: {HOW_TO_WRITE}", file=sys.stderr)
        return 1
    feature = feature_of(src, text, a.feature)
    if feature is None:
        print(f"testplan trace: cannot derive a feature name from {a.doc} — pass "
              f"--feature <name>", file=sys.stderr)
        return 2
    dirs = [d for d in a.tests.split(",") if d]
    missing = [d for d in dirs if not pathlib.Path(d).exists()]
    if missing:
        print(f"testplan trace: --tests path(s) not found: {', '.join(missing)} — "
              f"nothing was scanned", file=sys.stderr)
        return 2
    hits = {k: [] for k in acs}
    skipped = {k: [] for k in acs}
    orphans, bare, other, ignored, scanned = [], [], 0, 0, 0
    for p in walk_tests(dirs):
        try:
            body = p.read_text(errors="replace")
        except OSError:
            continue
        if not is_test_file(str(p)):
            ignored += len(NS_TAG.findall(body)) + len(BARE_TAG.findall(body))
            continue
        scanned += 1
        for feat, num, line, kind in live_tags(str(p), body):
            key, loc = f"AC-{num}", f"{p}:{line}"
            if feat is None:
                if kind == "live":
                    bare.append(f"{loc} {key}")
                continue
            if feat != feature:
                other += 1
            elif key not in acs:
                orphans.append(f"{loc} {feature}/{key}")
            elif kind == "skipped":
                skipped[key].append(loc)
            elif loc not in hits[key]:
                hits[key].append(loc)
    uncovered = [k for k in acs if not hits[k]]
    result = {"spec": a.doc, "feature": feature, "tests": dirs,
              "test_files_scanned": scanned,
              "tags_in_non_test_files_ignored": ignored,
              "other_feature_tags_ignored": other, "bare_tags_not_counted": bare,
              "criteria": [{"id": k, "tag": f"{feature}/{k}", "text": acs[k],
                            "covered": bool(hits[k]), "locations": hits[k],
                            "skipped": skipped[k]} for k in acs],
              "uncovered": uncovered, "unknown_tags": orphans}
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        for c in result["criteria"]:
            mark = "covered  " if c["covered"] else "UNCOVERED"
            print(f"  {mark} {c['id']}: {c['text'][:70]}")
            for loc in c["locations"]:
                print(f"            {loc}")
            for loc in c["skipped"]:
                print(f"            {loc} (skipped test — does not count)")
        for o in orphans:
            print(f"  WARN tag for an AC the spec does not define: {o}")
        if bare:
            print(f"  HINT {len(bare)} bare AC-<n> tag(s) not counted (first: {bare[0]}) — "
                  f"AC ids repeat across specs, so tag tests `{feature}/AC-<n>`")
        print(f"\ntrace {feature}: {len(acs) - len(uncovered)}/{len(acs)} ACs covered, "
              f"{scanned} test files scanned, {ignored} AC tag(s) in non-test files "
              f"ignored, {other} tag(s) for other features ignored")
        if uncovered:
            print(f"uncovered: {', '.join(uncovered)} — add a test tagged with the id "
                  f"(e.g. test('{feature}/{uncovered[0]} ...')) or remove the AC from "
                  f"the spec")
    return 1 if uncovered else 0


# ---------------------------------------------------------------------------
# matrix
# ---------------------------------------------------------------------------

TIERS = json.loads((DATA / "scale_tiers.json").read_text())["_order"]
WEB_BROWSERS = [
    ("Chrome (latest)", "Desktop Chrome", "every PR"),
    ("Edge (latest)", "Desktop Edge, channel: 'msedge'", "nightly"),
    ("Firefox (latest)", "Desktop Firefox", "nightly"),
    ("Safari (latest, WebKit)", "Desktop Safari", "every PR at growth+, else nightly"),
    ("Mobile Safari (iOS, latest)", "iPhone 12", "nightly"),
    ("Chrome Android (latest)", "Pixel 5", "nightly"),
]
WEB_VIEWPORTS = [("320", "WCAG 2.2 SC 1.4.10 Reflow: no horizontal scroll at 320 CSS px"),
                 ("768", "tablet portrait"), ("1280+", "desktop")]
WEB_SOURCES = [
    "Browserslist `defaults` = `> 0.5%, last 2 versions, Firefox ESR, not dead` "
    "(https://github.com/browserslist/browserslist#full-list); resolve the exact list in "
    "your project with `npx browserslist defaults` — the set above is a representative "
    "sample, not the resolution",
    "Playwright device descriptors and the msedge channel: "
    "https://playwright.dev/docs/test-projects",
    "WCAG 2.2 SC 1.4.10 Reflow (320 CSS px): https://www.w3.org/TR/WCAG22/#reflow",
    "PR-vs-nightly split by tier: SOURCE: original",
]
MOBILE_ROWS = [
    ("min supported iOS version", "ASK", "C decision — market share vs. cost; never default"),
    ("min supported Android API level", "ASK", "C decision — never default"),
    ("tablets / foldables in scope", "ASK", "C decision — changes layout test surface"),
    ("phone, smallest supported screen", "required", "layout + truncation"),
    ("phone, largest supported screen", "required", "layout"),
    ("OS font scale at max (Dynamic Type / fontScale 2.0)", "required",
     "WCAG 2.2 SC 1.4.4 Resize Text"),
    ("dark mode", "required", "contrast in both themes"),
    ("screen reader pass (VoiceOver + TalkBack)", "required (manual)", "WCAG 2.2 AA"),
    ("current OS major + min supported OS", "required", "run Maestro flows on both"),
]
MOBILE_SOURCES = [
    "Maestro flows (appId / launchApp / tapOn / assertVisible): "
    "https://docs.maestro.dev/",
    "WCAG 2.2 SC 1.4.4 Resize Text: https://www.w3.org/TR/WCAG22/#resize-text",
    "Minimum OS is a C (must-ask) decision: docs/OPERATING-MODEL.md §5",
]


def cmd_matrix(a):
    tier = a.tier
    if tier not in TIERS:
        print(f"testplan matrix: unknown --tier {tier!r}; one of {TIERS}", file=sys.stderr)
        return 2
    if a.work == "web-ui":
        browsers = []
        for name, dev, cadence in WEB_BROWSERS:
            if tier == "prototype" and name != "Chrome (latest)":
                cadence = "before release"
            elif tier in ("growth", "scale") and name.startswith("Safari"):
                cadence = "every PR"
            elif name.startswith("Safari"):
                cadence = "nightly"
            browsers.append({"browser": name, "playwright_device": dev, "cadence": cadence})
        data = {"work": "web-ui", "tier": tier, "target": "Browserslist defaults",
                "browsers": browsers,
                "viewports": [{"width": w, "why": y} for w, y in WEB_VIEWPORTS],
                "accessibility": "WCAG 2.2 AA at every tier (axe tags wcag2a, wcag2aa, "
                                 "wcag21a, wcag21aa, wcag22aa)",
                "ask": [], "sources": WEB_SOURCES}
    else:
        data = {"work": "mobile", "tier": tier,
                "rows": [{"dimension": d, "value": v, "why": y} for d, v, y in MOBILE_ROWS],
                "accessibility": "WCAG 2.2 AA at every tier",
                "ask": [d for d, v, _ in MOBILE_ROWS if v == "ASK"],
                "sources": MOBILE_SOURCES}
    if a.json:
        print(json.dumps(data, indent=2))
        return 0
    print(f"QA matrix — {data['work']}, tier {tier}\n")
    if a.work == "web-ui":
        print("| browser | Playwright device | cadence |\n|---|---|---|")
        for b in data["browsers"]:
            print(f"| {b['browser']} | {b['playwright_device']} | {b['cadence']} |")
        print("\n| viewport width | why |\n|---|---|")
        for v in data["viewports"]:
            print(f"| {v['width']} | {v['why']} |")
    else:
        print("| dimension | value | why |\n|---|---|---|")
        for r in data["rows"]:
            print(f"| {r['dimension']} | {r['value']} | {r['why']} |")
    print(f"\naccessibility: {data['accessibility']}")
    if data["ask"]:
        print("ASK (must be answered by the user, never defaulted): " + "; ".join(data["ask"]))
    print("\nsources:")
    for s in data["sources"]:
        print(f"  - {s}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new", help="generate a test plan from a spec/PRD's AC ids")
    n.add_argument("doc")
    n.add_argument("--out", nargs="?", const=AUTO_OUT,
                   help="write the plan to this file; bare --out writes "
                        "<records root>/specs/<feature>/testplan.md")
    n.add_argument("--owner", default="qa-engineer")
    n.add_argument("--force", action="store_true")
    n.add_argument("--dry-run", action="store_true", help="say what --out would write")
    n.add_argument("--feature", help="namespace for test tags (default: the spec's "
                                     "| feature | field, else its directory name)")
    n.add_argument("--all-edge-cases", action="store_true",
                   help="one case per open §7 edge case of any source, not only screen "
                        "families and role:<name> rows")
    n.set_defaults(fn=cmd_new)
    t = sub.add_parser("trace", help="report each AC as covered/uncovered by tagged tests")
    t.add_argument("doc")
    t.add_argument("--tests", required=True, help="comma-separated test dirs or files")
    t.add_argument("--json", action="store_true")
    t.add_argument("--feature", help="count only <feature>/AC-<n> tags (default: the "
                                     "spec's | feature | field, else its directory name)")
    t.set_defaults(fn=cmd_trace)
    m = sub.add_parser("matrix", help="default device/browser QA matrix")
    m.add_argument("--work", choices=["web-ui", "mobile"], required=True)
    m.add_argument("--tier", default="small")
    m.add_argument("--json", action="store_true")
    m.set_defaults(fn=cmd_matrix)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
