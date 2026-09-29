#!/usr/bin/env python3
"""Render the corpus + screening funnel as the research deliverable."""
import json, pathlib, datetime, collections

# One-shot research-pipeline scripts with module-level execution: importing them, or
# passing --help, would otherwise start a live GitHub harvest. Answer --help from the
# docstring before any of that runs.
import sys as _sys
if __name__ != "__main__" or any(a in ("--help", "-h") for a in _sys.argv[1:]):
    print(__doc__ or __file__)
    raise SystemExit(0)


R = pathlib.Path("research/raw")
cand = json.loads((R/"candidates.json").read_text())
rej1 = json.loads((R/"rejected_b1.json").read_text())
kept = json.loads((R/"scored_kept.json").read_text())
drop = json.loads((R/"scored_dropped.json").read_text())
corp = json.loads((R/"corpus.json").read_text())
enr  = json.loads((R/"enriched.json").read_text())

DIMS = ["D1_verification","D2_antibloat","D3_agentic","D4_correctness",
        "D5_security","D6_ops","D7_governance"]
SHORT = {"D1_verification":"D1","D2_antibloat":"D2","D3_agentic":"D3",
         "D4_correctness":"D4","D5_security":"D5","D6_ops":"D6","D7_governance":"D7"}
TARGET = {"js-infra":55,"js-app":35,"python":50,"go":40,"mobile":30,
          "agentic-dev":25,"reliability-exemplar":25}

o = []
w = o.append
w("# Repo Corpus\n")
w(f"Screen date **{datetime.date.today()}**. Gates and scoring per "
  f"[`00-signal-rubric.md`](00-signal-rubric.md) (as revised through v4).\n")

w("## Screening funnel\n")
w("| stage | in | out | remaining |")
w("|---|---|---|---|")
w(f"| GitHub search: >=20k stars, pushed <=90d, 14 languages, not fork/archived | — | — | {len(cand)+len(rej1)} |")
w(f"| B1 noise-pattern + license rejection | {len(cand)+len(rej1)} | {len(rej1)} | {len(cand)} |")
w(f"| A/B/C gate evaluation (GraphQL enrichment) | {len(cand)} | {len(drop)} | {len(kept)} |")
w(f"| Part F cluster allocation | {len(kept)} | {len(kept)-len(corp)} | **{len(corp)}** |")
w("")

w("## Gate failure attribution\n")
w("Why the 723 rejected repos were rejected. A repo can fail several gates.\n")
w("| gate | meaning | rejected |")
w("|---|---|---|")
MEAN = {"A3":"<250 commits in 12 months","A4":"<10 recent authors and <2000 commits/yr",
        "A5":"archived","A6":"is a fork","A7":"no license","A8":"no build manifest",
        "A9":"no test signal","A10":"younger than 24mo (12mo for agentic-dev)",
        "A11":"star velocity >15000/mo — unvalidatable adoption signal",
        "C":"<2 of 5 production-reality proxies"}
fc = collections.Counter(f.split(":")[0] for r in drop for f in r["gate_failures"])
for g, n in sorted(fc.items(), key=lambda kv: -kv[1]):
    w(f"| {g} | {MEAN.get(g,'')} | {n} |")
w("")

w("## Corpus by cluster\n")
w("| cluster | selected | eligible | target | note |")
w("|---|---|---|---|---|")
byc = collections.defaultdict(list)
for r in kept: byc[r["cluster"]].append(r)
for cl, cap in TARGET.items():
    sel = len([r for r in corp if r["cluster"] == cl]); el = len(byc[cl])
    note = "**SHORTFALL — supply-limited, not padded**" if sel < cap else "at target"
    w(f"| {cl} | {sel} | {el} | {cap} | {note} |")
w(f"| **total** | **{len(corp)}** | {len(kept)} | 260 | |")
w("")

w("## Headline finding: AI-agent instruction-file adoption\n")
w(f"Measured across all **{len(enr)}** enriched repos (>=20k stars, active within 90 days) "
  "by probing for the file on the default branch. This is the adoption rate among "
  "serious production repositories, not a curated sample.\n")
w("| artifact | repos | share |")
w("|---|---|---|")
import re
PAT = {"AGENTS.md": r"^AGENTS\.md/?$", "CLAUDE.md": r"^CLAUDE\.md/?$",
       ".claude/ skills|agents|commands|hooks": r"^\.claude/(skills|agents|commands|hooks)/",
       ".agents/ directory": r"^\.agents/",
       ".github/copilot-instructions.md": r"^\.github/copilot-instructions\.md/?$",
       ".cursor/rules or .cursorrules": r"^\.cursorrules/?$|^\.cursor/rules/",
       "other (windsurf/gemini/cline/aider/junie)": r"^\.windsurfrules|^GEMINI\.md|^\.clinerules|^\.aider|^\.junie",
       ".mcp.json": r"^\.mcp\.json/?$"}
for label, pat in PAT.items():
    rx = re.compile(pat, re.I)
    n = sum(1 for r in enr if any(rx.search(p) for p in (r.get("paths") or [])))
    w(f"| `{label}` | {n} | {100*n/len(enr):.1f}% |")
anyrx = [re.compile(p, re.I) for p in PAT.values()]
n = sum(1 for r in enr if any(rx.search(p) for rx in anyrx for p in (r.get("paths") or [])))
w(f"| **any of the above** | **{n}** | **{100*n/len(enr):.1f}%** |")
w("")

w("## The corpus\n")
w("`sc` = total signal score (max 21). `D1`-`D7` = per-dimension score 0-3 "
  "(0 absent, 1 present, 2 CI-enforced, 3 exemplary). `T` = tier. "
  "`agent` = agent instruction files present.\n")
AG = {"agent_agents_md":"A","agent_claude_md":"C","agent_claude_dir":"S",
      "agent_agents_dir":"D","agent_copilot":"P","agent_cursor":"R","agent_mcp":"M"}
for cl in TARGET:
    rows = sorted([r for r in corp if r["cluster"] == cl], key=lambda r: -r["signal_score"])
    if not rows: continue
    w(f"### {cl} ({len(rows)})\n")
    w("| repo | stars | lang | age | c/12mo | sc | T | " + " | ".join(SHORT[d] for d in DIMS) + " | agent |")
    w("|---|--:|---|--:|--:|--:|--:|" + "--:|"*7 + "---|")
    for r in rows:
        ag = "".join(v for k, v in AG.items() if k in r["signal_keys"]) or "—"
        w(f"| [{r['full_name']}](https://github.com/{r['full_name']}) | {r['stars']:,} | "
          f"{r['language'] or '—'} | {r['age_months']:.0f}mo | {r['commits_12mo']:,} | "
          f"**{r['signal_score']}** | {r['tier']} | "
          + " | ".join(str(r['dim_scores'][d]) for d in DIMS) + f" | {ag} |")
    w("")
w("Agent-file legend: `A`=AGENTS.md `C`=CLAUDE.md `S`=.claude/skills|agents|commands|hooks "
  "`D`=.agents/ `P`=copilot-instructions `R`=cursor rules `M`=.mcp.json\n")

w("## Known limitations of this screen\n")
w("- **Directory probe, not full tree.** Enrichment reads ~20 targeted directories per repo "
  "via GraphQL, not the recursive tree. A signal file in an unprobed path is invisible. "
  "Absence in this table means *not found at the probed paths*, never *does not exist*.\n")
w("- **A4 is a proxy.** Distinct authors among the last 100 commits, with a 2000-commits/yr "
  "escape hatch. Squash-merge and bot-heavy repos can still be undercounted.\n")
w("- **CI detection is GitHub-Actions-biased.** Projects on other CI systems score lower on "
  "D1 than they deserve. This is why v3 removed CI from the hard gate.\n")
w("- **Production adoption is inferred, never observed.** Part C uses 5 proxies. No repo in "
  "this corpus was verified to have real users; we verified it has the *artifacts* of a "
  "project that does.\n")
w("- **Mobile is under-represented (11 of 30).** Mobile repos at 20k+ stars sustaining 250+ "
  "commits/year are scarce. Mobile findings draw on a correspondingly thinner base, and are "
  "supplemented by named below-gate repos recorded in the mobile findings document.\n")
w("- **Scores measure presence of machinery, not quality of use.** A repo scoring 3 on D1 has "
  "many test signals; it does not follow that its tests are good. Tier-1 status licenses a "
  "deep read, it does not certify the practice.\n")

pathlib.Path("research/10-repo-corpus.md").write_text("\n".join(o) + "\n")
print(f"wrote research/10-repo-corpus.md  ({len(o)} lines, {len(corp)} repos)")
