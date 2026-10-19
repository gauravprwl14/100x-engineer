#!/usr/bin/env python3
"""Blind, placebo-controlled A/B bench for a prompt or instruction (the prompt-bench skill's engine).

Measures whether a prompt changes answers on hard tasks with hidden ground truth, against a
placebo arm, with shuffled blind labels and an exact sign test. It never calls a model: the
main session runs the arms as isolated subagents and feeds tokens/duration back via `record`.

    prompt_bench.py init <bench> --spec spec.json
    prompt_bench.py record <bench> --run ID --phase v1|v2 --tokens N --ms N
    prompt_bench.py snapshot <bench> --run ID [--force]
    prompt_bench.py blind <bench> [--seed N] [--force]
    prompt_bench.py probe <bench> --label LABEL
    prompt_bench.py judge-plan <bench> [--task ID]
    prompt_bench.py aggregate <bench> [--json]
    prompt_bench.py report <bench>

Spec: {"category": one of CATEGORIES, "design": "paired-followup"|"parallel-arms", "reps": n,
       "arms": {"placebo": "...", "<name>": "..."},
       "tasks": [{"id", "fixture_dir", "task_prompt", "ground_truth", "probes"?: [python], "code"?: bool}]}
fixture_dir is relative to the spec file. In parallel-arms an arm text containing {task} is a
template (the task prompt is substituted); otherwise it is prepended as standing instructions.

Layout written under <bench> (nothing is written outside it, nothing is ever deleted):
  plan.json  ARMS.md  GROUND_TRUTH.md  fixtures/<task>/  runs/<task>-<n>/ (a git repo each)
  snapshots/<run>/v1/  metrics.csv  blind/<task>/<LABEL>.md (+ .files/)  blind_key.json
  scores/<task>.json (judges)  REPORT.md  INDEX.md
Exit codes: 0 ok, 1 refused / incomplete input, 2 usage. Python stdlib only.
"""
import argparse, csv, json, math, os, pathlib, random, re, shutil, statistics, subprocess, sys
import tempfile
import _mutation_guard

TOOL = "prompt_bench"
PLACEBO = "placebo"
DESIGNS = ("paired-followup", "parallel-arms")
CATEGORIES = {
    "follow-up": "paired-followup",
    "always-on": "parallel-arms",
    "task-template": "parallel-arms",
    "skill-description": "parallel-arms",
    "output-format": "parallel-arms",
    "persona": "parallel-arms",
}
DIMS = ("correctness", "recall", "precision", "surgical", "usefulness", "concision", "overall")
DEFAULT_SEED = 20261013
ALPHA = 0.05            # two-sided sign test
MIN_EFFECT = 0.5        # points on the 0-10 overall score; smaller is not worth a prompt
CEILING = 8.5           # mean baseline score at or above this leaves no room to improve
MIN_RUNS_PER_ARM = 6    # below 6 untied pairs a sign test cannot reach p < 0.05
LENGTH_WARN_PCT = 25
PROBE_TIMEOUT_S = 20
SKIP_NAMES = {".git", "__pycache__", ".DS_Store"}
ANSWER_RX = re.compile(r"^answer_v[12]\.md$")
VERDICT_BETTER = "better than placebo"
VERDICT_SAME = "no better than placebo (within noise)"
VERDICT_WORSE = "worse"
VERDICT_REF = "reference (placebo)"

PLACEMENT = {
    "follow-up": {
        VERDICT_BETTER: "Send it as the follow-up after a first answer (by hand, a slash command, or a "
                        "Stop-hook re-check). It is a second pass, not a standing rule: keep it out of "
                        "CLAUDE.md/AGENTS.md.",
        VERDICT_SAME: "The second pass is the lever, not this wording. Use the placebo follow-up "
                      "(or the shortest arm) and drop the extra words.",
        VERDICT_WORSE: "Do not use it. Keep the placebo follow-up.",
    },
    "always-on": {
        VERDICT_BETTER: "Add it to AGENTS.md (CLAUDE.md as a pointer), only if the gain is worth "
                        "its per-turn context cost (see Cost).",
        VERDICT_SAME: "Do not add it to AGENTS.md/CLAUDE.md: it costs context on every turn and "
                      "changed nothing measurable.",
        VERDICT_WORSE: "Remove it from the always-on instructions.",
    },
    "task-template": {
        VERDICT_BETTER: "Save it as a slash command or prompt template for this task type.",
        VERDICT_SAME: "Keep writing the task plainly; the template adds words, not quality.",
        VERDICT_WORSE: "Do not use the template.",
    },
    "skill-description": {
        VERDICT_BETTER: "Ship it as the skill body. Whether the skill fires is a separate question: "
                        "check routing with skill_triggers.py.",
        VERDICT_SAME: "The loaded text does not change answers; shorten it or fold it into a "
                      "skill that does. Routing is checked separately (skill_triggers.py).",
        VERDICT_WORSE: "Do not ship this skill text.",
    },
    "output-format": {
        VERDICT_BETTER: "Put the rule in the skill or command that produces that output, not in "
                        "global instructions.",
        VERDICT_SAME: "Drop the rule; the default output was as good.",
        VERDICT_WORSE: "Drop the rule.",
    },
    "persona": {
        VERDICT_BETTER: "Use it as the subagent's system prompt (agents/<name>.md), scoped to "
                        "that agent.",
        VERDICT_SAME: "Drop the persona; it changed nothing measurable.",
        VERDICT_WORSE: "Drop the persona.",
    },
}


class Refused(Exception):
    pass


# ---------------------------------------------------------------- io helpers
def bench_path(bench, rel):
    """Resolve rel under bench and refuse anything that escapes it."""
    root = pathlib.Path(bench).resolve()
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise Refused(f"refusing to touch {p}: outside the bench {root}")
    return p


def write(bench, rel, text):
    p = bench_path(bench, rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def load_json(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def load_plan(bench):
    p = pathlib.Path(bench) / "plan.json"
    if not p.is_file():
        raise Refused(f"{p} not found: run `init` first")
    return load_json(p)


def run_by_id(plan, rid):
    for r in plan["runs"]:
        if r["id"] == rid:
            return r
    raise Refused(f"unknown run {rid!r}; runs are listed in plan.json")


def task_by_id(plan, tid):
    for t in plan["tasks"]:
        if t["id"] == tid:
            return t
    raise Refused(f"unknown task {tid!r}")


def is_code(task):
    return bool(task.get("code") or task.get("probes"))


def code_files(root):
    """Relative paths of every file a runner could have changed (answers and caches excluded)."""
    root = pathlib.Path(root)
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_NAMES for part in rel.parts) or p.suffix == ".pyc":
            continue
        if p.is_file() and not ANSWER_RX.match(rel.name):
            out.append(rel.as_posix())
    return out


def copy_tree(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP_NAMES, "*.pyc"),
                    dirs_exist_ok=True)


def copy_code(bench, src, rel_dst):
    """Copy only the code files (no answers, no .git) of src to rel_dst under the bench."""
    files = code_files(src)
    for rel in files:
        out = bench_path(bench, f"{rel_dst}/{rel}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pathlib.Path(src) / rel, out)
    return files


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=prompt-bench", "-c", "user.email=prompt-bench@localhost",
                        "-c", "commit.gpgsign=false", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Refused(f"git {' '.join(args)} failed in {cwd}: {r.stderr.strip()}")


def mean(xs):
    return round(statistics.mean(xs), 2) if xs else None


def imean(xs):
    return int(round(statistics.mean(xs))) if xs else None


def sign_test(pos, neg):
    """Exact two-sided binomial sign test; ties are dropped before calling."""
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


# ---------------------------------------------------------------- prompts
def isolation(d):
    return (f"Work only inside {d}. Do not read, list or write anything outside that directory, "
            f"do not use the network, and do not start other agents. Everything you need is in "
            f"that directory; if something is missing, say so in your answer instead of looking "
            f"elsewhere.")


def answer_line(d, phase):
    return (f"When you are done, write your complete final answer (markdown) to "
            f"{d}/answer_{phase}.md and reply with the same answer.")


def runner_prompts(design, arm_text, task_prompt, d):
    if design == "paired-followup":
        v1 = f"{isolation(d)}\n\nTask:\n{task_prompt}\n\n{answer_line(d, 'v1')}"
        v2 = f"{arm_text}\n\n{answer_line(d, 'v2')}"
        return v1, v2
    if "{task}" in arm_text:
        body = arm_text.replace("{task}", task_prompt)
        return f"{isolation(d)}\n\n{body}\n\n{answer_line(d, 'v1')}", None
    standing = (f"Standing instructions for this session:\n<instructions>\n{arm_text}\n"
                f"</instructions>" if arm_text.strip() else "")
    parts = [isolation(d), standing, f"Task:\n{task_prompt}", answer_line(d, "v1")]
    return "\n\n".join(p for p in parts if p), None


# ---------------------------------------------------------------- init
def validate_spec(spec, spec_dir):
    errs = []
    cat, design = spec.get("category"), spec.get("design")
    if cat not in CATEGORIES:
        errs.append(f"category must be one of {sorted(CATEGORIES)}, got {cat!r}")
    if design not in DESIGNS:
        errs.append(f"design must be one of {list(DESIGNS)}, got {design!r}")
    reps = spec.get("reps")
    if not isinstance(reps, int) or reps < 1:
        errs.append("reps must be a positive integer")
    arms = spec.get("arms") or {}
    if PLACEBO not in arms:
        errs.append(f"arms must include a '{PLACEBO}' arm: without it a second pass and the "
                    f"wording cannot be told apart")
    if len(arms) < 2:
        errs.append("arms needs the placebo and at least one prompt under test")
    for name, text in arms.items():
        if not _mutation_guard.safe_record_name(name, TOOL):
            errs.append(f"arm name {name!r} is not a safe name")
        if not isinstance(text, str) or (design == "paired-followup" and not text.strip()):
            errs.append(f"arm {name!r} needs prompt text")
    tasks = spec.get("tasks") or []
    if not tasks:
        errs.append("tasks is empty")
    seen = set()
    for t in tasks:
        tid = t.get("id", "")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", tid or ""):
            errs.append(f"task id {tid!r} must be kebab-case")
        if tid in seen:
            errs.append(f"duplicate task id {tid!r}")
        seen.add(tid)
        for k in ("fixture_dir", "task_prompt", "ground_truth"):
            if not t.get(k):
                errs.append(f"task {tid!r} is missing {k}")
        if t.get("fixture_dir") and not (spec_dir / t["fixture_dir"]).is_dir():
            errs.append(f"task {tid!r}: fixture_dir {spec_dir / t['fixture_dir']} is not a directory")
        if not isinstance(t.get("probes", []), list):
            errs.append(f"task {tid!r}: probes must be a list of python snippets")
    return errs


def cmd_init(a):
    spec_path = pathlib.Path(a.spec).resolve()
    spec = load_json(spec_path)
    errs = validate_spec(spec, spec_path.parent)
    if errs:
        raise Refused("invalid spec:\n  " + "\n  ".join(errs))
    bench = pathlib.Path(a.bench).resolve()
    if bench.exists() and any(bench.iterdir()):
        raise Refused(f"{bench} exists and is not empty; pick a new bench directory")
    bench.mkdir(parents=True, exist_ok=True)
    design, arms = spec["design"], spec["arms"]
    if CATEGORIES[spec["category"]] != design:
        print(f"note: category {spec['category']} usually uses {CATEGORIES[spec['category']]}, "
              f"spec says {design}", file=sys.stderr)
    arm_names = [PLACEBO] + [n for n in arms if n != PLACEBO]
    tasks, runs = [], []
    for t in spec["tasks"]:
        fx = bench_path(bench, f"fixtures/{t['id']}")
        copy_tree(spec_path.parent / t["fixture_dir"], fx)
        tasks.append({"id": t["id"], "task_prompt": t["task_prompt"], "code": is_code(t),
                      "probes": t.get("probes", []), "fixture": f"fixtures/{t['id']}"})
        n = 0
        for arm in arm_names:
            for rep in range(1, spec["reps"] + 1):
                n += 1
                rid = f"{t['id']}-{n}"
                d = bench_path(bench, f"runs/{rid}")
                copy_tree(fx, d)
                git(d, "init", "-q")
                git(d, "add", "-A")
                git(d, "commit", "-qm", "fixture", "--no-verify", "--allow-empty")
                v1, v2 = runner_prompts(design, arms[arm], t["task_prompt"], str(d))
                runs.append({"id": rid, "task": t["id"], "arm": arm, "rep": rep,
                             "dir": f"runs/{rid}", "prompt_v1": v1, "prompt_v2": v2})
    plan = {"schema": 1, "category": spec["category"], "design": design, "reps": spec["reps"],
            "placebo": PLACEBO, "arms": {n: arms[n] for n in arm_names}, "tasks": tasks, "runs": runs}
    write(bench, "plan.json", json.dumps(plan, indent=1) + "\n")
    am = ["# Arms (hidden from runners and judges)", "",
          f"Design: `{design}`. Category: `{spec['category']}`. Runs per arm per task: {spec['reps']}.", ""]
    for arm in arm_names:
        ids = ", ".join(r["id"] for r in runs if r["arm"] == arm)
        am += [f"## {arm}", "", "```text", arms[arm], "```", "", f"Runs: {ids}", ""]
    write(bench, "ARMS.md", "\n".join(am))
    gt = ["# Ground truth (hidden from runners)", ""]
    for t in spec["tasks"]:
        gt += [f"## {t['id']}", "", t["ground_truth"].strip(), ""]
    write(bench, "GROUND_TRUTH.md", "\n".join(gt))
    print(f"{TOOL}: {len(tasks)} task(s) x {len(arm_names)} arm(s) x {spec['reps']} rep(s) = "
          f"{len(runs)} runs in {bench}")
    print("next: send each run's prompt_v1 from plan.json to its own isolated subagent")
    return 0


# ---------------------------------------------------------------- record / snapshot
METRIC_FIELDS = ["run", "arm", "phase", "tokens", "duration_ms"]


def read_metrics(bench):
    p = pathlib.Path(bench) / "metrics.csv"
    if not p.is_file():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_record(a):
    plan = load_plan(a.bench)
    run = run_by_id(plan, a.run)
    if a.phase == "v2" and plan["design"] != "paired-followup":
        raise Refused("parallel-arms runs have one phase (v1)")
    if a.tokens < 0 or a.ms < 0:
        raise Refused("--tokens and --ms must be >= 0")
    rows = read_metrics(a.bench)
    if any(r["run"] == a.run and r["phase"] == a.phase for r in rows):
        raise Refused(f"{a.run} {a.phase} is already recorded in metrics.csv")
    p = bench_path(a.bench, "metrics.csv")
    new = not p.is_file()
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(METRIC_FIELDS)
        w.writerow([a.run, run["arm"], a.phase, a.tokens, a.ms])
    print(f"{TOOL}: recorded {a.run} {a.phase}")
    return 0


def cmd_snapshot(a):
    plan = load_plan(a.bench)
    run = run_by_id(plan, a.run)
    if not task_by_id(plan, run["task"])["code"]:
        raise Refused(f"task {run['task']} is not a code task; its answer file is the whole output")
    src = bench_path(a.bench, run["dir"])
    if not (src / "answer_v1.md").is_file():
        raise Refused(f"{run['dir']}/answer_v1.md is missing: snapshot after the v1 answer, "
                      f"before the follow-up")
    dst = bench_path(a.bench, f"snapshots/{a.run}/v1")
    if dst.exists() and not a.force:
        raise Refused(f"{dst} already exists (use --force to overwrite)")
    files = copy_code(a.bench, src, f"snapshots/{a.run}/v1")
    print(f"{TOOL}: saved {len(files)} file(s) of {a.run} v1 to snapshots/{a.run}/v1")
    return 0


# ---------------------------------------------------------------- blind / probe
def render_code(code_root, fixture_root):
    code_root, fixture_root = pathlib.Path(code_root), pathlib.Path(fixture_root)
    have = set(code_files(code_root))
    parts = []
    for rel in sorted(have):
        new = (code_root / rel).read_text(encoding="utf-8", errors="replace")
        old_p = fixture_root / rel
        if old_p.is_file() and old_p.read_text(encoding="utf-8", errors="replace") == new:
            continue
        lang = {".py": "python", ".ts": "ts", ".js": "js", ".sql": "sql"}.get(pathlib.Path(rel).suffix, "")
        parts.append(f"### {rel}\n```{lang}\n{new.rstrip()}\n```\n")
    gone = sorted(set(code_files(fixture_root)) - have)
    if gone:
        parts.append("### deleted\n" + "\n".join(f"- {g}" for g in gone) + "\n")
    return "\n".join(parts) if parts else "### code\n(no code changes)\n"


def cmd_blind(a):
    plan = load_plan(a.bench)
    bench = pathlib.Path(a.bench).resolve()
    if (bench / "blind_key.json").exists() and not a.force:
        raise Refused("blind_key.json exists; re-blinding relabels every answer and invalidates "
                      "scores/ (use --force only before judging)")
    phases = ["v1", "v2"] if plan["design"] == "paired-followup" else ["v1"]
    missing, items_by_task = [], {}
    for t in plan["tasks"]:
        items = []
        for r in (r for r in plan["runs"] if r["task"] == t["id"]):
            d = bench / r["dir"]
            for ph in phases:
                ans = d / f"answer_{ph}.md"
                if not ans.is_file():
                    missing.append(f"{r['dir']}/answer_{ph}.md")
                    continue
                code_root = None
                if t["code"]:
                    code_root = d
                    if ph == "v1" and plan["design"] == "paired-followup":
                        code_root = bench / "snapshots" / r["id"] / "v1"
                        if not code_root.is_dir():
                            missing.append(f"snapshots/{r['id']}/v1 (run `snapshot` after v1)")
                            continue
                items.append((r, ph, ans, code_root))
        items_by_task[t["id"]] = items
    if missing:
        raise Refused("cannot blind, missing:\n  " + "\n  ".join(missing))
    rng = random.Random(a.seed)
    key = {"seed": a.seed, "labels": {}}
    leaks = []
    arm_marks = [n for n in plan["arms"] if len(n) >= 4]
    arm_marks += [v.strip()[:40] for v in plan["arms"].values() if len(v.strip()) >= 20]
    for ti, t in enumerate(plan["tasks"], 1):
        items = items_by_task[t["id"]]
        rng.shuffle(items)
        for i, (r, ph, ans, code_root) in enumerate(items, 1):
            label = f"T{ti}-{i:02d}"
            text = ans.read_text(encoding="utf-8", errors="replace")
            for s in (str((bench / r["dir"]).resolve()), r["dir"]):
                text = re.sub(re.escape(s) + r"(?![0-9])", "<workdir>", text)
            if code_root is not None:
                text = render_code(code_root, bench / t["fixture"]) + "\n### answer\n" + text
                copy_code(bench, code_root, f"blind/{t['id']}/{label}.files")
            write(bench, f"blind/{t['id']}/{label}.md", text)
            for w in arm_marks:
                if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", text, re.I):
                    leaks.append(f"{label}: contains {w!r} (an arm name or its prompt)")
            key["labels"][label] = {"task": t["id"], "run": r["id"], "arm": r["arm"], "rep": r["rep"],
                                    "version": ph, "chars": len(text)}
    write(bench, "blind_key.json", json.dumps(key, indent=1) + "\n")
    print(f"{TOOL}: {len(key['labels'])} blind answers in blind/, key in blind_key.json (seed {a.seed})")
    for x in leaks:
        print(f"  WARN  possible arm leak, {x}: edit that blind file before judging")
    return 0


def cmd_probe(a):
    plan = load_plan(a.bench)
    bench = pathlib.Path(a.bench).resolve()
    if not re.fullmatch(r"T\d+-\d+", a.label):
        raise Refused(f"label {a.label!r} is not a blind label like T1-03")
    hits = list((bench / "blind").glob(f"*/{a.label}.files"))
    if not hits:
        raise Refused(f"no code for {a.label} under blind/ (not a code task, or not blinded yet)")
    task = task_by_id(plan, hits[0].parent.name)
    if not task["probes"]:
        raise Refused(f"task {task['id']} has no probes")
    fails = 0
    with tempfile.TemporaryDirectory(prefix="prompt-bench-probe-") as tmp:
        work = pathlib.Path(tmp) / "w"
        copy_tree(bench / task["fixture"], work)
        copy_tree(hits[0], work)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        for i, snippet in enumerate(task["probes"], 1):
            head = snippet.strip().splitlines()[0][:70]
            try:
                r = subprocess.run([sys.executable, "-c", snippet], cwd=work, env=env,
                                   capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
                ok, why = r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1]
            except subprocess.TimeoutExpired:
                ok, why = False, f"timed out after {PROBE_TIMEOUT_S}s"
            fails += not ok
            print(f"  {'PASS' if ok else 'FAIL'} probe {i}: {head}" + ("" if ok else f"  -- {why}"))
    print(f"{TOOL}: {a.label} {len(task['probes']) - fails}/{len(task['probes'])} probes pass")
    return 1 if fails else 0


# ---------------------------------------------------------------- judge plan
def ground_truth(bench):
    text = (pathlib.Path(bench) / "GROUND_TRUTH.md").read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"^## (\S+)\n(.*?)(?=^## |\Z)", text, re.S | re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


def cmd_judge_plan(a):
    plan = load_plan(a.bench)
    bench = pathlib.Path(a.bench).resolve()
    key = bench / "blind_key.json"
    if not key.is_file():
        raise Refused("run `blind` first")
    labels = load_json(key)["labels"]
    gts = ground_truth(bench)
    me = pathlib.Path(__file__).resolve()
    tasks = [task_by_id(plan, a.task)] if a.task else plan["tasks"]
    schema = {"<LABEL>": {**{d: "0-10 integer" for d in DIMS},
                          "wrong_claims": ["short quote -- why it is wrong"], "probe_failures": ["..."]}}
    for t in tasks:
        mine = sorted(lab for lab, k in labels.items() if k["task"] == t["id"])
        lines = [f"=== judge prompt: {t['id']} -> {bench}/scores/{t['id']}.json ===",
                 f"You are a blind judge. Score each of the {len(mine)} answers in {bench}/blind/{t['id']}/ "
                 f"({mine[0]} .. {mine[-1]}, one <LABEL>.md each) against the ground truth below.",
                 f"Read only that folder and the original fixture {bench}/{t['fixture']}/. Do not open "
                 f"blind_key.json, ARMS.md, plan.json, metrics.csv, runs/, snapshots/ or another task's "
                 f"files. Do not guess which prompt produced an answer or whether it is a first or a "
                 f"revised answer; score every answer on its own.", "",
                 "Task the runner was given:", t["task_prompt"], "",
                 "Ground truth (never shown to runners):", gts.get(t["id"], "(missing: check GROUND_TRUTH.md)"), ""]
        if t["probes"]:
            lines += [f"Code task: for every label run `python3 {me} probe {bench} --label <LABEL>`. "
                      f"Each FAIL goes into probe_failures and caps correctness at 4.", ""]
        lines += ["Rubric, each an integer 0-10: correctness (claims and code are right), recall (finds "
                  "what the ground truth requires), precision (no noise or false alarms), surgical (no "
                  "scope beyond what is needed), usefulness (a reader can act on it), concision, and "
                  "overall (your holistic judgement, not an average).",
                  "Penalise process leakage: sections that narrate how the answer was checked or revised "
                  "('Changed after re-check', audit logs, 'what I verified') instead of answering. "
                  "Lower concision, and overall when it buries the answer.",
                  "wrong_claims lists every factually wrong statement, one short entry each.", "",
                  f"Write {bench}/scores/{t['id']}.json with exactly one entry per label:",
                  json.dumps(schema, indent=1), ""]
        print("\n".join(lines))
    return 0


# ---------------------------------------------------------------- aggregate
def collect(bench, plan):
    bench = pathlib.Path(bench)
    kp = bench / "blind_key.json"
    if not kp.is_file():
        raise Refused("blind_key.json missing: run `blind`, then the judges")
    labels = load_json(kp)["labels"]
    scores, warns = {}, []
    for t in plan["tasks"]:
        p = bench / "scores" / f"{t['id']}.json"
        if not p.is_file():
            warns.append(f"scores/{t['id']}.json missing: task {t['id']} is not counted")
            continue
        for lab, s in load_json(p).items():
            if lab not in labels:
                raise Refused(f"scores/{t['id']}.json: unknown label {lab}")
            if not isinstance(s.get("overall"), (int, float)) or not 0 <= s["overall"] <= 10:
                raise Refused(f"scores/{t['id']}.json: {lab} needs overall in 0..10")
            scores[lab] = s
    if not scores:
        raise Refused("no scores/<task>.json found: run the judges from `judge-plan` first")
    unscored = [lab for lab, k in labels.items() if lab not in scores
                and (bench / "scores" / f"{k['task']}.json").is_file()]
    if unscored:
        warns.append(f"{len(unscored)} blind answer(s) have no score: {', '.join(sorted(unscored)[:6])}")
    obs = {}
    for lab, s in scores.items():
        k = labels[lab]
        obs[(k["run"], k["version"])] = {**k, "overall": s["overall"], "wrong": len(s.get("wrong_claims", [])),
                                         "probe_failures": len(s.get("probe_failures", [])),
                                         **{d: s[d] for d in DIMS if d in s}}
    return obs, warns


def metric_means(rows, run_ids, phase):
    sel = [r for r in rows if r["run"] in run_ids and r["phase"] == phase]
    return (imean([int(r["tokens"]) for r in sel]), imean([int(r["duration_ms"]) for r in sel]), len(sel))


def pct(a, b):
    return round((b - a) / a * 100, 1) if a else None


def verdict(diff, p):
    if diff is None:
        return VERDICT_SAME
    if p < ALPHA and diff >= MIN_EFFECT:
        return VERDICT_BETTER
    if p < ALPHA and diff <= -MIN_EFFECT:
        return VERDICT_WORSE
    return VERDICT_SAME


def aggregate(bench):
    plan = load_plan(bench)
    obs, warns = collect(bench, plan)
    metrics = read_metrics(bench)
    paired = plan["design"] == "paired-followup"
    arms = list(plan["arms"])
    task_ids = [t["id"] for t in plan["tasks"]]

    def runs_of(arm, task=None):
        return [r for r in plan["runs"] if r["arm"] == arm and (task is None or r["task"] == task)]

    def unit(rid):
        """The per-run outcome: v2 - v1 (paired) or the score itself (parallel)."""
        v1 = obs.get((rid, "v1"))
        if paired:
            v2 = obs.get((rid, "v2"))
            return v2["overall"] - v1["overall"] if v1 and v2 else None
        return v1["overall"] if v1 else None

    def summarise(arm, task=None):
        rs = runs_of(arm, task)
        ids = {r["id"] for r in rs}
        v1 = [obs[(r["id"], "v1")] for r in rs if (r["id"], "v1") in obs]
        out = {"runs": len(rs), "scored": len(v1)}
        tok1, ms1, _ = metric_means(metrics, ids, "v1")
        out.update(v1_mean=mean([o["overall"] for o in v1]), wrong_v1=mean([o["wrong"] for o in v1]),
                   chars_v1=imean([o["chars"] for o in v1]), tokens_v1=tok1, ms_v1=ms1)
        if paired:
            v2 = [obs[(r["id"], "v2")] for r in rs if (r["id"], "v2") in obs]
            ds = [d for d in (unit(r["id"]) for r in rs) if d is not None]
            tok2, ms2, _ = metric_means(metrics, ids, "v2")
            out.update(v2_mean=mean([o["overall"] for o in v2]), delta=mean(ds), deltas=ds,
                       wrong_v2=mean([o["wrong"] for o in v2]), chars_v2=imean([o["chars"] for o in v2]),
                       tokens_v2=tok2, ms_v2=ms2,
                       improved=sum(d > 0 for d in ds), same=sum(d == 0 for d in ds),
                       worse=sum(d < 0 for d in ds))
            out["length_pct"] = pct(out["chars_v1"], out["chars_v2"])
        return out

    res = {"design": plan["design"], "category": plan["category"], "placebo": PLACEBO,
           "arms": {}, "warnings": list(warns)}
    for arm in arms:
        a = {"all": summarise(arm), "tasks": {t: summarise(arm, t) for t in task_ids}}
        res["arms"][arm] = a
    base = res["arms"][PLACEBO]["all"]
    for arm in arms:
        a = res["arms"][arm]
        if arm == PLACEBO:
            a.update(verdict=VERDICT_REF, p=None, vs_placebo=None, pairs=None)
            continue
        pairs = []
        for r in runs_of(arm):
            mate = [m for m in runs_of(PLACEBO, r["task"]) if m["rep"] == r["rep"]]
            x, y = unit(r["id"]), unit(mate[0]["id"]) if mate else None
            if x is not None and y is not None:
                pairs.append(x - y)
        pos, neg = sum(d > 0 for d in pairs), sum(d < 0 for d in pairs)
        p = round(sign_test(pos, neg), 4)
        key = "delta" if paired else "v1_mean"
        diff = (round(a["all"][key] - base[key], 2)
                if a["all"][key] is not None and base[key] is not None else None)
        a.update(vs_placebo=diff, p=p, pairs={"better": pos, "same": len(pairs) - pos - neg, "worse": neg},
                 verdict=verdict(diff, p))
        if not paired:
            a["all"]["length_pct"] = pct(base["chars_v1"], a["all"]["chars_v1"])
    for t in task_ids:
        if paired:
            xs = [obs[(r["id"], "v1")]["overall"] for r in plan["runs"]
                  if r["task"] == t and (r["id"], "v1") in obs]
        else:
            xs = [obs[(r["id"], "v1")]["overall"] for r in runs_of(PLACEBO, t) if (r["id"], "v1") in obs]
        if xs and statistics.mean(xs) >= CEILING:
            res["warnings"].append(f"ceiling: task {t} baseline mean {mean(xs)} >= {CEILING}; little room "
                                   f"to improve, so a real effect cannot show. Make the task harder.")
    for arm in arms:
        n = res["arms"][arm]["all"]["scored"]
        if n < MIN_RUNS_PER_ARM:
            res["warnings"].append(f"n={n} scored runs for arm {arm} (< {MIN_RUNS_PER_ARM}): the sign test "
                                   f"cannot reach p < {ALPHA}; read the result as directional only")
        lp = res["arms"][arm]["all"].get("length_pct")
        if arm != PLACEBO or paired:
            if lp is not None and lp > LENGTH_WARN_PCT:
                ref = "v1" if paired else "placebo"
                res["warnings"].append(f"length: arm {arm} answers are {lp:+}% longer than {ref} "
                                       f"(> {LENGTH_WARN_PCT}%); a judge may be rewarding volume")
    return plan, res


def fmt(x, suffix=""):
    return "–" if x is None else f"{x}{suffix}"


def signed(x):
    return "–" if x is None else f"{x:+}"


def summary_table(plan, res):
    paired = res["design"] == "paired-followup"
    if paired:
        head = ["| arm | verdict | Δ v1→v2 | vs placebo | p | runs better/same/worse vs placebo | "
                "wrong claims v1→v2 | length v1→v2 | follow-up time |",
                "|---|---|---|---|---|---|---|---|---|"]
    else:
        head = ["| arm | verdict | mean score | vs placebo | p | runs better/same/worse vs placebo | "
                "wrong claims | length vs placebo | time |", "|---|---|---|---|---|---|---|---|---|"]
    rows = []
    for arm, a in res["arms"].items():
        s, pr = a["all"], a["pairs"]
        pcell = "–" if pr is None else f"{pr['better']}/{pr['same']}/{pr['worse']}"
        if paired:
            rows.append(f"| {arm} | {a['verdict']} | {signed(s['delta'])} | {signed(a['vs_placebo'])} | "
                        f"{fmt(a['p'])} | {pcell} | {fmt(s['wrong_v1'])}→{fmt(s['wrong_v2'])} | "
                        f"{fmt(s['length_pct'], '%')} | {fmt(ms_s(s['ms_v2']), 's')} |")
        else:
            rows.append(f"| {arm} | {a['verdict']} | {fmt(s['v1_mean'])} | {signed(a['vs_placebo'])} | "
                        f"{fmt(a['p'])} | {pcell} | {fmt(s['wrong_v1'])} | {fmt(s.get('length_pct'), '%')} | "
                        f"{fmt(ms_s(s['ms_v1']), 's')} |")
    return head + rows


def ms_s(ms):
    return None if ms is None else round(ms / 1000, 1)


def task_table(res):
    paired = res["design"] == "paired-followup"
    if paired:
        out = ["| task | arm | v1 | v2 | Δ | improved/same/worse | wrong v1→v2 | chars v1→v2 |",
               "|---|---|---|---|---|---|---|---|"]
    else:
        out = ["| task | arm | mean score | wrong claims | chars |", "|---|---|---|---|---|"]
    tasks = list(next(iter(res["arms"].values()))["tasks"])
    for t in tasks:
        for arm, a in res["arms"].items():
            s = a["tasks"][t]
            if not s["scored"]:
                continue
            if paired:
                out.append(f"| {t} | {arm} | {fmt(s['v1_mean'])} | {fmt(s['v2_mean'])} | {signed(s['delta'])} | "
                           f"{s['improved']}/{s['same']}/{s['worse']} | {fmt(s['wrong_v1'])}→{fmt(s['wrong_v2'])} | "
                           f"{fmt(s['chars_v1'])}→{fmt(s['chars_v2'])} |")
            else:
                out.append(f"| {t} | {arm} | {fmt(s['v1_mean'])} | {fmt(s['wrong_v1'])} | {fmt(s['chars_v1'])} |")
    return out


def cmd_aggregate(a):
    plan, res = aggregate(a.bench)
    if a.json:
        print(json.dumps(res, indent=1))
        return 0
    print("\n".join(summary_table(plan, res)))
    print()
    print("\n".join(task_table(res)))
    if res["design"] == "paired-followup":
        print()
        for arm, x in res["arms"].items():
            print(f"{arm}: per-run Δ {x['all']['deltas']}  improved={x['all']['improved']} "
                  f"same={x['all']['same']} worse={x['all']['worse']}")
    for w in res["warnings"]:
        print(f"  WARN  {w}")
    return 0


# ---------------------------------------------------------------- report
def cost_table(res):
    paired = res["design"] == "paired-followup"
    out = ["| arm | tokens v1 | time v1 | " + ("tokens v2 | time v2 |" if paired else ""),
           "|---|---|---|" + ("---|---|" if paired else "")]
    for arm, a in res["arms"].items():
        s = a["all"]
        row = f"| {arm} | {fmt(s['tokens_v1'])} | {fmt(ms_s(s['ms_v1']), 's')} |"
        if paired:
            row += f" {fmt(s['tokens_v2'])} | {fmt(ms_s(s['ms_v2']), 's')} |"
        out.append(row)
    return out


def headline(res):
    tested = {k: v for k, v in res["arms"].items() if k != PLACEBO}
    better = [k for k, v in tested.items() if v["verdict"] == VERDICT_BETTER]
    worse = [k for k, v in tested.items() if v["verdict"] == VERDICT_WORSE]
    if better:
        return f"{', '.join(better)}: {VERDICT_BETTER}."
    if worse and len(worse) == len(tested):
        return f"{', '.join(worse)}: {VERDICT_WORSE} than placebo."
    parts = "; ".join(f"{k}: {v['verdict']}" for k, v in tested.items())
    return f"No tested arm beat the placebo beyond noise ({parts})."


def cmd_report(a):
    plan, res = aggregate(a.bench)
    bench = pathlib.Path(a.bench).resolve()
    cat = res["category"]
    tested = {k: v for k, v in res["arms"].items() if k != PLACEBO}
    summary = summary_table(plan, res)
    verdict_lines = [f"- **{k}** — {v['verdict']} (vs placebo {signed(v['vs_placebo'])}, sign test p = "
                     f"{fmt(v['p'])}, {v['pairs']['better']} better / {v['pairs']['same']} same / "
                     f"{v['pairs']['worse']} worse matched runs)" for k, v in tested.items()]
    place = [f"- **{k}**: {PLACEMENT[cat][v['verdict']]}" for k, v in tested.items()]
    warns = [f"- {w}" for w in res["warnings"]] or ["- none"]
    method = ["```mermaid", "flowchart LR",
              f"    T[{len(plan['tasks'])} tasks with hidden ground truth] --> R[{len(plan['runs'])} isolated runs]"]
    if res["design"] == "paired-followup":
        method += ["    R --> V1[v1 answer] --> F[follow-up per arm] --> V2[v2 answer]",
                   "    V1 & V2 --> B[shuffled blind labels] --> J[judge per task] --> S[sign test vs placebo]"]
    else:
        method += ["    R --> A[one answer per arm prompt] --> B[shuffled blind labels] --> J[judge per task]",
                   "    J --> S[sign test vs placebo]"]
    method += ["```"]
    sections = [
        ("Verdict", "Is each prompt better than the placebo, and how sure", verdict_lines),
        ("Category and placement", "Where the prompt should live given the verdict",
         [f"Category: `{cat}` (design `{res['design']}`).", ""] + place),
        ("Warnings", "Why the numbers may not be trusted as-is", warns),
        ("Per task", "Which tasks moved and which hit the ceiling", task_table(res)),
        ("Cost", "Mean tokens and wall time each arm adds", cost_table(res)),
        ("Method", "How runs, blinding and judging were done",
         method + ["", f"Placebo-controlled; labels shuffled (seed in blind_key.json); verdict needs "
                   f"p < {ALPHA} and |vs placebo| >= {MIN_EFFECT}. Files: [INDEX.md](INDEX.md)."]),
    ]
    contents = ["## Contents", "", "| Section | Answers | Size |", "|---|---|---|"]
    for name, answers, body in sections:
        anchor = re.sub(r"[^a-z0-9 -]", "", name.lower()).replace(" ", "-")
        contents.append(f"| [{name}](#{anchor}) | {answers} | ~{len(body)} lines |")
    out = [f"# Prompt bench — {cat}", "", f"**Result:** {headline(res)}", ""] + summary + [""] + contents + [""]
    for name, _, body in sections:
        out += [f"## {name}", ""] + body + [""]
    write(bench, "REPORT.md", "\n".join(out))
    idx = [f"# Prompt bench — {cat}", "", f"**Result:** {headline(res)}", "",
           "| File | Answers |", "|---|---|",
           "| [REPORT.md](REPORT.md) | Verdict, placement, per-task numbers and cost |",
           "| [ARMS.md](ARMS.md) | The prompts tested and which runs used each (hidden from judges) |",
           "| [GROUND_TRUTH.md](GROUND_TRUTH.md) | Hidden answer key per task |",
           "| `plan.json` | Every run with its arm and the exact prompts sent |",
           "| `fixtures/<task>/` | The task inputs, as given to runners |",
           "| `runs/<task>-<n>/` | Raw answers (answer_v1.md, answer_v2.md) and code per run |",
           "| `snapshots/<run>/v1/` | Code as it stood after the first answer (code tasks) |",
           "| `blind/<task>/`, `blind_key.json` | Shuffled anonymised answers and the unblinding key |",
           "| `scores/<task>.json` | Judge scores with wrong claims and failed probes |",
           "| `metrics.csv` | Tokens and duration per run and phase |", ""]
    write(bench, "INDEX.md", "\n".join(idx))
    print(f"{TOOL}: wrote {bench / 'REPORT.md'} and {bench / 'INDEX.md'}")
    print(headline(res))
    return 0


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("init"); p.add_argument("bench"); p.add_argument("--spec", required=True)
    p = sub.add_parser("record"); p.add_argument("bench"); p.add_argument("--run", required=True)
    p.add_argument("--phase", choices=["v1", "v2"], required=True)
    p.add_argument("--tokens", type=int, required=True); p.add_argument("--ms", type=int, required=True)
    p = sub.add_parser("snapshot"); p.add_argument("bench"); p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("blind"); p.add_argument("bench"); p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("probe"); p.add_argument("bench"); p.add_argument("--label", required=True)
    p = sub.add_parser("judge-plan"); p.add_argument("bench"); p.add_argument("--task")
    p = sub.add_parser("aggregate"); p.add_argument("bench"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("report"); p.add_argument("bench")
    a = ap.parse_args()
    if not a.cmd:
        ap.print_usage(sys.stderr)
        return 2
    fn = {"init": cmd_init, "record": cmd_record, "snapshot": cmd_snapshot, "blind": cmd_blind,
          "probe": cmd_probe, "judge-plan": cmd_judge_plan, "aggregate": cmd_aggregate,
          "report": cmd_report}[a.cmd]
    if a.cmd != "init" and not pathlib.Path(a.bench).is_dir():
        print(f"{TOOL}: {a.bench} is not a directory", file=sys.stderr)
        return 2
    try:
        return fn(a)
    except Refused as e:
        print(f"{TOOL}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
