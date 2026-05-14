# R1C1 Formula Format Support - Design Document

**Date:** 2026-02-23
**Status:** Approved for Implementation
**Author:** Claude Sonnet 4.5

---

## Problem Statement

Users analyzing spreadsheet structure need to identify unique formula patterns across ranges. R1C1 notation makes this trivial by normalizing relative references - a formula like `=SUM(R[-1]C:R[-5]C)` is identical across all cells where it appears, whereas A1 notation changes per cell (`=SUM(A1:A5)`, `=SUM(B1:B5)`, etc.).

The existing `get_sheet_formulas` tool only returns formulas in A1 notation because the Google Sheets REST API doesn't natively support R1C1 format (unlike Apps Script's `getFormulasR1C1()` method).

## Use Case

Typical workflow for spreadsheet structure analysis:
1. Extract formulas from a spreadsheet
2. Convert to R1C1 notation
3. Use R1C1 formula as hash key to group identical formula patterns
4. Identify which ranges use each unique formula
5. Analyze formula patterns across the spreadsheet

## Solution Overview

Add a `format` parameter to the existing `get_sheet_formulas` tool that accepts `'A1'` (default) or `'R1C1'`. When `format='R1C1'` is requested, perform client-side conversion from A1 to R1C1 notation using the fastest conversion method (pre-compiled regex + column lookup table).

## Design

### API Changes

**Modified function signature:**

```python
def get_sheet_formulas(spreadsheet_id: str,
                       sheet: str,
                       range: Optional[str] = None,
                       format: str = 'A1',  # NEW PARAMETER
                       ctx: Context = None) -> List[List[Any]]:
```

**Parameter:**
- `format` (str): Formula notation format. Either `'A1'` (default) or `'R1C1'`.
  - `'A1'`: Returns formulas like `=SUM(A1:A3)` (current behavior)
  - `'R1C1'`: Returns formulas like `=SUM(R[-2]C:RC)` (new behavior)

**Backward Compatibility:** Default value is `'A1'`, preserving existing behavior.

### Architecture

```
get_sheet_formulas(format='R1C1')
    ↓
1. Validate format parameter ('A1' or 'R1C1')
    ↓
2. Fetch formulas from Google Sheets API
   (returns A1 notation via valueRenderOption='FORMULA')
    ↓
3. IF format == 'R1C1':
     For each cell (row_idx, col_idx) in result:
       - Convert formula from A1 to R1C1
       - Account for cell position (row_idx + 1, col_idx + 1)
    ↓
4. Return 2D array of formulas
```

### Conversion Logic

**Module-level constants (loaded once):**
```python
# Pre-compile regex pattern for performance
CELL_REF_PATTERN = re.compile(r"(?:([^!]+!))?(\$)?([A-Z]+)(\$)?(\d+)")

# Pre-build column letter → number lookup table (A=1, Z=26, AA=27, etc.)
# Supports columns up to ZZZ (18,278 columns)
COLUMN_LUT = build_column_lut(1000)  # covers most use cases
```

**Conversion function:**
```python
def _a1_to_r1c1(formula: str, current_row: int, current_col: int) -> str:
    """
    Convert formula from A1 notation to R1C1 notation.

    Args:
        formula: Formula string in A1 notation (e.g., "=SUM(A1:B5)")
        current_row: 1-based row number of the cell containing this formula
        current_col: 1-based column number of the cell containing this formula

    Returns:
        Formula in R1C1 notation (e.g., "=SUM(R[-4]C[-1]:R[0]C[0])")
    """
    # Use regex to find and replace all cell references
    # Handle: A1, $A$1, A$1, $A1, Sheet1!A1, ranges A1:B5, etc.
```

**Reference type handling:**

| A1 Notation | From Cell B2 | R1C1 Result | Description |
|-------------|--------------|-------------|-------------|
| `A1` | B2 | `R[-1]C[-1]` | Relative reference (both relative) |
| `$A$1` | B2 | `R1C1` | Absolute reference (both fixed) |
| `A$1` | B2 | `R1C[-1]` | Mixed (absolute row, relative column) |
| `$A1` | B2 | `R[-1]C1` | Mixed (relative row, absolute column) |
| `A1:B5` | B2 | `R[-1]C[-1]:R[3]C` | Range reference |
| `Sheet1!A1` | B2 | `Sheet1!R[-1]C[-1]` | Sheet-qualified reference |
| `A:A` | B2 | `A:A` | Column reference (unchanged) |
| `1:1` | B2 | `1:1` | Row reference (unchanged) |

**Performance:** Benchmarked at 3.50μs per conversion (10,000 formulas in ~35ms).

### Error Handling

1. **Invalid format parameter:**
   - Validate `format in ('A1', 'R1C1')`
   - Return clear error message if invalid

2. **Malformed formulas:**
   - If conversion fails, log warning and return original formula
   - Don't fail entire request due to one bad formula

3. **Ultra-wide sheets:**
   - LUT covers columns A-ALL (1000 columns)
   - Fallback to computed conversion for columns beyond LUT

### Testing Strategy

1. **Unit tests for conversion:**
   - Test relative references: `=A1` from B2 → `=R[-1]C[-1]`
   - Test absolute references: `=$A$1` from B2 → `=R1C1`
   - Test mixed references: `=A$1`, `=$A1`
   - Test ranges: `=SUM(A1:B5)`
   - Test sheet references: `=Sheet1!A1`
   - Test complex formulas: `=IF($A$1>0,B2*C2,0)`
   - Test column/row references: `=SUM(A:A)`, `=SUM(1:1)`

2. **Integration tests:**
   - Test with real spreadsheet via API
   - Verify format='A1' returns expected A1 formulas
   - Verify format='R1C1' returns expected R1C1 formulas
   - Test with empty cells and non-formula cells

3. **Edge cases:**
   - Empty range (no formulas)
   - Large spreadsheet (performance test)
   - Formulas with string literals containing cell-like text: `="A1"`
   - Named ranges in formulas

4. **Backward compatibility:**
   - Verify default behavior (format='A1') unchanged
   - Test existing code continues to work

### Implementation Files

1. **`src/mcp_google_sheets/server.py`:**
   - Add module-level constants (CELL_REF_PATTERN, COLUMN_LUT)
   - Add `_build_column_lut()` helper function
   - Add `_a1_to_r1c1()` conversion function
   - Modify `get_sheet_formulas()` to add `format` parameter
   - Add format validation and conversion logic

2. **`tests/test_formula_conversion.py`** (new file):
   - Unit tests for `_a1_to_r1c1()` function
   - Test all reference types and edge cases

3. **`tests/test_r1c1_integration.py`** (new file):
   - Integration tests with real API calls
   - Verify end-to-end behavior

4. **`docs/plans/2026-02-23-r1c1-formula-format-implementation.md`:**
   - Detailed implementation steps
   - Code structure and order of implementation

## API Discovery Test Results

We tested whether the Google Sheets REST API natively supports R1C1 format:

**Test methodology:**
- Created test spreadsheet with formulas: `=SUM(A1:A3)`, `=A2*2`, `=A3+A2`
- Tested `spreadsheets.values.get` with `valueRenderOption='FORMULA'`
- Tested `spreadsheets.get` with `includeGridData=True` (accessing `userEnteredValue.formulaValue`)

**Results:**
Both methods return formulas in **A1 notation only**. If R1C1 was supported, we would see:
- `=SUM(R[-2]C:RC)` instead of `=SUM(A1:A3)`
- `=RC[-1]*2` instead of `=A2*2`

**Conclusion:** Client-side conversion is required.

## Performance Benchmark Results

Tested three conversion approaches on 8,000 formula conversions:

| Approach | Time per conversion | Relative speed |
|----------|-------------------|----------------|
| Computed (no LUT) | 4.28μs | 1.22x slower |
| LUT for columns | 3.59μs | 1.03x slower |
| **Compiled regex + LUT** | **3.50μs** | **1.00x (fastest)** |

**Winner:** Pre-compiled regex + column lookup table (22% faster than basic approach)

## Example Usage

```python
# Current behavior (A1 notation)
formulas = get_sheet_formulas(
    spreadsheet_id='abc123',
    sheet='Sheet1',
    range='A1:B10'
)
# Returns: [['=SUM(A1:A3)', '=B1*2'], ...]

# New behavior (R1C1 notation)
formulas_r1c1 = get_sheet_formulas(
    spreadsheet_id='abc123',
    sheet='Sheet1',
    range='A1:B10',
    format='R1C1'
)
# Returns: [['=SUM(R[-2]C:RC)', '=RC[-1]*2'], ...]

# Use R1C1 as hash key to group formulas
from collections import defaultdict
formula_groups = defaultdict(list)

for row_idx, row in enumerate(formulas_r1c1):
    for col_idx, formula in enumerate(row):
        if formula.startswith('='):
            formula_groups[formula].append((row_idx, col_idx))

# Now formula_groups maps unique formulas to their cell locations
```

## Documentation Updates

Update `README.md` to document the new `format` parameter:

```markdown
### get_sheet_formulas

Get formulas from a specific sheet in a Google Spreadsheet.

**Parameters:**
- `spreadsheet_id` (string): The spreadsheet ID (from its URL)
- `sheet` (string): Name of the sheet/tab
- `range` (optional string): A1 notation range. If omitted, gets all formulas from the sheet.
- `format` (optional string, default `'A1'`): Formula notation format
  - `'A1'`: Returns formulas in A1 notation (e.g., `=SUM(A1:A3)`)
  - `'R1C1'`: Returns formulas in R1C1 notation (e.g., `=SUM(R[-2]C:RC)`)

**Returns:**
A 2D array of formulas.

**Example:**
```python
# Get formulas in R1C1 notation to identify unique patterns
formulas = get_sheet_formulas(
    spreadsheet_id='abc123',
    sheet='Sheet1',
    format='R1C1'
)
```
```

## Success Criteria

- [ ] `get_sheet_formulas` accepts `format` parameter with values `'A1'` or `'R1C1'`
- [ ] Default behavior (`format='A1'`) unchanged (backward compatible)
- [ ] `format='R1C1'` returns formulas converted to R1C1 notation
- [ ] All reference types handled correctly (relative, absolute, mixed, ranges, sheets)
- [ ] Unit tests achieve 100% coverage of conversion logic
- [ ] Integration tests verify API behavior
- [ ] Performance: 10,000 formula conversions in < 50ms
- [ ] Documentation updated in README.md
- [ ] No breaking changes to existing API

## Future Enhancements

1. **Batch conversion optimization:** If converting entire sheet, could parallelize conversion across chunks
2. **R1C1 → A1 conversion:** Add reverse conversion if needed
3. **Formula analysis tools:** Build higher-level tools on top of R1C1 support (formula grouping, pattern detection)
4. **Named range expansion:** Optionally expand named ranges to R1C1 references

## References

- Google Apps Script Range.getFormulasR1C1(): https://developers.google.com/apps-script/reference/spreadsheet/range#getformulasr1c1
- Google Sheets API Cells Reference: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/cells
- Benchmark code: `/home/jfenal/dev/gh/mcp-google-sheets/benchmark_a1_to_r1c1.py`
- Test spreadsheet: https://docs.google.com/spreadsheets/d/1LxhBS01XKNz0CIDTqA92Cs8gJLxATu0M8aio4swLl4Y/edit
