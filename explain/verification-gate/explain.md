# How the verification gate works

> **What:** Before Claude commits, pushes or opens a PR, it must hold a signed receipt showing the required checks passed on exactly the files going out.
>
> **How:** A wrapper runs each check and signs a receipt tied to a fingerprint of the files; hooks at commit time and at the end of a turn compare it with the files now.
>
> **Watch out:** It stops a confused agent, not a determined one: a script file is never read, and an agent that reads the signing key can forge a receipt.

Part page of the 100x plugin overview (explain/100x-plugin). Think of a bank teller who will not hand over cash without a signed slip, and the slip names the exact amount: change the amount by a cent and the slip is void. Here the slip is a receipt that 100x verified writes after your tests pass. It is signed with a key only your account holds and stamped with a fingerprint of every file git would commit. Guards at commit, push and PR time, and at the end of Claude's turn, compare that fingerprint with the files as they are now. An edit after the tests, a hand-written receipt, or a flag that skips git's own hooks is refused.

| | |
|---|---|
| subject | concept · repo `gauravprwl14/100x-engineer` |
| tier | heavy |
| generated | `100x flow build` from `scenario.json`; regenerate it, do not edit |

## Contents

| section | answers |
|---|---|
| [Before you watch](#before-you-watch) | what the change does for a user, what it covers and where it starts |
| [Terms](#terms) | the words a reader outside the module needs |
| [Diagrams](#diagrams) | the flow at a glance, as diagrams |
| [Workflow outline](#workflow-outline) | the code path as pseudocode, each line linked to its step |
| [Map](#map) | which boxes the scenarios use, their role and where they live in the code |
| [Verify, commit, push: one receipt carries all the way](#verify-commit-push-one-receipt-carries-all-the-way) | happy scenario `happy`: each step, what it changes and its evidence |
| [An edit after verifying: the commit and the stop are both held](#an-edit-after-verifying-the-commit-and-the-stop-are-both-held) | failure scenario `stale`: each step, what it changes and its evidence |
| [Shortcuts around the gate: each is caught, except code it never sees](#shortcuts-around-the-gate-each-is-caught-except-code-it-never-sees) | issue scenario `evasion`: each step, what it changes and its evidence |
| [What if the receipt were plain, unsigned JSON?](#what-if-the-receipt-were-plain-unsigned-json) | issue scenario `forge`: each step, what it changes and its evidence |
| [Fix: every entry is signed with a key only the receipt writer uses](#fix-every-entry-is-signed-with-a-key-only-the-receipt-writer-uses) | fix scenario `fix-sign`: each step, what it changes and its evidence |
| [Decision](#decision) | which option was chosen, against what, and when to revisit it |
| [Numbers](#numbers) | every number on the page and what backs it |
| [Code reference](#code-reference) | every function and class in the files behind the page: lines, purpose, who uses it |

## Before you watch

**When Claude says the tests pass and commits, you can trust the commit is the code that was tested: commit, push and PR are refused unless a signed receipt shows the required checks passed against those exact files.**

Why now: The failure no instruction reliably prevents is: run the tests, edit a file, commit. The tests did pass, the claim is technically true, and the committed code was never tested.

In this PR:

- Writing a receipt: the wrapper's refusals, the fingerprint, the signature, where the file lives
- The commit, push and PR gate: how it reads a command line, and when it denies, asks or stays silent
- The Stop gate: why ending a turn on unverified edits is blocked once
- The policy file: required checks bound to exact commands, block and off modes, and why the committed copy wins
- What goes wrong (an edit after verifying, skip flags, a weakened policy, a forged receipt) and what catches each
- Every function behind it, in the Code reference

Not in this PR:

- Which commands a repo should require (the language-verification skill)
- How the result is merged: required checks, CODEOWNERS (the review-gates skill)
- The advisory writing and scope warnings the same hook adds to PR bodies; they never change a decision
- The re-check pass at the end of a turn, which has its own page (explain/recheck)

| entry point | kind | animated in | note | evidence |
|---|---|---|---|---|
| 100x verified --name LABEL [-- COMMAND] | command | `happy` (Verify, commit, push: one receipt carries all the way) |  | `scripts/verified.py:233` |
| git commit, git push, gh pr create (PreToolUse hook on Bash) | event | `happy` (Verify, commit, push: one receipt carries all the way) |  | `hooks/hooks.json:31` |
| git tag, git merge, gh pr merge, npm publish and other publishers | event | not animated | same gate and same checks as a commit; not animated | `hooks/require_verification.py:782` |
| Claude ending its turn (Stop hook) | event | `stale` (An edit after verifying: the commit and the stop are both held) |  | `hooks/hooks.json:126` |
| A commit message carrying [skip-verify] | event | `evasion` (Shortcuts around the gate: each is caught, except code it never sees) |  | `hooks/require_verification.py:1243` |

## Terms

| term | means | example |
|---|---|---|
| `receipt` | A small file the wrapper writes after running a check: the command, its exit code, a fingerprint of the files and a signature. It lives inside the git folder, so it is never committed. | $(git rev-parse --git-path 100x/verification-receipt.json) |
| `fingerprint` | One hash over every file git would commit (tracked and new untracked files): its path, mode and content. Same files, same hash. Staging or committing moves no content, so it does not change. | 100x verify_fingerprint |
| `signature` | A stamp computed from the receipt entry and a secret key (HMAC-SHA256). Change one character of the entry and the stamp no longer matches. |  |
| `signing key` | The secret the signature is made with, kept in your home folder, readable only by you. | ~/.config/100x/receipt.key |
| `policy file` | The repo's list of required checks, each bound to its exact command, plus a mode: block (the default) or off. | {"required_checks": {"test": "npm test"}} |
| `fresh` | A receipt entry whose fingerprint equals the fingerprint of the files right now. Any other entry is stale and proves nothing about the current code. |  |
| `PreToolUse hook` | A script Claude Code runs before a tool call, here before every Bash command that mentions git, gh, commit, push or a publisher. It can deny, ask, or say nothing. |  |
| `Stop hook` | A script Claude Code runs when Claude tries to end its turn. It may block the stop once, with a reason Claude must act on. |  |
| `deny, ask, pass` | The gate's three answers: deny refuses the command; ask hands the choice to you; pass says nothing, so your own permission rules still apply. |  |
| `skip flag` | An option that makes git skip its own hooks without a trace: --no-verify, -n, or core.hooksPath set on the command line. The gate denies these. |  |
| `[skip-verify]` | The visible way to ship without verifying: put it in the commit message and you, not Claude, are asked to approve. |  |
| `fail open` | On an internal error, make no decision at all instead of blocking. Safe for your shell, but a quiet gate is not proof that anything was checked. |  |

## Diagrams

### What the verification gate is made of

```mermaid
mindmap
  %% level: 1
  root((verification gate))
    Receipt writer
      signs with your key
    Fingerprint
      every file git would commit
    Commit gate
      deny, ask or say nothing
    Stop gate
      blocks a turn once
    Policy file
      required checks
      block or off
```

Read outward from the centre: one tool writes the receipt, one hash ties it to the files, two hooks read it, and the policy says what must be in it.

Evidence: `scripts/verified.py:301`, `hooks/verify_fingerprint.py:4`, `hooks/require_verification.py:1300`, `hooks/stop_gate.py:58`, `hooks/receipts.py:25`

### Verify, commit, push: who calls whom

```mermaid
sequenceDiagram
  %% level: 2
  actor Claude
  participant Wrapper as 100x verified
  participant Tests as Your check command
  participant Receipt
  participant Gate as Commit gate
  participant Git as git and GitHub
  Claude->>Wrapper: 100x verified --name test
  Wrapper->>Tests: npm test
  Tests-->>Wrapper: exit code
  Wrapper->>Receipt: write signed entry with fingerprint
  Claude->>Gate: git commit
  Gate->>Receipt: check signature and fingerprint
  Gate-->>Claude: no decision, so it runs
  Claude->>Git: commit
  Claude->>Gate: git push
  Gate-->>Claude: HEAD tree equals verified content
  Claude->>Git: push
```

Top to bottom: the check runs once through the wrapper; the commit and the push each read the same receipt, because committing moves no content.

Animated in `happy`. Evidence: `scripts/verified.py:233`, `scripts/verified.py:301`, `hooks/require_verification.py:1275`, `hooks/require_verification.py:1300`, `hooks/require_verification.py:1202`

### The order the commit gate decides in

```mermaid
flowchart TD
  %% level: 2
  A[git commit, push or gh pr create] --> R{inside a git repo?}
  R -- no --> Q[no decision]
  R -- yes --> P{policy file?}
  P -- none --> N[note: not configured]
  P -- unreadable --> D0[deny: fix the policy]
  P -- mode off --> Q
  P -- block --> E{"skip flag such as --no-verify?"}
  E -- yes --> T{skip-verify tag too?}
  T -- no --> D1[deny: say so openly instead]
  T -- yes --> AS[ask you to approve]
  E -- no --> S{skip-verify tag?}
  S -- yes --> AS
  S -- no --> W{earlier part of the line can write files?}
  W -- yes --> D2[deny: run it separately]
  W -- no --> RC{signed receipt fresh for every required check?}
  RC -- no --> D3[deny: re-run verification]
  RC -- yes --> K{commit changes the policy, or push sends more than HEAD?}
  K -- yes --> D4[deny]
  K -- no --> OK[say nothing: your permission rules still apply]
```

Each diamond is one test in the gate, in source order; the first deny wins. A pass is silence, never an allow.

Evidence: `hooks/require_verification.py:1229`, `hooks/require_verification.py:1230`, `hooks/require_verification.py:1235`, `hooks/require_verification.py:1243`, `hooks/require_verification.py:1250`, `hooks/require_verification.py:1275`, `hooks/require_verification.py:1281`, `hooks/require_verification.py:1283`, `hooks/require_verification.py:22`

### When the Stop gate holds a turn

```mermaid
flowchart TD
  %% level: 2
  S[Claude tries to end its turn] --> A{this stop already blocked once?}
  A -- yes --> L[let it stop]
  A -- no --> M{policy in block mode?}
  M -- no --> L
  M -- yes --> U{uncommitted changes?}
  U -- no --> L
  U -- yes --> F{a fresh entry for every required check?}
  F -- yes, even a failing one --> L
  F -- no --> B[block once: here are the commands to re-run]
```

The Stop gate asks whether the checks ran on these files, not whether they passed; a failing check still lets the turn end, and the commit gate refuses it later.

Animated in `stale`. Evidence: `hooks/stop_gate.py:26`, `hooks/stop_gate.py:38`, `hooks/stop_gate.py:44`, `hooks/stop_gate.py:55`, absent: any read of a check's exit code in the Stop gate (`git grep` finds 0 in `hooks/stop_gate.py`), `hooks/stop_gate.py:58`

## Workflow outline

`verified(label, command): writing a receipt`, animated in `happy`:

```
policy = load_policy(root)          # committed copy if the worktree one differs  # step 3
key = load_key(create=True)         # ~/.config/100x/receipt.key, mode 0600  # step 6
if policy binds label and command != bound: refuse  # step 3
if runner variable set or program shadowed: refuse  # step 4
before = fingerprint(); rc = run(command); after = fingerprint()  # step 5
keep old entries only if fingerprint == after and signature ok
entry = {argv, exit_code: rc, fingerprint: after, policy_sha, at}  # step 6
entry.sig = hmac_sha256(key, entry + label)  # step 6
write <git dir>/100x/verification-receipt.json  # step 6
exit rc                             # the check's own exit code
```

`judge(action): the commit, push and PR gate`, animated in `happy`:

```
actions = parse_command(cmd)        # every commit, push, PR, publish in the line  # step 7
policy = load_policy(root)          # unreadable: deny  # step 8
if no policy: note("not configured"); if mode off: pass
if skip flag and no [skip-verify]: deny
if [skip-verify]: ask a human
if an earlier part of the line can write files: deny
if no receipt: deny("run the checks first")
problems = evaluate(receipt, fingerprint now, policy)  # step 8, 9
  commit: policy changed in this commit -> receipt must carry it
  push: every ref is HEAD and HEAD's tree == verified content  # step 11
problems ? deny : systemMessage("PASSED")   # never "allow"  # step 10
```

`stop_gate(): the end-of-turn check`, animated in `stale`:

```
if stop_hook_active: let the stop through   # blocks once, never loops
if no policy or mode != block: let it through  # step 10
if nothing uncommitted: let it through  # step 10
result = evaluate(receipt, fingerprint now)  # step 10
stale = no fresh entry or a required label missing   # exit code not read  # step 10
if stale: block("re-run: 100x verified --name ...")  # step 10
```

## Map

| node | role | code |
|---|---|---|
| You | client |  |
| Claude (the agent) | service | `skills/verification-gate/SKILL.md` |
| 100x verified (receipt writer) | service | `scripts/verified.py:212` |
| Your check command | external |  |
| Working tree (files git would commit) | store | `hooks/verify_fingerprint.py:72` |
| Signing key (your home folder) | store | `hooks/receipts.py:49` |
| Policy file (.claude/verification-policy.json) | store | `hooks/receipts.py:120` |
| Receipt (signed, in the git folder) | cache | `hooks/receipts.py:20` |
| Commit gate (PreToolUse hook) | edge | `hooks/require_verification.py:1216` |
| Stop gate (Stop hook) | edge | `hooks/stop_gate.py:18` |
| git and GitHub | external |  |

## Verify, commit, push: one receipt carries all the way

`happy` · happy


| # | what happens | state after | evidence |
|---|---|---|---|
| 1 | **You ask Claude to fix a bug and ship it** Committing, pushing and reporting work done are the moments the verification-gate skill fires for. | no change | `skills/verification-gate/SKILL.md:16` |
| 2 | **Claude edits a file** | tree[files] = `"v2"` | *inferred* |
| 3 | **Claude runs the check through the receipt writer** The policy binds the label test to one exact command, so recording anything else under that label is refused. | holds bound = `"npm test"` | `scripts/verified.py:233`, `scripts/verified.py:251` |
| 4 | **The writer refuses tricks that could fake a pass** Variables such as PYTEST_ADDOPTS or NODE_OPTIONS change what a check runs without changing its command line; a program first on the PATH from inside the repo or a temp folder could just exit cleanly. | no runner variables set; npm resolves outside the repo | `scripts/verified.py:259`, `scripts/verified.py:20`, `scripts/verified.py:118`, `scripts/verified.py:265` |
| 5 | **Fingerprint before, run the check, fingerprint after** If the check itself rewrites files (a formatter, a snapshot), the receipt is bound to the files after the run, since that is what would be committed. | holds before = `"v2"`; holds after = `"v2"` | `scripts/verified.py:270`, `scripts/verified.py:278`, `scripts/verified.py:281` |
| 6 | **The writer signs the entry and stores the receipt in the git folder** The signature covers the command, exit code, fingerprint, the policy's hash and the label. The file sits in the git folder, so it is never a change git add could commit. | receipt[test] = `"v2"`; holds k = `"present"` | `scripts/verified.py:301`, `hooks/receipts.py:86`, `hooks/receipts.py:81`, `scripts/verified.py:304`, `hooks/receipts.py:20` |
| 7 | **Claude runs git commit; the gate reads the command line first** The hook is routed on any of 8 text patterns words, then parses the line the way a shell would and lists every commit, push, PR or publish it would perform. | no change | `hooks/hooks.json:31`, `hooks/require_verification.py:1476`, `hooks/require_verification.py:747` |
| 8 | **The gate loads the committed policy and the receipt, and checks the signature** A policy that cannot be parsed is a deny: the gate will not guess what it meant. | cache hit; holds mode = `"block"` | `hooks/require_verification.py:1225`, `hooks/receipts.py:124`, `hooks/receipts.py:91` |
| 9 | **The gate fingerprints the files now and finds the receipt fresh** | holds now = `"v2"` | `hooks/require_verification.py:1275`, `hooks/receipts.py:251` |
| 10 | **The gate passes by saying nothing, and git commits** It never answers allow: that would also skip your own ask rules for the command, and a verification gate has no business granting permissions. | no change | `hooks/require_verification.py:1300`, `hooks/require_verification.py:22` |
| 11 | **The push reuses the same receipt, because committing moved no content** The fingerprint ignores HEAD and staging. The push gate also checks that each pushed branch is the checked-out commit and that its tree equals the verified files. | no change | `hooks/verify_fingerprint.py:11`, `hooks/verify_fingerprint.py:6`, `hooks/require_verification.py:1190`, `hooks/require_verification.py:1202` |

Step 3:

```
policy = load_policy(root)
if cmd != policy.required[label]: refuse
```

Step 6:

```
entry = {argv, exit_code, fingerprint: after, policy_sha, at}
entry.sig = hmac_sha256(key, entry + label)
write <git dir>/100x/verification-receipt.json
```

Step 7:

```
actions = parse_command(cmd)
for action in actions: judge(action)
```

## An edit after verifying: the commit and the stop are both held

`stale` · failure


Steps 1–6 are the same as `happy`; this table starts where it diverges.

| # | what happens | state after | evidence |
|---|---|---|---|
| 7 | **Claude makes one more small edit after the check passed** Any change to content git would commit, tracked or a new untracked file, changes the fingerprint. | receipt[test] = `"v2"` (stale); tree[files] = `"v3"` | `hooks/verify_fingerprint.py:4`, `hooks/verify_fingerprint.py:91` |
| 8 | **The commit is denied: the code changed after verification** The receipt is still there and still signed, but it describes different files. A pass from before an edit proves nothing about the edit. | cache hit; holds now = `"v3"`; denied = 1 | `hooks/receipts.py:258`, `hooks/require_verification.py:1275` |
| 9 | **Claude tries to end the turn and report done instead** The commit gate only fires when Claude tries to ship. An agent that edits and simply says done never tries, so this second hook exists. | no change | `hooks/stop_gate.py:5`, `hooks/hooks.json:126` |
| 10 | **The Stop gate blocks once and names the commands to re-run** Block mode, uncommitted changes, and no fresh entry for the required check: the reason lists the exact commands, or asks Claude to say plainly what was not verified. | cache hit | `hooks/stop_gate.py:38`, `hooks/stop_gate.py:44`, `hooks/stop_gate.py:51`, `hooks/stop_gate.py:55`, `hooks/stop_gate.py:58` |
| 11 | **Claude re-runs the check; the new receipt matches the files** | receipt[test] = `"v3"`; holds after2 = `"v3"` | `scripts/verified.py:278`, `scripts/verified.py:301` |
| 12 | **The commit now passes** | no change | `hooks/require_verification.py:1300` |

Step 10:

```
stale = not fresh or a required label missing
return block(rerun_hint(policy))
```

## Shortcuts around the gate: each is caught, except code it never sees

`evasion` · issue · origin: in-code · severity medium

Open: no fix is shown yet.

Steps 1–6 are the same as `happy`; this table starts where it diverges.

| # | what happens | state after | evidence |
|---|---|---|---|
| 7 | **A commit with --no-verify is denied** That flag skips git's own hooks without a trace; git accepts any unambiguous prefix of it, and so does the check. | denied = 1 | `hooks/require_verification.py:487`, `hooks/require_verification.py:1235`, `hooks/require_verification.py:669` |
| 8 | **An alias hiding the same flag is denied too** The gate expands git aliases, including one defined earlier in the same line, up to 4 levels deep, and reads the flags of the commit they expand to. | denied = 2 | `hooks/require_verification.py:675`, `hooks/require_verification.py:509`, `hooks/require_verification.py:51` |
| 9 | **An edit and a commit in one command line are denied** The gate judges before the line runs, so anything earlier in it that could change files would ship content the gate never saw. | denied = 3 | `hooks/require_verification.py:1051`, `hooks/require_verification.py:1250`, `skills/verification-gate/SKILL.md:80` |
| 10 | **A commit and a push in one line: the push is denied** When the gate judges, that commit has not happened, so the tree the push would send cannot be checked. | denied = 4 | `hooks/require_verification.py:1194` |
| 11 | **A commit that switches the policy off is denied** The policy file is left out of the fingerprint, so the receipt stays fresh. That is why the gate enforces the committed copy, and a commit that changes the policy needs a receipt recorded with the new policy in place. | policy[mode] = `"off"`; denied = 5 | `hooks/verify_fingerprint.py:20`, `hooks/receipts.py:111`, `hooks/require_verification.py:1154`, `hooks/require_verification.py:1281` |
| 12 | **The open way out asks you; a script file slips past unread** With [skip-verify] in the message, you are asked to approve, and the bypass is in the transcript. But the gate does not open script files: a commit inside one is never seen. This class is documented, not fixed. | the receipt was never checked for this commit | `hooks/require_verification.py:1243`, `skills/verification-gate/SKILL.md:73`, `hooks/require_verification.py:890`, `docs/SAFETY.md:262`, `skills/verification-gate/SKILL.md:168` |

## What if the receipt were plain, unsigned JSON?

`forge` · issue · origin: what-if · severity high

> What-if: this is not in the code. It shows why the real design is the way it is.

Fixed by: `fix-sign`.

Steps 1–2 are the same as `happy`; this table starts where it diverges.

| # | what happens | state after | evidence |
|---|---|---|---|
| 3 | **Claude skips the check and writes a passing receipt by hand** The code's own threat model says an audit found this was enough to pass the first, unsigned version. | receipt[test] = `"pass, hand-written"` | `hooks/receipts.py:7` |
| 4 | **The gate sees a receipt that says pass** | cache hit | *inferred* |
| 5 | **Code that was never tested is committed** | no test ever ran on these files | *inferred* |

## Fix: every entry is signed with a key only the receipt writer uses

`fix-sign` · fix


Steps 1–2 are the same as `forge`; this table starts where it diverges.

| # | what happens | state after | evidence |
|---|---|---|---|
| 3 | **Claude writes a receipt by hand anyway** The skill forbids it; the signature makes the rule mechanical. | receipt[test] = `"pass, hand-written"` | `skills/verification-gate/SKILL.md:52` |
| 4 | **The gate recomputes the signature with your key, and it does not match** One forged entry spoils the whole receipt: a receipt containing a forgery is not evidence of anything. | cache hit; holds k = `"present"`; denied = 1 | `hooks/receipts.py:91`, `hooks/receipts.py:81`, `hooks/receipts.py:245` |
| 5 | **Only the receipt writer, which runs the real command, produces a receipt that passes** | receipt[test] = `"v2"`; holds after = `"v2"` | `scripts/verified.py:234`, `scripts/verified.py:301`, `hooks/require_verification.py:1300` |
| 6 | **Still open by design: an agent that reads the key file can sign anything** The key sits in your home folder and Claude runs as you. Closing that takes an operating-system boundary: a permission deny rule on the key's folder, or a sandbox. | deny Read, Edit and Bash on ~/.config/100x to close it | `hooks/receipts.py:9`, `docs/SAFETY.md:254` |

Step 4:

```
ok = compare_digest(entry.sig, hmac_sha256(key, entry + label))
if not ok: deny("forged, edited by hand, or another key")
```

## Decision

| option | solves it | pros | cons |
|---|---|---|---|
| A signed receipt bound to file content, read by hooks at commit and at stop **(chosen)** | pass | An edit after the check is caught, whatever the clock says<br>A hand-written receipt is denied<br>Commit then push needs no second run | Stops a confused agent, not one that reads the key<br>Code run from a script file is never seen |
| An instruction: verify before saying done | fail | Nothing to build | Prose is what the model talks itself past at the moment it wants to finish |
| Record only that the tests passed recently | fail | Simple to check | An edit a minute after the tests still passes, which is the exact failure to catch |
| Run the whole suite inside the commit hook | fail | Nothing to forge | The hook has 30 s to answer<br>A slow gate on every commit gets switched off, which is worse than none |

**Deciding factor:** The failure is a passing test followed by an edit, so the proof must be tied to the exact content, and cheap enough to check on every commit.
**Revisit when:** Claude Code ships an operating-system boundary that keeps the key out of the agent's reach, or the parser learns to read script files.
**Source:** skills/verification-gate/SKILL.md (The problem this solves; Failure modes); hooks/receipts.py threat model; SOURCE: original

## Numbers

| name | value | tag | backed by |
|---|---|---|---|
| `route_ifs` | 8 text patterns | measured | grep -c '"if"' hooks/hooks.json (at 4bdb47e) |
| `gate_timeout` | 30 s | verified | `hooks/hooks.json:33` |
| `max_depth` | 4 levels | verified | `hooks/require_verification.py:51` |
| `key_bytes` | 32 bytes | verified | `hooks/receipts.py:73` |
| `age_example` | 120 minutes | verified | `skills/verification-gate/SKILL.md:114` |

## Code reference

Read from the code by `100x code_ref`: names, lines and docstrings are the code's own; a note is the page author's one-line summary.

### `scripts/verified.py`

Run a verification command and write a signed, content-bound receipt.

| symbol | lines | what it does | used by | branches |
|---|---|---|---|---|
| `runner_env_set` | 24–29 | The runner-altering variables that are set and non-empty. | `main` | 3 |
| `resolve_executable` | 96–122 | (path to run, its real path) for argv[0], or raise Refusal. | `check_executable` | 10 |
| `check_executable` | 141–149 | resolve_executable, plus the same rule for the interpreter an `env` shebang | `main` | 2 |
| `parse` | 193–209 | Splits the arguments into a label, default verify, and the command after the double dash. | `main` | 5 |
| `main` | 212–311 | The command: loads policy and key, refuses a command that differs from the bound one, a runner variable or a shadowed program, fingerprints before and after the run, signs the entry, keeps only signed entries still fresh, writes the receipt, and exits with the check's own code. | — | 33 |
| `_policy_sha` | 186–190 | Hash of the working copy of the policy file, or absent; stored in each entry so the gate can tell which policy a check ran under. | `main` | 1 |

### `hooks/receipts.py`

Receipt signing, policy loading and receipt evaluation.

| symbol | lines | what it does | used by | branches |
|---|---|---|---|---|
| `load_key` | 49–76 | Return the HMAC key bytes. Raises GateError with a fix-it message. | — | 11 |
| `_canonical` | 79–82 | The bytes that get signed: the entry without its signature, plus its label, as sorted compact JSON. | `sign` | 1 |
| `sign` | 85–86 | HMAC-SHA256 of the canonical entry with the key, as hex. | `signature_ok` | 0 |
| `signature_ok` | 89–91 | Recomputes the signature and compares it in constant time. | `evaluate` | 1 |
| `_read_policy_text` | 106–117 | Returns the committed policy instead of the working copy whenever the two differ, with a note saying so. | `load_policy` | 3 |
| `load_policy` | 120–159 | Return a policy dict, or None when the repo has not configured one. | — | 15 |
| `receipt_path` | 164–185 | The receipt's absolute path in the per-worktree git directory. | `read_receipt` | 6 |
| `read_receipt` | 196–213 | Opens the receipt without following a symlink: missing means none, unreadable or malformed raises with a re-run hint. | `evaluate` | 7 |
| `evaluate` | 216–289 | Judge the receipt against the current content and the policy. | — | 25 |
| `rerun_hint` | 292–301 | The exact receipt-writer commands to run, one line per required label. | — | 4 |

### `hooks/verify_fingerprint.py`

Content fingerprint of the working tree.

| symbol | lines | what it does | used by | branches |
|---|---|---|---|---|
| `repo_root` | 41–43 | The top folder of the git repository, or None outside one. | `snapshot`, `tree_fingerprint` | 2 |
| `snapshot` | 72–131 | Return {fingerprint, root, unstaged, untracked} or None outside a repo. | `fingerprint` | 22 |
| `_digest` | 134–140 | A sha256 over the path, mode and blob id of every entry, in path order. | `snapshot`, `tree_fingerprint` | 2 |
| `tree_fingerprint` | 143–164 | Fingerprint of a commit's tree in snapshot()'s format. | — | 5 |
| `fingerprint` | 167–169 | The snapshot's fingerprint alone, or None outside a repository. | — | 1 |

### `hooks/require_verification.py`

PreToolUse gate: block completion-shaped actions without fresh verification.

| symbol | lines | what it does | used by | branches |
|---|---|---|---|---|
| `main` | 1452–1470 | Reads the hook input, ignores anything but Bash, decides, and on a non-blocking result adds the advisory writing and scope warnings. | — | 12 |
| `decide` | 1473–1498 | Parses the command into actions, judges each once, and returns the worst: a deny or ask wins outright, otherwise the pass and note messages are joined. | `main` | 11 |
| `parse_command` | 1054–1078 | Emit, into state.actions, the gated Actions a shell command would perform. | `_unwrap`, `decide`, `parse_argv`, `parse_git` | 9 |
| `_segment` | 997–1051 | One simple command: tracks variables, exports and cd, parses the rest, and remembers the first earlier part that could change files. | `parse_command` | 33 |
| `_is_read_only` | 979–994 | True for commands that cannot change files, such as cd, ls, git status or git diff without an output file; a redirect or git -c makes it false. | `_segment` | 10 |
| `parse_git` | 623–701 | Reads git's own options such as -C, -c, git dir and work tree, expands aliases including ones set earlier in the line, then hands the subcommand on. | `parse_argv` | 33 |
| `_resolve_alias` | 606–620 | Looks up the alias from -c values first, then config files named in the environment, then the repository's git config. | `parse_git` | 10 |
| `_git_subcommand` | 735–774 | Turns a git subcommand into a gated action: commit with its flags, push with the refs it sends, tag, merge, plumbing; also records git add and alias definitions. | `parse_git` | 31 |
| `_commit_flags` | 490–522 | Return (evasion, commit_all, pathspec) from `git commit` arguments, skipping | `_git_subcommand` | 16 |
| `_is_no_verify` | 485–487 | True for --no-verify or any unambiguous prefix of it, as git itself accepts. | `_commit_flags`, `_git_subcommand` | 1 |
| `_shell_invocation` | 947–971 | (kind, script) for `sh [options] …`: kind is command (`-c SCRIPT`), file, stdin | `parse_argv` | 13 |
| `_fallback_actions` | 1081–1091 | Input the parser cannot follow: gate on a plain word match rather than let | `_emit_fallback`, `decide` | 3 |
| `judge` | 1216–1303 | Return (rank, output) for one action. rank: 0 pass, 1 note, 2 ask, 3 deny. | `decide` | 39 |
| `_policy_problems` | 1137–1159 | The policy file is excluded from the fingerprint so editing it does not | `judge` | 9 |
| `_push_problems` | 1167–1208 | A push sends commits, not the working tree the receipt describes. Every ref | `judge` | 13 |
| `deny` | 1096–1100 | Hook output that refuses the command, with the reason. | `judge` | 0 |
| `ask` | 1103–1107 | Hook output that asks a human to approve, with the reason. | `judge` | 0 |
| `note` | 1110–1113 | Hook output that adds a message for Claude and decides nothing. | `_with_findings`, `decide`, `judge` | 0 |

### `hooks/stop_gate.py`

Stop gate: do not end a turn on unverified changes.

| symbol | lines | what it does | used by | branches |
|---|---|---|---|---|
| `main` | 18–63 | Lets the stop through when already blocked once, outside a repo, without a block-mode policy or with nothing uncommitted; otherwise blocks once when no fresh entry covers every required check. | — | 21 |
