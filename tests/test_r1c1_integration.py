"""
Integration tests for R1C1 formula format with real Google Sheets API.

Requires SERVICE_ACCOUNT_PATH environment variable to be set.
Uses test spreadsheet: 1LxhBS01XKNz0CIDTqA92Cs8gJLxATu0M8aio4swLl4Y
"""

import os
import pytest
from google.oauth2 import service_account
from googleapiclient.discovery import build
from mcp_google_sheets.server import SpreadsheetContext

# Skip tests if no credentials available
pytestmark = pytest.mark.skipif(
    not os.environ.get('SERVICE_ACCOUNT_PATH'),
    reason="SERVICE_ACCOUNT_PATH not set"
)

TEST_SPREADSHEET_ID = '1LxhBS01XKNz0CIDTqA92Cs8gJLxATu0M8aio4swLl4Y'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


@pytest.fixture
def sheets_context():
    """Create real Google Sheets API context."""
    service_account_path = os.environ.get('SERVICE_ACCOUNT_PATH')
    creds = service_account.Credentials.from_service_account_file(
        service_account_path,
        scopes=SCOPES
    )
    sheets_service = build('sheets', 'v4', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)

    return SpreadsheetContext(
        sheets_service=sheets_service,
        drive_service=drive_service,
        folder_id=None
    )


def test_get_sheet_formulas_r1c1_real_api(sheets_context):
    """Test R1C1 conversion with real API."""
    from mcp_google_sheets.server import get_sheet_formulas
    from unittest.mock import Mock

    # Create mock context
    ctx = Mock()
    ctx.request_context.lifespan_context = sheets_context

    # Test spreadsheet has formulas in B1:B3:
    # B1: =SUM(A1:A3)
    # B2: =A2*2
    # B3: =A3+A2

    # Get formulas in A1 format
    formulas_a1 = get_sheet_formulas(
        TEST_SPREADSHEET_ID,
        'Sheet1',
        'B1:B3',
        format='A1',
        ctx=ctx
    )

    assert formulas_a1 == [
        ['=SUM(A1:A3)'],
        ['=A2*2'],
        ['=A3+A2']
    ]

    # Get formulas in R1C1 format
    formulas_r1c1 = get_sheet_formulas(
        TEST_SPREADSHEET_ID,
        'Sheet1',
        'B1:B3',
        format='R1C1',
        ctx=ctx
    )

    assert formulas_r1c1 == [
        ['=SUM(RC[-1]:R[2]C[-1])'],  # B1: =SUM(A1:A3)
        ['=RC[-1]*2'],                # B2: =A2*2
        ['=RC[-1]+R[-1]C[-1]']        # B3: =A3+A2
    ]


def test_get_sheet_formulas_r1c1_preserves_non_formulas(sheets_context):
    """Test that non-formula cells are preserved."""
    from mcp_google_sheets.server import get_sheet_formulas
    from unittest.mock import Mock

    ctx = Mock()
    ctx.request_context.lifespan_context = sheets_context

    # Get range that includes both formulas (B column) and values (A column)
    formulas = get_sheet_formulas(
        TEST_SPREADSHEET_ID,
        'Sheet1',
        'A1:B3',
        format='R1C1',
        ctx=ctx
    )

    # A column has numbers (10, 20, 30), B column has formulas
    # Numbers should be preserved as-is, formulas should be converted
    assert len(formulas) == 3
    assert formulas[0][0] in (10, '10')  # Value cells preserved
    assert formulas[0][1].startswith('=')  # Formula converted
