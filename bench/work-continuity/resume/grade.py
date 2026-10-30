#!/usr/bin/env python3
"""Grade resume-bench runs against answers.json. Usage: grade.py <results dir>"""
import json, re, statistics, sys
from pathlib import Path

HERE = Path(__file__).parent
TRUTH = {k: v for k, v in json.loads((HERE / "answers.json").read_text()).items() if not k.startswith("_")}


def answers_of(run):
    """The structured answers from a `claude -p --output-format json --json-schema` result."""
    if isinstance(run.get("structured_output"), dict):
        return run["structured_output"]
    try:
        return json.loads(re.search(r"\{.*\}", run.get("result") or "", re.S).group(0))
    except (AttributeError, ValueError):
        return {}


def grade(run):
    got = answers_of(run)
    rows = {}
    for q, t in TRUTH.items():
        a = str(got.get(q, ""))
        ok = bool(re.search(t["pass"], a, re.I))
        wrong = bool(t["fail"]) and bool(re.search(t["fail"], a, re.I)) and not ok
        rows[q] = {"source": t["source"], "ok": ok, "confident_wrong": wrong, "answer": a[:160]}
    return rows


def main(results):
    by_arm = {}
    for f in sorted(Path(results).glob("*-[0-9]*.json")):
        arm = f.stem.split("-")[0]
        try:
            run = json.loads(f.read_text())
        except ValueError:  # the session crashed or wrote nothing: graded as all wrong, no cost
            run = {"result": "", "is_error": True}
        by_arm.setdefault(arm, []).append((run, grade(run)))
    print("| arm | runs | correct (of 7) | git-derivable (q1) | brief-only (q2-q6, of 5) | says unknown when unknowable (q7) | confident-wrong | cost per run | turns | seconds |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for arm, runs in sorted(by_arm.items()):
        mean = lambda xs: statistics.mean(xs) if xs else 0
        g = [r for _, r in runs]
        print(f"| {arm} | {len(runs)} | {mean([sum(x['ok'] for x in r.values()) for r in g]):.1f} | "
              f"{mean([r['q1']['ok'] for r in g]):.0%} | "
              f"{mean([sum(r[q]['ok'] for q in ('q2','q3','q4','q5','q6')) for r in g]):.1f} | "
              f"{mean([r['q7']['ok'] for r in g]):.0%} | "
              f"{mean([sum(x['confident_wrong'] for x in r.values()) for r in g]):.1f} | "
              f"${mean([run.get('total_cost_usd') or 0 for run, _ in runs]):.3f} | "
              f"{mean([run.get('num_turns') or 0 for run, _ in runs]):.1f} | "
              f"{mean([(run.get('duration_ms') or 0) / 1000 for run, _ in runs]):.0f} |")
    (Path(results) / "graded.json").write_text(json.dumps(
        {arm: [r for _, r in runs] for arm, runs in by_arm.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
