#!/usr/bin/env python
"""
Benchmark different approaches for converting A1 notation to R1C1 notation.
"""

import re
import time
from typing import Tuple, Optional

# ============================================================================
# Approach 1: Computed conversion (parse column letters on the fly)
# ============================================================================

def column_letter_to_number_computed(col: str) -> int:
    """Convert column letter(s) to number (A=1, Z=26, AA=27, etc.)"""
    num = 0
    for char in col:
        num = num * 26 + (ord(char) - ord('A') + 1)
    return num

def a1_to_r1c1_computed(formula: str, current_row: int, current_col: int) -> str:
    """Convert A1 notation to R1C1 using computed column conversion."""

    def replace_cell_ref(match):
        sheet_prefix = match.group(1) or ''
        col_abs = match.group(2)  # $ before column
        col_letters = match.group(3)
        row_abs = match.group(4)  # $ before row
        row_num = match.group(5)

        # Convert column letters to number
        col_num = column_letter_to_number_computed(col_letters)
        row = int(row_num)

        # Build R1C1 notation
        if row_abs:
            row_part = f"R{row}"
        else:
            offset = row - current_row
            row_part = f"R[{offset}]" if offset != 0 else "R"

        if col_abs:
            col_part = f"C{col_num}"
        else:
            offset = col_num - current_col
            col_part = f"C[{offset}]" if offset != 0 else "C"

        return f"{sheet_prefix}{row_part}{col_part}"

    # Regex to match cell references
    # Group 1: Optional sheet name with !
    # Group 2: Optional $ before column
    # Group 3: Column letters
    # Group 4: Optional $ before row
    # Group 5: Row number
    pattern = r"(?:([^!]+!))?(\$)?([A-Z]+)(\$)?(\d+)"

    return re.sub(pattern, replace_cell_ref, formula)


# ============================================================================
# Approach 2: LUT for column letters (pre-computed lookup table)
# ============================================================================

# Pre-build lookup table for columns A-ZZZ (up to column 18278)
def build_column_lut(max_col: int = 1000) -> dict:
    """Build lookup table for column letters to numbers."""
    lut = {}
    for i in range(1, max_col + 1):
        col_letter = ""
        num = i
        while num > 0:
            num -= 1
            col_letter = chr(num % 26 + ord('A')) + col_letter
            num //= 26
        lut[col_letter] = i
    return lut

COLUMN_LUT = build_column_lut(1000)

def a1_to_r1c1_lut(formula: str, current_row: int, current_col: int) -> str:
    """Convert A1 notation to R1C1 using lookup table for columns."""

    def replace_cell_ref(match):
        sheet_prefix = match.group(1) or ''
        col_abs = match.group(2)
        col_letters = match.group(3)
        row_abs = match.group(4)
        row_num = match.group(5)

        # Use LUT for column conversion
        col_num = COLUMN_LUT.get(col_letters)
        if col_num is None:
            # Fallback for columns beyond LUT
            col_num = column_letter_to_number_computed(col_letters)

        row = int(row_num)

        # Build R1C1 notation
        if row_abs:
            row_part = f"R{row}"
        else:
            offset = row - current_row
            row_part = f"R[{offset}]" if offset != 0 else "R"

        if col_abs:
            col_part = f"C{col_num}"
        else:
            offset = col_num - current_col
            col_part = f"C[{offset}]" if offset != 0 else "C"

        return f"{sheet_prefix}{row_part}{col_part}"

    pattern = r"(?:([^!]+!))?(\$)?([A-Z]+)(\$)?(\d+)"
    return re.sub(pattern, replace_cell_ref, formula)


# ============================================================================
# Approach 3: Compiled regex (pre-compile the pattern)
# ============================================================================

CELL_REF_PATTERN = re.compile(r"(?:([^!]+!))?(\$)?([A-Z]+)(\$)?(\d+)")

def a1_to_r1c1_compiled(formula: str, current_row: int, current_col: int) -> str:
    """Convert A1 notation to R1C1 using pre-compiled regex and LUT."""

    def replace_cell_ref(match):
        sheet_prefix = match.group(1) or ''
        col_abs = match.group(2)
        col_letters = match.group(3)
        row_abs = match.group(4)
        row_num = match.group(5)

        col_num = COLUMN_LUT.get(col_letters, column_letter_to_number_computed(col_letters))
        row = int(row_num)

        # Build R1C1 notation
        if row_abs:
            row_part = f"R{row}"
        else:
            offset = row - current_row
            row_part = f"R[{offset}]" if offset != 0 else "R"

        if col_abs:
            col_part = f"C{col_num}"
        else:
            offset = col_num - current_col
            col_part = f"C[{offset}]" if offset != 0 else "C"

        return f"{sheet_prefix}{row_part}{col_part}"

    return CELL_REF_PATTERN.sub(replace_cell_ref, formula)


# ============================================================================
# Benchmark
# ============================================================================

def benchmark():
    """Run benchmarks on different conversion approaches."""

    # Test formulas (realistic examples)
    test_cases = [
        ("=SUM(A1:A10)", 5, 2),
        ("=A2*2", 3, 2),
        ("=IF($A$1>0,B2*C2,0)", 2, 4),
        ("=VLOOKUP(A5,Sheet1!$A$1:$D$100,2,FALSE)", 5, 3),
        ("=INDEX($A$1:$Z$1000,MATCH(B10,A:A,0),3)", 10, 5),
        ("=SUMIF(Data!A:A,\">100\",Data!B:B)", 1, 1),
        ("=A1+B1+C1+D1+E1+F1", 1, 1),
        ("=$A1*B$2+C3", 3, 3),
    ]

    # Repeat test cases to simulate processing a large sheet
    large_test_set = test_cases * 1000  # 8,000 formulas

    methods = [
        ("Computed (no LUT)", a1_to_r1c1_computed),
        ("LUT for columns", a1_to_r1c1_lut),
        ("Compiled regex + LUT", a1_to_r1c1_compiled),
    ]

    print("="*80)
    print("A1 to R1C1 Conversion Benchmark")
    print("="*80)
    print(f"\nTest set: {len(test_cases)} unique formulas × 1000 = {len(large_test_set)} conversions\n")

    # Verify all methods produce same results
    print("Verifying correctness...")
    for formula, row, col in test_cases:
        results = [method(formula, row, col) for name, method in methods]
        if len(set(results)) != 1:
            print(f"ERROR: Methods produce different results for {formula}")
            for i, (name, _) in enumerate(methods):
                print(f"  {name}: {results[i]}")
        else:
            print(f"✓ {formula} → {results[0]}")

    print("\n" + "="*80)
    print("Performance Benchmark")
    print("="*80 + "\n")

    results = []

    for name, method in methods:
        start = time.perf_counter()

        for formula, row, col in large_test_set:
            _ = method(formula, row, col)

        end = time.perf_counter()
        elapsed = end - start
        per_conversion = (elapsed / len(large_test_set)) * 1_000_000  # microseconds

        results.append((name, elapsed, per_conversion))
        print(f"{name:25s}: {elapsed:.4f}s total, {per_conversion:.2f}μs per conversion")

    # Show relative performance
    print("\n" + "-"*80)
    print("Relative Performance (vs fastest):")
    print("-"*80)

    fastest_time = min(r[1] for r in results)
    for name, elapsed, per_conv in results:
        speedup = elapsed / fastest_time
        print(f"{name:25s}: {speedup:.2f}x {'(FASTEST)' if speedup == 1.0 else ''}")

    print("\n" + "="*80)

if __name__ == '__main__':
    benchmark()
