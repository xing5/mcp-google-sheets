# Local Testing Guide

This guide explains how to test the MCP Google Sheets server on your local machine.

## Prerequisites

### 1. Python 3.10 or Higher

Check your Python version:
```bash
python --version
```

If you need to upgrade, visit [python.org](https://www.python.org/downloads/).

### 2. Install `uv` (Python Package Manager)

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

Follow the installer instructions to add `uv` to your PATH if needed.

### 3. Google Cloud Platform Setup

You must configure Google Cloud Platform credentials and enable the necessary APIs:

1. **Create/Select a GCP Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one

2. **Enable Required APIs**
   - Navigate to "APIs & Services" → "Library"
   - Search for and enable:
     - **Google Sheets API**
     - **Google Drive API**

### 4. Set Up Authentication

We recommend using a **Service Account** for local testing.

#### Create a Service Account

1. In GCP Console → "IAM & Admin" → "Service Accounts"
2. Click "+ CREATE SERVICE ACCOUNT"
3. Name it (e.g., `mcp-sheets-service`)
4. Grant **Editor** role
5. Click "Done"
6. Find the account, click Actions (⋮) → "Manage keys"
7. Click "ADD KEY" → "Create new key" → **JSON** → "CREATE"
8. **Download and securely store** the JSON key file

#### Create & Share a Google Drive Folder

1. In [Google Drive](https://drive.google.com/), create a folder (e.g., "MCP Test Sheets")
2. Note the **Folder ID** from the URL:
   ```
   https://drive.google.com/drive/folders/1xcRQCU9xrNVBPTeNzHqx4hrG7yR91WIa
                                            └────────── Folder ID ──────────┘
   ```
3. Right-click the folder → "Share"
4. Enter the Service Account's email (from the JSON file `client_email`)
5. Grant **Editor** access
6. Uncheck "Notify people"
7. Click "Share"

#### Set Environment Variables

**Linux/macOS:**
```bash
export SERVICE_ACCOUNT_PATH="/path/to/your/service-account-key.json"
export DRIVE_FOLDER_ID="YOUR_DRIVE_FOLDER_ID"
```

**Windows CMD:**
```cmd
set SERVICE_ACCOUNT_PATH="C:\path\to\your\service-account-key.json"
set DRIVE_FOLDER_ID="YOUR_DRIVE_FOLDER_ID"
```

**Windows PowerShell:**
```powershell
$env:SERVICE_ACCOUNT_PATH = "C:\path\to\your\service-account-key.json"
$env:DRIVE_FOLDER_ID = "YOUR_DRIVE_FOLDER_ID"
```

## Running the Server

### Option 1: Development Mode (From Cloned Repo)

If you've cloned the repository and want to test local changes:

```bash
# Navigate to the project directory
cd /path/to/mcp-google-sheets

# Run using uv
uv run mcp-google-sheets
```

The server will start and print logs indicating it's ready.

### Option 2: Using `uvx` (Test Published Package)

To test the server as end-users would experience it:

```bash
uvx mcp-google-sheets@latest
```

This downloads and runs the latest published version.

## Testing with an MCP Client

You need an MCP-compatible client to test the functionality. The most common option is **Claude Desktop**.

### Configure Claude Desktop

Add the server configuration to your `claude_desktop_config.json`:

**For Development Testing (local code):**
```json
{
  "mcpServers": {
    "mcp-google-sheets-local": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/home/jfenal/dev/gh/mcp-google-sheets",
        "mcp-google-sheets"
      ],
      "env": {
        "SERVICE_ACCOUNT_PATH": "/path/to/service-account.json",
        "DRIVE_FOLDER_ID": "your_folder_id"
      }
    }
  }
}
```

**For Production Testing (published package):**
```json
{
  "mcpServers": {
    "google-sheets": {
      "command": "uvx",
      "args": ["mcp-google-sheets@latest"],
      "env": {
        "SERVICE_ACCOUNT_PATH": "/path/to/service-account.json",
        "DRIVE_FOLDER_ID": "your_folder_id"
      }
    }
  }
}
```

**macOS Note:** If you encounter a `spawn uvx ENOENT` error, use the full path:
```json
"command": "/Users/yourusername/.local/bin/uvx"
```

## Testing the Functionality

Once the server is running and connected to Claude Desktop, try these test prompts:

### Basic Operations
- "List all spreadsheets I have access to."
- "Create a new spreadsheet titled 'Test Spreadsheet'."
- "List the sheets in spreadsheet ID `<your_spreadsheet_id>`."

### Data Operations
- "Get data from range A1:C10 in Sheet1 of spreadsheet `<id>`."
- "Update cell B2 to 'Test Value' in Sheet1 of spreadsheet `<id>`."
- "Add a new sheet named 'Testing' to spreadsheet `<id>`."

### Advanced Operations
- "Get summaries of multiple spreadsheets."
- "Share spreadsheet `<id>` with test@example.com as a reader."
- "Copy Sheet1 from spreadsheet `<id1>` to spreadsheet `<id2>`."

## Testing Token Relay Mode (OpenShift Feature)

If you're testing the token relay functionality for containerized deployments, see the [Token Relay Mode Documentation](TOKEN_RELAY_MODE.md) for detailed setup instructions.

## Troubleshooting

### Authentication Errors
- Verify your service account JSON file path is correct
- Ensure the folder is shared with the service account's email
- Check that both Google Sheets API and Google Drive API are enabled in GCP

### Connection Issues
- Verify environment variables are set correctly
- Check that Claude Desktop config JSON is valid
- Look for errors in the server logs
- Restart Claude Desktop after config changes

### Permission Errors
- Ensure the service account has Editor access to the shared folder
- Verify the folder ID is correct
- Check that spreadsheets are within the shared folder (for service accounts)

## Alternative Authentication Methods

### OAuth 2.0 (Interactive Login)
See the main [README.md](../README.md#method-b-oauth-20-interactive--personal-use-) for OAuth setup instructions.

### Application Default Credentials (ADC)
For Google Cloud environments or local development with `gcloud`:

```bash
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/drive
gcloud auth application-default set-quota-project <project_id>
```

Then run the server without explicit credential environment variables.

## Next Steps

- Review the [README.md](../README.md) for complete feature documentation
- Check [TOKEN_RELAY_MODE.md](TOKEN_RELAY_MODE.md) for containerized deployment testing
- Explore all 19 available tools and their parameters
