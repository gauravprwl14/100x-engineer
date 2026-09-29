#!/usr/bin/env python3
"""Score this plugin's checks against seeded defects. This is the honest answer to
"how do we know it works".

What it measures: given a defect the plugin CLAIMS to catch, does the check actually
fail? And given clean code, does it stay quiet? That is a catch rate and a
false-positive rate — two numbers, reproducible, no interpretation.

What it does NOT measure: whether a person using this ships better software faster.
No benchmark here supports that claim, and none is offered.

    run_evals.py                 # run all
    run_evals.py --only ci-      # substring filter
    run_evals.py --json

Python stdlib only.
"""
import argparse, json, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES = ROOT / "evals" / "seeded"


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def prepare(case, tmp):
    """Build a throwaway git repo whose *diff* contains the seeded defect.

    The diff-scoped checks only inspect changes, so the defect must appear as an
    addition against a committed baseline — not as pre-existing history.
    """
    repo = tmp / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "e@e"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "e"], cwd=repo, check=True)
    (repo / ".keep").write_text("")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)

    if case.get("generated_repo"):
        # plan_feature.py resolves to the cwd's git root, so this lands inside `repo`
        subprocess.run([sys.executable, str(ROOT / "scripts" / "plan_feature.py"),
                        "new", "gen", "--kind", "crud", "--force"],
                       cwd=repo, capture_output=True)
    else:
        src = CASES / case["id"] / "repo"
        if src.exists():
            shutil.copytree(src, repo, dirs_exist_ok=True)
    return repo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    cases = []
    for cj in sorted(CASES.glob("*/case.json")):
        c = json.loads(cj.read_text())
        if a.only and a.only not in c["id"]:
            continue
        cases.append(c)
    if not cases:
        print("no eval cases matched", file=sys.stderr)
        return 2

    results = []
    for c in cases:
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            repo = prepare(c, tmp)
            cmd = c["command"].replace("{P}", str(ROOT))
            rc, out = run(cmd, repo)
            failed = rc != 0
            correct = failed == c["must_fail"]
            results.append({**c, "exit": rc, "detected": failed,
                            "correct": correct, "output": out[-400:]})

    pos = [r for r in results if r["must_fail"] and not r.get("known_gap")]
    gaps = [r for r in results if r.get("known_gap")]
    neg = [r for r in results if not r["must_fail"]]
    caught = sum(1 for r in pos if r["correct"])
    fp = sum(1 for r in neg if not r["correct"])
    gap_caught = sum(1 for r in gaps if r["detected"])

    if a.json:
        print(json.dumps({"results": results,
                          "catch_rate": f"{caught}/{len(pos)}",
                          "false_positives": f"{fp}/{len(neg)}",
                          "known_gaps": f"{gap_caught}/{len(gaps)} now detected"},
                         indent=2))
        return 0 if (caught == len(pos) and fp == 0) else 1

    print(f"{'case':38s} {'expect':8s} {'got':8s} verdict")
    print("-" * 72)
    for r in sorted(results, key=lambda x: (bool(x.get("known_gap")),
                                            not x["must_fail"], x["id"])):
        if r.get("known_gap"):
            continue
        exp = "detect" if r["must_fail"] else "quiet"
        got = "detect" if r["detected"] else "quiet"
        print(f"{r['id']:38s} {exp:8s} {got:8s} {'ok' if r['correct'] else 'MISS'}")
    print("-" * 72)
    print(f"seeded defects caught : {caught}/{len(pos)}"
          f"  ({100*caught/max(1,len(pos)):.0f}%)")
    print(f"false positives       : {fp}/{len(neg)} on clean controls")
    if gaps:
        print(f"\nKNOWN GAPS — defect classes this plugin does NOT catch ({len(gaps)}):")
        for r in sorted(gaps, key=lambda x: x["id"]):
            mark = "NOW CAUGHT" if r["detected"] else "uncaught"
            print(f"  [{mark:10s}] {r['id']}")
            print(f"               {r['description']}")
        print(f"  {gap_caught}/{len(gaps)} of these are now detected. Any that flip to "
              f"NOW CAUGHT should move out of the gap list.")
    for r in results:
        if r.get("known_gap"):
            continue
        if not r["correct"]:
            print(f"\n--- {r['id']} ({'missed' if r['must_fail'] else 'false positive'}) ---")
            print(f"    {r['description']}")
            print(f"    $ {r['command'].replace('{P}', 'PLUGIN')}")
            print("    " + (r["output"].strip().replace("\n", "\n    ")[:500] or "(no output)"))
    print("\nThis measures detection of defects the plugin claims to catch. It does not "
          "measure developer productivity, and nothing here supports a claim about it.")
    return 0 if (caught == len(pos) and fp == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
