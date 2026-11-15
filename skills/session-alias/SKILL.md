---
name: session-alias
description: >
  Name this Claude Code session so it can be resumed later without its hex id: picks the name
  from what the session covered (<author>-pr-<number>-<topic> for a PR, a short kebab-case slug
  otherwise), saves it, and turns a saved name back into the resume command.
---

# Session alias

A session id like `861c70e3-3a1e-…` is useless a week later. This skill names the current
session from what it actually covered, the way a folder gets a label instead of a number, and
`100x session_alias resolve <name>` turns the label back into `cd <folder> && claude --resume
<id>`. To find a session by topic rather than by a name you gave it, use `session-find`.

## Trigger

**Fire when:** the user asks to "alias this session", "name this session", "give this session a
name", "save this session as …", or asks to resume a session by a name they gave it.

**Do not fire when:** the user wants to find which session worked on a topic they never named
(use `session-find`), or wants the most recent session (`claude --continue` already does that).

## Steps

| # | step |
|---|---|
| 1 | Read the whole conversation and choose the mode. **PR mode** when one GitHub PR was the real subject (reviewed, built, debugged or discussed in depth): `<author>-pr-<number>-<topic>`, the author being the PR's own author, the topic 2-4 words (`comments-backend`, `rate-limit-fix`). **General mode** otherwise: 3-6 words naming the outcome (`fix-whoami-race`, `album-thumbnail-cache-design`), prefixed with the repo when the slug alone does not say it |
| 2 | Run `100x session_alias set "<name>"`. It reads the session id from `$CLAUDE_CODE_SESSION_ID` itself |
| 3 | On `COLLISION:` (exit 1), sharpen the topic words or append `-2` and run step 2 again |
| 4 | Confirm in one line: the name and which mode produced it |
| 5 | To resume later: `100x session_alias list`, then `100x session_alias resolve <name>` and run the printed command |

## Rules

1. Never ask the user for the session id or the name. The id comes from
   `$CLAUDE_CODE_SESSION_ID` and the name from the transcript; a vague session gets a General
   mode name rather than a question.
   *Enforced by:* `bash "$(100x root)/tests/test_session_alias.sh"` ("no session id" case) —
   the tool refuses to guess an id.
   `SOURCE: original`: naming trivia is the interruption this skill exists to remove.

2. A name already pointing at a different session is never overwritten. The same name for the
   same session is a no-op.
   *Enforced by:* `bash "$(100x root)/tests/test_session_alias.sh"` ("collision" and
   "set again" cases)
   `SOURCE: original`.

3. Names created by ecc's `sessions` skill keep resolving: the store keeps its file and format
   (`~/.claude/session-aliases.json`, version 1.0), and an old entry resolves through the last
   8 hex characters of the session id in its summary-file name.
   *Enforced by:* `bash "$(100x root)/tests/test_session_alias.sh"` ("old ecc entry" and
   "old entries unchanged" cases)
   `SOURCE: original`: checked against this user's own store, which held 14 ecc-created names.

4. A session from `~/.cc-1` resolves to a command that sets `CLAUDE_CONFIG_DIR`, because
   `claude --resume` only searches its own config dir.
   *Enforced by:* `bash "$(100x root)/tests/test_session_alias.sh"` ("~/.cc-1 session" case)
   `SOURCE: original`.

5. Stdlib only, and the tool writes nothing but the alias file.
   *Enforced by:* convention

## Verify

```bash
100x session_alias --help                            # <1s, the tool is installed
bash "$(100x root)/tests/test_session_alias.sh"       # ~2s, full regression suite
100x session_alias list                              # real run against this machine's store
```

## Failure modes

This skill rejects:

- **Overwriting another session's alias**: a name from an older session silently repointed
  to this one → rule 2; exit 1 with `COLLISION:`.
- **A guessed session id** taken from the branch, worktree or most recent transcript → rule 1;
  without `$CLAUDE_CODE_SESSION_ID` the tool exits 2.
- **Losing every old name** when ecc is turned off → rule 3.
- **A resume command that says "no conversation found"** for a `~/.cc-1` session → rule 4.
- **A truncated store after a crash mid-write** → the store is written to a temp file and renamed.

## Scale

`solo`. One person's own session names on one machine; no shared state.

## Sources

`SOURCE: original`. The store format is the one ecc 2.2.1's `scripts/lib/session-aliases.js`
writes, read from that plugin's installed copy and this user's own store; the transcript layout
(`<home>/projects/<project-dir>/<session-id>.jsonl`, `cwd` on each record) is the one
`session-find` already relies on.
