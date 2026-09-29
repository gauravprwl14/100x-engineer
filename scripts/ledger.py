#!/usr/bin/env python3
"""One index over every engineering record, and the traceability between them.

The problem this solves is growth. A flat `decisions/` directory is fine at 10
records and unusable at 300: nobody browses it, so nobody reads it, so writing to it
stops paying. Three mechanisms keep it traversable:

  1. TYPED records with stable, prefixed, monotonic ids (ADR-0007, RCA-0002). The id
     lives in the filename, so it is greppable and a link to it never breaks.
  2. DATE SHARDING once a type exceeds a threshold: records move to YYYY/QN/ and the
     master index links to per-shard indexes instead of listing every record. The id
     does not change, so nothing that referenced it breaks.
  3. A TRACEABILITY MAP answering the question that actually gets asked -- "is there a
     decision behind this spec?" -- rather than only "what records exist".

    ledger.py index          # regenerate ledger/INDEX.md
    ledger.py map            # regenerate ledger/MAP.md (the traceability matrix)
    ledger.py gaps           # audit linkage; exit 1 on problems
    ledger.py find <term>    # search titles, ids and bodies across every type
    ledger.py shard          # move oversized directories into YYYY/QN/
    ledger.py stats          # volume over time
    ledger.py check          # index + map + gaps, for CI

Python stdlib only.
"""
import argparse, collections, datetime, json, pathlib, re, subprocess, sys
import _mutation_guard as mg

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
META_RX = re.compile(r"```json meta\s*\n(.*?)\n```", re.S)
SHARD_THRESHOLD = 40          # records per directory before sharding kicks in


def project_root():
    """Returns (root, in_git_repo); see plan_feature.py's project_root for why."""
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return pathlib.Path(r.stdout.strip()), True
    return pathlib.Path.cwd(), False


ROOT, IN_GIT_REPO = project_root()
LEDGER = ROOT / "ledger"


def rel(p):
    try:
        return pathlib.Path(p).resolve().relative_to(ROOT.resolve())
    except Exception:
        return pathlib.Path(p)


# type -> (directory, filename glob, id prefix, what it records)
TYPES = {
    "prd":      ("prds",      "*/prd.md",   "PRD", "why we are building it"),
    "spec":     ("specs",     "*/spec.md",  "SPEC", "what we are building"),
    "decision": ("decisions", "ADR-*.md",   "ADR", "why it is built this way"),
    "rca":      ("rca",       "RCA-*.md",   "RCA", "why it broke"),
    "review":   ("reviews",   "REV-*.md",   "REV", "what a review concluded"),
    "lesson":   ("lessons",   "LESSON-*.md", "LESSON", "what we learned and would repeat or avoid"),
}


def discover():
    """Find every record of every type, including inside date shards."""
    out = []
    for kind, (d, glob, prefix, _) in TYPES.items():
        base = ROOT / d
        if not base.exists():
            continue
        seen = set()
        for pat in (glob, f"*/*/{glob}", f"*/*/*/{glob}"):
            for p in base.glob(pat):
                if not p.is_file() or p.resolve() in seen:
                    continue
                if p.name in ("INDEX.md", "ARCHIVE.md"):
                    continue
                seen.add(p.resolve())
                out.append(parse(kind, p))
    return out


def parse(kind, path):
    text = path.read_text(errors="replace")
    meta = {}
    m = META_RX.search(text)
    if m:
        try:
            meta = json.loads(m.group(1))
        except Exception:
            meta = {"_meta_error": "invalid JSON in meta block"}
    rec = {"kind": kind, "path": path, "text": text, **meta}
    if not rec.get("id"):
        mm = re.match(r"([A-Z]+-\d+)", path.name)
        rec["id"] = mm.group(1) if mm else path.parent.name
    if not rec.get("title"):
        h = re.search(r"^#\s+(.+)$", text, re.M)
        rec["title"] = (h.group(1) if h else path.stem).strip()
        rec["title"] = re.sub(r"^[A-Z]+-\d+:\s*", "", rec["title"])
    if not rec.get("date"):
        fm = re.search(r"\|\s*created\s*\|\s*([\d-]+)\s*\|", text)
        rec["date"] = fm.group(1) if fm else ""
    if not rec.get("status"):
        sm = re.search(r"\|\s*status\s*\|\s*\*{0,2}([\w -]+)", text)
        rec["status"] = (sm.group(1).strip() if sm else "")
    return rec


def feature_of(rec):
    """The feature a record belongs to: the directory name for prd/spec, otherwise
    inferred from explicit links, then tags, then the affects globs."""
    if rec["kind"] in ("prd", "spec"):
        return rec["path"].parent.name
    links = rec.get("links") or {}
    for key in ("feature", "spec", "prd"):
        if links.get(key):
            return str(links[key]).strip("/").split("/")[-1].replace(".md", "")
    for t in rec.get("tags") or []:
        if (ROOT / "specs" / t).exists():
            return t
    for g in rec.get("affects") or []:
        seg = [s for s in g.split("/") if s and "*" not in s]
        if seg:
            return seg[-1]
    return ""


def cmd_index(a):
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "ledger.py index", ROOT):
        return 2
    recs = discover()
    if not dry:
        LEDGER.mkdir(parents=True, exist_ok=True)
    by = collections.defaultdict(list)
    for r in recs:
        by[r["kind"]].append(r)
    o = ["# Engineering ledger", "",
         f"Every engineering record in this repository. Regenerated by "
         f"`python3 scripts/ledger.py index` — do not edit by hand.", "",
         "| type | records | what it answers | where |", "|---|--:|---|---|"]
    for kind, (d, _, _, answers) in TYPES.items():
        o.append(f"| {kind} | {len(by[kind])} | {answers} | `{d}/` |")
    o += [f"| **total** | **{len(recs)}** | | |", ""]

    for kind, (d, _, _, _) in TYPES.items():
        rows = sorted(by[kind], key=lambda r: (r.get("date") or "", r["id"]), reverse=True)
        if not rows:
            continue
        o += [f"## {kind} ({len(rows)})", ""]
        if len(rows) > SHARD_THRESHOLD:
            o += [f"Over {SHARD_THRESHOLD} records — run `ledger.py shard` to split by "
                  f"quarter. Showing the 25 most recent; the rest are in the per-shard "
                  f"indexes under `{d}/`.", ""]
            rows = rows[:25]
        o += ["| id | title | status | date | feature |", "|---|---|---|---|---|"]
        for r in rows:
            o.append(f"| [{r['id']}]({rel(r['path'])}) | {r['title'][:60]} | "
                     f"{r.get('status','') or '—'} | {r.get('date','') or '—'} | "
                     f"{feature_of(r) or '—'} |")
        o.append("")
    o += ["## Traversal", "",
          "- `ledger.py find <term>` — search every record",
          "- `ledger.py map` — which features have which records (`ledger/MAP.md`)",
          "- `ledger.py gaps` — records that should exist and do not",
          "- `decide.py trace <path>` — which decision governs a file", ""]
    new_text = "\n".join(o)
    if dry:
        old_text = (LEDGER / "INDEX.md").read_text() if (LEDGER / "INDEX.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, "ledger/INDEX.md")
        return 0
    (LEDGER / "INDEX.md").write_text(new_text)
    print(f"wrote ledger/INDEX.md ({len(recs)} records across {len(by)} type(s))")
    return 0


def cmd_map(a):
    """The traceability matrix. Answers: does this spec have a decision behind it?"""
    dry = getattr(a, "dry_run", False)
    if not dry and mg.require_git_root(IN_GIT_REPO, "ledger.py map", ROOT):
        return 2
    recs = discover()
    feats = collections.defaultdict(lambda: collections.defaultdict(list))
    orphans = []
    for r in recs:
        f = feature_of(r)
        if f:
            feats[f][r["kind"]].append(r)
        else:
            orphans.append(r)
    if not dry:
        LEDGER.mkdir(parents=True, exist_ok=True)
    o = ["# Traceability map", "",
         "Which records exist per feature. Regenerated by `python3 scripts/ledger.py map`.",
         "", "A blank cell is not automatically wrong — a small change needs no PRD. It "
         "is a question worth being able to ask.", "",
         "| feature | PRD | spec | decisions | RCA | reviews |", "|---|---|---|---|---|---|"]
    for f in sorted(feats):
        c = feats[f]
        def cell(kind):
            rs = c.get(kind) or []
            if not rs:
                return "—"
            return ", ".join(f"[{x['id']}]({rel(x['path'])})" for x in rs[:4]) + \
                   (f" +{len(rs)-4}" if len(rs) > 4 else "")
        o.append(f"| **{f}** | {cell('prd')} | {cell('spec')} | {cell('decision')} | "
                 f"{cell('rca')} | {cell('review')} |")
    o.append("")
    if orphans:
        o += ["## Records not attached to a feature", "",
              "These carry no `links.feature`, no tag matching a spec, and no `affects` "
              "glob that resolves to one. They are findable by id but not by feature.", "",
              "| id | kind | title |", "|---|---|---|"]
        for r in sorted(orphans, key=lambda x: x["id"]):
            o.append(f"| [{r['id']}]({rel(r['path'])}) | {r['kind']} | {r['title'][:60]} |")
        o.append("")
    new_text = "\n".join(o)
    if dry:
        old_text = (LEDGER / "MAP.md").read_text() if (LEDGER / "MAP.md").exists() else ""
        mg.print_diff_or_noop(old_text, new_text, "ledger/MAP.md")
        return 0
    (LEDGER / "MAP.md").write_text(new_text)
    print(f"wrote ledger/MAP.md ({len(feats)} feature(s), {len(orphans)} unattached)")
    return 0


def cmd_gaps(a):
    recs = discover()
    by_kind = collections.defaultdict(list)
    feats = collections.defaultdict(lambda: collections.defaultdict(list))
    problems = []
    for r in recs:
        by_kind[r["kind"]].append(r)
        f = feature_of(r)
        if f:
            feats[f][r["kind"]].append(r)
        if r.get("_meta_error"):
            problems.append(("ERROR", r["id"], r["_meta_error"]))

    for f, c in sorted(feats.items()):
        if c.get("spec") and not c.get("decision"):
            problems.append(("WARN", f, "spec with no decision record — if no non-obvious "
                                        "choice was made, say so; otherwise the reasoning "
                                        "is undocumented"))
        if c.get("prd") and not c.get("spec"):
            problems.append(("WARN", f, "PRD with no spec — nothing turns it into work"))
        if c.get("rca") and not c.get("decision"):
            problems.append(("WARN", f, "RCA with no linked decision — if an assumption "
                                        "was violated, link it"))
    for r in by_kind["decision"]:
        if not (r.get("affects") or (r.get("links") or {}).get("feature")):
            problems.append(("WARN", r["id"], "decision with no `affects` glob and no "
                                              "linked feature — unreachable from the code"))
    for kind, (d, _, _, _) in TYPES.items():
        base = ROOT / d
        if base.exists():
            flat = [p for p in base.glob(TYPES[kind][1]) if p.is_file()]
            if len(flat) > SHARD_THRESHOLD:
                problems.append(("WARN", d, f"{len(flat)} records in one directory "
                                            f"(threshold {SHARD_THRESHOLD}) — run "
                                            f"`ledger.py shard`"))
    errs = sum(1 for p in problems if p[0] == "ERROR")
    print(f"ledger gaps: {len(recs)} record(s), {len(problems)} finding(s)")
    for sev, who, msg in problems:
        print(f"  [{sev:5s}] {who}: {msg}")
    if not problems:
        print("  no linkage gaps")
    return 1 if (errs or problems) else 0


def cmd_find(a):
    recs = discover()
    term = a.term.lower()
    hits = []
    for r in recs:
        score = 0
        if term in r["id"].lower():
            score += 10
        if term in r["title"].lower():
            score += 5
        body = r["text"].lower()
        score += min(body.count(term), 5)
        if score:
            hits.append((score, r))
    hits.sort(key=lambda x: -x[0])
    if not hits:
        print(f"no record mentions {a.term!r}")
        return 0
    print(f"{len(hits)} record(s) mention {a.term!r}:\n")
    for score, r in hits[:a.limit]:
        print(f"  [{r['kind']:8s}] {r['id']:10s} {r['title'][:54]}")
        print(f"             {rel(r['path'])}")
        for line in r["text"].splitlines():
            if term in line.lower():
                print(f"             … {line.strip()[:92]}")
                break
    return 0


def cmd_shard(a):
    """Move records into YYYY/QN/ once a directory exceeds the threshold.

    MOVES FILES, so it prints a plan and does nothing without --yes. Under
    `--dangerously-skip-permissions` nothing else would ask, and a silent file move is
    precisely the surprise this plugin must not spring on anyone.
    """
    plan, moved = [], 0
    for kind, (d, glob, _, _) in TYPES.items():
        if kind in ("prd", "spec"):
            continue
        base = ROOT / d
        if not base.exists():
            continue
        flat = sorted(p_ for p_ in base.glob(glob) if p_.is_file())
        if len(flat) <= SHARD_THRESHOLD and not a.force:
            continue
        for p_ in flat:
            rec = parse(kind, p_)
            try:
                dt = datetime.date.fromisoformat((rec.get("date") or "")[:10])
            except Exception:
                dt = datetime.date.today()
            plan.append((p_, base / f"{dt.year}" / f"Q{(dt.month - 1) // 3 + 1}" / p_.name))
    if not plan:
        print(f"ledger shard: nothing to shard (threshold {SHARD_THRESHOLD}; "
              f"use --force to shard anyway)")
        return 0
    if not getattr(a, "yes", False):
        print(f"ledger shard: would move {len(plan)} record(s). Nothing has changed.\n")
        for src, dst in plan[:12]:
            print(f"  {rel(src)}  ->  {rel(dst)}")
        if len(plan) > 12:
            print(f"  ... {len(plan) - 12} more")
        print(f"\nIds are in the filenames and do not change, so links keep working.")
        print(f"Re-run with --yes to perform the move.")
        return 0
    for src, dst in plan:
        if dst.resolve() == src.resolve():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "mv", str(src), str(dst)], cwd=ROOT,
                           capture_output=True)
        if r.returncode != 0:             # untracked by git: move it directly
            src.rename(dst)
        moved += 1
    for kind, (d, glob, _, _) in TYPES.items():
        if kind in ("prd", "spec"):
            continue
        base = ROOT / d
        if not base.exists():
            continue
        for shard in sorted(base.glob("*/Q*")):
            rows = sorted(x for x in shard.glob("*.md") if x.name != "INDEX.md")
            (shard / "INDEX.md").write_text(
                f"# {d} — {shard.parent.name} {shard.name}\n\n"
                f"{len(rows)} record(s). The master index at `ledger/INDEX.md` links "
                f"here rather than listing every record.\n\n"
                + "\n".join(f"- [{x.stem}]({x.name})" for x in rows) + "\n")
    print(f"ledger shard: moved {moved} record(s) into YYYY/QN shards"
          if moved else "ledger shard: nothing to shard "
                        f"(threshold {SHARD_THRESHOLD}; use --force to shard anyway)")
    if moved:
        cmd_index(a); cmd_map(a)
    return 0


def cmd_stats(a):
    recs = discover()
    per = collections.Counter()
    for r in recs:
        d = (r.get("date") or "")[:7] or "undated"
        per[d] += 1
    print(f"{len(recs)} record(s) total\n")
    print("| month | records |")
    print("|---|--:|")
    for k in sorted(per):
        print(f"| {k} | {per[k]} |")
    print(f"\nsharding threshold: {SHARD_THRESHOLD} records per directory")
    return 0


def cmd_check(a):
    rc = 0
    print("=== index ==="); rc |= cmd_index(a)
    print("\n=== map ===");  rc |= cmd_map(a)
    print("\n=== gaps ==="); rc |= cmd_gaps(a)
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n, fn in (("index", cmd_index), ("map", cmd_map), ("gaps", cmd_gaps),
                  ("stats", cmd_stats), ("check", cmd_check)):
        sub.add_parser(n).set_defaults(fn=fn)
    f = sub.add_parser("find"); f.add_argument("term")
    f.add_argument("--limit", type=int, default=10); f.set_defaults(fn=cmd_find)
    sh = sub.add_parser("shard")
    sh.add_argument("--force", action="store_true",
                    help="shard even below the threshold")
    sh.add_argument("--yes", action="store_true",
                    help="actually move the files; without it a plan is printed only")
    sh.set_defaults(fn=cmd_shard)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
