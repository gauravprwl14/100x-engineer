#!/usr/bin/env python3
"""Stage B+C via GraphQL: activity gates + targeted directory probes.

Why GraphQL: separate rate-limit pool from REST core, and ~1 point per repo
vs 4 REST calls. Checkpoints every batch so a quota wall never loses work.
"""
import json, os, sys, time, datetime, pathlib, urllib.request, urllib.error

# One-shot research-pipeline scripts with module-level execution: importing them, or
# passing --help, would otherwise start a live GitHub harvest. Answer --help from the
# docstring before any of that runs.
import sys as _sys
if __name__ != "__main__" or any(a in ("--help", "-h") for a in _sys.argv[1:]):
    print(__doc__ or __file__)
    raise SystemExit(0)


OUT = pathlib.Path("research/raw"); OUT.mkdir(parents=True, exist_ok=True)
CKPT = OUT / "gql_partial.json"
TOKEN = os.popen("gh auth token").read().strip()
SINCE = (datetime.date.today() - datetime.timedelta(days=365)).isoformat() + "T00:00:00Z"
BATCH = 3

DIRS = {
 "root": "", "gh": ".github", "ghwf": ".github/workflows",
 "claude": ".claude", "claude_skills": ".claude/skills", "claude_agents": ".claude/agents",
 "claude_cmds": ".claude/commands", "claude_hooks": ".claude/hooks",
 "agents_dir": ".agents", "cursor_rules": ".cursor/rules",
 "docs_adr": "docs/adr", "rfcs": "rfcs",
 "tests": "tests", "test": "test", "e2e": "e2e", "fuzz": "fuzz",
 "changeset": ".changeset", "husky": ".husky", "migrations": "migrations",
}

FIELDS = """
    nameWithOwner stargazerCount forkCount pushedAt createdAt isArchived isFork
    diskUsage description homepageUrl
    licenseInfo { spdxId } primaryLanguage { name }
    repositoryTopics(first:15){ nodes { topic { name } } }
    releases { totalCount } latestRelease { publishedAt tagName }
    issues(states:OPEN){ totalCount }
    pullRequests(states:OPEN){ totalCount }
    defaultBranchRef { name target { ... on Commit {
      history(since:$since){ totalCount }
      recent: history(first:100){ nodes { author { user { login } } } } } } }
"""


def build(batch):
    parts = ["fragment T on Tree { entries { name type } }",
             "query($since:GitTimestamp!) {", "rateLimit { cost remaining resetAt }"]
    for i, r in enumerate(batch):
        o, n = r["owner"], r["name"]
        probes = " ".join(
            f'{a}: object(expression:"HEAD:{p}"){{ ...T }}' for a, p in DIRS.items())
        parts.append(f'r{i}: repository(owner:"{o}", name:"{n}") {{ {FIELDS} {probes} }}')
    parts.append("}")
    return "\n".join(parts)


def post(query, retries=4):
    body = json.dumps({"query": query, "variables": {"since": SINCE}}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request("https://api.github.com/graphql", data=body,
                headers={"Authorization": f"Bearer {TOKEN}",
                         "Content-Type": "application/json", "User-Agent": "100x-research"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            ra = e.headers.get("Retry-After")
            wait = int(ra) if ra and ra.isdigit() else min(60, 5 * (a + 1) ** 2)
            print(f"    HTTP {e.code}; sleeping {wait}s", flush=True)
            time.sleep(wait)
        except Exception as ex:
            print(f"    {type(ex).__name__}; sleeping 10s", flush=True)
            time.sleep(10)
    return None


def flatten(r):
    """Turn the GraphQL repo node into flat fields + a path list for signal matching."""
    out = {
      "full_name": r.get("nameWithOwner"),
      "stars": r.get("stargazerCount"), "forks": r.get("forkCount"),
      "pushed_at": r.get("pushedAt"), "created_at": r.get("createdAt"),
      "archived": r.get("isArchived"), "fork": r.get("isFork"),
      "size_kb": r.get("diskUsage"), "description": (r.get("description") or "")[:300],
      "homepage": r.get("homepageUrl"),
      "license": (r.get("licenseInfo") or {}).get("spdxId"),
      "language": (r.get("primaryLanguage") or {}).get("name"),
      "topics": [t["topic"]["name"] for t in ((r.get("repositoryTopics") or {}).get("nodes") or [])],
      "release_count": (r.get("releases") or {}).get("totalCount", 0),
      "latest_release": (r.get("latestRelease") or {}).get("publishedAt"),
      "open_issues": (r.get("issues") or {}).get("totalCount"),
      "open_prs": (r.get("pullRequests") or {}).get("totalCount"),
    }
    br = r.get("defaultBranchRef") or {}
    out["default_branch"] = br.get("name")
    tgt = br.get("target") or {}
    out["commits_12mo"] = (tgt.get("history") or {}).get("totalCount")
    logins = {((n.get("author") or {}).get("user") or {}).get("login")
              for n in ((tgt.get("recent") or {}).get("nodes") or [])}
    logins.discard(None)
    out["authors_last100"] = len(logins)
    # reconstruct pseudo-paths from the probed directories
    paths, dirs_present = [], []
    for alias, prefix in DIRS.items():
        node = r.get(alias)
        if not node or node.get("entries") is None:
            continue
        dirs_present.append(prefix or "<root>")
        for e in node["entries"]:
            p = f"{prefix}/{e['name']}" if prefix else e["name"]
            paths.append(p + ("/" if e["type"] == "tree" else ""))
    out["dirs_present"] = dirs_present
    out["paths"] = paths
    return out


cands = json.loads((OUT / "candidates.json").read_text())
done = {}
if CKPT.exists():
    done = {r["full_name"]: r for r in json.loads(CKPT.read_text())}
    print(f"resuming: {len(done)} already enriched")
todo = [c for c in cands if c["full_name"] not in done]
print(f"to enrich: {len(todo)} of {len(cands)}", flush=True)

spent = 0
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
_lk = threading.Lock()
batches = [todo[i:i+BATCH] for i in range(0, len(todo), BATCH)]

def run(batch):
    d = post(build(batch))
    if d is None:
        return 0, []
    data = d.get("data") or {}
    rl = data.get("rateLimit") or {}
    recs = []
    for i, c in enumerate(batch):
        node = data.get(f"r{i}")
        if node:
            rec = flatten(node)
            rec["search_topics"] = c.get("topics", [])
            recs.append(rec)
    return rl.get("cost", 0) or 0, recs

nb = 0
with ThreadPoolExecutor(max_workers=4) as ex:
    futs = [ex.submit(run, b) for b in batches]
    for f in as_completed(futs):
        try:
            cost, recs = f.result()
        except Exception as e:
            print(f"    batch error: {type(e).__name__}", flush=True); continue
        with _lk:
            spent += cost
            for rec in recs:
                done[rec["full_name"]] = rec
            nb += 1
            if nb % 15 == 0:
                CKPT.write_text(json.dumps(list(done.values()), indent=1))
                print(f"  {len(done)}/{len(cands)}  gql_spent={spent}", flush=True)
CKPT.write_text(json.dumps(list(done.values()), indent=1))

vals = list(done.values())
(OUT / "enriched.json").write_text(json.dumps(vals, indent=1))
print(f"\ndone: {len(vals)} enriched. graphql points spent={spent}")
nn = sum(1 for v in vals if v.get("commits_12mo") is None)
print(f"missing commits_12mo: {nn}")
