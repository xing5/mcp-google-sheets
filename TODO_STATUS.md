# mcp-google-sheets Todo Status

Last refreshed: 2026-05-14
Source: `gh` authenticated as `xing5`, repo `xing5/mcp-google-sheets`.

## Snapshot

- Open issues: 17
- Open pull requests: 9
- Current `main` already includes: Docker/SSE support, `CREDENTIALS_CONFIG`, folder targeting and `list_folders`, `search_spreadsheets`, `find_in_spreadsheet`, arbitrary `batch_update`, chart creation, tool filtering, ADC, and `include_grid_data`.
- Local verification run: `uv run python -m py_compile src/mcp_google_sheets/server.py`

## P0/P1: Do Next

- `done` Establish an initial test baseline before new feature work. Added credential-free unit tests around tool filtering, A1 helpers, request construction, return shapes, and selected error handling. Added opt-in Google integration tests for create/update/read/list/search flows.
- `todo` Resolve stdout logging risk: review PR #79 and PR #73 together. Current `main` still has diagnostic `print()` calls that can corrupt stdio JSON-RPC. PR #79 is clean and adds logging, timing, and `cache_discovery=False`; PR #73 is a smaller logging-only fix. Pick one path, avoid merging both blindly.
- `review` Confirm whether PR #65 is actually needed. Current decorator passes the original function directly to `mcp.tool()`, so the proposed wrapper may be unnecessary and could change MCP signature introspection in the wrong direction.
- `closeable` Close issue #53. Reporter retested, cannot reproduce, and explicitly asked to close.
- `todo` Add docs for service-account Drive quota behavior. Issues #40 and #75 are recurring reports that service accounts cannot create files in "My Drive" quota. Document OAuth vs service account behavior, Shared Drive workaround, and folder ownership expectations.
- `todo` Update Claude example prompts from issue #74 so examples explicitly use the Google Sheets MCP connector rather than encouraging local XLSX creation.

## PR Review Queue

- `review` #79 "Improve logging, add observability": clean, mergeable, 1 file, 44 additions. Highest-value candidate if logging/timing behavior is acceptable.
- `review` #73 "fix: use stdlib logging instead of print (stderr)": clean, mergeable, 1 file, small. Good fallback if #79 is too broad.
- `review` #68 "feat: add batching support and structured logging": clean but large and overlaps logging work. Review after deciding #79/#73. Consider splitting batching from logging/docs.
- `review` #67 "feat: add R1C1 formula format support": clean but large. Needs focused formula tests and API compatibility review.
- `review` #66 "chore: improve code quality with Gourmand AI standards": clean but broad refactor. Lower priority unless it reduces real maintenance risk.
- `review` #63 "Add comment management tools": conflicting. Rebase or replace before functional review.
- `review` #45 "feat: add format_cells tool": conflicting and requested by issue #25. Worth reviving because formatting demand is clear.
- `blocked` #39 "fix(server): change main to async def": conflicting and likely obsolete because current `main()` is sync and `mcp.run()` is sync-style.

## Issues: Close, Answer, or Narrow

- `closeable` #53 list_sheets only returns one sheet: user says fixed and asks to close.
- `closeable` #49 Docker/SSE mode: PR #50 merged. Leave a short note and close if current Docker instructions are sufficient.
- `closeable` #19 main transport parameters: current `main()` supports `--transport`, and host/port env vars are supported. Close or narrow to additional FastMCP kwargs.
- `closeable` #13 arbitrary batchUpdate: current `batch_update` exists. Close after checking docs mention Google request specs.
- `closeable or narrow` #76 cannot find sheet by name: `search_spreadsheets` exists on `main`. Update docs/examples, then close or ask reporter to retry latest.
- `answer` #56 Antigravity initialize EOF: ask for logs, transport, config, and version. Likely related to stdout logging; revisit after #79/#73.
- `todo` #44 Windows + WSL setup docs: add a Claude Desktop WSL config section and ensure logs go to stderr before recommending the setup broadly.
- `answer` #38 shifted column data: ask for version, exact tool call, and minimal reproduction. Could be model prompting or range construction, not yet actionable.
- `answer` #71 mctx hosting: business decision, not engineering work.
- `todo` #64 Docker MCP Toolkit: registry submission task.

## Feature Backlog

- `todo` #78 Canvas tools: research whether Google Sheets API exposes Canvas creation/update. If API coverage is absent, answer with limitation.
- `todo` #42 Tables API: design table create/read/update tools around Google Sheets tables API.
- `todo` #41 Cell notes: can be implemented through `batch_update`/`updateCells` notes; either document a recipe or add a dedicated helper.
- `todo` #25 Formatting: revive or replace PR #45; consider formatting, borders, number formats, alignment, and colors.

## Maintenance Notes

- Test policy: no new feature implementation should proceed without a written test plan and local unit tests. Live Google tests are opt-in through the `Google Integration Tests` workflow.
- Useful live-test setup: add GitHub secrets `GOOGLE_DRIVE_FOLDER_ID` and either `GOOGLE_SERVICE_ACCOUNT_JSON` or `GOOGLE_CREDENTIALS_CONFIG`. The folder must be disposable because tests create and delete spreadsheets.
- Once the new test workflow is merged, require the `Unit tests` check on PRs before reviewing feature changes.
- Many open issues are solved by current `main` but remain open because docs/comments were not updated.
- Prefer closing stale solved issues with a release/version note rather than leaving them as active backlog.
