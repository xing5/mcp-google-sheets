---
name: github-todo-triage
description: Use this skill in this repository when asked to fetch, review, triage, or update todos from GitHub issues and pull requests, especially for xing5/mcp-google-sheets. It defines the local workflow for refreshing GitHub state, reviewing new work, prioritizing next actions, and maintaining the repo todo status ledger.
---

# GitHub Todo Triage

Use this workflow when the user asks to check GitHub issues, pull requests, project todos, maintainer status, or what to work on next.

## State Files

- Status ledger: `TODO_STATUS.md`
- Raw GitHub snapshots: `.codex/github-todos/`
- Fetch helper: `.codex/skills/github-todo-triage/scripts/fetch-todos.sh`

## Workflow

1. Confirm the repo and account.
   - Run `git remote -v` and `gh auth status`.
   - Prefer the active `xing5` GitHub account when working on this repository.
   - Use `gh repo view --json nameWithOwner -q .nameWithOwner` or the `origin` remote to identify the GitHub repo.

2. Refresh GitHub state.
   - Run `.codex/skills/github-todo-triage/scripts/fetch-todos.sh`.
   - If the script fails, run equivalent `gh issue list` and `gh pr list` commands manually.
   - Do not close, merge, label, assign, or comment on GitHub unless the user explicitly asks.

3. Review open issues.
   - Group issues into: bugs/support, feature requests, docs/setup, ecosystem/registry, and stale or closeable.
   - Check whether `main` already implements the requested capability before treating an issue as active work.
   - For support issues, look for reproduction details, version, auth mode, transport, and client.

4. Review open PRs.
   - Check mergeability, conflicts, review comments, changed files, and overlap with other PRs.
   - Prefer small clean bugfix PRs before large overlapping feature/refactor PRs.
   - Treat conflicting PRs as active only after rebasing or replacing them against current `main`.

5. Enforce the test gate.
   - Do not implement or merge feature changes before defining the tests that prove the behavior.
   - Prefer unit tests with fake Google API services for request construction, argument handling, return shape, and error paths.
   - Use live Google integration tests only for behavior that cannot be validated with fakes, and keep them opt-in through environment variables.
   - For every PR, record whether tests are missing, unit-only, integration-ready, or verified live.

6. Update `TODO_STATUS.md`.
   - Preserve existing completed work and status notes unless they are superseded by fresh GitHub state.
   - Include the refresh date, source commands or snapshot path, priority buckets, active PR review queue, closeable issues, and open questions.
   - Mark items with clear statuses: `todo`, `review`, `blocked`, `closeable`, `merged`, or `done`.

7. Report to the user.
   - Lead with counts and highest-priority actions.
   - Separate "do now", "review/merge", "close or respond", and "backlog".
   - Mention files changed locally and any verification performed.

## Prioritization Rules

- P0: Bugs that break MCP stdio framing, startup, auth, or core read/write flows.
- P1: Clean, small PRs that unblock many users or fix support load.
- P2: User-visible features with clear scope and existing PRs.
- P3: Docs, registry/listing work, and ecosystem opportunities.
- Backlog: Broad platform features without a design, stale requests, and commercial solicitations.

## Test Requirements

- Baseline local command should be lightweight and credential-free.
- Live integration tests must require explicit opt-in, for example `RUN_GOOGLE_INTEGRATION=1`.
- Required live-test inputs should be paths or IDs, not pasted secrets:
  - `SERVICE_ACCOUNT_PATH` or `CREDENTIALS_CONFIG`
  - `DRIVE_FOLDER_ID` for a disposable test folder
  - Optional `TEST_SPREADSHEET_ID` for read/update tests against a pre-created disposable spreadsheet
- Tests that create files must name them with a clear temporary prefix and clean up when possible.
- Never run destructive live tests against user production spreadsheets.

## Useful Commands

```bash
.codex/skills/github-todo-triage/scripts/fetch-todos.sh
gh issue list --repo xing5/mcp-google-sheets --state open --limit 100
gh pr list --repo xing5/mcp-google-sheets --state open --limit 100
gh pr view <number> --repo xing5/mcp-google-sheets --json mergeStateStatus,mergeable,changedFiles,additions,deletions,latestReviews,statusCheckRollup,comments
gh issue view <number> --repo xing5/mcp-google-sheets --comments
```
