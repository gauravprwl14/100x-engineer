---
name: codebase-comprehension
description: >
  Use when asked to understand, explain, or onboard to a feature or module someone
  else built — "how does X work", "explain this flow", "why is this shaped this
  way", tracing a bug to its origin, or before modifying code you did not write and
  do not yet understand. Gives a fixed order of operations (entry points, data flow,
  boundaries, the one hot file) that avoids reading the whole repo, and a stop
  condition so investigation ends on understanding rather than on exhaustion. Use
  PROACTIVELY before touching unfamiliar code, not after getting confused by it.
---

# Codebase comprehension

Reading everything is not a strategy, it is the absence of one — it does not scale
past a few hundred files and it produces no signal about which files mattered. The
alternative is a fixed order that narrows fast: entry points tell you what the system
is *for*, data flow tells you what actually happens, boundaries tell you where it can
fail, and the one hot file is where most of the real logic lives. Stop there unless
evidence says otherwise.

## Trigger

**Fire when:** asked to explain or understand a feature/module you did not write;
about to modify code you do not yet understand; tracing a bug to its cause;
onboarding to a new repo or subsystem.

**Do not fire when:** reviewing a diff someone wrote — that is `reviewing-others-code`
(intent + risk, not comprehension) or `scoped-review` (defect classes) or
`stack-reviewer` (framework failure modes). Writing new code from a spec is
`feature-planning`. Recording a decision after the fact is `decision-log`, searching
across many past records is `engineering-ledger`. Something is actually broken and
you need a causal chain to production — that's `root-cause-analysis`, which adds
timeline reconstruction and a regression-test gate this skill has neither of; use
this skill first only to build the mental model `root-cause-analysis` then reasons
over. A file under ~100 lines with no unfamiliar imports — just read it; process
overhead on a trivial read is how process gets abandoned.

## Order of operations

Follow this order. Do not start at step 4 because the file "looks interesting" —
that is exactly the file whose neighbors you do not yet know matter.

1. **Entry points.** `python3 scripts/repo_map.py <root>` — orientation summary:
   stacks, entry points (route decorators, `main`, CLI registration, exported
   handlers), the most-connected files, test-to-source ratio, and which docs exist.
   Open the entry point it names, not the file that sounds central.
2. **Data flow.** From the entry point, follow one request or call all the way
   through — trace calls and assignments, not files in alphabetical order.
   `python3 scripts/repo_map.py <root> --symbol <Name>` jumps from an identifier to
   its definition and every file that references it, instead of grepping blind.
3. **Boundaries.** Name every boundary the flow crosses before reading implementation
   detail inside any one of them — network call, DB, queue, auth check, external
   service, filesystem, clock. A boundary is where production behavior can diverge
   from what a read-through implies (retries, partial failure, stale cache).
4. **The one hot file.** Read fully only the single most-connected file the flow
   passes through — `repo_map.py`'s ranking, or the file every boundary calls back
   into. That is usually where the real logic lives; everything around it is wiring.

## Use the repo's own evidence first

The maintainers already told you what matters; re-deriving it from the diff is
slower and less reliable.

- **AGENTS.md / CLAUDE.md / CONTRIBUTING** — what the maintainers say matters. Read
  before source, not after getting confused by it.
- **Test names**, not comments, for intended behavior. A comment can drift from the
  code silently; a test that still passes is at minimum internally consistent with
  it. (Same asymmetry `scoped-review`'s R5 uses from the review side: derive the
  expectation before reading the implementation.)
- **`git log -S<symbol> --oneline -- <path>`** (the pickaxe) finds the commit that
  introduced or changed a symbol — why the code is shaped this way, not just what
  shape it is now.
- **`git log --follow -p <file>`** — a file's real history including renames. Blame
  on the current shape alone misses the shape it used to be and why it moved.
- **CODEOWNERS** (`.github/CODEOWNERS`, `CODEOWNERS`) — who to ask when the history
  does not explain it. Absent in many repos (this one included); say so rather than
  guessing an owner.
- **`python3 scripts/decide.py trace <path>`** — which recorded decision, if any,
  governs this file. A shape with an ADR behind it is a decision; a shape with none
  might be one nobody wrote down, or might be nothing — both are worth knowing before
  you propose changing it.
- **`python3 scripts/ledger.py find <term>`** — search past decisions, specs, RCAs and
  reviews before re-deriving an answer someone already worked out
  (`skills/engineering-ledger`).

## Generate the diagram, don't write prose

`scripts/diagram_from_code.py <path> --kind sequence|flow|deps --level 1|2|3` is the
primary comprehension output — a generated diagram of the actual call/data flow, not
a hand-drawn approximation or a wall of prose. Use it once the entry point and rough
flow are known (step 2), to confirm the trace and show boundaries (step 3) in one
picture. Do not hand-build a second diagramming path in this skill; that tool owns it.

## Rules

1. Follow the four-step order (entry points → data flow → boundaries → hot file).
   Skipping to implementation detail before naming the boundaries is how a "fix" adds
   a bug at a boundary nobody named.
   *Enforced by:* review

2. Run `repo_map.py` before reading any file by hand. It is cheaper than exploring
   blind and it is deterministic, so two people orienting on the same repo get the
   same starting point.
   *Enforced by:* `python3 scripts/repo_map.py <root>`

3. State every finding as a claim with `file:line` evidence, tagged **verified by
   reading code** or **inferred**. An inferred claim presented as fact is the
   specific failure this skill exists to prevent.
   *Enforced by:* review

4. Check the repo's own evidence (AGENTS.md, tests, `git log -S`/`--follow`,
   CODEOWNERS, `decide.py trace`) before concluding a shape is accidental or wrong.
   *Enforced by:* `python3 scripts/decide.py trace <path>`

5. Generate the diagram rather than writing a prose walkthrough, once the rough flow
   is known.
   *Enforced by:* `python3 scripts/diagram_from_code.py <path> --kind sequence --level 1`

6. Stop when you can state the inputs, outputs, failure modes, and the one thing most
   likely to break — not when you have read every file the flow touches.
   *Enforced by:* review

7. Record what you learned if the shape was non-obvious, so the next person does not
   repeat the investigation — `decide.py new` if it is a decision worth tracking,
   otherwise search first with `ledger.py find` so you are not re-deriving a past
   answer.
   *Enforced by:* `python3 scripts/ledger.py find "<topic>"`

## Verify

```bash
# 1. orientation — entry points, most-connected files, docs worth reading (~1s)
python3 scripts/repo_map.py <root>

# 2. trace a specific symbol: definition + every referencing file (~1s)
python3 scripts/repo_map.py <root> --symbol <Name>

# 3. why is it shaped this way (~1s each; both need a git repo -- say so if absent)
git log -S<symbol> --oneline -- <root>
git log --follow --oneline <path>

# 4. is there a decision or a ledger entry behind this shape already (~1s)
python3 scripts/decide.py trace <path>
python3 scripts/ledger.py find "<topic>"

# 5. the primary comprehension artifact, once the rough flow is known
python3 scripts/diagram_from_code.py <path> --kind sequence --level 1
```

## Failure modes

This skill rejects:

- **Reading files in whatever order they were opened**, rather than entry point →
  data flow → boundaries → hot file. This is how a reviewer ends up deeply familiar
  with a utility file and vague about the actual request path.
- **A claim with no `file:line`.** "It looks like this validates the token" is not
  evidence; `auth.service.ts:34` is.
- **An inferred claim stated as fact.** "This retries on failure" when what was
  actually verified is "I did not see a retry, so I assume there is one" — the
  opposite of what was checked.
- **Stopping at "I read it" instead of "I can state the inputs, outputs, failure
  modes, and the one thing most likely to break."** The former is a token count; the
  latter is understanding.
- **Re-deriving a shape's reasoning from scratch** when `git log -S`, `decide.py
  trace`, or `ledger.py find` would have surfaced it in one command.
- **Treating a comment as ground truth for intended behavior** when a test exists
  that would have shown the comment is stale.

**Honest limitations:**
- `repo_map.py`'s ranking is in-degree over a regex-resolved import graph for
  Python/JS/TS only (`scripts/repo_map.py`, module docstring) — a cheaper
  approximation of aider's tree-sitter + PageRank repo-map
  (`Aider-AI/aider@main:aider/aider/repomap.py`, see
  `research/22-findings-agent-tool-internals.md`). Other languages are counted but
  not ranked; the tool says so rather than silently reporting 0.
- `git log -S`/`--follow` only work in a git repo with real history; a shallow clone
  or squash-merged history weakens both. Say so rather than presenting a thin history
  as "nothing changed here."
- Step 4 (the "one hot file") is a heuristic, not a guarantee — a flow can have two
  equally load-bearing files. If `repo_map.py`'s ranking gives no clear single
  answer, read the top two rather than forcing a single pick.

## Next

Now that you understand it: modifying it goes to `feature-planning` (new behavior)
or `bug-fix` (something's broken and the cause is now obvious) or
`root-cause-analysis` (broken and the cause is still not obvious). Reviewing someone
else's change to it is `reviewing-others-code`. Either way, record what you learned
if it was non-obvious (rule 7) before it's lost again.

## Scale

`solo` and up. At `solo` this is the only way an agent orients on unfamiliar code
without a teammate to ask. At `small-team` and `org` it is what keeps onboarding time
from scaling linearly with repo size, and `engineering-ledger` is what keeps the
second person from re-deriving what the first one already found.

## Sources
- The repo-map algorithm this script's ranking approximates, and the exact lines
  cited: `Aider-AI/aider@main:aider/aider/repomap.py:233,365,472-511,525,629-710`,
  summarized in `research/22-findings-agent-tool-internals.md`
  ("Context selection / repo-map algorithms").
- `scripts/repo_map.py`, the order-of-operations, and the claim/evidence labeling
  discipline: `SOURCE: original`.
- The test-names-over-comments asymmetry: the same distinction `skills/scoped-review`
  (R5) uses from the review side.
- `decide.py trace` / `ledger.py find` and the traceability matrix they read:
  `skills/decision-log`, `skills/engineering-ledger`.
- `scripts/diagram_from_code.py` (`--kind sequence|flow|deps --level 1|2|3`): built by
  a sibling effort in this plugin; referenced here as the primary comprehension
  output rather than duplicated.
