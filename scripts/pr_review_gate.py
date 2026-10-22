#!/usr/bin/env python3
"""Gate for a pr-review folder: every review rule plus GitHub-safe mermaid. Exit 0 only when both pass.

    pr_review_gate.py <pr-folder | run-root> [--snap SNAP] [--no-render-mermaid]

PR folder = has review.json. Run root = has PR-*/ folders (<feature>/ or <feature>/runs/<date>/).
--snap = pr_snapshot.py --dest dir (<snap>/<pr>/ head tree + <snap>/<pr>.diff): proves anchors,
hunks, suggestions and diffs (G10). Every failure names its rule tag (rubric §4).

Mermaid blocks (only in 1-context.md, 5-security.md and the run-root README.md) are linted for
syntax GitHub breaks on (<tag>, #123, ';' in a sequence diagram) and checked structurally
(diagram type, balanced brackets, subgraph/block 'end's). They are also rendered with
`npx -y -p @mermaid-js/mermaid-cli mmdc` when npx is on PATH; without npx, or with
--no-render-mermaid, rendering is skipped with a WARN -- a missing renderer never fails the gate.
PR_REVIEW_MERMAID_CACHE=<dir> remembers blocks that rendered.
No host, owner or repo is hard-coded: the repo base comes from review.json pr.url.
Exit codes: 0 pass, 1 rule failure, 2 usage. Python stdlib only.
"""
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pr_review as rr

KINDS = ("issue", "suggestion", "question", "nit", "praise")
BLOCKS = ("merge", "rollout", "none")
SEVS = ("critical", "major", "minor", "trivial")
STATUS_RE = re.compile(r"^(open|needs_decision|question|accepted|wont_fix|fixed:[0-9a-f]{7,40})$")
CHANGE_TYPES = ("suggestion", "diff", "pseudo", "none")
EVIDENCE = ("ran", "read", "inferred", "assumption", "user")
USER_FIELDS = ("title", "why", "comment", "kind", "blocks", "change", "where", "ask", "also_ask",
               "status", "confirm_by", "unknown")   # the last three let a question become a suggestion
RECS = ("approve", "comment", "request_changes")
CHECKED_OK = re.compile(r"^(typecheck ok|lint ok|typecheck \+ lint ok|applies cleanly — typecheck not run \(.+\))$")
CHECKED_RE = re.compile(r"^(typecheck ok|lint ok|typecheck \+ lint ok|applies cleanly — typecheck not run \(.+\)|not checked — .+|n/a)$")
ID_RE = re.compile(r"^(\d+)-[A-Z]{1,4}-\d{2,3}$")
LEAK_ID = rr.LEAK_ID
LEAK_EMOJI = re.compile("[🔴🟠🟡🟢⚪➖✅❓🔎📖▶⚠]")
JARGON = re.compile(r"\b(Should-fix|Needs decision|Read in code|Ran it|Sev:|Severity:|Evidence:|merged into|Merged ID|kept as)\b", re.I)
ACTION_NUM = re.compile(r"(?<![\w/&])#\d{1,2}\b")
PR_URL = re.compile(r"^https?://[^/\s]+/[^/\s]+/[^/\s]+/pull/(\d+)$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
CJK = re.compile(r"[぀-ヿ㐀-鿿]")
WHY_MAX, TITLE_MAX, COMMENT_MAX = 300, 100, 900
CONTEXT_HEADINGS = ["## Problem", "## Before → after", "## Terms", "## Author's decisions", "## Not in this PR"]
REQUIRED_FILES = ["review.json", "README.md", "1-context.md", "2-comments-to-post.md", "3-questions.md", "4-findings.md", "github-review.json"]

fails = []
def fail(where, rule, msg): fails.append(f"FAIL  {where}  [{rule}] {msg}")

def concrete(s):
    """A real value: code span, number, or quoted text (rubric §3 'example with every claim')."""
    return bool(re.search(r"`[^`]+`|\d|\"[^\"]{3,}\"|“[^”]{3,}”|「[^」]+」", s or ""))


# ---------------------------------------------------------------- G1 schema
def need(obj, key, typ, where, rule="G1-schema", allow_none=False):
    if not isinstance(obj, dict) or key not in obj or (obj[key] is None and not allow_none):
        fail(where, rule, f"missing '{key}'"); return None
    v = obj[key]
    if v is not None and not isinstance(v, typ): fail(where, rule, f"'{key}' must be {typ.__name__ if isinstance(typ, type) else typ}"); return None
    return v

def check_schema(r, f):
    pr = need(r, "pr", dict, f) or {}
    for k, t in (("url", str), ("number", int), ("title", str), ("author", str), ("head_sha", str), ("base", str)): need(pr, k, t, f + " pr")
    run = need(r, "run", dict, f) or {}
    for k, t in (("date", str), ("for", str), ("agents", list)): need(run, k, t, f + " run")
    for a in run.get("agents") or []:
        if not (isinstance(a, dict) and a.get("role") and a.get("model")): fail(f + " run.agents", "G1-schema", "each agent needs role + model")
    sm = need(r, "summary", dict, f) or {}
    wid = need(sm, "what_it_does", list, f + " summary")
    if wid is not None and not 1 <= len(wid) <= 3: fail(f + " summary", "G1-schema", "what_it_does: 1–3 plain lines")
    if sm.get("recommendation") not in RECS: fail(f + " summary", "G1-schema", f"recommendation must be one of {RECS}")
    need(sm, "reason", str, f + " summary")
    if sm.get("lang", "en") not in ("en", "ja"): fail(f + " summary", "G1-schema", "lang must be en or ja (auto is resolved by the orchestrator)")
    items = need(r, "items", list, f) or []
    need(r, "not_to_raise", list, f)
    cov = need(r, "coverage", list, f)
    if cov is not None and not cov: fail(f, "G1-schema", "coverage: one row per review dimension (even 'nothing found')")
    seen = set()
    for i in items:
        iid = i.get("id", "?")
        w = f"{f} item {iid}"
        m = ID_RE.match(str(iid))
        if not m: fail(w, "G1-schema", "id must look like <PR>-<DIM>-<NN>")
        elif pr.get("number") is not None and int(m.group(1)) != pr["number"]: fail(w, "G1-schema", f"id must start with the PR number {pr['number']}")
        if iid in seen: fail(w, "G1-schema", "duplicate id")
        seen.add(iid)
        if i.get("kind") not in KINDS: fail(w, "G1-schema", f"kind must be one of {KINDS}")
        if i.get("blocks") not in BLOCKS: fail(w, "G1-schema", f"blocks must be one of {BLOCKS}")
        if i.get("severity") not in SEVS: fail(w, "G1-schema", f"severity must be one of {SEVS}")
        if not STATUS_RE.match(str(i.get("status"))): fail(w, "G1-schema", "status must be open|needs_decision|question|fixed:<sha>|accepted|wont_fix")
        ev = need(i, "evidence", dict, w) or {}
        if ev.get("type") not in EVIDENCE: fail(w, "G1-schema", f"evidence.type must be one of {EVIDENCE}")
        need(ev, "detail", str, w + " evidence")
        wh = need(i, "where", dict, w) or {}
        if "in_diff" not in wh or not isinstance(wh.get("in_diff"), bool): fail(w, "G1-schema", "where.in_diff must be true/false")
        ch = need(i, "change", dict, w) or {}
        if ch.get("type") not in CHANGE_TYPES: fail(w, "G1-schema", f"change.type must be one of {CHANGE_TYPES}")
        need(i, "ask", dict, w)
        # G14: user decisions from `/pr-review adjust` and the post record
        u = i.get("user")
        if u is not None:
            if not isinstance(u, dict) or u.get("decision") not in ("post", "skip"): fail(w, "G14-user", "user.decision must be post or skip")
            else:
                ed = u.get("edited") or []
                if not isinstance(ed, list) or any(x not in USER_FIELDS for x in ed): fail(w, "G14-user", f"user.edited lists changed fields from {USER_FIELDS}")
                elif ev.get("type") != "user" and any(x not in (u.get("original") or {}) for x in ed):
                    fail(w, "G14-user", "user.original must keep the reviewer's value of every edited field (shown as before → after)")
                if not u.get("by") or not u.get("at"): fail(w, "G14-user", "user.by (login) and user.at (date) are required")
        if ev.get("type") == "user" and not ((u or {}).get("decision")): fail(w, "G14-user", "evidence.type 'user' only on items added by you (user block required)")
        if ev.get("type") == "user" and "-U-" not in str(iid): fail(w, "G14-user", "items you add use id <PR>-U-NN")
        pz = i.get("posted")
        if pz is not None:
            if not (isinstance(pz, dict) and pz.get("mode") in ("draft", "submit") and pz.get("at") and str(pz.get("url", "")).startswith(pr.get("url", "?"))):
                fail(w, "G14-user", "posted = {at, mode: draft|submit, url on this PR}")
            if (u or {}).get("decision") == "skip": fail(w, "G14-user", "already posted — can't be skipped now; delete or resolve it on GitHub instead")
    return not fails


# ---------------------------------------------------------------- G2 item completeness · G3 clean author text · G4 existing comments
def check_items(r, f):
    rec_url = rr.repo_url(r)
    for i in r["items"]:
        w = f"{f} item {i['id']}"
        for k in ("title", "why", "comment"):
            if not str(i.get(k) or "").strip(): fail(w, "G2-item", f"'{k}' is empty")
        why = i.get("why") or ""
        if len(why) > WHY_MAX or why.count("\n") > 1: fail(w, "G2-item", f"why: plain, ≤ 2 lines and ≤ {WHY_MAX} chars (has {len(why)})")
        if len(i.get("title") or "") > TITLE_MAX: fail(w, "G2-item", f"title ≤ {TITLE_MAX} chars")
        if len(i.get("comment") or "") > COMMENT_MAX: fail(w, "G2-item", f"comment ≤ {COMMENT_MAX} chars — put depth in 4-findings.md")
        by_user = i["evidence"].get("type") == "user" or "comment" in ((i.get("user") or {}).get("edited") or [])
        if i["kind"] != "praise" and not by_user and not concrete(i.get("comment")): fail(w, "G2-item", "comment needs one real value (code span, number or quoted text)")
        a = i["ask"]
        if not str(a.get("who") or "").strip() or not str(a.get("where") or "").strip(): fail(w, "G2-item", "ask.who and ask.where are both required")
        for x in i.get("also_ask") or []:
            if not (x.get("who") and x.get("where") and x.get("say")): fail(w, "G2-item", "also_ask entries need who, where, say")
        wh = i["where"]
        if wh.get("in_diff") and not (wh.get("path") and wh.get("line")): fail(w, "G2-item", "where.in_diff=true needs path + line")
        if wh.get("start_line") and wh.get("line") and wh["start_line"] > wh["line"]: fail(w, "G2-item", "where.start_line after where.line")
        ch = i["change"]
        if ch.get("type") == "none" and i["kind"] not in ("question", "praise") and not by_user: fail(w, "G2-item", "change 'none' only for question/praise — show what the code becomes (pseudo is fine)")
        if ch.get("type") != "none" and not str(ch.get("body") or "").strip(): fail(w, "G2-item", f"change.type {ch.get('type')} with an empty body")
        if i["evidence"]["type"] in ("inferred", "assumption") and not str(i.get("confirm_by") or "").strip():
            fail(w, "G2-item", "inferred/assumption evidence needs confirm_by (exact command or test)")
        if rr.in_questions(i) and i["evidence"].get("type") != "user":
            for k in ("unknown", "confirm_by"):
                if not str(i.get(k) or "").strip(): fail(w, "G2-item", f"'{k}' is required: this item is listed in 3-questions.md")
        if i["kind"] == "nit":
            if i["blocks"] != "none": fail(w, "G2-item", "a nit cannot block")
            if ch.get("type") == "suggestion": fail(w, "G2-item", "nits are bundled into one general comment: use diff/pseudo, not suggestion")
        if i["kind"] == "praise" and i["blocks"] != "none": fail(w, "G2-item", "praise cannot block")
        if rr.is_author(i):
            aw = a["where"].strip().lower()
            if aw not in ("line comment", "pr comment"): fail(w, "G2-item", "ask.who=author → ask.where is 'line comment' or 'PR comment'")
            if aw == "line comment" and not wh.get("in_diff"): fail(w, "G2-item", "'line comment' needs where.in_diff=true (GitHub only takes inline comments on diff lines)")
            if i["kind"] == "nit" and aw != "pr comment": fail(w, "G2-item", "nits go in one general comment: ask.where 'PR comment'")
        # G3: author-facing and reader-facing text carries no internal IDs, status emojis or rubric jargon
        texts = {"title": i.get("title"), "why": i.get("why"), "comment": i.get("comment"), "unknown": i.get("unknown"),
                 "ask": f"{a.get('who')} {a.get('where')}"}
        for x in i.get("also_ask") or []: texts["also_ask"] = f"{x.get('who')} {x.get('where')} {x.get('say')}"
        for k, t in texts.items():
            t = t or ""
            for rx, what in ((LEAK_ID, "internal ID"), (LEAK_EMOJI, "status emoji"), (JARGON, "rubric jargon")):
                m = rx.search(t)
                if m: fail(w, "G3-clean", f"{k} shows {what} '{m.group(0)}' — readers and the author can't decode it")
        # G4: existing PR comments
        d = i.get("dup_of_existing_comment")
        if d and not str(d).startswith(rr.repo_url(r) + "/pull/" + str(r["pr"]["number"])):
            fail(w, "G4-existing", f"dup_of_existing_comment must be a URL into this PR ({r['pr']['url']}…)")
        if r["run"].get("recheck_of") is None and i.get("previous_status"): fail(w, "G9-recheck", "previous_status only on a recheck (run.recheck_of set)")
        if i.get("previous_status") and not STATUS_RE.match(i["previous_status"]): fail(w, "G9-recheck", "previous_status uses the status vocabulary")
        # G7: links stay on this repo at the pinned SHA
        for k, t in (("evidence.detail", i["evidence"].get("detail")), ("comment", i.get("comment")), ("why", i.get("why"))):
            for m in re.finditer(r"https?://\S+?/blob/([^/\s)]+)/", t or ""):
                if not m.group(0).startswith(rec_url + "/blob/") or m.group(1) != r["pr"]["head_sha"]:
                    fail(w, "G7-links", f"{k}: blob link must be {rec_url}/blob/<pinned head SHA>/… (found {m.group(0)[:80]})")
    for x in r.get("not_to_raise", []):
        if not (x.get("topic") and x.get("why")): fail(f + " not_to_raise", "G2-item", "each row needs topic + why")
        for k in ("topic", "why"):
            m = LEAK_ID.search(x.get(k) or "") or LEAK_EMOJI.search(x.get(k) or "")
            if m: fail(f + " not_to_raise", "G3-clean", f"{k} shows '{m.group(0)}'")
    for x in r.get("not_to_raise", []) + [{"why": r["summary"].get("reason")}]:
        m = ACTION_NUM.search(x.get("why") or "")
        if m: fail(f + " summary/not_to_raise", "G13-handwritten", f"cites action number '{m.group(0)}' — numbers are assigned at render time")
    for k in ("reason", "review_intro"):
        t = r["summary"].get(k) or ""
        m = LEAK_ID.search(t) or LEAK_EMOJI.search(t) or JARGON.search(t)
        if m: fail(f + " summary", "G3-clean", f"{k} shows '{m.group(0)}'")
    for t in r["summary"]["what_it_does"]:
        m = LEAK_ID.search(t) or LEAK_EMOJI.search(t)
        if m: fail(f + " summary", "G3-clean", f"what_it_does shows '{m.group(0)}'")
    ec = r["run"].get("existing_comments")
    if not (isinstance(ec, dict) and ec.get("checked") is True and isinstance(ec.get("count"), int)):
        fail(f + " run", "G4-existing", "run.existing_comments {checked: true, count: N, note} — read PR comments, review threads and bot reviews first")
    if r["summary"].get("lang") == "ja":
        for i in rr.actionable(r):
            if not CJK.search(i["comment"]): fail(f"{f} item {i['id']}", "G8-lang", "summary.lang is ja but the comment has no Japanese text")
        if not r["summary"].get("review_intro"): fail(f + " summary", "G8-lang", "lang ja needs summary.review_intro (the default intro is English)")


# ---------------------------------------------------------------- G5 suggestions checked · G6 recommendation · G7 pr/url
def check_checked(r, d, f):
    log = {}
    lp = d / "suggestion-checks.json"
    if lp.is_file():
        try: log = json.loads(lp.read_text(encoding="utf-8"))
        except ValueError: fail(str(lp), "G5-checked", "not valid JSON")
    for i in r["items"]:
        ch, w = i["change"], f"{f} item {i['id']}"
        c = ch.get("checked")
        if ch.get("type") in ("suggestion", "diff"):
            if not c or not CHECKED_RE.match(c) or c == "n/a":
                fail(w, "G5-checked", "suggestion/diff needs change.checked: 'typecheck ok' | 'lint ok' | 'applies cleanly — typecheck not run (<why>)' | 'not checked — <why>'")
            elif CHECKED_OK.match(c):
                e = log.get(i["id"])
                h = hashlib.sha256(ch["body"].encode()).hexdigest()
                if not e or e.get("result") != c or e.get("sha256") != h:
                    fail(w, "G5-checked", f"claims '{c}' but suggestion-checks.json has no matching run for this exact change (run check_suggestions.py)")
        elif c and c != "n/a" and not c.startswith("not checked"):
            fail(w, "G5-checked", f"change.type {ch.get('type')} cannot claim '{c}'")

def check_recommendation(r, f):
    want = rr.computed_recommendation(r)
    if r["summary"]["recommendation"] != want:
        fail(f + " summary", "G6-recommendation", f"recommendation is '{r['summary']['recommendation']}' but the items give '{want}' "
             "(open blocks:merge → request_changes; else open issue/question → comment; else approve)")

def check_pr_meta(r, f):
    m = PR_URL.match(r["pr"]["url"])
    if not m: fail(f + " pr.url", "G7-links", "must be https://<host>/<owner>/<repo>/pull/<n> (copied from gh pr view, never typed)")
    elif int(m.group(1)) != r["pr"]["number"]: fail(f + " pr.url", "G7-links", "number in pr.url ≠ pr.number")
    if not SHA40.match(r["pr"]["head_sha"]): fail(f + " pr.head_sha", "G7-links", "must be the full 40-hex pinned head SHA")


# ---------------------------------------------------------------- G10 snapshot
def diff_hunks(text):
    h, cur = {}, None
    for l in text.split("\n"):
        if l.startswith("+++ "): cur = l[4:].strip(); cur = cur[2:] if cur.startswith("b/") else cur; h.setdefault(cur, [])
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", l)
        if m and cur: h[cur].append((int(m.group(1)), int(m.group(2) or 1)))
    return h

def check_snapshot(r, snap, f):
    n = r["pr"]["number"]
    tree, dfile = snap / str(n), snap / f"{n}.diff"
    if not tree.is_dir(): fail(str(tree), "G10-snapshot", "no snapshot tree for this PR"); return
    hunks = diff_hunks(dfile.read_text(errors="replace")) if dfile.is_file() else None
    if hunks is None: fail(str(dfile), "G10-snapshot", "no diff file")
    for i in r["items"]:
        w, wh, ch = f"{f} item {i['id']}", i["where"], i["change"]
        if wh.get("path"):
            fp = tree / wh["path"]
            if not fp.is_file(): fail(w, "G10-snapshot", f"{wh['path']} does not exist at the pinned head"); continue
            cur = fp.read_text(errors="replace").split("\n")
            if wh.get("line"):
                a, b = rr.lines_of(wh)
                if b > len(cur): fail(w, "G10-snapshot", f"L{b} is past the end of {wh['path']} ({len(cur)} lines)"); continue
                if hunks is not None:
                    inside = any(s <= a and b <= s + ln - 1 for s, ln in hunks.get(wh["path"], []))
                    if wh.get("in_diff") and not inside: fail(w, "G10-snapshot", f"{wh['path']} {rr.line_label(wh)} is not inside one hunk of the PR diff — set in_diff false")
                    if not wh.get("in_diff") and inside: fail(w, "G10-snapshot", f"{wh['path']} {rr.line_label(wh)} IS in the diff — set in_diff true so it can be posted inline")
                if ch.get("type") == "suggestion" and [x.rstrip() for x in ch["body"].rstrip("\n").split("\n")] == [x.rstrip() for x in cur[a - 1:b]]:
                    fail(w, "G10-snapshot", "suggestion is identical to the current lines")
        if ch.get("type") == "suggestion" and not (wh.get("in_diff") and wh.get("line")):
            fail(w, "G10-snapshot", "```suggestion only on an in-diff line (GitHub can't apply it elsewhere) — use diff or pseudo")
        if ch.get("type") == "diff":
            target, lines = None, None
            body = ch["body"].split("\n")
            if not any(x.startswith("+++ ") for x in body): fail(w, "G10-snapshot", "diff needs '--- a/<path>' and '+++ b/<path>' headers")
            for x in body:
                if x.startswith("+++ "):
                    p = x[4:].strip(); p = p[2:] if p.startswith("b/") else p
                    target = tree / p
                    lines = set(y.strip() for y in target.read_text(errors="replace").split("\n")) if target.is_file() else None
                    if lines is None: fail(w, "G10-snapshot", f"diff targets {p}, which does not exist at the pinned head")
                elif x.startswith("-") and not x.startswith("--- ") and lines is not None and x[1:].strip() and x[1:].strip() not in lines:
                    fail(w, "G10-snapshot", f"diff removes a line that is not in the file: '{x[1:].strip()[:60]}'")


# ---------------------------------------------------------------- G15 reviewer lenses (Design DES, Scenario SCN)
UNVERIFIED = ("inferred", "assumption")
LENS_QUESTION = ("question", "needs_decision")
LENS_COLUMNS = ("Risk if wrong", "Cost to undo")

def check_lens(r, f):
    for i in r["items"]:
        if not rr.lens_of(i["id"]) or i["evidence"]["type"] not in UNVERIFIED: continue
        if i["status"] not in LENS_QUESTION or i["blocks"] == "merge":
            fail(f"{f} item {i['id']}", "G15-lens", f"unverified lens claim → make it a question for the author: evidence '{i['evidence']['type']}' "
                 f"needs status {' or '.join(LENS_QUESTION)} and blocks other than merge (has status '{i['status']}', blocks '{i['blocks']}')")
    for p, n in sorted(rr.lens_counts(r["items"]).items()):
        if n > rr.LENS_MAX: fail(f, "G15-lens", f"{n} new {p} lens items — cap is {rr.LENS_MAX}; keep the ones with the biggest blast radius")

def check_decision_columns(t, c):
    """When the Design lens ran, 1-context.md must weigh each of the author's decisions."""
    m = re.search(r"^## Author's decisions[ \t]*\r?\n(.*?)(?=^## |\Z)", t, re.S | re.M)
    rows = [l for l in (m.group(1) if m else "").split("\n") if l.startswith("|")]
    if not any(all(k in l for k in LENS_COLUMNS) for l in rows):
        fail(str(c), "G15-lens", f"the Design lens ran, so the '## Author's decisions' table needs '{LENS_COLUMNS[0]}' and '{LENS_COLUMNS[1]}' columns")


# ---------------------------------------------------------------- G11 rendered files · G12 README · G13 hand-written files
def check_rendered(r, d):
    expect = rr.render_pr(r, (d / "5-security.md").is_file())
    for name, text in expect.items():
        p = d / name
        if p.is_file() and p.read_text(encoding="utf-8") != text:
            fail(str(p), "G11-rendered", "differs from pr_review.py render output — never hand-edit; change review.json and re-render")
    fp = d / "4-findings.md"
    if fp.is_file():
        t = fp.read_text(encoding="utf-8")
        regs = rr.render_regions(r)
        found = {m.group(2): m.group(3) for m in rr.REGION_RE.finditer(t)}
        for k, v in regs.items():
            if k not in found: fail(str(fp), "G11-rendered", f"missing <!-- rendered:{k} START --> … <!-- rendered:{k} END --> markers")
            elif found[k] != v: fail(str(fp), "G11-rendered", f"rendered region '{k}' differs from review.json — re-run pr_review.py render")
        ids = {i["id"] for i in r["items"]}
        for m in re.finditer(r"^### (\S+) — ", t, re.M):
            if m.group(1) not in ids: fail(str(fp), "G13-handwritten", f"evidence note for {m.group(1)}, which is not an item in review.json")
        if "```mermaid" in t: fail(str(fp), "G13-handwritten", "diagrams live in 1-context.md / 5-security.md only")

def check_readme(r, d):
    p = d / "README.md"
    if not p.is_file(): return
    t = p.read_text(encoding="utf-8")
    for need_row in ("| Reviewed by |", "| Requested by (you) |", "| PR author (gets the comments) |", "| Commit reviewed |", "| Date |", "| Recheck of |"):
        if need_row not in t: fail(str(p), "G12-readme", f"'who reviewed' table row missing: {need_row}")
    sec = t.split("## Your action items", 1)
    refs = set()
    if len(sec) == 2:
        for line in sec[1].split("\n## ", 1)[0].split("\n"):
            if line.startswith("| ") and not line.startswith("| #") and not line.startswith("|---"):
                last = line.rstrip(" |").rsplit("|", 1)[-1]
                refs |= {x.strip() for x in last.split(",") if x.strip() and x.strip() != "—"}
    else: fail(str(p), "G12-readme", "no '## Your action items' table")
    want = {i["id"] for i in rr.to_post(r)}
    if refs != want: fail(str(p), "G12-readme", f"action table refs {sorted(refs)} ≠ open, not-skipped items {sorted(want)}")
    body = t.split("## Your action items", 1)[0]
    for m in LEAK_ID.finditer(body): fail(str(p), "G3-clean", f"internal ID '{m.group(0)}' above the action table")

def check_handwritten(d, r):
    c = d / "1-context.md"
    if c.is_file():
        t = c.read_text(encoding="utf-8")
        design_ran = any(a.get("role") == "Design" for a in r["run"]["agents"]) or any(rr.lens_of(i["id"]) == "DES" for i in r["items"])
        if design_ran: check_decision_columns(t, c)
        for h in CONTEXT_HEADINGS:
            if not re.search(rf"^{re.escape(h)}", t, re.M): fail(str(c), "G13-handwritten", f"missing section '{h}'")
        if "```mermaid" not in t: fail(str(c), "G13-handwritten", "needs one before → after diagram")
    for name in ("1-context.md", "5-security.md"):
        p = d / name
        if not p.is_file(): continue
        t = p.read_text(encoding="utf-8")
        m = ACTION_NUM.search(t)
        if m: fail(str(p), "G13-handwritten", f"cites action number '{m.group(0)}' — numbers are assigned at render time; name the item instead")
        for m in re.finditer(r"^```mermaid\n.*?^```\n", t, re.S | re.M):
            after = t[m.end():].lstrip("\n")
            if not after.startswith("**Reading this diagram**"): fail(str(p), "G13-handwritten", "each diagram is followed by '**Reading this diagram**' + 2–3 bullets")
    for name in ("2-comments-to-post.md", "3-questions.md"):
        p = d / name
        if p.is_file():
            for m in LEAK_ID.finditer(p.read_text(encoding="utf-8")): fail(str(p), "G3-clean", f"internal ID '{m.group(0)}'")


# ---------------------------------------------------------------- folders
def check_pr(d, snap):
    d = pathlib.Path(d)
    for n in REQUIRED_FILES:
        if not (d / n).is_file(): fail(str(d / n), "G0-files", "missing")
    if not (d / "review.json").is_file(): return
    try: r = json.loads((d / "review.json").read_text(encoding="utf-8"))
    except ValueError as e: fail(str(d / "review.json"), "G1-schema", f"not valid JSON: {e}"); return
    f = str(d / "review.json")
    before = len(fails)
    check_schema(r, f)
    if len(fails) > before: return            # later rules assume the shape
    check_pr_meta(r, f); check_items(r, f); check_lens(r, f); check_checked(r, d, f); check_recommendation(r, f)
    if snap: check_snapshot(r, snap, f)
    check_rendered(r, d); check_readme(r, d); check_handwritten(d, r)

def check_root(root, snap):
    root = pathlib.Path(root)
    prs = sorted(p for p in root.glob("PR-*") if p.is_dir())
    if not (root / "PINS.md").is_file(): fail(str(root / "PINS.md"), "G0-files", "missing (copy from pr_snapshot.py --dest)")
    for p in prs: check_pr(p, snap)
    readme = root / "README.md"
    if not readme.is_file(): fail(str(readme), "G0-files", "missing (pr_review.py feature)")
    elif all((p / "review.json").is_file() for p in prs) and readme.read_text(encoding="utf-8") != rr.render_feature(root):
        fail(str(readme), "G11-rendered", "feature README differs from pr_review.py feature output")



# ---------------------------------------------------------------- mermaid
MERMAID_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*mermaid[ \t]*\n(.*?)^ {0,3}\1[ \t]*$", re.S | re.M)
MERMAID_TYPES = ("graph", "flowchart", "sequenceDiagram", "classDiagram", "stateDiagram", "stateDiagram-v2",
                 "erDiagram", "journey", "gantt", "pie", "gitGraph", "mindmap", "timeline", "quadrantChart",
                 "requirementDiagram", "C4Context", "C4Container", "C4Component", "C4Dynamic", "C4Deployment",
                 "sankey-beta", "xychart-beta", "block-beta", "packet-beta", "architecture-beta", "kanban")
SEQ_BLOCKS = ("alt", "opt", "loop", "par", "rect", "critical", "break", "box")
MMDC = ["npx", "-y", "-p", "@mermaid-js/mermaid-cli", "mmdc", "-q"]

def mermaid_files(target):
    """Files that may hold diagrams; runs/ below the target is its own run root and is skipped."""
    out = []
    for p in sorted(target.rglob("*.md")):
        if "runs" in p.relative_to(target).parts[:-1]: continue
        if p.name in ("1-context.md", "5-security.md"): out.append(p)
    readme = target / "README.md"
    if readme.is_file() and not (target / "review.json").is_file(): out.append(readme)
    return out

def mermaid_blocks(path):
    text = path.read_bytes().decode("utf-8", "replace").replace("\r\n", "\n")
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return [(f"{path}#block{i}", m.group(2)) for i, m in enumerate(MERMAID_FENCE.finditer(text))]

def mermaid_lint(src):
    """GitHub-unsafe syntax and structural errors a renderer would reject. [(line, why, text)]"""
    lines = src.split("\n")
    body = [(n, l.strip()) for n, l in enumerate(lines, 1) if l.strip() and not l.strip().startswith("%%")]
    if not body: return [(1, "empty diagram", "")]
    head = body[0][1].split()[0]
    probs = []
    if head not in MERMAID_TYPES: probs.append((body[0][0], f"unknown diagram type '{head}'", body[0][1]))
    seq = head == "sequenceDiagram"
    depth = 0
    for n, s in body:
        t = re.sub(r"<br\s*/?>|<<\w+>>", "", s, flags=re.I)
        t = re.sub(r"\b(fill|stroke|color)\s*:\s*#[0-9a-fA-F]{3,8}\b", "", t)
        why = [w for w, bad in (("<tag>", re.search(r"<[A-Za-z][^>]*>", t)), ("#number", re.search(r"(?<![&\w])#\d", t)),
                                 ("';' in a sequence diagram", seq and ";" in t)) if bad]
        if t.count('"') % 2: why.append("unbalanced double quote")
        bare = re.sub(r'"[^"]*"', '""', t)
        for o, c in ("[]", "()", "{}"):
            if bare.count(o) != bare.count(c): why.append(f"unbalanced '{o}{c}'")
        if why: probs.append((n, ", ".join(why), s))
        word = s.split()[0]
        if word == "subgraph" or (seq and word in SEQ_BLOCKS): depth += 1
        elif word == "end": depth -= 1
        if depth < 0: probs.append((n, "'end' without an open block", s)); depth = 0
    if depth > 0: probs.append((len(lines), f"{depth} block(s) never closed with 'end'", ""))
    return probs

def check_mermaid(target, render):
    """(ok, messages). A renderer that is absent is a warning, never a failure."""
    blocks = [b for f in mermaid_files(target) for b in mermaid_blocks(f)]
    if not blocks: return True, []
    ok, msgs = True, []
    if render and not shutil.which("npx"):
        msgs.append(f"WARN  mermaid render skipped for {len(blocks)} block(s): npx not found (syntax checked with the stdlib fallback only)")
        render = False
    elif not render:
        msgs.append(f"WARN  mermaid render skipped for {len(blocks)} block(s): --no-render-mermaid (syntax checked with the stdlib fallback only)")
    cache = os.environ.get("PR_REVIEW_MERMAID_CACHE")
    with tempfile.TemporaryDirectory() as tmp:
        for k, (where, src) in enumerate(blocks):
            probs = mermaid_lint(src)
            if probs:
                ok = False; msgs.append(f"FAIL  {where}  [mermaid] GitHub-unsafe or malformed syntax")
                msgs += [f"      {n}: {why}: {s}" for n, why, s in probs]
                continue
            if not render: continue
            key = pathlib.Path(cache) / (hashlib.sha256(src.encode()).hexdigest()[:40] + ".ok") if cache else None
            if key is not None and key.is_file(): continue
            mmd = pathlib.Path(tmp, f"{k:03d}.mmd"); mmd.write_text(src, encoding="utf-8")
            try:
                p = subprocess.run(MMDC + ["-i", str(mmd), "-o", str(mmd.with_suffix(".svg"))], capture_output=True, text=True, timeout=300)
            except (OSError, subprocess.TimeoutExpired) as e:
                msgs.append(f"WARN  {where}  mermaid render could not run ({e}); syntax checked with the stdlib fallback only")
                continue
            if p.returncode != 0:
                ok = False; msgs.append(f"FAIL  {where}  [mermaid] parse error")
                msgs += ["      " + l for l in (p.stderr or p.stdout).splitlines() if re.search(r"Error|line|\^", l)][:3]
                continue
            if key is not None:
                key.parent.mkdir(parents=True, exist_ok=True); key.write_text("", encoding="utf-8")
    return ok, msgs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pr_review_gate.py", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="PR folder (has review.json) or run root (has PR-*/)")
    ap.add_argument("--snap", help="pr_snapshot.py --dest dir")
    ap.add_argument("--no-render-mermaid", action="store_true", help="skip mermaid-cli even when npx exists")
    a = ap.parse_args(argv)
    target, snap = pathlib.Path(a.target), (pathlib.Path(a.snap) if a.snap else None)
    if snap is not None and not snap.is_dir(): print(f"pr_review_gate: --snap {snap} is not a directory", file=sys.stderr); return 2
    if (target / "review.json").is_file() or target.name.startswith("PR-"): check_pr(target, snap)
    elif target.is_dir() and list(target.glob("PR-*")): check_root(target, snap)
    else: print(f"pr_review_gate: {target}: neither a PR folder (review.json) nor a run root (PR-*/)", file=sys.stderr); return 2
    for x in fails: print(x)
    print(("PASS  rules         " if not fails else f"FAIL  {len(fails)} rule failure(s) in ") + str(target))
    mok, msgs = check_mermaid(target, not a.no_render_mermaid)
    for m in msgs: print(m)
    if mok: print(f"PASS  mermaid       {target}")
    return 0 if not fails and mok else 1

if __name__ == "__main__":
    sys.exit(main())
