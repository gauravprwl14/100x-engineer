---
name: session-find
description: >
  Which past Claude Code session built, reviewed or explained a feature (a tagging module, a PR,
  a spec): search ~/.claude and ~/.cc-1 session transcripts by keyword, ranked by recency, to
  resume the right one instead of starting over.
---

# Session find

Feature work routinely spans several sessions and worktrees — design, backend PR, frontend PR,
integration test, review pass — and weeks later there is no record of which session did it short
of grepping raw transcripts by hand. This is that grep, made repeatable: it searches every session
transcript under this user's Claude Code home directories and ranks the sessions that mention a
topic by how recently they were touched, so the right one can be resumed with `claude --resume`.

## Trigger

**Fire when:** the user asks which session implemented, reviewed, explained or discussed
something ("which session built the tagging module", "find the session for PR 1471", "where did
we design this", "resume the session on X").

**Do not fire when:** browsing session history chronologically or by alias (use the `sessions`
skill's `/sessions list` / `/resume-session`, which work on curated `~/.claude/session-data`
summaries, not raw transcripts); picking up the single most recent session (`claude --resume`
with no argument, or `/resume-session`, already does that).

## Steps

| # | step |
|---|---|
| 1 | Run `100x session_find "<topic>"` with the shortest phrase that names the feature |
| 2 | Read the ranked table: session ID, home (`.claude`/`.cc-1`), cwd, last-activity, hit count, snippet |
| 3 | If nothing useful surfaces, retry with a shorter or different phrase — matching is a literal substring, not semantic |
| 4 | Resume the chosen session: `claude --resume <session-id>` |
| 5 | For a sandboxed or non-default search location, pass `--roots <dir1>,<dir2>` explicitly |

## Rules

1. Only `"type":"user"` and `"type":"assistant"` lines count as a hit. Hook output,
   mode/permission records and other bookkeeping lines are skipped even when the keyword
   appears in them, so a tool invocation or config path never masquerades as a real mention.
   *Enforced by:* `bash "$(100x root)/tests/test_session_find.sh"` ("false positive" case)
   `SOURCE: original`: verified directly against this user's own session JSONL files — hook and
   mode records routinely echo tool/file names that are unrelated to what the session was about.

2. The default search scope is exactly `~/.claude/projects` and `~/.cc-1/projects`, whichever
   exist — never silently more, never silently fewer. `--roots` overrides it for a sandbox or a
   test fixture, and only then.
   *Enforced by:* `bash "$(100x root)/tests/test_session_find.sh"` (default-roots cases)
   `SOURCE: original`: this user runs two separate Claude Code home directories day to day; a
   tool that only checked `~/.claude` would silently miss half the history.

3. "No session matched" (exit 1) and "the search could not run" (exit 2, e.g. neither home
   directory exists) are different outcomes and must never share an exit code — a caller or
   script branching on this tool cannot otherwise tell "nothing to resume" from "broken".
   *Enforced by:* `bash "$(100x root)/tests/test_session_find.sh"` (no-match / missing-roots cases)

4. Stdlib only — no new dependency, matching this plugin's own rule.
   *Enforced by:* convention

5. Read-only: the scan never writes to, truncates, or renames a session file. A corrupt trailing
   line in an old transcript is skipped, never repaired or deleted.
   *Enforced by:* review

## Verify

```bash
100x session_find --help                            # <1s — confirms the tool is installed
bash "$(100x root)/tests/test_session_find.sh"       # ~4s — full regression suite, exits non-zero on any failure
100x session_find "<topic>" --limit 5                # real run against this machine's own history
```

## Failure modes

This skill rejects:

- **A hook-output line that happens to contain the keyword** (e.g. `"ran hook for tagging module
  config sync"`) being reported as a real mention → rule 1; only `user`/`assistant` turns count.
- **A corrupt or half-written trailing line aborting the whole scan**, hiding a real hit earlier
  in the same file → `search_session` skips an unparsable line and keeps going.
- **Only `~/.claude` being searched** when the topic was actually discussed in a `~/.cc-1`
  session (or vice versa) → rule 2; both default homes are always checked.
- **"Nothing matched" and "the tool is broken" reported the same way** → rule 3; exit 1 vs exit 2.

## Scale

`solo`. This is one person's own cross-machine session history; it has no shared-state, authz or
multi-tenant dimension.

## Sources

`SOURCE: original`. No production repo documents "search your own Claude Code session
transcripts by keyword" — the JSONL record shape this tool relies on (`type`, `message.content`,
`cwd`, one `<uuid>.jsonl` file per session under `<home>/projects/<project-dir>/`) was verified
directly against this user's own `~/.claude/projects` and `~/.cc-1/projects` files, not against
any published schema.
