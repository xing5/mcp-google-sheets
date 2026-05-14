#!/usr/bin/env python
"""
Test script to determine what format formulas are returned in by the Google Sheets API.
Tests both spreadsheets.values.get and spreadsheets.get methods.
"""

import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Use service account from environment
SERVICE_ACCOUNT_PATH = os.environ.get('SERVICE_ACCOUNT_PATH')
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

def test_formula_formats(spreadsheet_id=None):
    """Test what format formulas are returned in."""

    # Authenticate
    if not SERVICE_ACCOUNT_PATH or not os.path.exists(SERVICE_ACCOUNT_PATH):
        print("ERROR: SERVICE_ACCOUNT_PATH not set or file doesn't exist")
        print("Please set SERVICE_ACCOUNT_PATH environment variable")
        return

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_PATH,
        scopes=SCOPES
    )

    sheets_service = build('sheets', 'v4', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)

    created_new = False

    if not spreadsheet_id:
        # Create a test spreadsheet
        print("Creating test spreadsheet...")
        file_body = {
            'name': 'R1C1 Formula Test',
            'mimeType': 'application/vnd.google-apps.spreadsheet',
        }

        spreadsheet = drive_service.files().create(
            body=file_body,
            fields='id, name'
        ).execute()

        spreadsheet_id = spreadsheet.get('id')
        created_new = True
        print(f"Created spreadsheet: {spreadsheet_id}")
    else:
        print(f"Using existing spreadsheet: {spreadsheet_id}")

    # Get first sheet name
    spreadsheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    first_sheet = spreadsheet_metadata['sheets'][0]['properties']['title']
    print(f"Using sheet: {first_sheet}")

    if created_new:
        # Add some test formulas
        # Put values in A1:A3 and a formula in B1
        print("\nAdding test data and formulas...")
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f'{first_sheet}!A1:A3',
            valueInputOption='USER_ENTERED',
            body={'values': [[10], [20], [30]]}
        ).execute()

        # Add a formula that references cells above
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f'{first_sheet}!B1',
            valueInputOption='USER_ENTERED',
            body={'values': [['=SUM(A1:A3)']]}
        ).execute()

        # Add another formula with relative reference
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f'{first_sheet}!B2',
            valueInputOption='USER_ENTERED',
            body={'values': [['=A2*2']]}
        ).execute()

        test_range = f'{first_sheet}!B1:B2'
    else:
        # Use existing sheet - find some cells with formulas
        print("\nScanning for existing formulas...")
        test_range = f'{first_sheet}!A1:Z100'  # Scan a reasonable range

    print("\n" + "="*80)
    print("TEST 1: Using spreadsheets.values.get with valueRenderOption='FORMULA'")
    print("="*80)

    # Test 1: values.get with FORMULA option
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=test_range,
        valueRenderOption='FORMULA'
    ).execute()

    print(f"\nResult from values.get (first 10 formulas found):")
    values = result.get('values', [])
    formula_count = 0
    for row_idx, row in enumerate(values):
        for col_idx, cell in enumerate(row):
            if isinstance(cell, str) and cell.startswith('='):
                print(f"  Row {row_idx+1}, Col {col_idx+1}: {cell[:100]}")
                formula_count += 1
                if formula_count >= 10:
                    break
        if formula_count >= 10:
            break
    print(f"\nTotal formulas found: {formula_count}")

    print("\n" + "="*80)
    print("TEST 2: Using spreadsheets.get with includeGridData=True")
    print("="*80)

    # Test 2: spreadsheets.get with grid data
    result2 = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=[test_range],
        includeGridData=True
    ).execute()

    print(f"\nResult from spreadsheets.get (full structure):")
    print(json.dumps(result2, indent=2))

    # Extract just the formula values for clarity
    if 'sheets' in result2:
        for sheet in result2['sheets']:
            if 'data' in sheet:
                for grid_data in sheet['data']:
                    if 'rowData' in grid_data:
                        print("\n" + "-"*80)
                        print("Extracted formula values from CellData:")
                        print("-"*80)
                        for row_idx, row in enumerate(grid_data['rowData']):
                            if 'values' in row:
                                for col_idx, cell in enumerate(row['values']):
                                    if 'userEnteredValue' in cell:
                                        user_val = cell['userEnteredValue']
                                        if 'formulaValue' in user_val:
                                            print(f"Cell B{row_idx+1}: {user_val['formulaValue']}")

    # Clean up - delete the test spreadsheet if we created it
    print("\n" + "="*80)
    if created_new:
        delete = input("\nDelete test spreadsheet? (y/n): ")
        if delete.lower() == 'y':
            drive_service.files().delete(fileId=spreadsheet_id).execute()
            print(f"Deleted spreadsheet {spreadsheet_id}")
        else:
            print(f"\nTest spreadsheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")
    else:
        print(f"\nUsed existing spreadsheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")

if __name__ == '__main__':
    import sys
    # Allow passing spreadsheet ID as argument
    spreadsheet_id = sys.argv[1] if len(sys.argv) > 1 else None
    test_formula_formats(spreadsheet_id)
