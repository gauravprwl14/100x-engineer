# ADR-0006: Work record is private plain files in ~/.config/100x/work, backed up by the owner's own setup; the plugin never pushes

```json meta
{
  "id": "ADR-0006",
  "title": "Work record is private plain files in ~/.config/100x/work, backed up by the owner's own setup; the plugin never pushes",
  "status": "proposed",
  "date": "2026-10-30",
  "decided_by": "gaurav",
  "tags": [
    "safety",
    "work-continuity"
  ],
  "affects": [
    "prds/work-continuity/**",
    "scripts/work*.py",
    "hooks/**"
  ],
  "commit": "ad5da99",
  "assumptions": [
    {
      "id": "A1",
      "claim": "No plugin tool or hook pushes, or writes a ref, branch or file into the project repository for the work record",
      "verify": "! grep -rnE '\\[\"git\"[^]]*\"push\"|refs/100x' scripts/[a-z]*.py hooks/*.py",
      "revisit_when": "a request for the work record to be visible to teammates",
      "confidence": "high"
    },
    {
      "id": "A2",
      "claim": "The owner's backup tool syncs ~/.config/100x/work between laptops as an append-only mirror",
      "verify": "grep -qx '.config/100x/work union' \"$HOME/Sites/projects/rnd/claude-setup/mirrors.txt\"",
      "revisit_when": "claude-setup stops being the owner's backup, or the union mirror PR (gauravprwl14/claude-setup#1) is not merged",
      "confidence": "medium"
    },
    {
      "id": "A3",
      "claim": "A cloud session can start from a prompt that carries the brief (claude --cloud <description>)",
      "verify": "",
      "revisit_when": "the PRD's phase 0 tries it",
      "confidence": "low"
    }
  ],
  "options": [
    {
      "name": "private ref refs/100x/work in each project repo (ADR-0004)",
      "fit": "fail",
      "chosen": false,
      "why_not": "puts the record in the team's repository; the owner requires nothing there"
    },
    {
      "name": "Claude Code auto-memory (~/.claude/projects/<path>/memory)",
      "fit": "fail",
      "chosen": false,
      "why_not": "one folder per working path, so every worktree and each config dir gets its own; MEMORY.md is a single file several sessions edit"
    },
    {
      "name": "a dedicated private repository the plugin pushes to",
      "fit": "pass",
      "chosen": false,
      "why_not": "the plugin would push off the machine (docs/SAFETY.md); more moving parts than reusing the owner's existing backup"
    },
    {
      "name": "plain append-only files in ~/.config/100x/work, backed up by the owner's setup",
      "fit": "pass",
      "chosen": true,
      "why": "nothing in any project repository, the plugin never pushes, and the owner's existing backup restores it on a new laptop with no manual step"
    }
  ],
  "supersedes": "ADR-0004",
  "revisit_by": "2027-04-01"
}
```

## Context

The owner requires that nothing about the work record reaches a team repository, since teammates
do not use it, and that switching laptops needs no manual step. ADR-0004 (a private ref in each
project repository) and ADR-0005 (letting the plugin push it) are rejected for the first reason.
A solution-architect review on 2026-10-30 checked this design against the owner's backup tool.

## Options considered

### Option A — private ref in each project repository
Rejected: it lives in the team's repository.

### Option B — Claude Code auto-memory
Already backed up. Rejected: it is per working path and per config dir, so worktrees and the two
config dirs would each see a different record, and its single `MEMORY.md` breaks append-only writes.

### Option C — a dedicated private repository the plugin pushes to
Works from the cloud too. Rejected: the plugin would have to push, which `docs/SAFETY.md` rules out.

### Option D — plain files in `~/.config/100x/work` (chosen)
One event per uniquely named file. Claim locks and session cursors stay outside it, in
`~/.cache/100x`, because a claim only means something on one machine. Downside: a cloud
session cannot read it. It only gets the brief inside its starting prompt.

## Decision

Option D. The folder defaults to `~/.config/100x/work`, where the plugin already keeps its user-level
files, and `HUNDREDX_WORK_DIR` overrides it. Backup is not the plugin's job. The owner's claude-setup
mirrors the folder as an append-only `union` mirror. Anyone else can back up the plain files with
any tool, and `100x work doctor` says when none is set up.

## Consequences

Easy: no team exposure, no push in the plugin, and a laptop switch restores everything. Hard:
- Cloud sessions get the brief one way only, from the laptop.
- Two laptops agree only after each has synced.
- Erasing a leaked secret means rewriting claude-setup history. The plugin therefore refuses secret-like text when an event is written.

## Gaps accepted

| gap | consequence if hit | accepted? | follow-up |
|-----|--------------------|-----------|-----------|
| a cloud session cannot write back to the record | what it learns comes back only through the PR | accepted | `100x work cloud` passes the brief in the starting prompt (PRD phase 0 checks it works) |
| two laptops see each other's events only after a sync on each | a hold set on one laptop is unknown to the other for a while | accepted | claude-setup pushes a union mirror as soon as it changes |
| a user without claude-setup has no backup | the record is lost with the laptop | accepted | `100x work doctor` warns "not backed up" |
