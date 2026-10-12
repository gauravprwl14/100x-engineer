---
name: recheck
description: >
  Re-check, double-check or "are you sure" on Claude's own just-given answer or edit in this
  session: assume a mistake, name 3 likely faults, verify each against the files, fix or cut.
  Also runs once automatically. Not for a PR or diff (→ diff-review).
---

# Re-check

A first answer that reads well can still be wrong in a way only a second look finds. In blind
A/B runs, no first answer to a silent money-parsing bug was safe (0/8); after any follow-up
pass, 7/8 were ([references/evidence.md](references/evidence.md)). The wording mattered far
less than doing the pass at all, so this skill makes the pass cheap and routine.

## Trigger

**Fire when:** the user asks to re-check, double-check, audit or verify the answer or edit
Claude just gave in this session ("are you sure?", "highest confidence?", "check again",
`/100x:recheck`); or the plugin's `Stop` hook blocks with the re-check prompt.

**Do not fire when:** reviewing a PR, a teammate's diff or your own diff before pushing
(→ `diff-review`); proving work is done before commit or push (→ `verification-gate`);
there is no prior answer in this session to audit.

## How it runs

| mode | what happens | set by |
|---|---|---|
| `auto` (default) | the `Stop` hook blocks once per substantive turn with the prompt as its reason | `HUNDREDX_RECHECK=auto` or config |
| `manual` | only when you type `/100x:recheck` | `HUNDREDX_RECHECK=manual` or config |
| `off` | never, subagents included | `HUNDREDX_RECHECK=off` or config |
| subagents (opt-in) | the same hook on `SubagentStop` re-checks a subagent's substantive turn | `subagents`: `"off"` (default), `"all"`, or a list of agent types; env `HUNDREDX_RECHECK_SUBAGENTS=off\|all\|a,b` |

A turn is **substantive** when it called `Write`, `Edit`, `MultiEdit` or `NotebookEdit`, or
its final answer is at least `min_chars` long. The hook skips a turn that already ran the
re-check (`/100x:recheck`, the prompt pasted, or a `Re-check:` line in the answer) and never
blocks twice for one stop (`stop_hook_active`). Stop hooks run in parallel, so when
`stop_gate.py` also blocks, both reasons arrive together; on the next stop neither blocks again.

Config, optional — the environment variable wins over the file:

```json
// ~/.config/100x/recheck.json
{ "mode": "auto", "min_chars": 1500, "subagents": ["100x:backend-engineer", "general-purpose"] }
```

A list entry matches the agent type exactly or without its plugin prefix (`backend-engineer`
matches `100x:backend-engineer`). The type comes from `SubagentStop`'s documented `agent_type`;
`agentType`, `subagent_type`, `agent_name` and the subagent's `.meta.json` are read as
fallbacks, **unverified** against every host version. The subagent's transcript is
`agent_transcript_path` if given, else `<session>/subagents/agent-<agent_id>.jsonl` beside the
main transcript, else that agent's sidechain entries in the main one.

**Cost.** Each re-check is one more model pass: about 1.5–2 minutes and a few thousand tokens
per substantive turn (round 2 follow-ups ran 90–118 s). Short Q&A turns pay nothing. Use
`manual` when speed matters more than a second look. With subagents on, **every substantive
subagent run takes ~1.5–2 min longer**, and parallel agents each pay it; an allowlist of the
agents that write code limits that.

## Steps (manual `/100x:recheck`)

| # | step |
|---|---|
| 1 | Take the latest answer or change in this session as the subject; if there is none, say so and stop |
| 2 | Apply the prompt in [references/recheck-prompt.md](references/recheck-prompt.md), verbatim |
| 3 | For each of the 3 suspected faults, open the file, run the command or read the doc that settles it |
| 4 | Reply with the corrected final answer only, then the one `Re-check:` line |

## Rules

1. The prompt text lives only in `references/recheck-prompt.md`; the hook and the manual
   command both use it unchanged, so a wording change is one edit and is re-measured.
   *Enforced by:* `bash tests/test_hooks_recheck.sh` (hook reason equals the file's block)

2. Settle each suspected fault from a source read in this pass — a file, a command's output,
   a doc — never from memory of what was written earlier. A fault you could not check is
   marked unverified, not declared fine.
   *Enforced by:* review

3. Fix what is real, keep what holds, and cut what is not needed for it to work. The re-check
   does not add scope: a checklist arm that invited additions made answers 32% longer.
   *Enforced by:* review

4. Output the final answer only, plus one line `Re-check: <what changed>` or
   `Re-check: no changes — verified <what>`. No "changes vs v1" section; graders marked
   process sections down, and the line is what tells the hook the pass already ran.
   *Enforced by:* `hooks/recheck_gate.py` (a `Re-check:` line suppresses the block)

5. One re-check per turn. A second pass found the defects; a third was never measured, and a
   loop would burn time on every stop.
   *Enforced by:* `stop_hook_active` check in `hooks/recheck_gate.py`, tested by
   `bash tests/test_hooks_recheck.sh`

## Verify

```bash
# the hook decides correctly, matches the prompt file, and fails open (~3s)
bash "$(100x root)/tests/test_hooks_recheck.sh"
100x lint_skills
# what mode is this machine in?
python3 -c 'import json,os,pathlib; p=pathlib.Path.home()/".config/100x/recheck.json"; print(os.environ.get("HUNDREDX_RECHECK") or (json.loads(p.read_text()) if p.exists() else "auto (default)"))'
```

## Failure modes

This skill rejects:

- **The confident first answer that passes the test and is still wrong.** H3: stripping every
  `,` made `"1,234.50"` parse, and silently turned `"12,50"` into 125000 cents (was an error).
  No first answer caught it; the second pass did in 7 of 8 runs.
- **"Re-checked, looks good"** with nothing opened → rule 2: each suspected fault names the
  file or command that settled it, or is marked unverified.
- **A re-check that grows the answer** — new sections, refactors, extra options → rule 3.
- **A "Changes after re-check" essay** before the answer → rule 4: answer, then one line.
- **A Stop hook that re-checks forever** → rule 5; the hook blocks once per stop.

Known limits: the pass is self-review by the same model, so it shares the first answer's blind
spots unless it actually reads the files; it is no substitute for `diff-review` by a second
reviewer or for a receipt from `verification-gate`. Wording effects between prompts were within
noise at n=6–8 per arm.

## Scale

`solo` and up. Pays most where no human reviews each answer — a solo developer with an agent,
or long autonomous runs. On a team it is a cheap pre-filter before human review, not a
replacement for it.

## Sources

- Blind A/B rounds, method and tables: [references/evidence.md](references/evidence.md).
  `SOURCE: original`
- Stop/SubagentStop `decision: block`, `reason`, `stop_hook_active`, `agent_type`,
  `last_assistant_message` (the transcript may lag the turn):
  https://code.claude.com/docs/en/hooks.md
- Self-review with grounding: Chain-of-Verification, arXiv:2309.11495; Self-Refine,
  arXiv:2303.17651; and the counterpoint that self-correction without external feedback can
  hurt, arXiv:2310.01798 — why rule 2 requires checking against files, not memory.
