#!/usr/bin/env python
"""
Google Spreadsheet MCP Server
A Model Context Protocol (MCP) server built with FastMCP for interacting with Google Sheets.
"""

import base64
import functools
import logging
import os
import re
import sys
import time
import random
import warnings
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
import json
from dataclasses import dataclass
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

# Suppress deprecation warning from Google auth libraries about file_cache
# The google-auth-oauthlib library prints this warning to stderr which bypasses our logging
warnings.filterwarnings('ignore', message='file_cache is only supported with oauth2client<4.0.0')

# Configure logging BEFORE importing MCP to suppress its verbose messages
# MCP logs "Processing request of type..." at INFO level - we need to block those
logging.basicConfig(level=logging.CRITICAL, format='%(message)s', force=True)
logging.getLogger('mcp').setLevel(logging.CRITICAL)
logging.getLogger('mcp.server').setLevel(logging.CRITICAL)
logging.getLogger('mcp.server.lowlevel').setLevel(logging.CRITICAL)
logging.getLogger('mcp.server.lowlevel.server').setLevel(logging.CRITICAL)

# MCP imports
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations

# Google API imports
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.auth

# Constants
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
CREDENTIALS_CONFIG = os.environ.get('CREDENTIALS_CONFIG')
TOKEN_PATH = os.environ.get('TOKEN_PATH', 'token.json')
CREDENTIALS_PATH = os.environ.get('CREDENTIALS_PATH', 'credentials.json')
SERVICE_ACCOUNT_PATH = os.environ.get('SERVICE_ACCOUNT_PATH', 'service_account.json')
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '')  # Working directory in Google Drive
USER_ACCESS_TOKEN = os.environ.get('USER_ACCESS_TOKEN')  # External OAuth token for token relay mode

# Tool filtering: parse from environment variable or command-line
_enabled_tools_str = None
for i, arg in enumerate(sys.argv):
    if arg == '--include-tools' and i + 1 < len(sys.argv):
        _enabled_tools_str = sys.argv[i + 1]
        break

if not _enabled_tools_str:
    _enabled_tools_str = os.environ.get('ENABLED_TOOLS')

if _enabled_tools_str:
    _tools_set = {tool.strip() for tool in _enabled_tools_str.split(',') if tool.strip()}
    ENABLED_TOOLS = _tools_set if _tools_set else None
else:
    ENABLED_TOOLS = None

# API Configuration
API_TIMEOUT = 180  # Google Sheets API timeout limit in seconds
MAX_RETRIES = 5
MAX_BACKOFF = 64  # Maximum backoff time in seconds
HTTP_TOO_MANY_REQUESTS = 429  # HTTP status code for rate limiting
ALPHABET_SIZE = 26  # Number of letters in the alphabet (A-Z)

# Logging configuration
LOG_LEVELS = {'DEBUG': 10, 'INFO': 20, 'WARN': 30, 'ERROR': 40}
_LOG_LEVEL = LOG_LEVELS.get(os.environ.get('LOG_LEVEL', 'INFO').upper(), LOG_LEVELS['INFO'])

def log(message: str, level: str = 'INFO'):
    """Log message with timestamp and level to stderr"""
    level_value = LOG_LEVELS.get(level.upper(), LOG_LEVELS['INFO'])
    if level_value >= _LOG_LEVEL:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        print(f"[{timestamp}] [{level:5s}] {message}", file=sys.stderr, flush=True)

def execute_with_retry(request, operation_name: str = "API call"):
    """
    Execute a Google API request with exponential backoff retry on 429 rate limit errors.

    Implements Google's recommended retry strategy:
    - Exponential backoff with randomized delays
    - Maximum backoff of 32-64 seconds
    - Up to 5 retries

    Args:
        request: A Google API request object (from sheets_service.spreadsheets().get() etc.)
        operation_name: Human-readable name of the operation for logging

    Returns:
        The result of the API call

    Raises:
        HttpError: If the error is not a rate limit or max retries exceeded
    """
    last_exception = None
    start_time = time.time()
    log(f"Starting: {operation_name}", 'DEBUG')

    for attempt in range(MAX_RETRIES):
        try:
            api_response = request.execute()
            elapsed = time.time() - start_time
            log(f"✓ {operation_name} ({elapsed:.2f}s)", 'DEBUG')
            return api_response
        except HttpError as e:
            if e.resp.status == HTTP_TOO_MANY_REQUESTS:
                if attempt == MAX_RETRIES - 1:
                    elapsed = time.time() - start_time
                    log(f"✗ Rate limit max retries ({MAX_RETRIES}) after {elapsed:.2f}s: {operation_name}", 'ERROR')
                    raise

                # Calculate exponential backoff with jitter
                base_delay = min(2 ** attempt, MAX_BACKOFF)
                jitter = random.uniform(0, 1)  # Up to 1 second randomization
                delay = base_delay + jitter

                log(f"Rate limit hit, retry {attempt + 1}/{MAX_RETRIES} after {delay:.2f}s: {operation_name}", 'WARN')
                time.sleep(delay)
                last_exception = e
            else:
                # Not a rate limit error, log and raise immediately
                elapsed = time.time() - start_time
                log(f"✗ HTTP {e.resp.status} after {elapsed:.2f}s: {operation_name} - {e}", 'ERROR')
                raise
        except Exception as e:
            # Other exceptions, log and raise immediately
            elapsed = time.time() - start_time
            log(f"✗ {type(e).__name__} after {elapsed:.2f}s: {operation_name} - {e}", 'ERROR')
            raise

    # Should not reach here, but if we do, raise the last exception
    if last_exception:
        raise last_exception

def _setup_sheets_api_call(ctx: Context, sheet: str, range_spec: Optional[str] = None) -> tuple:
    """
    Setup common parameters for Sheets API calls.

    Returns:
        tuple: (sheets_service, full_range)
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    full_range = f"{sheet}!{range_spec}" if range_spec else sheet
    return sheets_service, full_range

# ============================================================================
# A1 to R1C1 Conversion Utilities
# ============================================================================

def _column_letter_to_number(col: str) -> int:
    """
    Convert column letter(s) to number (A=1, Z=26, AA=27, etc.).

    Args:
        col: Column letter(s) in uppercase (e.g., 'A', 'Z', 'AA')

    Returns:
        Column number (1-indexed)
    """
    num = 0
    for char in col:
        num = num * ALPHABET_SIZE + (ord(char) - ord('A') + 1)
    return num


def _build_column_lut(max_col: int = 1000) -> dict:
    """
    Build lookup table for column letters to numbers.

    Args:
        max_col: Maximum column number to include in LUT

    Returns:
        Dictionary mapping column letters to numbers
    """
    lut = {}
    for i in range(1, max_col + 1):
        col_letter = ""
        num = i
        while num > 0:
            num -= 1
            col_letter = chr(num % ALPHABET_SIZE + ord('A')) + col_letter
            num //= ALPHABET_SIZE
        lut[col_letter] = i
    return lut


# Pre-build column lookup table at module load (covers columns A-ALL = 1000 columns)
COLUMN_LUT = _build_column_lut(1000)

# Pre-compile regex pattern for cell references (performance optimization)
CELL_REF_PATTERN = re.compile(r"(?:([^!]+!))?(\$)?([A-Z]+)(\$)?(\d+)")


def _a1_to_r1c1(formula: str, current_row: int, current_col: int) -> str:
    """
    Convert formula from A1 notation to R1C1 notation.

    Args:
        formula: Formula string in A1 notation (e.g., "=SUM(A1:B5)")
        current_row: 1-based row number of the cell containing this formula
        current_col: 1-based column number of the cell containing this formula

    Returns:
        Formula in R1C1 notation (e.g., "=SUM(R[-4]C[-1]:RC[0])")

    Examples:
        >>> _a1_to_r1c1('=A1', 2, 2)
        '=R[-1]C[-1]'
        >>> _a1_to_r1c1('=$A$1', 2, 2)
        '=R1C1'
    """
    def replace_cell_ref(match):
        sheet_prefix = match.group(1) or ''
        col_abs = match.group(2)  # $ before column
        col_letters = match.group(3)
        row_abs = match.group(4)  # $ before row
        row_num = match.group(5)

        # Use LUT for column conversion (fallback to computed for ultra-wide sheets)
        col_num = COLUMN_LUT.get(col_letters, _column_letter_to_number(col_letters))
        row = int(row_num)

        # Build R1C1 notation
        if row_abs:
            row_part = f"R{row}"
        else:
            offset = row - current_row
            if offset == 0:
                row_part = "R"
            else:
                row_part = f"R[{offset}]"

        if col_abs:
            col_part = f"C{col_num}"
        else:
            offset = col_num - current_col
            if offset == 0:
                col_part = "C"
            else:
                col_part = f"C[{offset}]"

        return f"{sheet_prefix}{row_part}{col_part}"

    return CELL_REF_PATTERN.sub(replace_cell_ref, formula)

@dataclass
class SpreadsheetContext:
    """Context for Google Spreadsheet service"""
    sheets_service: Any
    drive_service: Any
    folder_id: Optional[str] = None


@asynccontextmanager
async def spreadsheet_lifespan(server: FastMCP) -> AsyncIterator[SpreadsheetContext]:
    """Manage Google Spreadsheet API connection lifecycle"""
    # Authenticate and build the service
    creds = None

    # Check for external OAuth token (Token Relay Mode) - highest priority
    # This allows end-user authentication in containerized/OpenShift environments
    if USER_ACCESS_TOKEN:
        try:
            log("Using external OAuth token (Token Relay Mode)")
            # Create credentials from the provided access token
            creds = Credentials(token=USER_ACCESS_TOKEN)
            # Note: Token validation happens on first API call
            # The caller is responsible for token refresh
        except Exception as e:
            log(f"Error using external access token: {e}")
            creds = None

    if not creds and CREDENTIALS_CONFIG:
        creds = service_account.Credentials.from_service_account_info(json.loads(base64.b64decode(CREDENTIALS_CONFIG)), scopes=SCOPES)
    
    # Check for explicit service account authentication first (custom SERVICE_ACCOUNT_PATH)
    if not creds and SERVICE_ACCOUNT_PATH and os.path.exists(SERVICE_ACCOUNT_PATH):
        try:
            # Regular service account authentication
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_PATH,
                scopes=SCOPES
            )
            log("Using service account authentication", 'INFO')
            log(f"Google Drive folder ID: {DRIVE_FOLDER_ID or 'Not specified'}", 'DEBUG')
        except Exception as e:
            log(f"Service account authentication error: {e}", 'WARN')
            creds = None

    # Fall back to OAuth flow if service account auth failed or not configured
    if not creds:
        log("Trying OAuth authentication flow", 'DEBUG')
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, 'r') as token:
                creds = Credentials.from_authorized_user_info(json.load(token), SCOPES)
                
        # If credentials are not valid or don't exist, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    log("Refreshing expired OAuth token...", 'DEBUG')
                    creds.refresh(Request())
                    log("Token refreshed successfully", 'INFO')
                    # Save the refreshed token
                    with open(TOKEN_PATH, 'w') as token:
                        token.write(creds.to_json())
                except Exception as refresh_error:
                    log(f"Token refresh failed: {refresh_error}", 'WARN')
                    log("Triggering reauthentication flow...", 'DEBUG')
                    creds = None  # Clear creds to trigger OAuth flow below

            # If refresh failed or creds don't exist, run OAuth flow
            if not creds:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                    creds = flow.run_local_server(port=0)

                    # Save the credentials for the next run
                    with open(TOKEN_PATH, 'w') as token:
                        token.write(creds.to_json())
                    log("Successfully authenticated using OAuth flow", 'INFO')
                except Exception as e:
                    log(f"OAuth flow error: {e}", 'ERROR')
                    creds = None

    # Try Application Default Credentials if no creds thus far
    # This will automatically check GOOGLE_APPLICATION_CREDENTIALS, gcloud auth, and metadata service
    if not creds:
        try:
            log("Attempting Application Default Credentials (ADC)", 'DEBUG')
            log("ADC checks: GOOGLE_APPLICATION_CREDENTIALS, gcloud auth, metadata service", 'DEBUG')
            creds, project = google.auth.default(
                scopes=SCOPES
            )
            log(f"Successfully authenticated using ADC for project: {project}", 'INFO')
        except Exception as e:
            log(f"ADC authentication error: {e}", 'ERROR')
            raise Exception("All authentication methods failed. Please configure credentials.")

    # Build the services
    # Note: static_discovery=False forces fetching fresh API discovery docs which can add latency
    # on first request but ensures compatibility. For production, consider caching discovery docs.
    log(f"Building Google API services (API timeout limit: {API_TIMEOUT}s)", 'INFO')
    sheets_service = build('sheets', 'v4', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    
    try:
        # Provide the service in the context
        yield SpreadsheetContext(
            sheets_service=sheets_service,
            drive_service=drive_service,
            folder_id=DRIVE_FOLDER_ID if DRIVE_FOLDER_ID else None
        )
    finally:
        # No explicit cleanup needed for Google APIs
        pass


DEFAULT_PORT = 8000
_resolved_host = os.environ.get('HOST') or os.environ.get('FASTMCP_HOST') or "0.0.0.0"
_resolved_port_str = os.environ.get('PORT') or os.environ.get('FASTMCP_PORT') or str(DEFAULT_PORT)
try:
    _resolved_port = int(_resolved_port_str)
except ValueError:
    _resolved_port = DEFAULT_PORT

mcp = FastMCP("Google Spreadsheet",
              dependencies=["google-auth", "google-auth-oauthlib", "google-api-python-client"],
              lifespan=spreadsheet_lifespan,
              host=_resolved_host,
              port=_resolved_port,
              log_level='WARNING')  # Suppress "Processing request..." messages


def tool(annotations: Optional[ToolAnnotations] = None):
    """
    Conditional tool decorator that only registers tools if they're enabled.

    This wrapper checks ENABLED_TOOLS configuration and only applies the @mcp.tool
    decorator if the tool should be enabled. If ENABLED_TOOLS is None (default),
    all tools are enabled.

    Args:
        annotations: Optional ToolAnnotations for the tool

    Returns:
        Decorator function
    """
    def decorator(func):
        tool_name = func.__name__

        if ENABLED_TOOLS is None or tool_name in ENABLED_TOOLS:
            # Wrap the function to add logging using functools.wraps to preserve signature
            @functools.wraps(func)
            def logged_func(*args, **kwargs):
                start_time = time.time()

                # Filter out ctx parameter for cleaner logging
                log_kwargs = {k: v for k, v in kwargs.items() if k != 'ctx'}
                params_str = ', '.join(f'{k}={repr(v)[:50]}' for k, v in log_kwargs.items())
                log(f"→ {tool_name}({params_str})", 'INFO')
                try:
                    tool_response = func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    log(f"✓ {tool_name} ({elapsed:.2f}s)", 'INFO')
                    return tool_response
                except Exception as e:
                    elapsed = time.time() - start_time
                    log(f"✗ {tool_name} failed ({elapsed:.2f}s): {type(e).__name__}: {e}", 'ERROR')
                    raise

            if annotations:
                return mcp.tool(annotations=annotations)(logged_func)
            else:
                return mcp.tool()(logged_func)
        else:
            return func

    return decorator


@tool(
    annotations=ToolAnnotations(
        title="Get Sheet Data",
        readOnlyHint=True,
    ),
)
def get_sheet_data(
    spreadsheet_id: str,
    ranges: Union[str, List[str]],
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Get data from one or more ranges in a SINGLE Google Spreadsheet.

    IMPORTANT - MULTIPLE RANGES ARE BATCHED:
    You can fetch multiple ranges from the SAME spreadsheet in a SINGLE API call by passing
    an array instead of a string. This is 5-10x faster than making separate calls.

    WHEN TO USE SINGLE STRING:
    - One range from one spreadsheet: "Sheet1!A1:B10"

    WHEN TO USE ARRAY:
    - Multiple ranges from SAME spreadsheet: ["Sheet1!A1:B10", "Sheet2!C1:D20"]
    - Multiple sheets from same spreadsheet: ["Sales!A:D", "Inventory!A:Z"]
    - Different ranges from same sheet: ["Data!A1:A10", "Data!C1:C10"]
    → All batched into ONE API call (~10 seconds total, not per range)

    MULTIPLE DIFFERENT SPREADSHEETS:
    There is no single tool call that reads from multiple spreadsheets.
    Call this tool separately for each spreadsheet (one call per spreadsheet):
        get_sheet_data("spreadsheet-1-id", ranges)  # Call 1
        get_sheet_data("spreadsheet-2-id", ranges)  # Call 2

    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
        ranges: String for single range OR array of strings for multiple ranges.
            All ranges must be from the same spreadsheet.
            Format: "SheetName!A1:B10" or just "SheetName" for entire sheet.

    Returns:
        Dictionary containing:
            - spreadsheetId: The spreadsheet ID
            - valueRanges: Array of results (always an array, even for single range)
                - range: The A1 notation of the fetched range
                - values: 2D array of cell values [[row1], [row2], ...]

    Examples:
        # Single range
        get_sheet_data("1abc...", "Sheet1!A1:B10")
        → Returns: {valueRanges: [{range: "Sheet1!A1:B10", values: [...]}]}

        # Multiple ranges - BATCHED in one API call (recommended!)
        get_sheet_data("1abc...", ["Sheet1!A1:B10", "Sheet2!C1:D20", "Sheet3!E:F"])
        → Returns: {valueRanges: [{range: "Sheet1!A1:B10", values: [...]}, ...]}

        # Entire sheets
        get_sheet_data("1abc...", ["Sales", "Inventory", "Reports"])

    SEE ALSO: get_sheet_formulas - for fetching formulas instead of values

    Performance: ~10 seconds per API call, regardless of how many ranges (1 or 100).
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    # Normalize to list for consistent handling
    is_single_range = isinstance(ranges, str)
    range_list = [ranges] if is_single_range else ranges

    log(f"Fetching {len(range_list)} range(s) from spreadsheet {spreadsheet_id}", 'DEBUG')

    # Always use batchGet for consistency - works for single or multiple ranges
    request = sheets_service.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=range_list
    )

    batch_response = execute_with_retry(
        request,
        f"get_sheet_data {spreadsheet_id} ({len(range_list)} range{'s' if len(range_list) > 1 else ''})"
    )

    log(f"✓ Successfully fetched {len(range_list)} range(s)", 'DEBUG')

    return batch_response


@tool(
    annotations=ToolAnnotations(
        title="Get Sheet Formulas",
        readOnlyHint=True,
    ),
)
def get_sheet_formulas(
    spreadsheet_id: str,
    ranges: Union[str, List[str]],
    format: str = 'A1',
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Get formulas from one or more ranges in a SINGLE Google Spreadsheet.

    IMPORTANT - MULTIPLE RANGES ARE BATCHED:
    You can fetch formulas from multiple ranges in the SAME spreadsheet in a SINGLE API call
    by passing an array instead of a string. This is 5-10x faster than making separate calls.

    WHEN TO USE SINGLE STRING:
    - One range from one spreadsheet: "Sheet1!A1:B10"

    WHEN TO USE ARRAY:
    - Multiple formula columns from same spreadsheet: ["Sheet1!B:B", "Sheet2!C:C", "Sheet3!D:D"]
    - Multiple sheets from same spreadsheet: ["Calculations!A:Z", "Analysis!A:Z"]
    - Different ranges from same sheet: ["Data!A1:A100", "Data!C1:C100"]
    → All batched into ONE API call (~10 seconds total, not per range)

    MULTIPLE DIFFERENT SPREADSHEETS:
    There is no single tool call that reads formulas from multiple spreadsheets.
    Call this tool separately for each spreadsheet (one call per spreadsheet):
        get_sheet_formulas("spreadsheet-1-id", ranges, format)  # Call 1
        get_sheet_formulas("spreadsheet-2-id", ranges, format)  # Call 2

    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
        ranges: String for single range OR array of strings for multiple ranges.
            All ranges must be from the same spreadsheet.
            Format: "SheetName!A1:B10" or just "SheetName" for entire sheet.
        format: Formula notation format. Either 'A1' (default) or 'R1C1'.
            - 'A1': Returns formulas like =SUM(A1:A3)
            - 'R1C1': Returns formulas like =SUM(R[-2]C:RC) for pattern analysis

    Returns:
        Dictionary containing:
            - spreadsheetId: The spreadsheet ID
            - valueRanges: Array of results (always an array, even for single range)
                - range: The A1 notation of the fetched range
                - values: 2D array of formulas [[row1], [row2], ...]

    Examples:
        # Single range
        get_sheet_formulas("1abc...", "Sheet1!B:B", format="A1")
        → Returns formulas in A1 notation: =SUM(A1:A10)

        # Multiple ranges - BATCHED in one API call (recommended!)
        get_sheet_formulas("1abc...", ["Sheet1!B:B", "Sheet2!C:C"], format="R1C1")
        → Returns formulas in R1C1 notation: =SUM(R[-9]C[-1]:RC[-1])

        # Analyze formula patterns across sheets
        get_sheet_formulas("1abc...", ["Sales!D:D", "Costs!D:D", "Profit!D:D"], format="R1C1")

    SEE ALSO: get_sheet_data - for fetching cell values instead of formulas

    Performance: ~10 seconds per API call, regardless of how many ranges (1 or 100).
    """
    # Validate format parameter
    if format not in ('A1', 'R1C1'):
        raise ValueError(f"format must be 'A1' or 'R1C1', got '{format}'")

    sheets_service = ctx.request_context.lifespan_context.sheets_service

    # Normalize to list for consistent handling
    is_single_range = isinstance(ranges, str)
    range_list = [ranges] if is_single_range else ranges

    log(f"Fetching formulas from {len(range_list)} range(s) in spreadsheet {spreadsheet_id}", 'DEBUG')

    # Use batchGet to fetch formulas from all ranges
    request = sheets_service.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=range_list,
        valueRenderOption='FORMULA'  # Request formulas instead of values
    )

    batch_response = execute_with_retry(
        request,
        f"get_sheet_formulas {spreadsheet_id} ({len(range_list)} range{'s' if len(range_list) > 1 else ''})"
    )

    # Convert to R1C1 if requested
    if format == 'R1C1':
        for value_range in batch_response.get('valueRanges', []):
            full_range = value_range['range']
            formulas = value_range.get('values', [])

            # Parse the range to determine starting row/column
            # Format: "Sheet1!B1:B10" or "Sheet1!B1" or "Sheet1"
            range_match = re.search(r'!([A-Z]+)(\d+)', full_range)
            if range_match:
                start_col_letter = range_match.group(1)
                start_row = int(range_match.group(2))
                start_col = COLUMN_LUT.get(start_col_letter, _column_letter_to_number(start_col_letter))
            else:
                # If no range specified, assume starting at A1
                start_row = 1
                start_col = 1

            # Convert each formula
            converted_formulas = []
            for row_idx, row in enumerate(formulas):
                converted_row = []
                for col_idx, cell_value in enumerate(row):
                    if isinstance(cell_value, str) and cell_value.startswith('='):
                        current_row = start_row + row_idx
                        current_col = start_col + col_idx
                        converted_formula = _a1_to_r1c1(cell_value, current_row, current_col)
                        converted_row.append(converted_formula)
                    else:
                        # Not a formula, keep as-is
                        converted_row.append(cell_value)
                converted_formulas.append(converted_row)

            # Update the value range with converted formulas
            value_range['values'] = converted_formulas

    log(f"✓ Successfully fetched formulas from {len(range_list)} range(s)", 'DEBUG')

    return batch_response

@tool(
    annotations=ToolAnnotations(
        title="Update Cells",
        destructiveHint=True,
    ),
)
def update_cells(spreadsheet_id: str,
                sheet: str,
                range: str,
                cell_values: List[List[Any]],
                ctx: Context = None) -> Dict[str, Any]:
    """
    Update cells in a Google Spreadsheet.

    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
        sheet: The name of the sheet
        range: Cell range in A1 notation (e.g., 'A1:C10')
        cell_values: 2D array of values to update

    Returns:
        Result of the update operation
    """
    sheets_service, full_range = _setup_sheets_api_call(ctx, sheet, range)

    # Prepare the value range object
    value_range_body = {
        'values': cell_values
    }

    # Call the Sheets API to update values
    request = sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=full_range,
        valueInputOption='USER_ENTERED',
        body=value_range_body
    )
    update_response = execute_with_retry(request, f"update_cells {spreadsheet_id}:{full_range}")

    return update_response


@tool(
    annotations=ToolAnnotations(
        title="Batch Update Cells",
        destructiveHint=True,
    ),
)
def batch_update_cells(spreadsheet_id: str,
                       sheet: str,
                       ranges: Dict[str, List[List[Any]]],
                       ctx: Context = None) -> Dict[str, Any]:
    """
    Batch update multiple ranges in a Google Spreadsheet.
    
    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
        sheet: The name of the sheet
        ranges: Dictionary mapping range strings to 2D arrays of values
               e.g., {'A1:B2': [[1, 2], [3, 4]], 'D1:E2': [['a', 'b'], ['c', 'd']]}
    
    Returns:
        Result of the batch update operation
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    # Prepare the batch update request
    value_range_updates = []
    for range_str, values in ranges.items():
        value_range_updates.append({
            'range': f"{sheet}!{range_str}" if range_str else sheet,
            'values': values
        })

    batch_body = {
        'valueInputOption': 'USER_ENTERED',
        'data': value_range_updates
    }

    # Call the Sheets API to perform batch update
    request = sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=batch_body
    )
    batch_response = execute_with_retry(request, f"batch_update_cells {spreadsheet_id}")

    return batch_response


@tool(
    annotations=ToolAnnotations(
        title="Add Rows",
        destructiveHint=True,
    ),
)
def add_rows(spreadsheet_id: str,
             sheet: str,
             count: int,
             start_row: Optional[int] = None,
             ctx: Context = None) -> Dict[str, Any]:
    """
    Add rows to a sheet in a Google Spreadsheet.
    
    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
        sheet: The name of the sheet
        count: Number of rows to add
        start_row: 0-based row index to start adding. If not provided, adds at the beginning.
    
    Returns:
        Result of the operation
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    
    # Get sheet ID
    request = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id)
    spreadsheet = execute_with_retry(request, f"add_rows:get_sheet {spreadsheet_id}")
    sheet_id = None

    for s in spreadsheet['sheets']:
        if s['properties']['title'] == sheet:
            sheet_id = s['properties']['sheetId']
            break

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    # Prepare the insert rows request
    request_body = {
        "requests": [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": start_row if start_row is not None else 0,
                        "endIndex": (start_row if start_row is not None else 0) + count
                    },
                    "inheritFromBefore": start_row is not None and start_row > 0
                }
            }
        ]
    }

    # Execute the request
    request = sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=request_body
    )
    batch_update_response = execute_with_retry(request, f"add_rows {spreadsheet_id}:{sheet}")

    return batch_update_response


@tool(
    annotations=ToolAnnotations(
        title="Add Columns",
        destructiveHint=True,
    ),
)
def add_columns(spreadsheet_id: str,
                sheet: str,
                count: int,
                start_column: Optional[int] = None,
                ctx: Context = None) -> Dict[str, Any]:
    """
    Add columns to a sheet in a Google Spreadsheet.
    
    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
        sheet: The name of the sheet
        count: Number of columns to add
        start_column: 0-based column index to start adding. If not provided, adds at the beginning.
    
    Returns:
        Result of the operation
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    # Get sheet ID
    request = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id)
    spreadsheet = execute_with_retry(request, f"add_columns:get_sheet {spreadsheet_id}")
    sheet_id = None

    for s in spreadsheet['sheets']:
        if s['properties']['title'] == sheet:
            sheet_id = s['properties']['sheetId']
            break

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    # Prepare the insert columns request
    request_body = {
        "requests": [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": start_column if start_column is not None else 0,
                        "endIndex": (start_column if start_column is not None else 0) + count
                    },
                    "inheritFromBefore": start_column is not None and start_column > 0
                }
            }
        ]
    }

    # Execute the request
    request = sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=request_body
    )
    batch_update_response = execute_with_retry(request, f"add_columns {spreadsheet_id}:{sheet}")

    return batch_update_response


@tool(
    annotations=ToolAnnotations(
        title="List Sheets",
        readOnlyHint=True,
    ),
)
def list_sheets(spreadsheet_id: str, ctx: Context = None) -> List[str]:
    """
    List all sheets in a Google Spreadsheet.
    
    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
    
    Returns:
        List of sheet names
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    # Get spreadsheet metadata
    request = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id)
    spreadsheet = execute_with_retry(request, f"list_sheets {spreadsheet_id}")

    # Extract sheet names
    sheet_names = [sheet['properties']['title'] for sheet in spreadsheet['sheets']]

    return sheet_names


@tool(
    annotations=ToolAnnotations(
        title="Copy Sheet",
        destructiveHint=True,
    ),
)
def copy_sheet(src_spreadsheet: str,
               src_sheet: str,
               dst_spreadsheet: str,
               dst_sheet: str,
               ctx: Context = None) -> Dict[str, Any]:
    """
    Copy a sheet from one spreadsheet to another.
    
    Args:
        src_spreadsheet: Source spreadsheet ID
        src_sheet: Source sheet name
        dst_spreadsheet: Destination spreadsheet ID
        dst_sheet: Destination sheet name
    
    Returns:
        Result of the operation
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    # Get source sheet ID
    request = sheets_service.spreadsheets().get(spreadsheetId=src_spreadsheet)
    src = execute_with_retry(request, f"copy_sheet:get_source {src_spreadsheet}")
    src_sheet_id = None

    for s in src['sheets']:
        if s['properties']['title'] == src_sheet:
            src_sheet_id = s['properties']['sheetId']
            break

    if src_sheet_id is None:
        return {"error": f"Source sheet '{src_sheet}' not found"}

    # Copy the sheet to destination spreadsheet
    request = sheets_service.spreadsheets().sheets().copyTo(
        spreadsheetId=src_spreadsheet,
        sheetId=src_sheet_id,
        body={
            "destinationSpreadsheetId": dst_spreadsheet
        }
    )
    copy_result = execute_with_retry(request, f"copy_sheet {src_spreadsheet}:{src_sheet} -> {dst_spreadsheet}")

    # If destination sheet name is different from the default copied name, rename it
    if 'title' in copy_result and copy_result['title'] != dst_sheet:
        # Get the ID of the newly copied sheet
        copy_sheet_id = copy_result['sheetId']

        # Rename the copied sheet
        rename_request = {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": copy_sheet_id,
                            "title": dst_sheet
                        },
                        "fields": "title"
                    }
                }
            ]
        }

        request = sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=dst_spreadsheet,
            body=rename_request
        )
        rename_result = execute_with_retry(request, f"copy_sheet:rename {dst_spreadsheet}:{dst_sheet}")
        
        return {
            "copy": copy_result,
            "rename": rename_result
        }
    
    return {"copy": copy_result}


@tool(
    annotations=ToolAnnotations(
        title="Rename Sheet",
        destructiveHint=True,
    ),
)
def rename_sheet(spreadsheet: str,
                 sheet: str,
                 new_name: str,
                 ctx: Context = None) -> Dict[str, Any]:
    """
    Rename a sheet in a Google Spreadsheet.
    
    Args:
        spreadsheet: Spreadsheet ID
        sheet: Current sheet name
        new_name: New sheet name
    
    Returns:
        Result of the operation
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    # Get sheet ID
    request = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet)
    spreadsheet_data = execute_with_retry(request, f"rename_sheet:get_sheet {spreadsheet}")
    sheet_id = None

    for s in spreadsheet_data['sheets']:
        if s['properties']['title'] == sheet:
            sheet_id = s['properties']['sheetId']
            break

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    # Prepare the rename request
    request_body = {
        "requests": [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "title": new_name
                    },
                    "fields": "title"
                }
            }
        ]
    }

    # Execute the request
    request = sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet,
        body=request_body
    )
    rename_response = execute_with_retry(request, f"rename_sheet {spreadsheet}:{sheet}->{new_name}")

    return rename_response


@tool(
    annotations=ToolAnnotations(
        title="Get Multiple Spreadsheet Summary",
        readOnlyHint=True,
    ),
)
def get_multiple_spreadsheet_summary(spreadsheet_ids: List[str],
                                   rows_to_fetch: int = 5,
                                   ctx: Context = None) -> List[Dict[str, Any]]:
    """
    Get a summary of multiple Google Spreadsheets, including sheet names, 
    headers, and the first few rows of data for each sheet.
    
    Args:
        spreadsheet_ids: A list of spreadsheet IDs to summarize.
        rows_to_fetch: The number of rows (including header) to fetch for the summary (default: 5).
    
    Returns:
        A list of dictionaries, each representing a spreadsheet summary. 
        Includes spreadsheet title, sheet summaries (title, headers, first rows), or an error.
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    summaries = []
    
    for spreadsheet_id in spreadsheet_ids:
        summary_data = {
            'spreadsheet_id': spreadsheet_id,
            'title': None,
            'sheets': [],
            'error': None
        }
        try:
            # Get spreadsheet metadata
            request = sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields='properties.title,sheets(properties(title,sheetId))'
            )
            spreadsheet = execute_with_retry(request, f"get_multiple_summary:get_metadata {spreadsheet_id}")

            summary_data['title'] = spreadsheet.get('properties', {}).get('title', 'Unknown Title')

            sheet_summaries = []
            for sheet in spreadsheet.get('sheets', []):
                sheet_title = sheet.get('properties', {}).get('title')
                sheet_id = sheet.get('properties', {}).get('sheetId')
                sheet_summary = {
                    'title': sheet_title,
                    'sheet_id': sheet_id,
                    'headers': [],
                    'first_rows': [],
                    'error': None
                }

                if not sheet_title:
                    sheet_summary['error'] = 'Sheet title not found'
                    sheet_summaries.append(sheet_summary)
                    continue

                try:
                    # Fetch the first few rows (e.g., A1:Z5)
                    # Adjust range if fewer rows are requested
                    max_row = max(1, rows_to_fetch) # Ensure at least 1 row is fetched
                    range_to_get = f"{sheet_title}!A1:{max_row}" # Fetch all columns up to max_row

                    request = sheets_service.spreadsheets().values().get(
                        spreadsheetId=spreadsheet_id,
                        range=range_to_get
                    )
                    summary_response = execute_with_retry(request, f"get_multiple_summary:get_rows {spreadsheet_id}:{sheet_title}")

                    values = summary_response.get('values', [])
                    
                    if values:
                        sheet_summary['headers'] = values[0]
                        if len(values) > 1:
                            sheet_summary['first_rows'] = values[1:max_row]
                    else:
                        # Handle empty sheets or sheets with less data than requested
                        sheet_summary['headers'] = []
                        sheet_summary['first_rows'] = []

                except Exception as sheet_e:
                    sheet_summary['error'] = f'Error fetching data for sheet {sheet_title}: {sheet_e}'
                
                sheet_summaries.append(sheet_summary)
            
            summary_data['sheets'] = sheet_summaries
            
        except Exception as e:
            summary_data['error'] = f'Error fetching spreadsheet {spreadsheet_id}: {e}'
            
        summaries.append(summary_data)
        
    return summaries


@mcp.resource("spreadsheet://{spreadsheet_id}/info")
def get_spreadsheet_info(spreadsheet_id: str) -> str:
    """
    Get basic information about a Google Spreadsheet.
    
    Args:
        spreadsheet_id: The ID of the spreadsheet
    
    Returns:
        JSON string with spreadsheet information
    """
    # Access the context through mcp.get_lifespan_context() for resources
    context = mcp.get_lifespan_context()
    sheets_service = context.sheets_service

    # Get spreadsheet metadata
    request = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id)
    spreadsheet = execute_with_retry(request, f"get_spreadsheet_info {spreadsheet_id}")
    
    # Extract relevant information
    info = {
        "title": spreadsheet.get('properties', {}).get('title', 'Unknown'),
        "sheets": [
            {
                "title": sheet['properties']['title'],
                "sheetId": sheet['properties']['sheetId'],
                "gridProperties": sheet['properties'].get('gridProperties', {})
            }
            for sheet in spreadsheet.get('sheets', [])
        ]
    }
    
    return json.dumps(info, indent=2)


@tool(
    annotations=ToolAnnotations(
        title="Create Spreadsheet",
        destructiveHint=True,
    ),
)
def create_spreadsheet(title: str, folder_id: Optional[str] = None, ctx: Context = None) -> Dict[str, Any]:
    """
    Create a new Google Spreadsheet.
    
    Args:
        title: The title of the new spreadsheet
        folder_id: Optional Google Drive folder ID where the spreadsheet should be created.
                  If not provided, uses the configured default folder or creates in root.
    
    Returns:
        Information about the newly created spreadsheet including its ID
    """
    drive_service = ctx.request_context.lifespan_context.drive_service
    # Use provided folder_id or fall back to configured default
    target_folder_id = folder_id or ctx.request_context.lifespan_context.folder_id

    # Create the spreadsheet
    file_body = {
        'name': title,
        'mimeType': 'application/vnd.google-apps.spreadsheet',
    }
    if target_folder_id:
        file_body['parents'] = [target_folder_id]

    request = drive_service.files().create(
        supportsAllDrives=True,
        body=file_body,
        fields='id, name, parents'
    )
    spreadsheet = execute_with_retry(request, f"create_spreadsheet {title}")

    spreadsheet_id = spreadsheet.get('id')
    parents = spreadsheet.get('parents')
    folder_info = f" in folder {target_folder_id}" if target_folder_id else " in root"
    log(f"Spreadsheet created with ID: {spreadsheet_id}{folder_info}", 'INFO')

    return {
        'spreadsheetId': spreadsheet_id,
        'title': spreadsheet.get('name', title),
        'folder': parents[0] if parents else 'root',
    }


@tool(
    annotations=ToolAnnotations(
        title="Create Sheet",
        destructiveHint=True,
    ),
)
def create_sheet(spreadsheet_id: str,
                title: str,
                ctx: Context = None) -> Dict[str, Any]:
    """
    Create a new sheet tab in an existing Google Spreadsheet.
    
    Args:
        spreadsheet_id: The ID of the spreadsheet
        title: The title for the new sheet
    
    Returns:
        Information about the newly created sheet
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    
    # Define the add sheet request
    request_body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": title
                    }
                }
            }
        ]
    }
    
    # Execute the request
    request = sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=request_body
    )
    create_sheet_response = execute_with_retry(request, f"create_sheet {spreadsheet_id}:{title}")

    # Extract the new sheet information
    new_sheet_props = create_sheet_response['replies'][0]['addSheet']['properties']

    return {
        'sheetId': new_sheet_props['sheetId'],
        'title': new_sheet_props['title'],
        'index': new_sheet_props.get('index'),
        'spreadsheetId': spreadsheet_id
    }


@tool(
    annotations=ToolAnnotations(
        title="List Spreadsheets",
        readOnlyHint=True,
    ),
)
def list_spreadsheets(folder_id: Optional[str] = None, ctx: Context = None) -> List[Dict[str, str]]:
    """
    List all spreadsheets in the specified Google Drive folder.
    If no folder is specified, uses the configured default folder or lists from 'My Drive'.
    
    Args:
        folder_id: Optional Google Drive folder ID to search in.
                  If not provided, uses the configured default folder or searches 'My Drive'.
    
    Returns:
        List of spreadsheets with their ID and title
    """
    drive_service = ctx.request_context.lifespan_context.drive_service
    # Use provided folder_id or fall back to configured default
    target_folder_id = folder_id or ctx.request_context.lifespan_context.folder_id
    
    query = "mimeType='application/vnd.google-apps.spreadsheet'"
    
    # If a specific folder is provided or configured, search only in that folder
    if target_folder_id:
        query += f" and '{target_folder_id}' in parents"
        log(f"Searching for spreadsheets in folder: {target_folder_id}", 'DEBUG')
    else:
        log("Searching for spreadsheets in 'My Drive'", 'DEBUG')
    
    # List spreadsheets
    request = drive_service.files().list(
        q=query,
        spaces='drive',
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        fields='files(id, name)',
        orderBy='modifiedTime desc'
    )
    results = execute_with_retry(request, f"list_spreadsheets folder:{target_folder_id or 'My Drive'}")
    
    spreadsheets = results.get('files', [])
    
    return [{'id': sheet['id'], 'title': sheet['name']} for sheet in spreadsheets]


@tool(
    annotations=ToolAnnotations(
        title="Share Spreadsheet",
        destructiveHint=True,
    ),
)
def share_spreadsheet(spreadsheet_id: str,
                      recipients: List[Dict[str, str]],
                      send_notification: bool = True,
                      ctx: Context = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Share a Google Spreadsheet with multiple users via email, assigning specific roles.
    
    Args:
        spreadsheet_id: The ID of the spreadsheet to share.
        recipients: A list of dictionaries, each containing 'email_address' and 'role'.
                    The role should be one of: 'reader', 'commenter', 'writer'.
                    Example: [
                        {'email_address': 'user1@example.com', 'role': 'writer'},
                        {'email_address': 'user2@example.com', 'role': 'reader'}
                    ]
        send_notification: Whether to send a notification email to the users. Defaults to True.

    Returns:
        A dictionary containing lists of 'successes' and 'failures'. 
        Each item in the lists includes the email address and the outcome.
    """
    drive_service = ctx.request_context.lifespan_context.drive_service
    successes = []
    failures = []
    
    for recipient in recipients:
        email_address = recipient.get('email_address')
        role = recipient.get('role', 'writer') # Default to writer if role is missing for an entry
        
        if not email_address:
            failures.append({
                'email_address': None,
                'error': 'Missing email_address in recipient entry.'
            })
            continue
            
        if role not in ['reader', 'commenter', 'writer']:
             failures.append({
                'email_address': email_address,
                'error': f"Invalid role '{role}'. Must be 'reader', 'commenter', or 'writer'."
            })
             continue

        permission = {
            'type': 'user',
            'role': role,
            'emailAddress': email_address
        }
        
        try:
            request = drive_service.permissions().create(
                fileId=spreadsheet_id,
                body=permission,
                sendNotificationEmail=send_notification,
                fields='id'
            )
            permission_response = execute_with_retry(request, f"share_spreadsheet {spreadsheet_id} with {email_address}")
            successes.append({
                'email_address': email_address,
                'role': role,
                'permissionId': permission_response.get('id')
            })
        except Exception as e:
            error_details = str(e)
            if hasattr(e, 'content'):
                error_content_json = json.loads(e.content) if isinstance(e.content, (str, bytes)) else None
                if error_content_json:
                    error_details = error_content_json.get('error', {}).get('message', error_details)
            failures.append({
                'email_address': email_address,
                'error': f"Failed to share: {error_details}"
            })
            
    return {"successes": successes, "failures": failures}


@tool(
    annotations=ToolAnnotations(
        title="List Folders",
        readOnlyHint=True,
    ),
)
def list_folders(parent_folder_id: Optional[str] = None, ctx: Context = None) -> List[Dict[str, str]]:
    """
    List all folders in the specified Google Drive folder.
    If no parent folder is specified, lists folders from 'My Drive' root.
    
    Args:
        parent_folder_id: Optional Google Drive folder ID to search within.
                         If not provided, searches the root of 'My Drive'.
    
    Returns:
        List of folders with their ID, name, and parent information
    """
    drive_service = ctx.request_context.lifespan_context.drive_service
    
    query = "mimeType='application/vnd.google-apps.folder'"
    
    # If a specific parent folder is provided, search only within that folder
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"
        log(f"Searching for folders in parent folder: {parent_folder_id}", 'DEBUG')
    else:
        # Search in root of My Drive (folders that don't have any parent folders)
        query += " and 'root' in parents"
        log("Searching for folders in 'My Drive' root", 'DEBUG')
    
    # List folders
    request = drive_service.files().list(
        q=query,
        spaces='drive',
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        fields='files(id, name, parents)',
        orderBy='name'
    )
    results = execute_with_retry(request, f"list_folders parent:{parent_folder_id or 'root'}")
    
    folders = results.get('files', [])
    
    return [
        {
            'id': folder['id'], 
            'name': folder['name'],
            'parent': folder.get('parents', ['root'])[0] if folder.get('parents') else 'root'
        } 
        for folder in folders
    ]




@tool(
    annotations=ToolAnnotations(
        title="Search Spreadsheets by Name or Content",
        readOnlyHint=True,
    ),
)
def search_spreadsheets(query: str,
                        max_results: int = 20,
                        ctx: Context = None) -> List[Dict[str, Any]]:
    """
    Search for spreadsheets in Google Drive by name or content.

    Args:
        query: Search query string. Searches in file name and content.
               Examples: "budget 2024", "sales report", "project tracker"
        max_results: Maximum number of results to return (default 20, max 100)

    Returns:
        List of matching spreadsheets with their ID, name, and metadata
    """
    drive_service = ctx.request_context.lifespan_context.drive_service

    # Limit max_results to reasonable bounds
    max_results = min(max(1, max_results), 100)

    # Build the search query for Google Drive
    # Search only for spreadsheets and match the query in name or fullText
    search_query = (
        f"mimeType='application/vnd.google-apps.spreadsheet' and "
        f"(name contains '{query}' or fullText contains '{query}')"
    )

    request = drive_service.files().list(
        q=search_query,
        pageSize=max_results,
        spaces='drive',
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        fields='files(id, name, createdTime, modifiedTime, owners, webViewLink)',
        orderBy='modifiedTime desc'
    )
    search_results = execute_with_retry(request, f"search_spreadsheets query:{query}")

    files = search_results.get('files', [])

    return [
        {
            'id': f['id'],
            'name': f['name'],
            'created_time': f.get('createdTime'),
            'modified_time': f.get('modifiedTime'),
            'owners': [owner.get('emailAddress') for owner in f.get('owners', [])],
            'web_link': f.get('webViewLink')
        }
        for f in files
    ]


def _column_index_to_letter(index: int) -> str:
    """Convert 0-based column index to A1 notation letter (0='A', 25='Z', 26='AA', etc.)"""
    ALPHABET_SIZE = 26
    column_letter = ""
    while index >= 0:
        column_letter = chr(index % ALPHABET_SIZE + ord('A')) + column_letter
        index = index // ALPHABET_SIZE - 1
    return column_letter


@tool(
    annotations=ToolAnnotations(
        title="Find Cells",
        readOnlyHint=True,
    ),
)
def find_in_spreadsheet(spreadsheet_id: str,
                        query: str,
                        sheet: Optional[str] = None,
                        case_sensitive: bool = False,
                        max_results: int = 50,
                        ctx: Context = None) -> List[Dict[str, Any]]:
    """
    Find cells containing a specific value in a Google Spreadsheet.

    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
        query: The text to search for in cell values
        sheet: Optional sheet name to search in. If not provided, searches all sheets.
        case_sensitive: Whether the search should be case-sensitive (default False)
        max_results: Maximum number of results to return (default 50)

    Returns:
        List of found cells with their location (sheet, cell in A1 notation) and value
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    results = []

    request = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields='sheets(properties(title,sheetId))'
    )
    spreadsheet = execute_with_retry(request, f"find_in_spreadsheet:get_sheets {spreadsheet_id}")

    sheets_to_search = []
    for s in spreadsheet.get('sheets', []):
        sheet_title = s.get('properties', {}).get('title')
        if sheet is None or sheet_title == sheet:
            sheets_to_search.append(sheet_title)

    if not sheets_to_search:
        return [{'error': f"Sheet '{sheet}' not found"}]

    search_query = query if case_sensitive else query.lower()

    for sheet_name in sheets_to_search:
        if len(results) >= max_results:
            break

        request = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sheet_name
        )
        response = execute_with_retry(request, f"find_in_spreadsheet:search {spreadsheet_id}:{sheet_name}")

        values = response.get('values', [])

        for row_idx, row in enumerate(values):
            if len(results) >= max_results:
                break

            for col_idx, cell_value in enumerate(row):
                if len(results) >= max_results:
                    break

                cell_str = str(cell_value)
                compare_value = cell_str if case_sensitive else cell_str.lower()

                if search_query in compare_value:
                    cell_ref = f"{_column_index_to_letter(col_idx)}{row_idx + 1}"
                    results.append({
                        'sheet': sheet_name,
                        'cell': cell_ref,
                        'value': cell_value
                    })

    return results


@tool(
    annotations=ToolAnnotations(
        title="Batch Update",
        destructiveHint=True,
    ),
)
def batch_update(spreadsheet_id: str,
                 requests: List[Dict[str, Any]],
                 ctx: Context = None) -> Dict[str, Any]:
    """
    Execute a batch update on a Google Spreadsheet using the full batchUpdate endpoint.
    This provides access to all batchUpdate operations including adding sheets, updating properties,
    inserting/deleting dimensions, formatting, and more.
    
    Args:
        spreadsheet_id: The ID of the spreadsheet (found in the URL)
        requests: A list of request objects. Each request object can contain any valid batchUpdate operation.
                 Common operations include:
                 - addSheet: Add a new sheet
                 - updateSheetProperties: Update sheet properties (title, grid properties, etc.)
                 - insertDimension: Insert rows or columns
                 - deleteDimension: Delete rows or columns
                 - updateCells: Update cell values and formatting
                 - updateBorders: Update cell borders
                 - addConditionalFormatRule: Add conditional formatting
                 - deleteConditionalFormatRule: Remove conditional formatting
                 - updateDimensionProperties: Update row/column properties
                 - and many more...
                 
                 Example requests:
                 [
                     {
                         "addSheet": {
                             "properties": {
                                 "title": "New Sheet"
                             }
                         }
                     },
                     {
                         "updateSheetProperties": {
                             "properties": {
                                 "sheetId": 0,
                                 "title": "Renamed Sheet"
                             },
                             "fields": "title"
                         }
                     },
                     {
                         "insertDimension": {
                             "range": {
                                 "sheetId": 0,
                                 "dimension": "ROWS",
                                 "startIndex": 1,
                                 "endIndex": 3
                             }
                         }
                     }
                 ]
    
    Returns:
        Result of the batch update operation, including replies for each request
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    
    # Validate input
    if not requests:
        return {"error": "requests list cannot be empty"}
    
    if not all(isinstance(req, dict) for req in requests):
        return {"error": "Each request must be a dictionary"}
    
    # Prepare the batch update request body
    request_body = {
        "requests": requests
    }

    # Execute the batch update
    request = sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=request_body
    )
    batch_update_result = execute_with_retry(request, f"batch_update {spreadsheet_id}")

    return batch_update_result


def main():
    log("=" * 60, 'INFO')
    log("MCP Google Sheets Server Starting", 'INFO')
    log("=" * 60, 'INFO')
    log(f"Python: {sys.version.split()[0]}", 'INFO')
    log(f"Working directory: {os.getcwd()}", 'INFO')

    # Show log level
    level_name = [k for k, v in LOG_LEVELS.items() if v == _LOG_LEVEL][0]
    log(f"Log level: {level_name} (set LOG_LEVEL env var to change: DEBUG/INFO/WARN/ERROR)", 'INFO')

    # Log tool filtering configuration if enabled
    if ENABLED_TOOLS is not None:
        log(f"Tool filtering: ENABLED ({len(ENABLED_TOOLS)} tools)", 'INFO')
        log(f"  Active tools: {', '.join(sorted(ENABLED_TOOLS))}", 'INFO')
    else:
        log("Tool filtering: DISABLED (all tools enabled)", 'INFO')

    log(f"API timeout limit: {API_TIMEOUT}s", 'INFO')
    log(f"Rate limit retries: {MAX_RETRIES} (max backoff: {MAX_BACKOFF}s)", 'INFO')
    log("=" * 60, 'INFO')

    # Run the server
    transport = "stdio"
    for i, arg in enumerate(sys.argv):
        if arg == "--transport" and i + 1 < len(sys.argv):
            transport = sys.argv[i + 1]
            break

    log(f"Starting MCP server with transport: {transport}", 'INFO')
    mcp.run(transport=transport)
