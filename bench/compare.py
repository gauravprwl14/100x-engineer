#!/usr/bin/env python3
"""Score the three bench arms and compare them per scenario.

Reads the `claude plugin eval --json` files that run.sh writes:
  new.json  arms.with = NEW plugin, arms.without = no plugin (the ablation arm)
  old.json  arms.with = OLD plugin (run.sh --old-ref, default commit 4c1cd93)
For every run it also runs bench/checks.py over the workspace kept by --keep-temp, then
scores the run as passed weight / total weight across the eval's own graders and the
deterministic checks (each check weighs 1). Prints one row per scenario and an exact sign
test of NEW vs OLD and NEW vs no plugin across scenarios (ties dropped). The footer also
counts, per arm, the runs whose trace shows a Bash call to the screen checklist
(`plan_feature cases`, or `plan_feature` with --screens/--roles); it is a usage signal and
not part of the score.

    compare.py --new results/new.json --old results/old.json [--tools-root DIR] [--json OUT]

Deterministic results are cached in bench-checks.json beside new.json; --rescore ignores it.
Python stdlib only.
"""
import argparse
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # keep bench/ free of __pycache__
import checks  # noqa: E402

ARMS = ("none", "old", "new")


def load_sign_test(tools_root):
    # Reuse the exact test prompt_bench already ships rather than keep a second copy.
    sys.path.insert(0, str(Path(tools_root) / "scripts"))
    try:
        from prompt_bench import sign_test
    finally:
        sys.path.pop(0)
    return sign_test


def kept_workspace(trace_path, scratch):
    """Copy the agent's workspace out of the harness's sealed, read-only kept directory."""
    root = Path(trace_path).parent.parent
    for candidate in (root / "sealed" / "home" / "cwd", root / "home" / "cwd"):
        for path in (root, root / "sealed"):
            if path.exists():
                os.chmod(path, 0o700)
        if candidate.is_dir():
            target = Path(tempfile.mkdtemp(dir=scratch)) / "cwd"
            shutil.copytree(candidate, target, symlinks=True)
            return target
    return None


# Checklist use, not any mention: `plan_feature cases`, or a call with --screens/--roles.
# OLD's `plan_feature new --kind ...` and a grep for the name do not count.
CHECKLIST_RX = re.compile(r"plan_feature(\.py)?\s+cases\b|plan_feature(\.py)?\b[^|;&]*\s--(screens|roles)\b")


def bash_commands(node):
    """Every Bash tool_use command anywhere in one trace event (stream-json nests them)."""
    if isinstance(node, dict):
        if node.get("type") == "tool_use" and node.get("name") == "Bash":
            yield str((node.get("input") or {}).get("command", ""))
        for value in node.values():
            yield from bash_commands(value)
    elif isinstance(node, list):
        for value in node:
            yield from bash_commands(value)


def trace_facts(trace_path):
    """(final message text, whether the 100x plugin's skills were loaded, whether a Bash call
    used the screen checklist) from trace.jsonl; the flags are None when the trace cannot be read."""
    text, loaded, planned = "", None, None
    try:
        lines = Path(trace_path).read_text().splitlines()
    except OSError:
        return text, loaded, planned
    planned = False
    for raw in lines:
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            loaded = any(str(cmd).startswith("100x:") for cmd in event.get("slash_commands", []))
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            text = event["result"]
        planned = planned or any(CHECKLIST_RX.search(command) for command in bash_commands(event))
    return text, loaded, planned


def runs_by_arm(new, old):
    pairs = {"new": (new, "with"), "none": (new, "without"), "old": (old, "with")}
    out = {}
    for arm, (doc, key) in pairs.items():
        for case in doc.get("cases", []):
            out.setdefault(case["name"], {})[arm] = case.get("arms", {}).get(key, [])
    return out


def score_run(case, run, cache, tools_root, scratch, rescore):
    trace = run.get("tracePath") or ""
    if trace and (rescore or trace not in cache):
        text, loaded, planned = trace_facts(trace)
        workspace = kept_workspace(trace, scratch)
        result = (checks.score(case, workspace, text, tools_root) if workspace
                  else {"checks": {"workspace_kept": False}, "error": "no kept workspace"})
        result["plugin_loaded"], result["checklist_called"] = loaded, planned
        cache[trace] = result
    elif trace in cache and "checklist_called" not in cache[trace]:
        cache[trace]["checklist_called"] = trace_facts(trace)[2]  # caches from before the column
    det = cache.get(trace, {"checks": {"workspace_kept": False}, "error": "no trace"})
    graders = [g for g in run.get("graders", []) if g.get("scored", True)]
    native_total = sum(g.get("weight", 1) for g in graders)
    native_passed = sum(g.get("weight", 1) for g in graders if g.get("passed"))
    det_values = list(det["checks"].values())
    total = native_total + len(det_values)
    return {
        "score": (native_passed + sum(map(bool, det_values))) / total if total else 0.0,
        "native": native_passed / native_total if native_total else None,
        "det": sum(map(bool, det_values)) / len(det_values) if det_values else None,
        "cost": run.get("costUsd", 0) or 0,
        "error": run.get("error") or det.get("error"),
        "plugin_loaded": det.get("plugin_loaded"),
        "checklist_called": det.get("checklist_called"),
        "failed": [k for k, v in det["checks"].items() if not v]
        + [g["name"] for g in graders if not g.get("passed")],
    }


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def fmt(value):
    return "  -  " if value is None else f"{value:.2f}"


def compare(scores, a, b, sign_test):
    pos = sum(1 for arms in scores.values() if arms.get(a) and arms.get(b)
              and arms[a]["score"] > arms[b]["score"])
    neg = sum(1 for arms in scores.values() if arms.get(a) and arms.get(b)
              and arms[a]["score"] < arms[b]["score"])
    ties = sum(1 for arms in scores.values() if arms.get(a) and arms.get(b)) - pos - neg
    return pos, neg, ties, sign_test(pos, neg)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--tools-root", type=Path, default=checks.BENCH.parent,
                        help="repo whose scripts/ (craft_check, prose_check) grade every arm")
    parser.add_argument("--rescore", action="store_true")
    parser.add_argument("--json", type=Path, help="also write the per-run scores here")
    args = parser.parse_args()
    # checks.py runs tools from inside each run's overlay, where a relative path breaks.
    args.tools_root = args.tools_root.resolve()

    new, old = (json.loads(path.read_text()) for path in (args.new, args.old))
    cache_path = args.new.parent / "bench-checks.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    sign_test = load_sign_test(args.tools_root)

    per_run, scores = {}, {}
    with tempfile.TemporaryDirectory(prefix="bench-compare-") as scratch:
        for case, arms in sorted(runs_by_arm(new, old).items()):
            for arm, runs in arms.items():
                rows = [score_run(case, run, cache, args.tools_root, scratch, args.rescore)
                        for run in runs]
                per_run.setdefault(case, {})[arm] = rows
                # A timed-out run leaves the fixture untouched, which can pass every check;
                # it is missing data, not a result.
                completed = [r for r in rows if not r["error"]]
                if completed:
                    scores.setdefault(case, {})[arm] = {
                        "score": mean(r["score"] for r in completed),
                        "native": mean(r["native"] for r in completed),
                        "det": mean(r["det"] for r in completed),
                        "runs": len(completed)}
    cache_path.write_text(json.dumps(cache, indent=1))

    print(f"{'scenario':24} " + " ".join(f"{arm:>20}" for arm in ARMS))
    print(f"{'':24} " + " ".join(f"{'score (llm/det) n':>20}" for _ in ARMS))
    for case in sorted(scores):
        cells = []
        for arm in ARMS:
            s = scores[case].get(arm)
            cells.append(f"{fmt(s['score'])} ({fmt(s['native'])}/{fmt(s['det'])}) n{s['runs']}" if s else "-")
        print(f"{case:24} " + " ".join(f"{cell:>20}" for cell in cells))
    overall = {arm: mean(scores[c][arm]["score"] for c in scores if arm in scores[c]) for arm in ARMS}
    print(f"{'mean':24} " + " ".join(f"{fmt(overall[arm]):>20}" for arm in ARMS))

    print()
    for a, b in (("new", "old"), ("new", "none"), ("old", "none")):
        pos, neg, ties, p = compare(scores, a, b, sign_test)
        print(f"sign test {a} vs {b}: {a} better in {pos}, worse in {neg}, tied {ties}; "
              f"two-sided p = {p:.3f}")

    print()
    for arm in ARMS:
        rows = [r for case in per_run.values() for r in case.get(arm, [])]
        loaded = [r["plugin_loaded"] for r in rows if r["plugin_loaded"] is not None]
        expected = arm != "none"
        wrong = sum(1 for flag in loaded if flag != expected)
        errors = sum(1 for r in rows if r["error"])
        traced = [r["checklist_called"] for r in rows if r["checklist_called"] is not None]
        print(f"{arm:5} runs {len(rows):3}  cost ${sum(r['cost'] for r in rows):7.2f}  "
              f"errors {errors}  plugin-load mismatches {wrong}  "
              f"checklist calls {sum(traced)}/{len(traced)}")
        if wrong:
            print(f"  WARNING: {wrong} {arm} run(s) did not have the expected plugin state")

    if args.json:
        args.json.write_text(json.dumps({"scores": scores, "runs": per_run}, indent=1))


if __name__ == "__main__":
    main()
