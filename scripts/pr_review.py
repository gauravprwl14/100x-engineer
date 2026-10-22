#!/usr/bin/env python3
"""Render, find and index read-only PR reviews (the /pr-review skill's engine).

One review.json per PR folder is the only hand-maintained source; every file a reader
uses is rendered from it, so the files cannot disagree. Rules: the pr-review skill's
references/rubric.md. Posts nothing: GitHub calls stay in the skill's own steps.

    pr_review.py out-dir [--repo PATH] [--url PR_URL] [--out DIR] [--json]
    pr_review.py paths   [--repo PATH] [--url PR_URL] [--out DIR] [--json]
    pr_review.py init    [--repo PATH] [--url PR_URL] [--out DIR] [--json]   (also: out-dir --ensure)
    pr_review.py context --refresh <CR> [--repo PATH]
    pr_review.py render <pr-dir | review.json>
    pr_review.py feature <run-root>
    pr_review.py merge <pr-dir> <fragment.json>...
    pr_review.py emit <pr-dir> draft|submit          (exit 3: nothing new to post)
    pr_review.py preview <pr-dir>
    pr_review.py mark-posted <pr-dir> <review-url> draft|submit
    pr_review.py followup-text <pr-dir> <review-url>
    pr_review.py find <CR> <pr-url>  |  find <CR> <feature-folder> <pr-number>   (exit 1: never reviewed)
    pr_review.py slug <head-branch>
    pr_review.py next-run <feature-dir>
    pr_review.py index <CR>

Review root CR (out-dir), first match wins:
  --out  >  $PR_REVIEW_OUT  >  `git config pr-review.out` in the target repo  >
  ~/.config/pr-review/config.json {"out": ...}  >  <parent of the main repo>/code-review/<repo>/.
<repo> is the name in the remote URL (else the folder name); a worktree maps to its main
repo through `git rev-parse --git-common-dir`. With no local clone, or when that parent is
itself inside a git work tree (never write into another repo), CR is
~/.config/pr-review/reviews/<host>/<owner>/<repo>/. $PR_REVIEW_HOME replaces ~/.config/pr-review.

User decisions (set by `/pr-review adjust`, kept across re-reviews):
  item.user   = {decision: post|skip, edited: [fields], original: {field: old value}, note, by, at}
  item.posted = {at, mode: draft|submit, url}      -- never posted twice
  user-added items: id <PR>-U-NN, evidence.type "user"

Rendered, never edit: README.md, 2-comments-to-post.md, 3-questions.md, github-review.json,
4-findings.md between <!-- rendered:NAME START ... --> and <!-- rendered:NAME END -->.
Hand-written: 1-context.md, 5-security.md, 4-findings.md outside the markers.
No host, owner or repo is known here: every link is built from review.json pr.url.
Exit codes: 0 ok, 1 not found / refused, 2 usage, 3 nothing new to post. Python stdlib only.
"""
import argparse, json, os, pathlib, re, subprocess, sys

ACTIONABLE = ("open", "needs_decision", "question")
BLOCKS_RANK = {"merge": 0, "rollout": 1, "none": 2}
SEV_RANK = {"critical": 0, "major": 1, "minor": 2, "trivial": 3}
REC_TEXT = {
    "request_changes": "Request changes",
    "comment": "Comment — don't approve yet, nothing blocks the merge",
    "approve": "Approve",
}
EVIDENCE_TEXT = {"ran": "Ran it", "read": "Read in the code", "inferred": "Inferred — not tested", "assumption": "Assumption — not checked",
                 "user": "Added by you"}
STATUS_TEXT = {"open": "open", "needs_decision": "needs a decision", "question": "question open",
               "accepted": "accepted", "wont_fix": "won't fix"}
FENCE = {"suggestion": "suggestion", "diff": "diff", "pseudo": "text"}
REGION_RE = re.compile(r"(<!-- rendered:(\w+) START[^>]*-->\n)(.*?)(<!-- rendered:\2 END -->)", re.S)
OUTPUTS = ["README.md", "2-comments-to-post.md", "3-questions.md", "github-review.json"]


# ---------------------------------------------------------------- helpers
def load(pr_dir):
    return json.loads((pathlib.Path(pr_dir) / "review.json").read_text(encoding="utf-8"))

def repo_url(r): return r["pr"]["url"].split("/pull/")[0]

def status_text(s): return f"fixed in `{s.split(':', 1)[1]}`" if s.startswith("fixed:") else STATUS_TEXT.get(s, s)

def cell(s):
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", "<br>")

def base(path):
    """Short file name for tables; generic names (index.ts) keep their folder."""
    parts = path.split("/")
    return "/".join(parts[-2:]) if parts[-1].split(".")[0] in ("index", "main", "mod", "__init__") and len(parts) > 1 else parts[-1]

def lines_words(w):
    a, b = lines_of(w)
    return f"line {a}" if a == b else f"lines {a}–{b}"

def lines_of(w):
    a, b = w.get("start_line") or w.get("line"), w.get("line")
    return (a, b)

def line_label(w):
    a, b = lines_of(w)
    return f"L{a}" if a == b else f"L{a}–L{b}"

def permalink(r, w):
    if not w.get("path"): return None
    url = f"{repo_url(r)}/blob/{r['pr']['head_sha']}/{w['path']}"
    if w.get("line"):
        a, b = lines_of(w)
        url += f"#L{a}" if a == b else f"#L{a}-L{b}"
    return url

def is_author(item): return item["ask"]["who"].strip().lower() == "author"

def actionable(r):
    return [i for i in r["items"] if i["kind"] != "praise" and i["status"] in ACTIONABLE]

def is_skipped(i): return (i.get("user") or {}).get("decision") == "skip"
def is_edited(i): return bool((i.get("user") or {}).get("edited"))
def is_posted(i): return bool(i.get("posted"))

LEAK_ID = re.compile(r"\b\d+-[A-Z]{1,4}-\d{2,3}\b|\b[AQX]-\d{2,3}\b")   # internal item IDs; the gate's G3 uses this too

def user_note(r, i, default):
    """The user's adjust note, with any item ID swapped for that item's title — files 2 and 3 must not show IDs."""
    n = ((i.get("user") or {}).get("note") or "").strip()
    if not n: return default
    titles = {x["id"]: x["title"] for x in r["items"]}
    return LEAK_ID.sub(lambda m: f"\"{titles[m.group(0)]}\"" if m.group(0) in titles else "another item", n)

def to_post(r):
    """Open, not skipped by the user — the items that get a number and a row in the action table."""
    return [i for i in actionable(r) if not is_skipped(i)]

def skipped(r):
    return [i for i in r["items"] if is_skipped(i)]

def post_state(i):
    """Will-post cell: who sends it and whether it already went out."""
    s = section_of(i)
    if is_posted(i):
        p = i["posted"]; return f"Posted ({'draft' if p['mode'] == 'draft' else 'submitted'}, {p['at']})"
    if s == "C": return "You, by hand"
    if s == "D": return "You, reply in thread"
    return "Yes — edited by you" if is_edited(i) else "Yes"

def section_of(i):
    """A line comment · B general PR comment · C ask someone else · D reply in an existing thread."""
    if i.get("dup_of_existing_comment"): return "D"
    if not is_author(i): return "C"
    if i["kind"] == "nit": return "B"
    if i["where"].get("in_diff") and i["ask"]["where"].strip().lower() == "line comment": return "A"
    return "B"

def numbered(r):
    """[(number, [items])] in posting order: section A → B → C → D (see section_of), then blocks merge → rollout → none,
    then severity, then review.json order. All open author nits share one number: the last one in section B."""
    acts = to_post(r)
    order = {id(i): k for k, i in enumerate(r["items"])}
    key = lambda i: ("ABCD".index(section_of(i)), i["kind"] == "nit", BLOCKS_RANK[i["blocks"]], SEV_RANK[i["severity"]], order[id(i)])
    out, nits = [], []
    for i in sorted(acts, key=key):
        if i["kind"] == "nit" and section_of(i) == "B": nits.append(i); continue
        if nits and section_of(i) != "B": out.append((len(out) + 1, nits)); nits = []
        out.append((len(out) + 1, [i]))
    if nits: out.append((len(out) + 1, nits))
    return out

def number_of(r):
    return {i["id"]: n for n, group in numbered(r) for i in group}

def decoration(i):
    if i["kind"] == "praise": return ""
    return {"merge": " (blocking)", "rollout": " (before rollout)", "none": " (non-blocking)"}[i["blocks"]]

def change_block(i):
    ch = i.get("change") or {"type": "none"}
    if ch["type"] == "none" or not ch.get("body"): return ""
    lang = ch.get("lang") if ch["type"] == "pseudo" and ch.get("lang") else FENCE[ch["type"]]
    return f"```{lang}\n{ch['body'].rstrip()}\n```"

def paste_text(i):
    """The exact author-facing text: Conventional Comments label + comment + change block."""
    out = f"**{i['kind']}{decoration(i)}:** {i['comment'].strip()}"
    cb = change_block(i)
    return out + ("\n\n" + cb if cb else "")

def nit_bundle_text(nits, lang):
    intro = "細かい点です（任意）:" if lang == "ja" else "A few small optional things:"
    parts = [f"**nit (non-blocking):** {intro}"]
    for k, i in enumerate(nits, 1):
        p = f"**({k})** {i['comment'].strip()}"
        if i["where"].get("path"): p += f" — `{i['where']['path']}` {line_label(i['where'])}" if i["where"].get("line") else f" — `{i['where']['path']}`"
        cb = change_block(i)
        if cb: p += f"\n\n<details><summary>Proposed change</summary>\n\n{cb}\n\n</details>"
        parts.append(p)
    return "\n\n".join(parts)

def quote(text): return "\n".join("> " + l if l else ">" for l in text.split("\n"))

def where_text(r, i):
    w = i["where"]
    if i.get("dup_of_existing_comment"): return f"Reply / +1 in the [existing thread]({i['dup_of_existing_comment']})"
    if not is_author(i): s = f"Ask {i['ask']['who']} — {i['ask']['where']}"
    elif i["kind"] == "nit": s = "General PR comment (one comment for all nits)"
    elif section_of(i) == "A": s = f"Inline on [`{base(w['path'])}` {lines_words(w)}]({permalink(r, w)})"
    elif w.get("path"):
        loc = f" {line_label(w)}" if w.get("line") else ""
        s = f"General PR comment (about [`{base(w['path'])}`{loc}]({permalink(r, w)}), not in this PR's diff)"
    else: s = "General PR comment"
    for a in i.get("also_ask") or []: s += f" + ping {a['who']} on {a['where']}"
    return s

def blocks_text(b): return {"merge": "**Yes — merge**", "rollout": "Not the merge — **before rollout**", "none": "No"}[b]

def anchor(n): return f"c{n}"


# ---------------------------------------------------------------- recommendation (rubric §4, rendered)
def computed_recommendation(r):
    acts = actionable(r)
    if any(i["blocks"] == "merge" for i in acts): return "request_changes"
    if any(i["kind"] in ("issue", "question") for i in acts): return "comment"
    return "approve"


# ---------------------------------------------------------------- README.md
def render_readme(r):
    pr, run, sm = r["pr"], r["run"], r["summary"]
    groups = numbered(r)
    acts = to_post(r)
    secs = {}
    for n, g in groups: secs.setdefault(section_of(g[0]), []).append(n)
    n_author = len(secs.get("A", [])) + len(secs.get("B", []))
    others = len(secs.get("C", [])) + sum(len(i.get("also_ask") or []) for i in acts)
    merge_n = [n for n, g in groups if g[0]["blocks"] == "merge"]
    roll_n = [n for n, g in groups if g[0]["blocks"] == "rollout"]
    nums = lambda ns: ", ".join(f"#{n}" for n in ns)
    in10 = f"**{REC_TEXT[sm['recommendation']].split(' — ')[0]}.** {sm['reason'].strip()} "
    in10 += f"Post {n_author} comment{'s' if n_author != 1 else ''} to @{pr['author']} ({len(secs.get('A', []))} on lines, {len(secs.get('B', []))} general)"
    if others: in10 += f"; ask someone else {others} thing{'s' if others != 1 else ''}"
    if secs.get("D"): in10 += f"; reply in {len(secs['D'])} existing thread{'s' if len(secs['D']) != 1 else ''}"
    in10 += ". " + (f"{nums(merge_n)} block{'s' if len(merge_n) == 1 else ''} the merge" if merge_n else "Nothing blocks the merge")
    in10 += (f"; {nums(roll_n)} must be answered before rollout." if roll_n else ".")
    agents = " · ".join(f"{a['role']} ({a['model']})" for a in run["agents"])
    commit = f"[`{pr['head_sha'][:8]}`]({repo_url(r)}/commit/{pr['head_sha']})"
    L = [f"# PR {pr['number']} — {pr['title']}", "",
         f"> **In 10 seconds:** {in10}", "",
         "## Who is who", "",
         "| | |", "|---|---|",
         f"| Reviewed by | {cell(agents)} |",
         f"| Requested by (you) | @{run['for']} |",
         f"| PR author (gets the comments) | @{pr['author']} |",
         f"| PR | [{pr['url'].split('/pull/')[0].split('/')[-1]} PR {pr['number']}]({pr['url']}) · `{pr['base']}` · CI {cell(pr.get('ci', '?'))} · {pr.get('behind', '?')} commits behind |",
         f"| Commit reviewed | {commit} (every link points here) |",
         f"| Date | {run['date']} |",
         f"| Recheck of | {('`' + run['recheck_of'] + '`') if run.get('recheck_of') else '— (first review)'} |", "",
         "## What the PR does", ""]
    L += [f"- {x}" for x in sm["what_it_does"]] + [""]
    L += [f"## Recommendation: {REC_TEXT[sm['recommendation']]}", "", sm["reason"].strip(), "",
          "| Blocks | Items |", "|---|---|",
          f"| The merge | {nums(merge_n) or 'nothing'} |",
          f"| The rollout (before enabling for real users) | {nums(roll_n) or 'nothing'} |", "",
          "## Your action items (in order)", "",
          "| # | What | Type | Where to write it | Blocks? | Will post? | How we know | Text | ref |",
          "|---|---|---|---|---|---|---|---|---|"]
    for n, g in groups:
        i = g[0]
        what = i["title"] if len(g) == 1 else f"{len(g)} small optional points (one comment)"
        typ = f"{i['kind']}{decoration(i)}" if len(g) == 1 else "nit (non-blocking)"
        how = EVIDENCE_TEXT[i["evidence"]["type"]] if len(g) == 1 else "Read in the code"
        if len(g) > 1 and any(x["evidence"]["type"] != "read" for x in g): how = "mixed — see file 4"
        ref = ", ".join(x["id"] for x in g)
        states = sorted({post_state(x) for x in g})
        will = states[0] if len(states) == 1 else "mixed — see file 2"
        L.append(f"| {n} | {cell(what)} | {typ} | {cell(where_text(r, i))} | {blocks_text(i['blocks'])} | {will} | {how} | [#{n}](2-comments-to-post.md#{anchor(n)}) | {ref} |")
    if not groups: L.append("| — | Nothing to post | — | — | — | — | — | — | — |")
    L += ["", "Paste text for each row is in [2-comments-to-post.md](2-comments-to-post.md); open questions (who answers, where to ask) in [3-questions.md](3-questions.md).",
          "Not happy with a comment? `/pr-review adjust <feature> <pr>` and say what to change (drop, reword, add, change blocking). Nothing is posted until `/pr-review post`.", ""]
    sk = skipped(r)
    if sk:
        L += ["## Skipped by you (will not be posted)", "", "| What | Your note | ref |", "|---|---|---|"]
        L += [f"| {cell(i['title'])} | {cell((i.get('user') or {}).get('note') or '—')} | {i['id']} |" for i in sk] + [""]
    posts = r["run"].get("posts") or []
    if posts:
        L += ["## Posted to GitHub", "", "| When | Mode | Comments | Link |", "|---|---|---|---|"]
        L += [f"| {p['at']} | {'draft (pending — submit it in Files changed)' if p['mode'] == 'draft' else 'submitted'} | {len(p.get('items', []))} | {p['url']} |" for p in posts] + [""]
    L += ["## Things you don't need to raise", "", "| Topic | Why it's fine |", "|---|---|"]
    L += [f"| {cell(x['topic'])} | {cell(x['why'])} |" for x in r.get("not_to_raise", [])] or ["| — | — |"]
    L.append("")
    if run.get("recheck_of"):
        ch = [i for i in r["items"] if i.get("previous_status") != i["status"]]
        L += [f"## Changed since the last review (`{run['recheck_of']}`)", "", "| # | What | Before | Now |", "|---|---|---|---|"]
        num = number_of(r)
        for i in ch:
            before = status_text(i["previous_status"]) if i.get("previous_status") else "new"
            L.append(f"| {('#' + str(num[i['id']])) if i['id'] in num else '—'} | {cell(i['title'])} | {before} | {status_text(i['status'])} |")
        if not ch: L.append("| — | Nothing changed | — | — |")
        L.append("")
    L += ["## Read next", "", "| File | Read it when |", "|---|---|",
          "| [1-context.md](1-context.md) | You are new to the PR: problem, before → after diagram, terms |",
          "| [2-comments-to-post.md](2-comments-to-post.md) | You are ready to comment: exact text per row above |",
          "| [3-questions.md](3-questions.md) | You need to know who answers what, and where to ask |",
          "| [4-findings.md](4-findings.md) | You want the evidence behind a point |"]
    if r.get("_has_security"): L.append("| [5-security.md](5-security.md) | You want the attacks tried and what was verified safe |")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- 2-comments-to-post.md
SECTION_TITLES = {
    "A": ("A) Line comments", "Post inline on the changed line (Files changed tab), or let `post` do it."),
    "B": ("B) General PR comments", "Post in the PR conversation (or the review summary); these are not on a changed line."),
    "C": ("C) Ask someone else", "Not for the PR author: ask the named person, in the named place."),
    "D": ("D) Already raised on the PR", "Someone already said this: reply or +1 in that thread instead of a new comment."),
}

PRIORITY_TEXT = {"merge": "1 · Blocks merge", "rollout": "2 · Before rollout", "none": "3 · Non-blocking"}

def quick_index(r, groups):
    """Every numbered comment in one table, sorted by priority (blocks, then severity), with its optional `theme`.
    Items sharing a theme overlap; `duplicate_of` (an item id) marks a near-copy of another comment."""
    if not groups: return []
    num = {i["id"]: n for n, g in groups for i in g}
    theme_of = {n: (g[0].get("theme") or "").strip() for n, g in groups}
    rows = []
    for n, g in groups:
        i = g[0]
        s = section_of(i)
        if i["kind"] == "nit":
            what, typ, sev = f"Small fixes, bundled ({len(g)})", "nit", "trivial"
        else:
            what, typ, sev = i["title"], i["kind"], i["severity"]
        goes = {"A": "Inline", "B": "General comment", "C": f"Ask {i['ask']['who']}", "D": "Reply in existing thread"}[s]
        th = theme_of[n]
        dup = num.get(i.get("duplicate_of") or "")
        related = [m for m, t in theme_of.items() if th and t == th and m not in (n, dup)]
        rel = (f"near-duplicate of [#{dup}](#{anchor(dup)})" + ("; " if related else "") if dup else "") + ", ".join(f"[#{m}](#{anchor(m)})" for m in related)
        rows.append(((BLOCKS_RANK[i["blocks"]], SEV_RANK[sev], n),
                     f"| {PRIORITY_TEXT[i['blocks']]} | [#{n}](#{anchor(n)}) | {cell(what)} | {typ} | {sev} | {cell(th) or '—'} | {rel or '—'} | {goes} |"))
    L = ["## Quick index — by priority", "",
         "Read top to bottom: what blocks the merge first, then what must be settled before rollout, then the rest. "
         "Comments with the same **Theme** overlap, so read them together and consider posting only the strongest one.", "",
         "| Priority | # | Comment | Type | Severity | Theme | Related | Goes to |", "|---|---|---|---|---|---|---|---|"]
    L += [row for _, row in sorted(rows)]
    themes = {}
    for n, t in theme_of.items():
        if t: themes.setdefault(t, []).append(n)
    if themes:
        L += ["", "| Theme | Comments |", "|---|---|"]
        L += [f"| {cell(t)} | {', '.join(f'[#{m}](#{anchor(m)})' for m in sorted(ns))} |" for t, ns in sorted(themes.items(), key=lambda kv: min(kv[1]))]
    return L + [""]

def render_comments(r):
    pr, lang = r["pr"], r["summary"].get("lang", "en")
    groups = numbered(r)
    by = {"A": [], "B": [], "C": [], "D": []}
    for n, g in groups: by[section_of(g[0])].append((n, g))
    also = [(n, g[0], a) for n, g in groups for a in g[0].get("also_ask") or []]
    praise = [i for i in r["items"] if i["kind"] == "praise" and not is_skipped(i)]
    nA, nB = len(by["A"]), len(by["B"])
    nC, nD = len(by["C"]) + len(also), len(by["D"])
    in10 = (f"{nA + nB} comment{'s' if nA + nB != 1 else ''} for @{pr['author']}: {nA} inline, {nB} general"
            + (f"; {nC} to ask someone else" if nC else "") + (f"; {nD} replies in existing threads" if nD else "") + ". "
            "Copy each **Paste this** box, or run `/pr-review post` to post A + B as one draft review only you can see. "
            "To change any of it first: `/pr-review adjust`.")
    L = [f"# PR {pr['number']} — comments to post", "", f"> **In 10 seconds:** {in10}", "",
         "Numbers match the action table in [README.md](README.md). Text in **Why (for you)** is for you, not the author.", ""]
    L += quick_index(r, groups)
    for s in "ABCD":
        extra = [(n, i, a) for n, i, a in also] if s == "C" else []
        if not by[s] and not extra: continue
        t, sub = SECTION_TITLES[s]
        L += [f"## {t}", "", sub, ""]
        for n, g in by[s]:
            i = g[0]
            L.append(f'<a id="{anchor(n)}"></a>')
            if i["kind"] == "nit":
                L += [f"### {n} · nit (non-blocking) · general PR comment", "",
                      "**Why (for you):** small things worth fixing but not worth a thread each; bundled into one comment.", ""]
                for k, x in enumerate(g, 1): L.append(f"- ({k}) {x['why'].strip()}")
                L += ["", "**Paste this:**", "", quote(nit_bundle_text(g, lang)), ""]
                continue
            w = i["where"]
            loc = f"`{base(w['path'])}` {line_label(w)}" if w.get("path") and w.get("line") else (f"`{base(w['path'])}`" if w.get("path") else "whole PR")
            head = {"A": f"inline on {loc}", "B": f"general PR comment · about {loc}" if w.get("path") else "general PR comment",
                    "C": f"ask {i['ask']['who']} · {i['ask']['where']}", "D": "reply in the existing thread"}[s]
            flags = (" · edited by you" if is_edited(i) else "") + (f" · posted {i['posted']['at']}" if is_posted(i) else "")
            L += [f"### {n} · {i['kind']}{decoration(i)} · {head}{flags}", ""]
            if w.get("path"):
                L += [f"**Where:** [`{w['path']}` {line_label(w) if w.get('line') else ''}]({permalink(r, w)})"
                      + ("" if w.get("in_diff") or not w.get("line") else " — not in this PR's diff, so it goes in the general comment"), ""]
            if s == "D": L += [f"**Existing thread:** {i['dup_of_existing_comment']}", ""]
            L += [f"**Why (for you):** {i['why'].strip()}", ""]
            if is_edited(i) and (i.get("user") or {}).get("note"): L += [f"**Your change:** {user_note(r, i, '')}", ""]
            L += ["**Paste this:**" if s != "C" else f"**Say this to {i['ask']['who']}:**", "", quote(paste_text(i) if s != "D" else f"+1 — {i['comment'].strip()}"), ""]
            ch = i.get("change") or {}
            if ch.get("type") in ("suggestion", "diff"): L += [f"<sub>Change checked: {ch.get('checked')}</sub>", ""]
        for n, i, a in extra:
            L += [f"### {n} (also) · ask {a['who']} · {a['where']}", "",
                  f"**Why (for you):** the answer to [#{n}](#{anchor(n)}) depends on {a['who']}, not only on the PR author.", "",
                  f"**Say this to {a['who']}:**", "", quote(a["say"].strip()), ""]
    if praise:
        L += ["## E) Praise (optional)", "", "Goes at the top of the review summary when you post.", ""]
        L += [quote(paste_text(i)) + "\n" for i in praise]
    sk = skipped(r)
    if sk:
        L += ["## Not posting (skipped by you)", ""]
        L += [f"- {i['title']} — your note: {user_note(r, i, 'none')}" for i in sk] + [""]
    if not groups and not praise: L += ["Nothing to post.", ""]
    return "\n".join(L).rstrip() + "\n"


# ---------------------------------------------------------------- 3-questions.md
def in_questions(i):
    return i["kind"] == "question" or i["status"] in ("question", "needs_decision") or i["evidence"]["type"] in ("inferred", "assumption")

def render_questions(r):
    pr = r["pr"]
    num = number_of(r)
    qs = [i for i in r["items"] if in_questions(i)]
    order = {i["id"]: k for k, i in enumerate(r["items"])}
    qs.sort(key=lambda i: (num.get(i["id"], 10 ** 6), order[i["id"]]))
    whos = sorted({i["ask"]["who"] for i in qs} | {a["who"] for i in qs for a in i.get("also_ask") or []})
    in10 = (f"{len(qs)} thing{'s' if len(qs) != 1 else ''} this review could not confirm or needs someone to answer"
            + (f" — answered by: {', '.join(whos)}." if qs else "."))
    L = [f"# PR {pr['number']} — open questions", "", f"> **In 10 seconds:** {in10}", "",
         "| Comment # | What we don't know | Why it matters | How to confirm | Who answers | Where to ask | Comment |",
         "|---|---|---|---|---|---|---|"]
    for i in qs:
        n = num.get(i["id"])
        who = i["ask"]["who"] + "".join(f"; also {a['who']}" for a in i.get("also_ask") or [])
        where = i["ask"]["where"] + "".join(f"; {a['where']}" for a in i.get("also_ask") or [])
        link = f"[#{n}](2-comments-to-post.md#{anchor(n)})" if n else f"— ({status_text(i['status'])}, not posted)"
        L.append(f"| {n or '—'} | {cell(i['unknown'])} | {cell(i['why'])} | {cell(i['confirm_by'])} | {cell(who)} | {cell(where)} | {link} |")
    if not qs: L.append("| — | Nothing open | — | — | — | — | — |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- 4-findings.md regions
def render_regions(r):
    num = number_of(r)
    cov = ["| Dimension | What was checked | Result |", "|---|---|---|"]
    cov += [f"| {cell(c['dimension'])} | {cell(c['checked'])} | {cell(c['result'])} |" for c in r.get("coverage", [])]
    f = ["| # | ID | Kind | Blocks | Sev | Status | Finding | Evidence | Where | Change |", "|---|---|---|---|---|---|---|---|---|---|"]
    for i in r["items"]:
        w, ch = i["where"], i.get("change") or {"type": "none"}
        wl = f"[`{base(w['path'])}` {line_label(w) if w.get('line') else ''}]({permalink(r, w)})" if w.get("path") else "whole PR"
        chs = ch["type"] + (f" ({ch['checked']})" if ch["type"] in ("suggestion", "diff") else "")
        f.append(f"| {num.get(i['id'], '—')} | {i['id']} | {i['kind']} | {i['blocks']} | {i['severity']} | {status_text(i['status'])} | "
                 f"{cell(i['title'])} | {EVIDENCE_TEXT[i['evidence']['type']]}: {cell(i['evidence']['detail'])} | {wl} | {chs} |")
    return {"coverage": "\n".join(cov) + "\n", "findings": "\n".join(f) + "\n"}

def findings_skeleton(r):
    return (f"# PR {r['pr']['number']} — findings (depth)\n\n"
            "> **In 10 seconds:** Every review dimension with what was checked, and every point with its evidence. Internal IDs are used in this file only.\n\n"
            "## Coverage\n\n<!-- rendered:coverage START — edit review.json, then re-run 100x pr_review render -->\n<!-- rendered:coverage END -->\n\n"
            "## All points\n\n<!-- rendered:findings START — edit review.json, then re-run 100x pr_review render -->\n<!-- rendered:findings END -->\n\n"
            "## Evidence notes\n\n<!-- Hand-written. One `### <ID> — <title>` per point that needs more than the table row:"
            " quoted lines, command + output, the example scenario. -->\n")

def apply_regions(text, regions):
    return REGION_RE.sub(lambda m: m.group(1) + regions.get(m.group(2), m.group(3)) + m.group(4), text)


# ---------------------------------------------------------------- github-review.json
def github_review(r, event=None):
    lang = r["summary"].get("lang", "en")
    intro = r["summary"].get("review_intro") or "Thanks for the PR! A few notes below — inline ones are on the changed lines."
    praise = [paste_text(i) for i in r["items"] if i["kind"] == "praise" and not is_skipped(i) and not is_posted(i)]
    inline, general = [], []
    for n, g in numbered(r):
        g = [x for x in g if not is_posted(x)]
        if not g: continue
        i, s = g[0], section_of(g[0])
        if s == "A":
            a, b = lines_of(i["where"])
            c = {"path": i["where"]["path"], "line": b, "side": "RIGHT", "body": paste_text(i)}
            if a != b: c.update(start_line=a, start_side="RIGHT")
            inline.append(c)
        elif s == "B":
            if len(g) > 1 or i["kind"] == "nit": general.append(nit_bundle_text(g, lang)); continue
            w = i["where"]
            head = f"**About `{w['path']}`{(' ' + line_label(w)) if w.get('line') else ''}** (not in this PR's diff)\n\n" if w.get("path") else ""
            general.append(head + paste_text(i))
    body = "\n\n".join([intro] + praise + (["---\n\n" + "\n\n---\n\n".join(general)] if general else []))
    out = {"commit_id": r["pr"]["head_sha"], "body": body, "comments": inline}
    if event: out["event"] = event
    return out


# ---------------------------------------------------------------- entry points
def render_pr(r, has_security=False):
    r = dict(r, _has_security=has_security)
    return {"README.md": render_readme(r), "2-comments-to-post.md": render_comments(r), "3-questions.md": render_questions(r),
            "github-review.json": json.dumps(github_review(r), ensure_ascii=False, indent=2) + "\n"}

def write_pr(pr_dir):
    d = pathlib.Path(pr_dir)
    r = load(d)
    for name, text in render_pr(r, (d / "5-security.md").is_file()).items(): (d / name).write_text(text, encoding="utf-8")
    fpath = d / "4-findings.md"
    base_text = fpath.read_text(encoding="utf-8") if fpath.is_file() else findings_skeleton(r)
    fpath.write_text(apply_regions(base_text, render_regions(r)), encoding="utf-8")
    print(f"rendered {d}: {', '.join(OUTPUTS)} + 4-findings.md regions")

def render_feature(root):
    root = pathlib.Path(root)
    prs = sorted((p for p in root.glob("PR-*/review.json")), key=lambda p: json.loads(p.read_text())["pr"]["number"])
    revs = [(p.parent.name, json.loads(p.read_text(encoding="utf-8"))) for p in prs]
    meta = json.loads((root / "feature.json").read_text(encoding="utf-8")) if (root / "feature.json").is_file() else {}
    title = meta.get("feature", root.name if root.parent.name != "runs" else root.parent.parent.name)
    recs = [r["summary"]["recommendation"] for _, r in revs]
    in10 = f"{len(revs)} PR{'s' if len(revs) != 1 else ''} reviewed: " + ", ".join(
        f"PR {r['pr']['number']} → {REC_TEXT[r['summary']['recommendation']].split(' — ')[0]}" for _, r in revs) + ". Open each PR's README.md first."
    L = [f"# {title} — review", "", f"> **In 10 seconds:** {in10}", ""]
    if meta.get("source"): L += [f"Source: {meta['source']}", ""]
    L += ["| PR | Title | Author | Recommendation | Comments to post | Blocks merge | Blocks rollout | Start here |",
          "|---|---|---|---|---|---|---|---|"]
    for folder, r in revs:
        g = numbered(r)
        bm = sum(1 for _, x in g if x[0]["blocks"] == "merge"); br = sum(1 for _, x in g if x[0]["blocks"] == "rollout")
        L.append(f"| [{r['pr']['number']}]({r['pr']['url']}) | {cell(r['pr']['title'])} | @{r['pr']['author']} | "
                 f"{REC_TEXT[r['summary']['recommendation']].split(' — ')[0]} | {len(g)} | {bm} | {br} | [README]({folder}/README.md) |")
    L += ["", "Pinned SHAs: [PINS.md](PINS.md).", ""]
    if len(revs) >= 2:
        order = meta.get("merge_order") or [r["pr"]["number"] for _, r in revs]
        L += ["## Merge order", "", "```mermaid", "flowchart LR"]
        L += [f"    P{a}[\"PR {a}\"] --> P{b}[\"PR {b}\"]" for a, b in zip(order, order[1:])] or [f"    P{order[0]}[\"PR {order[0]}\"]"]
        L += ["```", "", "**Reading this diagram**", "- A flowchart: each box is a PR, an arrow means \"merge this one first\".",
              "- The order comes from feature.json `merge_order` (else PR number order).", ""]
        cross = [(r, i) for _, r in revs for i in r["items"] if "-X-" in i["id"]]
        L += ["## Cross-PR items", "", "| PR | # | What | Why | Who answers |", "|---|---|---|---|---|"]
        L += [f"| {r['pr']['number']} | {number_of(r).get(i['id'], '—')} | {cell(i['title'])} | {cell(i['why'])} | {cell(i['ask']['who'])} |" for r, i in cross] or ["| — | — | None | — | — |"]
        L.append("")
    return "\n".join(L)

def merge(pr_dir, fragments):
    d = pathlib.Path(pr_dir); r = load(d)
    ids = {i["id"] for i in r["items"]}
    for fp in fragments:
        fr = json.loads(pathlib.Path(fp).read_text(encoding="utf-8"))
        for i in fr.get("items", []):
            if i.get("same_as"):
                print(f"skipped {i['id']}: same as {i['same_as']} — strengthen {i['same_as']} by hand if this one has better evidence/fix"); continue
            if i["id"] in ids: sys.exit(f"duplicate id {i['id']} from {fp}")
            r["items"].append(i); ids.add(i["id"])
        for k in ("not_to_raise", "coverage"): r.setdefault(k, []).extend(fr.get(k, []))
        for a in fr.get("agents", []):
            if a not in r["run"]["agents"]: r["run"]["agents"].append(a)
    (d / "review.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"merged {len(fragments)} fragment(s) into {d / 'review.json'}")

def posting_ids(r):
    """IDs that the next `post` would send: sections A + B (+ praise), not skipped, not yet posted."""
    out = [x["id"] for n, g in numbered(r) for x in g if section_of(x) in "AB" and not is_posted(x)]
    return out + [i["id"] for i in r["items"] if i["kind"] == "praise" and not is_skipped(i) and not is_posted(i)]

def preview(pr_dir):
    r = load(pr_dir)
    ids = set(posting_ids(r))
    print(f"Would post on {r['pr']['url']} @ {r['pr']['head_sha'][:10]} — {len(ids)} item(s)\n")
    for n, g in numbered(r):
        for x in g:
            s = section_of(x)
            tag = "POST " if x["id"] in ids else ("DONE " if is_posted(x) else "HAND ")
            where = f"{x['where']['path']}:{lines_label_short(x['where'])}" if s == "A" else ("general" if s == "B" else f"{x['ask']['who']} · {x['ask']['where']}")
            print(f"{tag} #{n} {x['kind']}{decoration(x)} · {where}{' · edited by you' if is_edited(x) else ''}  [{x['id']}]")
            print(quote(paste_text(x)) + "\n")
    for x in skipped(r): print(f"SKIP  {x['title']}  [{x['id']}] — {(x.get('user') or {}).get('note') or 'no note'}")

def lines_label_short(w):
    a, b = lines_of(w); return f"{a}" if a == b else f"{a}-{b}"

def mark_posted(pr_dir, url, mode):
    if mode not in ("draft", "submit"): sys.exit("mode must be draft or submit")
    d = pathlib.Path(pr_dir); r = load(d)
    if not url.startswith(r["pr"]["url"]): sys.exit(f"review url must be on {r['pr']['url']}")
    ids = posting_ids(r)
    if not ids: sys.exit("nothing to mark: no unposted items")
    rev = github_review(r)      # what was just sent; the summary is kept so a lost draft body can be re-posted
    import datetime
    at = datetime.date.today().isoformat()
    for i in r["items"]:
        if i["id"] in ids: i["posted"] = {"at": at, "mode": mode, "url": url}
    general = [x for x in ids if section_of(next(i for i in r["items"] if i["id"] == x)) != "A"]
    r["run"].setdefault("posts", []).append({"at": at, "mode": mode, "url": url, "items": ids,
                                             "summary_items": general, "summary": rev["body"]})
    (d / "review.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"marked {len(ids)} item(s) posted ({mode}) → {url}")

def followup_text(pr_dir, url):
    """The general comments of an earlier post, as one PR comment — for a draft whose summary was lost on submit."""
    r = load(pr_dir)
    post = next((p for p in r["run"].get("posts", []) if p["url"] == url), None)
    if not post or not post.get("summary_items"): sys.exit("no general comments recorded for that post")
    parts = post["summary"].split("\n\n---\n\n")[1:]
    head = ("レビューのまとめに入らなかった点です:" if r["summary"].get("lang") == "ja"
            else "A few more points from my review that didn't make it into the review summary:")
    print(head + "\n\n---\n\n" + "\n\n---\n\n".join(parts))

BODY_MAX = 3000   # review summary length (chars) above which emit warns; long summaries are hard to read

def emit(pr_dir, mode, body_max=BODY_MAX):
    if mode not in ("draft", "submit"): sys.exit("mode must be draft or submit")
    r = load(pr_dir)
    if not posting_ids(r): print("nothing new to post: every comment is skipped, already posted, or for you to send by hand", file=sys.stderr); sys.exit(3)
    rev = github_review(r, "COMMENT" if mode == "submit" else None)
    print(json.dumps(rev, ensure_ascii=False, indent=2))
    print(f"{'DRAFT (pending, only you see it)' if mode == 'draft' else 'SUBMIT as COMMENT (visible to everyone)'} review on {r['pr']['url']} @ {r['pr']['head_sha'][:10]}", file=sys.stderr)
    for c in rev["comments"]: print(f"  inline  {c['path']}:{c.get('start_line', c['line'])}{'-' + str(c['line']) if 'start_line' in c else ''}  {c['body'].splitlines()[0][:90]}", file=sys.stderr)
    print(f"  body    {len(rev['body'])} chars, {rev['body'].count('---') } general comment(s)", file=sys.stderr)
    if len(rev["body"]) > body_max:
        print(f"  WARN    body is over {body_max} chars: offer to post the general comments as separate PR comments", file=sys.stderr)

# ---------------------------------------------------------------- find · slug · next run · root INDEX.md
PULL_RE = re.compile(r"^(https?://[^/\s]+/[^/\s]+/[^/\s]+/pull/\d+)")

def norm_pr_url(u):
    m = PULL_RE.match(u.strip())
    if not m: sys.exit(f"not a PR URL: {u} (want https://<host>/<owner>/<repo>/pull/<n>)")
    return m.group(1).lower()

def all_reviews(cr):
    """Every v3 review.json under the review root, skipping its _meta/ dir."""
    out = []
    for p in sorted(pathlib.Path(cr).glob("**/review.json")):
        if META_DIR in p.parts: continue
        try: r = json.loads(p.read_text(encoding="utf-8"))
        except ValueError: continue
        out.append((p.parent, r))
    return out

def legacy_folders(cr):
    """Top-level folders that hold reviews in the older formats (no review.json anywhere at their top level)."""
    out = []
    for f in sorted(pathlib.Path(cr).iterdir()):
        if not f.is_dir() or f.name.startswith(("_", ".")): continue
        if any(f.glob("PR-*/review.json")): continue
        if (f / "INDEX.md").is_file() or any(f.glob("PR-*")): out.append(f)
    return out

def find_in_feature(cr, feature, number):
    """`<feature> <pr-number>` form: newest review of PR <number> inside <CR>/<feature>/."""
    f = pathlib.Path(cr) / feature
    if not f.is_dir(): print(f"no folder {f}", file=sys.stderr); sys.exit(1)
    hits = [(d, r) for d, r in all_reviews(cr) if f in d.parents and r["pr"]["number"] == int(number)]
    hits.sort(key=lambda x: (x[1]["run"]["date"], str(x[0])), reverse=True)
    for d, r in hits: print(f"v3\t{d}\t{r['pr']['head_sha']}\t{r['run']['date']}\t{r['pr']['url']}")
    if not hits and any(f.glob(f"**/PR-{number}__*")): print(f"legacy\t{f}")
    sys.exit(0 if hits or any(f.glob(f"**/PR-{number}__*")) else 1)

def find(cr, url):
    want = norm_pr_url(url)
    hits = [(d, r) for d, r in all_reviews(cr) if r["pr"]["url"].lower() == want]
    hits.sort(key=lambda x: (x[1]["run"]["date"], str(x[0])), reverse=True)
    for d, r in hits: print(f"v3\t{d}\t{r['pr']['head_sha']}\t{r['run']['date']}\t{r['pr']['url']}")
    n = want.rsplit("/", 1)[-1]; repo = want.split("/pull/")[0]
    leg = []
    for f in legacy_folders(cr):
        for t in f.rglob("*.md"):
            txt = t.read_text(encoding="utf-8", errors="replace").lower()
            if f"{repo}/pull/{n}" in txt or (f"pr-{n}__" in str(t).lower() and repo.rsplit("/", 1)[-1] in txt):
                leg.append(f); break
    for f in sorted(set(leg)): print(f"legacy\t{f}")
    sys.exit(0 if hits or leg else 1)

def slug(branch):
    last = branch.rstrip("/").rsplit("/", 1)[-1]
    out = re.sub(r"[^a-z0-9]+", "-", last.lower()).strip("-")
    return out or "review"

def next_run(feature_dir):
    import datetime
    today = datetime.date.today().isoformat()
    runs = pathlib.Path(feature_dir) / "runs"
    k, cand = 1, runs / today
    while cand.exists():
        k += 1; cand = runs / f"{today}-{k}"
    print(cand)

def first_line(md):
    for l in md.read_text(encoding="utf-8", errors="replace").splitlines():
        if l.startswith("> **In 10 seconds:**"): return l.split(":**", 1)[1].strip()
    for l in md.read_text(encoding="utf-8", errors="replace").splitlines():
        if l.startswith("# "): return l[2:].strip()
    return ""

def render_index(cr, quiet=False):
    cr = pathlib.Path(cr)
    revs = all_reviews(cr)
    latest = {}
    for d, r in revs:
        k = r["pr"]["url"].lower()
        if k not in latest or (r["run"]["date"], str(d)) > (latest[k][1]["run"]["date"], str(latest[k][0])): latest[k] = (d, r)
    rel = lambda p: p.relative_to(cr).as_posix()
    feat = lambda d: d.relative_to(cr).parts[0]
    L = ["# Code reviews", "",
         f"> **In 10 seconds:** {len(latest)} PR(s) reviewed in the current format, {len(revs)} review run(s) in total. "
         "Start from the PR's latest README. This file is regenerated by `100x pr_review index` after every review, adjust and post — never edit it by hand.", "",
         "## Reviewed PRs (latest review of each)", "",
         "| PR | Title | Author | Feature | Reviewed | Commit | Recommendation | To post | Posted | Skipped by you | Start here |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    rows = sorted(latest.values(), key=lambda x: (x[1]["run"]["date"], x[1]["pr"]["number"]), reverse=True)
    for d, r in rows:
        g = numbered(r)
        topost = sum(1 for _, x in g if section_of(x[0]) in "AB" and not all(is_posted(y) for y in x))
        posted = sum(1 for i in r["items"] if is_posted(i))
        name = r["pr"]["url"].split("/pull/")[0].rsplit("/", 1)[-1]
        L.append(f"| [{name} PR {r['pr']['number']}]({r['pr']['url']}) | {cell(r['pr']['title'])} | @{r['pr']['author']} | {feat(d)} | {r['run']['date']} | "
                 f"`{r['pr']['head_sha'][:8]}` | {REC_TEXT[r['summary']['recommendation']].split(' — ')[0]} | {topost} | {posted} | {len(skipped(r))} | [README]({rel(d)}/README.md) |")
    if not rows: L.append("| — | No reviews yet | — | — | — | — | — | — | — | — | — |")
    L += ["", "## Every review run", "", "| Feature | Run | PR | Commit | Recommendation | README |", "|---|---|---|---|---|---|"]
    for d, r in sorted(revs, key=lambda x: (feat(x[0]), x[1]["run"]["date"], str(x[0])), reverse=True):
        run = d.parent.relative_to(cr / feat(d)).as_posix() if d.parent != cr / feat(d) else "(first review)"
        L.append(f"| {feat(d)} | {run} | {r['pr']['number']} | `{r['pr']['head_sha'][:8]}` | {REC_TEXT[r['summary']['recommendation']].split(' — ')[0]} | [README]({rel(d)}/README.md) |")
    leg = legacy_folders(cr)
    if leg:
        L += ["", "## Older-format reviews (read-only, kept as they were)", "", "| Folder | What | Start here |", "|---|---|---|"]
        for f in leg:
            start = f / "START-HERE.md" if (f / "START-HERE.md").is_file() else f / "INDEX.md"
            L.append(f"| {f.name} | {cell(first_line(start) if start.is_file() else '')} | [{start.name}]({rel(start)}) |" if start.is_file() else f"| {f.name} | — | — |")
    L += ["", "## How to use", "", "| Step | Command |", "|---|---|",
          "| Review (or re-review) a PR | `/pr-review <pr-url>` |", "| Change the comments | `/pr-review adjust <pr-url>` |",
          "| Post them as a draft review | `/pr-review post <pr-url>` |", "", "Rules: the `pr-review` skill (`skills/pr-review/references/rubric.md` in the 100x-engineer plugin).", ""]
    (cr / "INDEX.md").write_text("\n".join(L), encoding="utf-8")
    if not quiet: print(f"rendered {cr / 'INDEX.md'}: {len(latest)} PR(s), {len(revs)} run(s), {len(leg)} older folder(s)")



# ---------------------------------------------------------------- review root (out-dir) · paths
HOME_ENV = "PR_REVIEW_HOME"
OUT_ENV = "PR_REVIEW_OUT"
GIT_CONFIG_KEY = "pr-review.out"
DEFAULT_DIR = "code-review"
META_DIR = "_meta"
META_FILES = ("focus.md", "decisions.md", "settings.json")
REMOTE_RE = re.compile(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", re.I)

def config_home():
    h = os.environ.get(HOME_ENV)
    return pathlib.Path(h).expanduser() if h else pathlib.Path.home() / ".config" / "pr-review"

def git(repo, *args):
    """stdout of a read-only git call, or None when git fails or is missing."""
    try:
        p = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True)
    except OSError:
        return None
    return p.stdout.strip() if p.returncode == 0 else None

def parse_remote(url):
    """(host, owner, repo) from an https / ssh / scp-style remote or PR URL, else None."""
    if not url: return None
    url = url.split("/pull/")[0].strip()
    m = REMOTE_RE.match(url)
    if not m: return None
    parts = [x for x in m.group(2).split("/") if x]
    if len(parts) < 2: return None
    return m.group(1).lower(), "/".join(parts[:-1]), parts[-1]

def main_repo(repo):
    """Top of the main working tree for repo (a worktree resolves to its main repo), or None."""
    common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        common = git(repo, "rev-parse", "--git-common-dir")
        if common and not os.path.isabs(common): common = str(pathlib.Path(repo, common))
    if not common: return None
    common = pathlib.Path(common).resolve()
    if common.name == ".git": return common.parent
    top = git(repo, "rev-parse", "--show-toplevel")
    return pathlib.Path(top).resolve() if top else None

def remote_slug(repo, url):
    """(host, owner, repo) for the PR: --url first, then the repo's remotes."""
    if url:
        s = parse_remote(url)
        if s: return s
    if repo:
        names = (git(repo, "remote") or "").split()
        for name in [n for n in ("upstream", "origin") if n in names] + [n for n in names if n not in ("upstream", "origin")]:
            s = parse_remote(git(repo, "config", "--get", f"remote.{name}.url"))
            if s: return s
    return None

def fallback_cr(slug, name):
    host, owner, repo = slug if slug else ("local", "local", name or "unknown")
    return config_home() / "reviews" / host / owner / repo

def resolve_cr(repo=None, url=None, out=None):
    """(CR, rule) — see the module docstring for the order."""
    if out: return pathlib.Path(out).expanduser().resolve(), "--out"
    if os.environ.get(OUT_ENV): return pathlib.Path(os.environ[OUT_ENV]).expanduser().resolve(), f"env {OUT_ENV}"
    top = main_repo(repo) if repo else None
    if top:
        v = git(top, "config", "--get", GIT_CONFIG_KEY)
        if v:
            p = pathlib.Path(v).expanduser()
            return (p if p.is_absolute() else top / p).resolve(), f"git config {GIT_CONFIG_KEY}"
    cfg = config_home() / "config.json"
    if cfg.is_file():
        try: v = json.loads(cfg.read_text(encoding="utf-8")).get("out")
        except (ValueError, AttributeError): sys.exit(f"pr_review: {cfg} is not a JSON object")
        if v: return pathlib.Path(v).expanduser().resolve(), f"{cfg} out"
    slug = remote_slug(top, url)
    name = slug[2] if slug else (top.name if top else None)
    if not top:
        return fallback_cr(slug, name).resolve(), "no local clone: user fallback"
    parent = top.parent
    if git(parent, "rev-parse", "--is-inside-work-tree") == "true":
        return fallback_cr(slug, name).resolve(), "parent of the repo is inside a git work tree: user fallback"
    return (parent / DEFAULT_DIR / name).resolve(), f"default <parent>/{DEFAULT_DIR}/<repo>"

def paths_info(cr, rule):
    meta = cr / META_DIR
    profile = config_home() / "profile.md"
    return {"cr": str(cr), "meta": str(meta), "profile": str(profile), "source_of_rule": rule,
            "context": str(cr / CONTEXT_FILE), "context_exists": (cr / CONTEXT_FILE).is_file(),
            "meta_files": {n: {"path": str(meta / n), "exists": (meta / n).is_file()} for n in META_FILES},
            "profile_exists": profile.is_file()}

def cmd_out_dir(a, full):
    if a.repo and not pathlib.Path(a.repo).is_dir(): print(f"pr_review: --repo {a.repo} is not a directory", file=sys.stderr); sys.exit(2)
    cr, rule = resolve_cr(a.repo, a.url, a.out)
    if getattr(a, "ensure", False): scaffold(cr, a.repo, a.url)
    info = paths_info(cr, rule)
    if a.json:
        if not full: info = {k: info[k] for k in ("cr", "meta", "profile", "source_of_rule")}
        print(json.dumps(info, indent=2))
    elif full:
        print(f"cr\t{info['cr']}\nmeta\t{info['meta']}\nprofile\t{info['profile']}\nrule\t{rule}")
    else:
        print(cr)


# ---------------------------------------------------------------- init · CONTEXT.md
CONTEXT_FILE = "CONTEXT.md"
AUTO_START, AUTO_END = "<!-- auto:start -->", "<!-- auto:end -->"
AUTO_RE = re.compile(re.escape(AUTO_START) + r"\n.*?" + re.escape(AUTO_END), re.S)
# (manifest file name, what it says about the stack); looked for at the top level and one level down
STACK_SIGNALS = (
    ("package.json", "Node.js / JavaScript"), ("tsconfig.json", "TypeScript"),
    ("pnpm-lock.yaml", "pnpm"), ("package-lock.json", "npm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"),
    ("Gemfile", "Ruby (bundler)"), ("go.mod", "Go"), ("pyproject.toml", "Python (pyproject)"),
    ("requirements.txt", "Python (pip)"), ("uv.lock", "Python (uv)"), ("poetry.lock", "Python (poetry)"),
    ("Cargo.toml", "Rust"), ("build.gradle", "Gradle"), ("build.gradle.kts", "Gradle (Kotlin DSL)"),
    ("pom.xml", "Maven"), ("composer.json", "PHP (composer)"), ("mix.exs", "Elixir"),
    ("pubspec.yaml", "Dart / Flutter"), ("Package.swift", "Swift"), ("Dockerfile", "Docker"),
    ("docker-compose.yml", "Docker Compose"), ("compose.yaml", "Docker Compose"), ("Makefile", "make"),
)
CONVENTION_GLOBS = ("CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md", ".github/copilot-instructions.md",
                    ".github/skills/*/SKILL.md", ".claude/skills/*/SKILL.md", "CONTRIBUTING.md", ".github/CONTRIBUTING.md",
                    ".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md", ".github/PULL_REQUEST_TEMPLATE/*.md",
                    "pull_request_template.md", "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
FOCUS_STUB = """# Focus — this repo

Repo-specific review checklist, added on top of the plugin's generic one
(`skills/pr-review/references/focus-generic.md`). One line per bug class a review of THIS repo
found; name the module, key or convention it concerns. Lines here win over the generic ones.

## Backend

## Frontend

## Spec / PRD

## PR hygiene
"""
DECISIONS_STUB = """# Team decisions

Decisions and accepted gaps reviewers must respect (they go to `not_to_raise`, not to comments).

| Date | Decision | Source | Applies to |
|---|---|---|---|
"""

def main_branch_of(top):
    remote = None
    names = (git(top, "remote") or "").split()
    for n in ("upstream", "origin") + tuple(names):
        if n in names: remote = n; break
    if not remote: return None, None
    ref = git(top, "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
    return remote, (ref.split("/", 1)[1] if ref else None)

def cell_list(xs): return ", ".join(f"`{x}`" for x in xs) if xs else "—"

def context_auto(top, url):
    """The two mechanical blocks of CONTEXT.md: (identity…related repos, last refreshed)."""
    slug = remote_slug(top, url)
    host, owner, repo = slug if slug else ("—", "—", top.name if top else "—")
    L = ["## Identity", "", "| Field | Value |", "|---|---|", f"| Host | {host} |", f"| Owner / repo | {owner}/{repo} |"]
    if not top:
        L += ["| Local path | — (no local clone) |", ""]
        return "\n".join(L + ["## Stack", "", "—", "", "## Layout", "", "—", "", "## Conventions sources", "", "—", "",
                              "## Related repos", "", "—"]), f"{datetime_today()} · no local clone"
    remote, default = main_branch_of(top)
    L += [f"| Remote | {remote or '—'} {cell(git(top, 'remote', 'get-url', remote) if remote else '')} |",
          f"| Default branch | {default or '— (no <remote>/HEAD; run `git remote set-head <remote> -a`)'} |",
          f"| Local path | `{top}` |", ""]
    stack = []
    for d in [top] + sorted(x for x in top.iterdir() if x.is_dir() and not x.name.startswith(".") and x.name != "node_modules"):
        found = [label for name, label in STACK_SIGNALS if (d / name).is_file()]
        if found: stack.append((("." if d == top else d.name + "/"), found))
    L += ["## Stack", "", "| Where | Detected from manifests |", "|---|---|"]
    L += [f"| `{w}` | {', '.join(f)} |" for w, f in stack] or ["| — | nothing recognised |"]
    dirs = sorted(x.name + "/" for x in top.iterdir() if x.is_dir() and not x.name.startswith("."))
    L += ["", "## Layout", "", f"Top-level dirs: {cell_list(dirs)}", "", "## Conventions sources", ""]
    conv = sorted({p.relative_to(top).as_posix() for g in CONVENTION_GLOBS for p in top.glob(g) if p.is_file()})
    L += [f"- `{c}`" for c in conv] or ["None found."]
    L += ["", "## Related repos", "", "Siblings under the same parent whose remote has the same owner:", ""]
    rel = []
    for sib in sorted(top.parent.iterdir()):
        if sib == top or not sib.is_dir() or not (sib / ".git").exists(): continue
        s = remote_slug(sib, None)
        if s and slug and s[0] == host and s[1] == owner: rel.append(f"- `{sib.name}` → {s[0]}/{s[1]}/{s[2]}")
    L += rel or ["None found."]
    head = git(top, "rev-parse", "HEAD") or "no commits"
    return "\n".join(L), f"{datetime_today()} · HEAD `{head}`"

def datetime_today():
    import datetime
    return datetime.date.today().isoformat()

def context_text(top, url):
    a, b = context_auto(top, url)
    name = (remote_slug(top, url) or (None, None, top.name if top else "repo"))[2]
    return "\n".join([f"# Repo context — {name}", "",
        "Read by every pr-review agent before reviewing this repo. Blocks between auto markers are",
        "regenerated by `100x pr_review context --refresh <CR>`; everything else is yours to edit.", "",
        AUTO_START, a, AUTO_END, "",
        "## Review rubric / severity labels", "",
        "<!-- fill: the labels this team uses on PR comments (e.g. must / should / nit) and how they map to the rubric's blocks merge / rollout / none -->", "",
        "## Team decisions", "",
        f"Recorded in [{META_DIR}/decisions.md]({META_DIR}/decisions.md). Summarise the ones every review must know here.", "",
        "<!-- fill: the 3-5 decisions or accepted gaps a reviewer would otherwise flag -->", "",
        "## Last refreshed", "",
        AUTO_START, b, AUTO_END, ""])

def write_new(path, text):
    """Create path with text unless it exists. True when written."""
    if path.exists(): return False
    path.write_text(text, encoding="utf-8")
    return True

def scaffold(cr, repo, url):
    """Idempotent: creates CR, its _meta stubs, CONTEXT.md and INDEX.md; never overwrites a file."""
    top = main_repo(repo) if repo else None
    meta = cr / META_DIR
    meta.mkdir(parents=True, exist_ok=True)
    made = [n for n, txt in ((meta / "focus.md", FOCUS_STUB), (meta / "decisions.md", DECISIONS_STUB),
                             (meta / "settings.json", "{}\n"), (cr / CONTEXT_FILE, context_text(top, url)))
            if write_new(n, txt)]
    if not (cr / "INDEX.md").exists(): render_index(cr, quiet=True); made.append(cr / "INDEX.md")
    return made

def cmd_init(a):
    if a.repo and not pathlib.Path(a.repo).is_dir(): print(f"pr_review: --repo {a.repo} is not a directory", file=sys.stderr); sys.exit(2)
    cr, rule = resolve_cr(a.repo, a.url, a.out)
    made = scaffold(cr, a.repo, a.url)
    if a.json:
        info = paths_info(cr, rule); info["created"] = [str(m) for m in made]
        print(json.dumps(info, indent=2))
    else:
        for m in made: print(f"created {m}")
        print(f"{cr} ready ({len(made)} file(s) created, existing files left untouched)")

def local_path_of(text):
    m = re.search(r"^\| Local path \| `([^`]+)` \|$", text, re.M)
    return m.group(1) if m else None

def cmd_context(a):
    cr = pathlib.Path(a.cr).resolve()
    f = cr / CONTEXT_FILE
    if not f.is_file(): sys.exit(f"pr_review: no {f} -- run `pr_review.py init` first")
    text = f.read_text(encoding="utf-8")
    blocks = AUTO_RE.findall(text)
    if len(blocks) != 2: sys.exit(f"pr_review: {f} has {len(blocks)} auto block(s), want 2 -- restore the {AUTO_START}/{AUTO_END} markers")
    repo = a.repo or local_path_of(text)
    if repo and not pathlib.Path(repo).is_dir(): sys.exit(f"pr_review: repo {repo} not found -- pass --repo")
    top = main_repo(repo) if repo else None
    new = iter(context_auto(top, a.url))
    out = AUTO_RE.sub(lambda m: f"{AUTO_START}\n{next(new)}\n{AUTO_END}", text)
    if out != text: f.write_text(out, encoding="utf-8")
    print(f"refreshed {f}" if out != text else f"{f} already current")


def render_target(p):
    p = pathlib.Path(p)
    if p.is_file() and p.name == "review.json": p = p.parent
    if not (p / "review.json").is_file(): sys.exit(f"pr_review: no review.json in {p}")
    write_pr(p)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="pr_review.py", description=__doc__.split("\n\n")[0],
                                 epilog="See the module docstring for the review-root order.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", metavar="<subcommand>")
    for name, hlp in (("out-dir", "print the per-repo review root CR"), ("paths", "print CR, its _meta dir, CONTEXT.md and the user profile path"),
                      ("init", "scaffold CR: CONTEXT.md, INDEX.md, _meta/ stubs (never overwrites)")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("--repo", help="local clone (a worktree is fine)")
        s.add_argument("--url", help="PR URL; names the repo when there is no clone")
        s.add_argument("--out", help="explicit review root")
        s.add_argument("--json", action="store_true")
        if name == "out-dir": s.add_argument("--ensure", action="store_true", help="also run init")
    s = sub.add_parser("context", help="regenerate the auto blocks of <CR>/CONTEXT.md")
    s.add_argument("--refresh", required=True, metavar="CR", dest="cr")
    s.add_argument("--repo", help="clone to read (default: the Local path recorded in CONTEXT.md)")
    s.add_argument("--url", help="PR URL; names the repo when there is no clone")
    s = sub.add_parser("render", help="render the files next to review.json"); s.add_argument("target")
    s = sub.add_parser("feature", help="render <run-root>/README.md"); s.add_argument("run_root")
    s = sub.add_parser("merge", help="merge agent fragments into review.json"); s.add_argument("pr_dir"); s.add_argument("fragments", nargs="+")
    s = sub.add_parser("emit", help="print the GitHub review payload"); s.add_argument("pr_dir"); s.add_argument("mode", choices=("draft", "submit"))
    s.add_argument("--body-max", type=int, default=BODY_MAX, help=f"warn when the summary is longer (default {BODY_MAX})")
    s = sub.add_parser("preview", help="print what post would send"); s.add_argument("pr_dir")
    s = sub.add_parser("mark-posted", help="record a successful post"); s.add_argument("pr_dir"); s.add_argument("url"); s.add_argument("mode", choices=("draft", "submit"))
    s = sub.add_parser("followup-text", help="general comments of a post as one PR comment"); s.add_argument("pr_dir"); s.add_argument("url")
    s = sub.add_parser("find", help="earlier reviews of a PR"); s.add_argument("cr"); s.add_argument("args", nargs="+", metavar="pr-url | folder n")
    s = sub.add_parser("slug", help="feature folder name from a head branch"); s.add_argument("branch")
    s = sub.add_parser("next-run", help="run root for a re-review"); s.add_argument("feature_dir")
    s = sub.add_parser("index", help="rebuild <CR>/INDEX.md"); s.add_argument("cr")
    a = ap.parse_args(argv)
    if a.cmd is None: ap.print_help(sys.stderr); return 2
    if a.cmd in ("out-dir", "paths"): cmd_out_dir(a, a.cmd == "paths")
    elif a.cmd == "init": cmd_init(a)
    elif a.cmd == "context": cmd_context(a)
    elif a.cmd == "render": render_target(a.target)
    elif a.cmd == "feature":
        (pathlib.Path(a.run_root) / "README.md").write_text(render_feature(a.run_root), encoding="utf-8"); print(f"rendered {a.run_root}/README.md")
    elif a.cmd == "merge": merge(a.pr_dir, a.fragments)
    elif a.cmd == "emit": emit(a.pr_dir, a.mode, a.body_max)
    elif a.cmd == "preview": preview(a.pr_dir)
    elif a.cmd == "mark-posted": mark_posted(a.pr_dir, a.url, a.mode)
    elif a.cmd == "followup-text": followup_text(a.pr_dir, a.url)
    elif a.cmd == "find":
        if not pathlib.Path(a.cr).is_dir(): print(f"no review root {a.cr}", file=sys.stderr); return 1
        if len(a.args) == 1: find(a.cr, a.args[0])
        elif len(a.args) == 2: find_in_feature(a.cr, a.args[0], a.args[1])
        else: ap.error("find takes <pr-url> or <folder> <pr-number>")
    elif a.cmd == "slug": print(slug(a.branch))
    elif a.cmd == "next-run": next_run(a.feature_dir)
    elif a.cmd == "index":
        if not pathlib.Path(a.cr).is_dir(): sys.exit(f"pr_review: {a.cr} is not a directory")
        render_index(a.cr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
