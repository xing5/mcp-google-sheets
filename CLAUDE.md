# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run locally from the cloned repo:
```bash
uv run mcp-google-sheets
uv run mcp-google-sheets --transport sse   # SSE instead of stdio
```

Build and publish:
```bash
uv build       # produces dist/*.whl
uv sync        # install deps from uv.lock
```

Docker:
```bash
docker build -t mcp-google-sheets .
docker run --rm -p 8000:8000 \
  -e CREDENTIALS_CONFIG=<base64> \
  -e DRIVE_FOLDER_ID=<id> \
  mcp-google-sheets
```

There are no tests in this project.

## Architecture

All logic lives in a single file: `src/mcp_google_sheets/server.py`. `__init__.py` just re-exports `main()`.

**Startup / auth** (`spreadsheet_lifespan`): FastMCP lifespan context manager that authenticates on server start and injects a `SpreadsheetContext` (holding `sheets_service` and `drive_service`) into every tool call via `ctx.request_context.lifespan_context`. Auth is attempted in priority order: `CREDENTIALS_CONFIG` (base64 service account) → `SERVICE_ACCOUNT_PATH` → OAuth flow (`CREDENTIALS_PATH`/`TOKEN_PATH`) → Application Default Credentials.

**Tool registration** (`tool` decorator wrapper): A custom `@tool()` decorator wraps `@mcp.tool()`. It checks `ENABLED_TOOLS` (set via `ENABLED_TOOLS` env var or `--include-tools` CLI arg) and skips registration for any tool not in the allowlist. This is how tool filtering works — tools simply aren't registered with FastMCP rather than being conditionally hidden.

**Two Google API clients**: The server builds both a Sheets client (`sheets/v4`) and a Drive client (`drive/v3`). Most tools use only the Sheets client; `list_spreadsheets`, `create_spreadsheet`, `share_spreadsheet`, and `list_folders` use Drive. `create_spreadsheet` uses Drive to create the file (so it can place it in a folder), not the Sheets API.

**A1 notation helpers**: `_parse_a1_notation`, `_column_index_to_letter`, and `_letter_to_column_index` convert between A1 ranges and the 0-based row/column indices the Sheets batchUpdate API requires. The Sheets values API uses A1 notation directly; batchUpdate requires numeric indices — keep that distinction in mind when adding new tools.

**MCP resource**: There's one registered resource (`spreadsheet://{spreadsheet_id}/info`) that uses `mcp.get_lifespan_context()` (not `ctx`) because resources don't receive a `Context` argument the same way tools do.

**`batch_update` tool**: This is a passthrough to the Sheets `spreadsheets().batchUpdate()` endpoint and accepts raw request objects. It's the escape hatch for any operation not covered by the named tools (formatting, conditional formatting, dimension properties, etc.).

## Development workflow

**MCP restart**: After `docker compose restart mcp-google-sheets`, Claude Code does not automatically reconnect to the SSE server — you must restart Claude Code too to re-establish the connection.

## Style guidelines

**Log suppressions**: When silencing a noisy logger with `setLevel(logging.WARNING)`, always add an inline comment explaining why — e.g. `# suppress keepalive ping noise`.
