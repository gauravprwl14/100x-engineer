#!/usr/bin/env python3
"""Stage A: harvest candidate repos from GitHub search API.

Slices by language x star bucket because search caps at 1000 results/query.
Applies Part B1 name-pattern rejection immediately to cut noise at the source.
"""
import json, re, subprocess, sys, time, datetime, pathlib

# One-shot research-pipeline scripts with module-level execution: importing them, or
# passing --help, would otherwise start a live GitHub harvest. Answer --help from the
# docstring before any of that runs.
import sys as _sys
if __name__ != "__main__" or any(a in ("--help", "-h") for a in _sys.argv[1:]):
    print(__doc__ or __file__)
    raise SystemExit(0)


OUT = pathlib.Path("research/raw")
OUT.mkdir(parents=True, exist_ok=True)

SCREEN_DATE = datetime.date.today()
ALIVE_SINCE = (SCREEN_DATE - datetime.timedelta(days=90)).isoformat()

# Part B1 noise patterns
NOISE = re.compile(
    r"(awesome|roadmap|free-programming|interview|coding-challenge|leetcode"
    r"|cheat-?sheet|every-programmer|project-based|build-your-own|system-design"
    r"|tech-interview|^computer-science|the-book-of|^papers|^resources"
    r"|^guides?$|^tutorial|^course|^learn-|30-seconds|public-apis|dev-?roadmap"
    r"|^clean-code|design-patterns|^hello-world|^demo|^example|^starter"
    r"|^boilerplate|^template|^dotfiles|^configs?$|books?$|^books|study"
    r"|^interview|questions$|^algorithms?$|^coding|bootcamp|curriculum"
    r"|^notes$|^wiki$|^docs$|^blog$|^cv$|^resume)",
    re.I,
)

LANGS = [
    "TypeScript", "JavaScript", "Python", "Go",
    "Swift", "Kotlin", "Dart", "Java",
    "Rust", "C++", "C", "Ruby", "PHP", "C#",
]
# star buckets keep each query under the 1000-result cap
BUCKETS = ["20000..30000", "30000..50000", "50000..80000", "80000..500000"]


def gh_search(q, page=1):
    cmd = ["gh", "api", "-X", "GET", "search/repositories",
           "-f", f"q={q}", "-f", "per_page=100", "-f", f"page={page}",
           "-f", "sort=stars", "-f", "order=desc"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ! query failed: {r.stderr.strip()[:200]}", file=sys.stderr)
        return None
    return json.loads(r.stdout)


seen, rows, rejected = set(), [], []
queries = 0

for lang in LANGS:
    for bucket in BUCKETS:
        q = f"stars:{bucket} pushed:>={ALIVE_SINCE} language:{lang} archived:false fork:false"
        for page in (1, 2, 3):
            data = gh_search(q, page)
            queries += 1
            time.sleep(2.2)  # search API: 30 req/min
            if not data or not data.get("items"):
                break
            for it in data["items"]:
                full = it["full_name"]
                if full in seen:
                    continue
                seen.add(full)
                rec = {
                    "full_name": full,
                    "owner": it["owner"]["login"],
                    "name": it["name"],
                    "stars": it["stargazers_count"],
                    "forks": it["forks_count"],
                    "open_issues": it["open_issues_count"],
                    "language": it.get("language"),
                    "pushed_at": it["pushed_at"],
                    "created_at": it["created_at"],
                    "size_kb": it.get("size"),
                    "license": (it.get("license") or {}).get("spdx_id"),
                    "topics": it.get("topics", []),
                    "description": (it.get("description") or "")[:300],
                    "default_branch": it.get("default_branch", "main"),
                    "archived": it.get("archived"),
                    "fork": it.get("fork"),
                }
                # Part B1: name + description + topic noise rejection
                blob = f"{it['name']} {' '.join(it.get('topics', []))} {rec['description']}"
                if NOISE.search(it["name"]) or NOISE.search(blob[:120]):
                    rec["reject_reason"] = "B1:name/topic noise pattern"
                    rejected.append(rec)
                    continue
                if not rec["license"] or rec["license"] in ("NOASSERTION",):
                    rec["reject_reason"] = f"A7:license={rec['license']}"
                    rejected.append(rec)
                    continue
                rows.append(rec)
            if len(data["items"]) < 100:
                break
        print(f"  {lang:12s} {bucket:16s} kept={len(rows):4d} rejected={len(rejected):4d}", flush=True)

rows.sort(key=lambda r: -r["stars"])
(OUT / "candidates.json").write_text(json.dumps(rows, indent=1))
(OUT / "rejected_b1.json").write_text(json.dumps(rejected, indent=1))
print(f"\nqueries={queries}  candidates={len(rows)}  rejected_at_b1={len(rejected)}")
print(f"screen_date={SCREEN_DATE}  alive_since={ALIVE_SINCE}")
