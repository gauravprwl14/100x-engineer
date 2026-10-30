[PRD](../../prds/work-continuity/prd.md) · [ADR-0004](../../decisions/ADR-0004-shared-work-record-lives-in-an-opt-in-private-git-ref-refs-100x-work.md) · [ADR-0005](../../decisions/ADR-0005-plugin-may-fetch-and-push-refs-100x-only-gh-stays-read-only-supersedes-adr-0002-scope.md)

# work-continuity bench

**What it answers:** does a workstream brief actually help, and is the design buildable? Results so far:
with a ~1 KB brief injected at session start, a fresh session answered 7 of 7 workstream questions in all 3 runs,
against 2 of 7 without it, for 20% less cost and in about half the time. Neither arm guessed. The private-ref and
hook mechanics the design depends on all work locally. The cloud check has not run yet.

| part | measures | cost | status |
|---|---|---|---|
| `transcript_metrics.py` | PRD M1 (restated corrections per 100 prompts), M3 (fork share), compactions, from real transcripts | free | baseline below |
| `resume/` | PRD M2: can a fresh headless session state a multi-PR workstream's facts, with and without the brief | about $0.35 per 6-session run | run 2026-10-30, below |
| `spike/probe_ref.sh` | the remote accepts `refs/100x/*`, a normal clone does not fetch it, append races and claim CAS behave | free, pushes and deletes test refs | 8 of 8 passed |
| `spike/hook-probe/` | UserPromptSubmit can inject context; SessionEnd fires in `claude -p` | $0.005 | both confirmed |
| `spike/cloud_probe.sh` | inside `claude --cloud`: plugin loaded, `gh` signed in, private-ref push works | your cloud session | **not run** |

## Baseline (real use, before any change)

`python3 bench/work-continuity/transcript_metrics.py <session>.jsonl ...`, 2026-10-30:

| session | prompts | compactions | tokens main / sub | fork share | M1 per 100 | confusion per 100 | approval-only per 100 |
|---|---|---|---|---|---|---|---|
| 7f980c91 | 64 | 6 | 1.10 B / 0.96 B | 0% | 29.7 | 12.5 | 6.2 |
| a94b2d46 | 752 | 28 | 7.25 B / 10.25 B | 46% | 11.3 | 5.2 | 0.7 |

Re-run it on the first workstream done with phase 1 and compare against the PRD targets: M1 ≤ 3 and fork share ≤ 5%.

## Resume bench (controlled A/B)

A scaffolded repo holds one workstream: three PRs on stacked branches and an `integration` branch. Seven questions,
with hidden answers in `resume/answers.json`:
- q1 can be worked out from git;
- q2–q6 exist only in the record (a hold, the merge order, two decisions, the integration rule);
- q7 is recorded nowhere, so the right answer is "unknown".

The `brief` arm injects `resume/brief.md` through a SessionStart hook, which is how `100x work brief` would deliver it.
Both arms run with `--setting-sources project`, so the runner's own `~/.claude` rules cannot fill the gaps. An earlier
run without it answered q5 from a personal rule.

`bash bench/work-continuity/resume/run.sh --yes --runs 3` (Sonnet, 2026-10-30):

| arm | runs | correct (of 7) | from git (q1) | only in the record (q2–q6, of 5) | "unknown" when unknowable (q7) | confident-wrong | cost per run | turns | seconds |
|---|---|---|---|---|---|---|---|---|---|
| brief | 3 | 7.0 | 100% | 5.0 | 100% | 0.0 | $0.052 | 3.3 | 9 |
| none | 3 | 2.0 | 100% | 0.0 | 100% | 0.0 | $0.065 | 6.3 | 17 |

**What it shows:**
- the brief arrives through the hook, and the agent uses it correctly every time;
- the brief stays small (960 bytes);
- the brief arm is cheaper and faster;
- without the brief, the agent says "unknown" rather than guessing.

**What it does not show:**
- that the no-brief arm *could* have known q2–q6. It could not, by design. In real use those gaps are filled by you restating them, which is what M1 measures.
- anything about a large workstream. A brief built from months of events is the next test: grow `brief.md` toward the 3,000-token budget and add questions.
- statistical significance. Three runs per arm is a smoke-level sample.

## Run it

```bash
bash tests/test_work_continuity_bench.sh                 # offline: metrics and grader regression suite
python3 bench/work-continuity/transcript_metrics.py ~/.claude/projects/<project>/<session>.jsonl
bash bench/work-continuity/resume/run.sh                  # prints the cost and stops
bash bench/work-continuity/resume/run.sh --yes --runs 3   # 6 sessions; results in resume/results/ (not committed)
bash bench/work-continuity/spike/probe_ref.sh origin      # pushes refs/100x/probe-* and deletes them
```

Hook probe, by hand:

```bash
WORK_PROBE_LOG=/tmp/probe.log claude -p --plugin-dir bench/work-continuity/spike/hook-probe --model haiku \
  --max-budget-usd 0.05 "If your context has a line starting 'work-probe marker:', reply with its value, else NONE."
```

It should print `PROBE-7731`, and the log should hold a `UserPromptSubmit` line and a `SessionEnd` line.

Cloud check (phase 0, still open): start `claude --cloud` on this repo, on this branch, and ask it to run
`bash bench/work-continuity/spike/cloud_probe.sh`. Every check passing means the PRD's phase 2 can be built as designed.
Any failure means re-planning per PRD §8.
