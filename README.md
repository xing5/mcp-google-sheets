# mcp-google-sheets: A Google Sheets MCP server

This MCP server integrates with your Google Drive and Google Sheets, to enable creating and modifying spreadsheets.

## Overview

A Model Context Protocol server for interacting with Google Sheets. This server provides tools to create, read, update, and manage spreadsheets through the Google Sheets API.

### Tools

1. `get_sheet_data`
   - Get data from a specific sheet in a Google Spreadsheet
   - Input:
     - `spreadsheet_id` (string): The ID of the spreadsheet (found in the URL)
     - `sheet` (string): The name of the sheet
     - `range` (optional string): Cell range in A1 notation (e.g., 'A1:C10')
   - Returns: A 2D array of the sheet data

2. `update_cells`
   - Update cells in a Google Spreadsheet
   - Input:
     - `spreadsheet_id` (string): The ID of the spreadsheet
     - `sheet` (string): The name of the sheet
     - `range` (string): Cell range in A1 notation
     - `data` (2D array): Values to update
   - Returns: Result of the update operation

3. `batch_update_cells`
   - Batch update multiple ranges in a Google Spreadsheet
   - Input:
     - `spreadsheet_id` (string): The ID of the spreadsheet
     - `sheet` (string): The name of the sheet
     - `ranges` (object): Dictionary mapping range strings to 2D arrays of values
   - Returns: Result of the batch update operation

4. `list_sheets`
   - List all sheets in a Google Spreadsheet
   - Input:
     - `spreadsheet_id` (string): The ID of the spreadsheet
   - Returns: List of sheet names

5. `list_spreadsheets`
   - List all spreadsheets in the configured Google Drive folder
   - Returns: List of spreadsheets with their ID and title
   - Note: If using service account authentication, this will list spreadsheets in the shared folder

6. `create_spreadsheet`
   - Create a new Google Spreadsheet
   - Input:
     - `title` (string): The title of the new spreadsheet
   - Returns: Information about the newly created spreadsheet including its ID
   - Note: When using service account authentication with a configured folder ID, the spreadsheet will be created in that folder

7. `create_sheet`
   - Create a new sheet tab in an existing Google Spreadsheet
   - Input:
     - `spreadsheet_id` (string): The ID of the spreadsheet
     - `title` (string): The title for the new sheet
   - Returns: Information about the newly created sheet

8. `get_multiple_sheet_data`
   - Get data from multiple specific ranges in Google Spreadsheets
   - Input:
     - `queries` (array of objects): Each object specifies 'spreadsheet_id', 'sheet', and 'range'
   - Returns: List of objects, each containing the query parameters and fetched 'data' or 'error'

9. `get_multiple_spreadsheet_summary`
   - Get a summary of multiple Google Spreadsheets (title, sheet names, headers, first few rows)
   - Input:
     - `spreadsheet_ids` (array of strings): List of spreadsheet IDs
     - `rows_to_fetch` (optional integer, default 5): Number of rows (including header) to fetch
   - Returns: List of objects, each representing a spreadsheet summary

10. Additional tools: `add_rows`, `add_columns`, `copy_sheet`, `rename_sheet`

11. `share_spreadsheet`
    - Share a Google Spreadsheet with multiple users via email, assigning specific roles.
    - Input:
      - `spreadsheet_id` (string): The ID of the spreadsheet to share.
      - `recipients` (array of objects): List of recipients, each with 'email_address' and 'role' ('reader', 'commenter', 'writer').
      - `send_notification` (optional boolean, default True): Whether to send notification emails.
    - Returns: Dictionary with lists of 'successes' and 'failures'.

### Resources

1. `spreadsheet://{spreadsheet_id}/info`
   - Get basic information about a Google Spreadsheet
   - Returns: JSON string with spreadsheet information

## Installation and Setup

The server requires some setup in Google Cloud Platform and choosing an authentication method before running.

### Google Cloud Platform Setup (Required for All Methods)

1. Create a Google Cloud Platform project:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Sheets API and Google Drive API

### Choose an Authentication Method

You can use one of two authentication methods:

#### Method 1: Service Account Authentication (Recommended)

Service accounts provide headless authentication without browser prompts, ideal for automated or server environments. Benefits include:
- No browser interaction needed for authentication
- Works well in headless environments
- Authentication doesn't expire as frequently as OAuth tokens
- Perfect for server deployments and automation

Setup steps:

1. Create a service account:
   - Go to Google Cloud Console → IAM & Admin → Service Accounts
   - Create a new service account with a descriptive name
   - Grant it appropriate roles (for Google Sheets access)
   - Create and download a JSON key file

2. Create a dedicated folder in Google Drive to share with the service account:
   - Go to Google Drive and create a new folder (e.g., "Claude Sheets")
   - Note the folder's ID from its URL: `https://drive.google.com/drive/folders/FOLDER_ID_HERE`
   - Right-click the folder and select "Share"
   - Share it with the service account email address (found in the JSON file as `client_email`)
   - Give it "Editor" access

3. Set these environment variables:
   - `SERVICE_ACCOUNT_PATH`: Path to service account JSON key file
   - `DRIVE_FOLDER_ID`: ID of the Google Drive folder shared with the service account

#### Method 2: OAuth 2.0 Authentication (Interactive)

This method requires browser interaction for the first-time setup, suitable for personal use or development.

1. Configure OAuth for your project:
   - Configure the OAuth consent screen
   - Create OAuth 2.0 Client ID credentials (Desktop application type)
   - Download the credentials JSON file and save it as `credentials.json`

2. Set these environment variables:
   - `CREDENTIALS_PATH`: Path to the downloaded OAuth credentials file (default: `credentials.json`)
   - `TOKEN_PATH`: Path where the authentication token will be stored (default: `token.json`)

### Setting Environment Variables

For Linux/Mac:
```bash
# For service account authentication (recommended)
export SERVICE_ACCOUNT_PATH=/path/to/your/service-account-key.json
export DRIVE_FOLDER_ID=your_shared_folder_id_here

# OR for OAuth authentication
export CREDENTIALS_PATH=/path/to/your/credentials.json
export TOKEN_PATH=/path/to/your/token.json
```

For Windows:
```cmd
# For service account authentication (recommended)
set SERVICE_ACCOUNT_PATH=C:\path\to\your\service-account-key.json
set DRIVE_FOLDER_ID=your_shared_folder_id_here

# OR for OAuth authentication
set CREDENTIALS_PATH=C:\path\to\your\credentials.json
set TOKEN_PATH=C:\path\to\your\token.json
```

## Running the Server

### Method 1: Using uvx (recommended for normal use)

When using [`uvx`](https://docs.astral.sh/uv/guides/tools/), you can run the server directly without installation:

```bash
# Set environment variables first, then run the server
uvx mcp-google-sheets
```

### Method 2: For Development and Modifications

If you want to modify and develop the server:

1. Clone the repository:
```bash
git clone https://github.com/yourusername/mcp-google-sheets.git
cd mcp-google-sheets
```

2. Run with uv:
```bash
# Set environment variables first, then run
uv run mcp-google-sheets
```

## Authentication Process

The server automatically selects the authentication method based on environment variables:

1. First, it checks for service account credentials (non-interactive)
   - It prioritizes `CREDENTIALS_CONFIG` if set.
   - If `CREDENTIALS_CONFIG` is not set, it checks for `SERVICE_ACCOUNT_PATH`.
2. If service account authentication fails or isn't configured, it falls back to OAuth flow using `CREDENTIALS_PATH` and `TOKEN_PATH`.

With service account authentication, no browser interaction is needed, and the server will directly operate on spreadsheets in the shared Google Drive folder (specified by `DRIVE_FOLDER_ID`).

With OAuth authentication, the first time you use the server, it will open a browser window to authenticate with your Google account. After authentication, a token will be saved in the location specified by the `TOKEN_PATH` environment variable.

### Usage with Claude Desktop

Add this to your `claude_desktop_config.json`:

<details>
<summary>Using uvx with service account authentication (recommended)</summary>

```json
"mcpServers": {
  "google-sheets": {
    "command": "uvx",
    "args": ["mcp-google-sheets"],
    "env": {
      "SERVICE_ACCOUNT_PATH": "/path/to/your/service-account-key.json",
      "DRIVE_FOLDER_ID": "your_shared_folder_id_here"
    }
  }
}
```
</details>

<details>
<summary>Using uvx with OAuth authentication</summary>

```json
"mcpServers": {
  "google-sheets": {
    "command": "uvx",
    "args": ["mcp-google-sheets"],
    "env": {
      "CREDENTIALS_PATH": "/path/to/your/credentials.json",
      "TOKEN_PATH": "/path/to/your/token.json"
    }
  }
}
```
</details>

<details>
<summary>For development</summary>

```json
"mcpServers": {
  "mcp-google-sheets": {
    "command": "uv",
    "args": [
      "--directory",
      "/path/to/mcp-google-sheets",
      "run",
      "mcp-google-sheets"
    ],
    "env": {
      "SERVICE_ACCOUNT_PATH": "/path/to/mcp-google-sheets/service-account-key.json",
      "DRIVE_FOLDER_ID": "your_shared_folder_id_here"
      // OR for OAuth: 
      // "CREDENTIALS_PATH": "/path/to/mcp-google-sheets/credentials.json",
      // "TOKEN_PATH": "/path/to/mcp-google-sheets/token.json"
    },
    "disabled": false
  }
}
```
</details>


## Example Prompts for Claude

Once the MCP server is connected to Claude, you can use prompts like these:

- "List all spreadsheets in my shared folder"
- "Create a new spreadsheet titled 'Budget 2024'"
- "Get the data from Sheet1 in my spreadsheet with ID 1A2B3C4D5E6F7G8H"
- "Add 3 rows to the beginning of Sheet2 in my spreadsheet"
- "Update cells A1:B2 in my spreadsheet with the values [[1, 2], [3, 4]]"
- "List all the sheets in my Budget spreadsheet"
- "Get a summary of my 'Project Tracker' and 'Team Roster' spreadsheets"
- "Fetch the first 10 rows from 'Tasks!A1:E10' in spreadsheet 'proj-abc' and the range 'Sheet1!B2:B' from spreadsheet 'roster-xyz'"
- "Share my 'Q3 Planning' spreadsheet with user1@example.com as writer and user2@example.com as reader"

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.

## Credits

This project was inspired by the [kazz187/mcp-google-spreadsheet](https://github.com/kazz187/mcp-google-spreadsheet) repository and ported to Python using FastMCP.