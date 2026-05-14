"""Tests for A1 to R1C1 formula conversion."""

import pytest
from mcp_google_sheets.server import _build_column_lut, _column_letter_to_number, _a1_to_r1c1


def test_column_letter_to_number_single_letters():
    """Test single letter column conversions."""
    assert _column_letter_to_number('A') == 1
    assert _column_letter_to_number('B') == 2
    assert _column_letter_to_number('Z') == 26


def test_column_letter_to_number_double_letters():
    """Test double letter column conversions."""
    assert _column_letter_to_number('AA') == 27
    assert _column_letter_to_number('AB') == 28
    assert _column_letter_to_number('AZ') == 52


def test_column_letter_to_number_triple_letters():
    """Test triple letter column conversions."""
    assert _column_letter_to_number('AAA') == 703


def test_build_column_lut():
    """Test column lookup table builder."""
    lut = _build_column_lut(100)

    assert lut['A'] == 1
    assert lut['Z'] == 26
    assert lut['AA'] == 27
    assert lut['CV'] == 100
    assert len(lut) == 100


def test_a1_to_r1c1_relative_reference():
    """Test relative cell reference conversion."""
    # Formula =A1 in cell B2 (row 2, col 2)
    result = _a1_to_r1c1('=A1', 2, 2)
    assert result == '=R[-1]C[-1]'

    # Formula =B3 in cell B2
    result = _a1_to_r1c1('=B3', 2, 2)
    assert result == '=R[1]C'


def test_a1_to_r1c1_absolute_reference():
    """Test absolute cell reference conversion."""
    # Formula =$A$1 in cell B2
    result = _a1_to_r1c1('=$A$1', 2, 2)
    assert result == '=R1C1'

    # Formula =$B$5 in cell C10
    result = _a1_to_r1c1('=$B$5', 10, 3)
    assert result == '=R5C2'


def test_a1_to_r1c1_mixed_reference():
    """Test mixed absolute/relative references."""
    # Formula =A$1 in cell B2 (absolute row, relative column)
    result = _a1_to_r1c1('=A$1', 2, 2)
    assert result == '=R1C[-1]'

    # Formula =$A1 in cell B2 (relative row, absolute column)
    result = _a1_to_r1c1('=$A1', 2, 2)
    assert result == '=R[-1]C1'


def test_a1_to_r1c1_range_reference():
    """Test range reference conversion."""
    # Formula =SUM(A1:A10) in cell B5
    result = _a1_to_r1c1('=SUM(A1:A10)', 5, 2)
    assert result == '=SUM(R[-4]C[-1]:R[5]C[-1])'

    # Formula =SUM($A$1:$D$100) in cell B2
    result = _a1_to_r1c1('=SUM($A$1:$D$100)', 2, 2)
    assert result == '=SUM(R1C1:R100C4)'


def test_a1_to_r1c1_sheet_reference():
    """Test sheet-qualified references."""
    # Formula =Sheet1!A1 in cell B2
    result = _a1_to_r1c1('=Sheet1!A1', 2, 2)
    assert result == '=Sheet1!R[-1]C[-1]'

    # Formula =Data!$A$1:$B$10 in cell A1
    result = _a1_to_r1c1('=Data!$A$1:$B$10', 1, 1)
    assert result == '=Data!R1C1:R10C2'


def test_a1_to_r1c1_complex_formula():
    """Test complex formula with multiple references."""
    # Formula =IF($A$1>0,B2*C2,0) in cell D2
    result = _a1_to_r1c1('=IF($A$1>0,B2*C2,0)', 2, 4)
    assert result == '=IF(R1C1>0,RC[-2]*RC[-1],0)'


def test_a1_to_r1c1_same_row_column():
    """Test references in same row or column."""
    # Formula =B2 in cell B2 (same cell)
    result = _a1_to_r1c1('=B2', 2, 2)
    assert result == '=RC'

    # Formula =A1+B1+C1 in cell A1
    result = _a1_to_r1c1('=A1+B1+C1', 1, 1)
    assert result == '=RC+RC[1]+RC[2]'


def test_a1_to_r1c1_preserves_numbers_and_operators():
    """Test that numbers and operators are preserved, cell references are converted."""
    # Numbers, operators, and function names should not change
    result = _a1_to_r1c1('=IF(A1>0,A1*2,0)', 2, 2)
    # Cell references should be converted
    assert 'R[-1]C[-1]' in result
    # Numbers and operators should be preserved
    assert '>0' in result
    assert '*2' in result
    assert ',0)' in result

    # Note: String literals that look like cell references (e.g., "A1") are also
    # converted. This is a known limitation of the regex-based approach. Proper
    # handling would require a full formula parser. For the use case of pattern
    # matching, this edge case is acceptable.
