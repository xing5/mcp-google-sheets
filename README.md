
<div align="center">
  <!-- Main Title Link -->
  <b>mcp-google-sheets</b>

  <!-- Description Paragraph -->
  <p align="center">
    <i>Your AI Assistant's Gateway to Google Sheets! </i>📊
  </p>

[![PyPI - Version](https://img.shields.io/pypi/v/mcp-google-sheets)](https://pypi.org/project/mcp-google-sheets/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/mcp-google-sheets)](https://pypi.org/project/mcp-google-sheets/)
![GitHub License](https://img.shields.io/github/license/xing5/mcp-google-sheets)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/xing5/mcp-google-sheets/release.yml)
</div>

---

## 🤔 What is this?

`mcp-google-sheets` is a Python-based MCP server that acts as a bridge between any MCP-compatible client (like Claude Desktop) and the Google Sheets API. It allows you to interact with your Google Spreadsheets using a defined set of tools, enabling powerful automation and data manipulation workflows driven by AI.


## 🚀 Quick Start (Using `uvx`)

Essentially the server runs in one line: `uvx mcp-google-sheets`. 

This cmd will automatically download the latest code if needed and run it. However, it takes quite a few steps to setup the Google Cloud, please read the steps below.

1.  **☁️ Prerequisite: Google Cloud Setup**
    *   You **must** configure Google Cloud Platform credentials and enable the necessary APIs first. We strongly recommend using a **Service Account**.
    *   ➡️ Jump to the [**Detailed Google Cloud Platform Setup**](#-google-cloud-platform-setup-detailed) guide below.

2.  **🐍 Install `uv`**
    *   `uvx` is part of `uv`, a fast Python package installer and resolver. Install it if you haven't already:
        ```bash
        # macOS / Linux
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Windows
        powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
        # Or using pip:
        # pip install uv
        ```
        *Follow instructions in the installer output to add `uv` to your PATH if needed.*

3.  **🔑 Set Essential Environment Variables (Service Account Recommended)**
    *   You need to tell the server how to authenticate. Set these variables in your terminal:
    *   **(Linux/macOS)**
        ```bash
        # Replace with YOUR actual path and folder ID from the Google Setup step
        export SERVICE_ACCOUNT_PATH="/path/to/your/service-account-key.json"
        export DRIVE_FOLDER_ID="YOUR_DRIVE_FOLDER_ID"
        ```
    *   **(Windows CMD)**
        ```cmd
        set SERVICE_ACCOUNT_PATH="C:\path\to\your\service-account-key.json"
        set DRIVE_FOLDER_ID="YOUR_DRIVE_FOLDER_ID"
        ```
    *   **(Windows PowerShell)**
        ```powershell
        $env:SERVICE_ACCOUNT_PATH = "C:\path\to\your\service-account-key.json"
        $env:DRIVE_FOLDER_ID = "YOUR_DRIVE_FOLDER_ID"
        ```
    *   ➡️ See [**Detailed Authentication & Environment Variables**](#-authentication--environment-variables-detailed) for other options (OAuth, `CREDENTIALS_CONFIG`).

4.  **🏃 Run the Server!**
    *   `uvx` will automatically download and run the latest version of `mcp-google-sheets`:
        ```bash
        uvx mcp-google-sheets
        ```
    *   The server will start and print logs indicating it's ready.

5.  **🔌 Connect your MCP Client**
    *   Configure your client (e.g., Claude Desktop) to connect to the running server.
    *   Depending on the client you use, you might not need step 4 because the client can launch the server for you. But it's a good practice to test run step 4 anyway to make sure things are set up properly.
    *   ➡️ See [**Usage with Claude Desktop**](#-usage-with-claude-desktop) for examples.

You're ready! Start issuing commands via your MCP client.

---

## ✨ Key Features

*   **Seamless Integration:** Connects directly to Google Drive & Google Sheets APIs.
*   **Comprehensive Tools:** Offers a wide range of operations (CRUD, listing, batching, sharing, formatting, etc.).
*   **Flexible Authentication:** Supports **Service Accounts (recommended)**, OAuth 2.0, and direct credential injection via environment variables.
*   **Easy Deployment:** Run instantly with `uvx` (zero-install feel) or clone for development using `uv`.
*   **AI-Ready:** Designed for use with MCP-compatible clients, enabling natural language spreadsheet interaction.

---

## 🛠️ Available Tools & Resources

This server exposes the following tools for interacting with Google Sheets:

*(Input parameters are typically strings unless otherwise specified)*

*   **`list_spreadsheets`**: Lists spreadsheets in the configured Drive folder (Service Account) or accessible by the user (OAuth).
    *   _Returns:_ List of objects `[{id: string, title: string}]`
*   **`create_spreadsheet`**: Creates a new spreadsheet.
    *   `title` (string): The desired title.
    *   _Returns:_ Object with spreadsheet info, including `spreadsheetId`.
*   **`get_sheet_data`**: Reads data from a range in a sheet.
    *   `spreadsheet_id` (string)
    *   `sheet` (string): Name of the sheet.
    *   `range` (optional string): A1 notation (e.g., `'A1:C10'`, `'Sheet1!B2:D'`). If omitted, reads the whole sheet.
    *   _Returns:_ Full grid data structure from Google Sheets API with all metadata preserved.
*   **`get_sheet_formulas`**: Reads formulas from a range in a sheet.
    *   `spreadsheet_id` (string)
    *   `sheet` (string): Name of the sheet.
    *   `range` (optional string): A1 notation (e.g., `'A1:C10'`, `'Sheet1!B2:D'`). If omitted, reads the whole sheet.
    *   _Returns:_ 2D array of cell formulas.
*   **`update_cells`**: Writes data to a specific range. Overwrites existing data.
    *   `spreadsheet_id` (string)
    *   `sheet` (string)
    *   `range` (string): A1 notation.
    *   `data` (2D array): Values to write.
    *   _Returns:_ Update result object.
*   **`batch_update_cells`**: Updates multiple ranges in one API call.
    *   `spreadsheet_id` (string)
    *   `sheet` (string)
    *   `ranges` (object): Dictionary mapping range strings (A1 notation) to 2D arrays of values `{ "A1:B2": [[1, 2], [3, 4]], "D5": [["Hello"]] }`.
    *   _Returns:_ Batch update result object.
*   **`add_rows`**: Appends rows to the end of a sheet (after the last row with data).
    *   `spreadsheet_id` (string)
    *   `sheet` (string)
    *   `data` (2D array): Rows to append.
    *   _Returns:_ Update result object.
*   **`list_sheets`**: Lists all sheet names within a spreadsheet.
    *   `spreadsheet_id` (string)
    *   _Returns:_ List of sheet name strings `["Sheet1", "Sheet2"]`.
*   **`create_sheet`**: Adds a new sheet (tab) to a spreadsheet.
    *   `spreadsheet_id` (string)
    *   `title` (string): Name for the new sheet.
    *   _Returns:_ New sheet properties object.
*   **`get_multiple_sheet_data`**: Fetches data from multiple ranges across potentially different spreadsheets in one call.
    *   `queries` (array of objects): Each object needs `spreadsheet_id`, `sheet`, and `range`. `[{spreadsheet_id: 'abc', sheet: 'Sheet1', range: 'A1:B2'}, ...]`.
    *   _Returns:_ List of objects, each containing the query params and fetched `data` or an `error`.
*   **`get_multiple_spreadsheet_summary`**: Gets titles, sheet names, headers, and first few rows for multiple spreadsheets.
    *   `spreadsheet_ids` (array of strings)
    *   `rows_to_fetch` (optional integer, default 5): How many rows (including header) to preview.
    *   _Returns:_ List of summary objects for each spreadsheet.
*   **`share_spreadsheet`**: Shares a spreadsheet with specified users/emails and roles.
    *   `spreadsheet_id` (string)
    *   `recipients` (array of objects): `[{email_address: 'user@example.com', role: 'writer'}, ...]`. Roles: `reader`, `commenter`, `writer`.
    *   `send_notification` (optional boolean, default True): Send email notifications.
    *   _Returns:_ Dictionary with `successes` and `failures` lists.
*   **`add_columns`**: Adds columns to a sheet. *(Verify parameters if implemented)*
*   **`copy_sheet`**: Duplicates a sheet within a spreadsheet. *(Verify parameters if implemented)*
*   **`rename_sheet`**: Renames an existing sheet. *(Verify parameters if implemented)*

**MCP Resources:**

*   **`spreadsheet://{spreadsheet_id}/info`**: Get basic metadata about a Google Spreadsheet.
    *   _Returns:_ JSON string with spreadsheet information.

---

## ☁️ Google Cloud Platform Setup (Detailed)

This setup is **required** before running the server.

1.  **Create/Select a GCP Project:** Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  **Enable APIs:** Navigate to "APIs & Services" -> "Library". Search for and enable:
    *   `Google Sheets API`
    *   `Google Drive API`
3.  **Configure Credentials:** You need to choose *one* authentication method below (Service Account is recommended).

---

## 🔑 Authentication & Environment Variables (Detailed)

The server needs credentials to access Google APIs. Choose one method:

### Method A: Service Account (Recommended for Servers/Automation) ✅

*   **Why?** Headless (no browser needed), secure, ideal for server environments. Doesn't expire easily.
*   **Steps:**
    1.  **Create Service Account:** In GCP Console -> "IAM & Admin" -> "Service Accounts".
        *   Click "+ CREATE SERVICE ACCOUNT". Name it (e.g., `mcp-sheets-service`).
        *   Grant Roles: Add `Editor` role for broad access, or more granular roles (like `roles/drive.file` and specific Sheets roles) for stricter permissions.
        *   Click "Done". Find the account, click Actions (⋮) -> "Manage keys".
        *   Click "ADD KEY" -> "Create new key" -> **JSON** -> "CREATE".
        *   **Download and securely store** the JSON key file.
    2.  **Create & Share Google Drive Folder:**
        *   In [Google Drive](https://drive.google.com/), create a folder (e.g., "AI Managed Sheets").
        *   Note the **Folder ID** from the URL: `https://drive.google.com/drive/folders/THIS_IS_THE_FOLDER_ID`.
        *   Right-click the folder -> "Share" -> "Share".
        *   Enter the Service Account's email (from the JSON file `client_email`).
        *   Grant **Editor** access. Uncheck "Notify people". Click "Share".
    3.  **Set Environment Variables:**
        *   `SERVICE_ACCOUNT_PATH`: Full path to the downloaded JSON key file.
        *   `DRIVE_FOLDER_ID`: The ID of the shared Google Drive folder.
        *(See [Ultra Quick Start](#-ultra-quick-start-using-uvx) for OS-specific examples)*

### Method B: OAuth 2.0 (Interactive / Personal Use) 🧑‍💻

*   **Why?** For personal use or local development where interactive browser login is okay.
*   **Steps:**
    1.  **Configure OAuth Consent Screen:** In GCP Console -> "APIs & Services" -> "OAuth consent screen". Select "External", fill required info, add scopes (`.../auth/spreadsheets`, `.../auth/drive`), add test users if needed.
    2.  **Create OAuth Client ID:** In GCP Console -> "APIs & Services" -> "Credentials". "+ CREATE CREDENTIALS" -> "OAuth client ID" -> Type: **Desktop app**. Name it. "CREATE". **Download JSON**.
    3.  **Set Environment Variables:**
        *   `CREDENTIALS_PATH`: Path to the downloaded OAuth credentials JSON file (default: `credentials.json`).
        *   `TOKEN_PATH`: Path to store the user's refresh token after first login (default: `token.json`). Must be writable.

### Method C: Direct Credential Injection (Advanced) 🔒

*   **Why?** Useful in environments like Docker, Kubernetes, or CI/CD where managing files is hard, but environment variables are easy/secure. Avoids file system access.
*   **How?** Instead of providing a *path* to the credentials file, you provide the *content* of the file, encoded in Base64, directly in an environment variable.
*   **Steps:**
    1.  **Get your credentials JSON file** (either Service Account key or OAuth Client ID file). Let's call it `your_credentials.json`.
    2.  **Generate the Base64 string:**
        *   **(Linux/macOS):** `base64 -w 0 your_credentials.json`
        *   **(Windows PowerShell):**
            ```powershell
            $filePath = "C:\path\to\your_credentials.json"; # Use actual path
            $bytes = [System.IO.File]::ReadAllBytes($filePath);
            $base64 = [System.Convert]::ToBase64String($bytes);
            $base64 # Copy this output
            ```
        *   **(Caution):** Avoid pasting sensitive credentials into untrusted online encoders.
    3.  **Set the Environment Variable:**
        *   `CREDENTIALS_CONFIG`: Set this variable to the **full Base64 string** you just generated.
            ```bash
            # Example (Linux/macOS) - Use the actual string generated
            export CREDENTIALS_CONFIG="ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb..."
            ```

### Method D: Application Default Credentials (ADC) 🌐

*   **Why?** Ideal for Google Cloud environments (GKE, Compute Engine, Cloud Run) and local development with `gcloud auth application-default login`. No explicit credential files needed.
*   **How?** Uses Google's Application Default Credentials chain to automatically discover credentials from multiple sources.
*   **ADC Search Order:**
    1.  `GOOGLE_APPLICATION_CREDENTIALS` environment variable (path to service account key) - **Google's standard variable**
    2.  `gcloud auth application-default login` credentials (local development)
    3.  Attached service account from metadata server (GKE, Compute Engine, etc.)
*   **Setup:**
    *   **Local Development:** Run `gcloud auth application-default login` once
    *   **Google Cloud:** Attach a service account to your compute resource
    *   **Environment Variable:** Set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json` (Google's standard)
*   **No additional environment variables needed** - ADC is used automatically as a fallback when other methods fail.

**Note:** `GOOGLE_APPLICATION_CREDENTIALS` is Google's official standard environment variable, while `SERVICE_ACCOUNT_PATH` is specific to this MCP server. If you set `GOOGLE_APPLICATION_CREDENTIALS`, ADC will find it automatically.

### Authentication Priority & Summary

The server checks for credentials in this order:

1.  `CREDENTIALS_CONFIG` (Base64 content)
2.  `SERVICE_ACCOUNT_PATH` (Path to Service Account JSON)
3.  `CREDENTIALS_PATH` (Path to OAuth JSON) - triggers interactive flow if token is missing/expired
4.  **Application Default Credentials (ADC)** - automatic fallback

**Environment Variable Summary:**

| Variable               | Method(s)                   | Description                                                     | Default          |
| :--------------------- | :-------------------------- | :-------------------------------------------------------------- | :--------------- |
| `SERVICE_ACCOUNT_PATH` | Service Account             | Path to the Service Account JSON key file (MCP server specific). | -                |
| `GOOGLE_APPLICATION_CREDENTIALS` | ADC                   | Path to service account key (Google's standard variable).       | -                |
| `DRIVE_FOLDER_ID`      | Service Account             | ID of the Google Drive folder shared with the Service Account.  | -                |
| `CREDENTIALS_PATH`     | OAuth 2.0                   | Path to the OAuth 2.0 Client ID JSON file.                    | `credentials.json` |
| `TOKEN_PATH`           | OAuth 2.0                   | Path to store the generated OAuth token.                        | `token.json`     |
| `CREDENTIALS_CONFIG`   | Service Account / OAuth 2.0 | Base64 encoded JSON string of credentials content.              | -                |

---

## ⚙️ Running the Server (Detailed)

### Method 1: Using `uvx` (Recommended for Users)

As shown in the [Ultra Quick Start](#-ultra-quick-start-using-uvx), this is the easiest way. Set environment variables, then run:

```bash
uvx mcp-google-sheets
```
`uvx` handles fetching and running the package temporarily.

### Method 2: For Development (Cloning the Repo)

If you want to modify the code:

1.  **Clone:** `git clone https://github.com/yourusername/mcp-google-sheets.git && cd mcp-google-sheets` (Use actual URL)
2.  **Set Environment Variables:** As described above.
3.  **Run using `uv`:** (Uses the local code)
    ```bash
    uv run mcp-google-sheets
    # Or via the script name if defined in pyproject.toml, e.g.:
    # uv run start
    ```

---

## 🔌 Usage with Claude Desktop

Add the server config to `claude_desktop_config.json` under `mcpServers`. Choose the block matching your setup:

<details>
<summary>🔵 Config: uvx + Service Account (Recommended)</summary>

```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "uvx",
      "args": ["mcp-google-sheets"],
      "env": {
        // Use ABSOLUTE paths here
        "SERVICE_ACCOUNT_PATH": "/full/path/to/your/service-account-key.json",
        "DRIVE_FOLDER_ID": "your_shared_folder_id_here"
      },
      "healthcheck_url": "http://localhost:8000/health" // Adjust host/port if needed
    }
  }
}
```
</details>

<details>
<summary>🔵 Config: uvx + OAuth 2.0</summary>

```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "uvx",
      "args": ["mcp-google-sheets"],
      "env": {
        // Use ABSOLUTE paths here
        "CREDENTIALS_PATH": "/full/path/to/your/credentials.json",
        "TOKEN_PATH": "/full/path/to/your/token.json" // Ensure this path is writable
      },
      "healthcheck_url": "http://localhost:8000/health"
    }
  }
}
```
*(A browser may open for Google login on first use)*
</details>

<details>
<summary>🔵 Config: uvx + CREDENTIALS_CONFIG (Service Account Example)</summary>

```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "uvx",
      "args": ["mcp-google-sheets"],
      "env": {
        // Paste the full Base64 string here
        "CREDENTIALS_CONFIG": "ewogICJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsCiAgInByb2plY3RfaWQiOiAi...",
        "DRIVE_FOLDER_ID": "your_shared_folder_id_here" // Still needed for Service Account folder context
      },
      "healthcheck_url": "http://localhost:8000/health"
    }
  }
}
```
</details>

<details>
<summary>🔵 Config: uvx + Application Default Credentials (ADC)</summary>

```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "uvx",
      "args": ["mcp-google-sheets"],
      "env": {
        // Option 1: Use Google's standard environment variable
        // "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account.json"
        
        // Option 2: No env vars needed if using `gcloud auth application-default login`
      },
      "healthcheck_url": "http://localhost:8000/health"
    }
  }
}
```
*Prerequisites: Either set `GOOGLE_APPLICATION_CREDENTIALS` OR run `gcloud auth application-default login`*
</details>

<details>
<summary>🟡 Config: Development (Running from cloned repo)</summary>

```json
{
  "mcpServers": {
    "mcp-google-sheets-local": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/your/mcp-google-sheets",
        "mcp-google-sheets"
      ],
      "env": {
        "SERVICE_ACCOUNT_PATH": "/path/to/your/mcp-google-sheets/service_account.json",
        "DRIVE_FOLDER_ID": "your_drive_folder_id_here"
      }
    }
  }
}
```
*Note: Use `--directory` flag to specify the project path, and adjust paths to match your actual workspace location.*
</details>

---

## 💬 Example Prompts for Claude

Once connected, try prompts like:

*   "List all spreadsheets I have access to." (or "in my AI Managed Sheets folder")
*   "Create a new spreadsheet titled 'Quarterly Sales Report Q3 2024'."
*   "In the 'Quarterly Sales Report' spreadsheet, get the data from Sheet1 range A1 to E10."
*   "Add a new sheet named 'Summary' to the spreadsheet with ID `1aBcDeFgHiJkLmNoPqRsTuVwXyZ`."
*   "In my 'Project Tasks' spreadsheet, Sheet 'Tasks', update cell B2 to 'In Progress'."
*   "Append these rows to the 'Log' sheet in spreadsheet `XYZ`: `[['2024-07-31', 'Task A Completed'], ['2024-08-01', 'Task B Started']]`"
*   "Get a summary of the spreadsheets 'Sales Data' and 'Inventory Count'."
*   "Share the 'Team Vacation Schedule' spreadsheet with `team@example.com` as a reader and `manager@example.com` as a writer. Don't send notifications."

---

## 🤝 Contributing

Contributions are welcome! Please open an issue to discuss bugs or feature requests. Pull requests are appreciated.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Credits

*   Built with [FastMCP](https://github.com/cognitiveapis/fastmcp).
*   Inspired by [kazz187/mcp-google-spreadsheet](https://github.com/kazz187/mcp-google-spreadsheet).
*   Uses Google API Python Client libraries.