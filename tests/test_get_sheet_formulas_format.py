"""Integration tests for get_sheet_formulas with format parameter."""

import pytest
from unittest.mock import Mock, MagicMock


def test_get_sheet_formulas_default_format_a1():
    """Test that default format returns A1 notation."""
    from mcp_google_sheets.server import get_sheet_formulas

    # Mock context and API response
    ctx = Mock()
    sheets_service = MagicMock()
    ctx.request_context.lifespan_context.sheets_service = sheets_service

    # Mock API to return formulas in A1 notation
    sheets_service.spreadsheets().values().get().execute.return_value = {
        'values': [
            ['=SUM(A1:A3)'],
            ['=A2*2'],
        ]
    }

    result = get_sheet_formulas('test-id', 'Sheet1', 'B1:B2', ctx=ctx)

    # Should return A1 notation (API default)
    assert result == [['=SUM(A1:A3)'], ['=A2*2']]


def test_get_sheet_formulas_format_r1c1():
    """Test format='R1C1' returns R1C1 notation."""
    from mcp_google_sheets.server import get_sheet_formulas

    ctx = Mock()
    sheets_service = MagicMock()
    ctx.request_context.lifespan_context.sheets_service = sheets_service

    # Mock API to return formulas in A1 notation
    sheets_service.spreadsheets().values().get().execute.return_value = {
        'values': [
            ['=SUM(A1:A3)'],  # Cell B1 (row 1, col 2)
            ['=A2*2'],        # Cell B2 (row 2, col 2)
        ]
    }

    result = get_sheet_formulas('test-id', 'Sheet1', 'B1:B2', format='R1C1', ctx=ctx)

    # Should convert to R1C1 notation
    assert result == [
        ['=SUM(RC[-1]:R[2]C[-1])'],  # =SUM(A1:A3) from B1
        ['=RC[-1]*2'],                # =A2*2 from B2
    ]


def test_get_sheet_formulas_invalid_format():
    """Test invalid format parameter raises error."""
    from mcp_google_sheets.server import get_sheet_formulas

    ctx = Mock()

    with pytest.raises(ValueError, match="format must be 'A1' or 'R1C1'"):
        get_sheet_formulas('test-id', 'Sheet1', format='invalid', ctx=ctx)
