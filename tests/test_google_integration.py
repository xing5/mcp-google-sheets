import base64
import json
import os
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from google.oauth2 import service_account
from googleapiclient.discovery import build

from mcp_google_sheets import server


TOOLS_WITH_INTEGRATION_COVERAGE = {
    "add_chart",
    "add_columns",
    "add_rows",
    "batch_update",
    "batch_update_cells",
    "copy_sheet",
    "create_sheet",
    "create_spreadsheet",
    "find_in_spreadsheet",
    "get_multiple_sheet_data",
    "get_multiple_spreadsheet_summary",
    "get_sheet_data",
    "get_sheet_formulas",
    "list_folders",
    "list_sheets",
    "list_spreadsheets",
    "rename_sheet",
    "search_spreadsheets",
    "share_spreadsheet",
    "update_cells",
}


def fake_ctx(sheets_service=None, drive_service=None, folder_id=None):
    lifespan_context = SimpleNamespace(
        sheets_service=sheets_service,
        drive_service=drive_service,
        folder_id=folder_id,
    )
    request_context = SimpleNamespace(lifespan_context=lifespan_context)
    return SimpleNamespace(request_context=request_context)


def integration_enabled():
    return os.environ.get("RUN_GOOGLE_INTEGRATION") == "1"


def current_tool_names():
    source = Path(server.__file__).read_text(encoding="utf-8")
    return set(re.findall(r"@tool\([\s\S]*?\)\ndef ([a-zA-Z_][a-zA-Z0-9_]*)\(", source))


class IntegrationCoverageDeclarationTests(unittest.TestCase):
    def test_declared_integration_coverage_matches_current_tools(self):
        self.assertEqual(TOOLS_WITH_INTEGRATION_COVERAGE, current_tool_names())


@unittest.skipUnless(integration_enabled(), "set RUN_GOOGLE_INTEGRATION=1 to run live Google tests")
class GoogleSheetsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder_id = os.environ.get("DRIVE_FOLDER_ID")
        if not folder_id:
            raise unittest.SkipTest("DRIVE_FOLDER_ID is required for live integration tests")

        creds = None
        credentials_config = os.environ.get("CREDENTIALS_CONFIG")
        service_account_path = os.environ.get("SERVICE_ACCOUNT_PATH")

        if credentials_config:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(base64.b64decode(credentials_config)),
                scopes=server.SCOPES,
            )
        elif service_account_path:
            creds = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=server.SCOPES,
            )
        else:
            raise unittest.SkipTest("SERVICE_ACCOUNT_PATH or CREDENTIALS_CONFIG is required")

        cls.sheets_service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        cls.drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
        cls.folder_id = folder_id
        cls.created_file_ids = []
        cls.ctx = fake_ctx(
            sheets_service=cls.sheets_service,
            drive_service=cls.drive_service,
            folder_id=folder_id,
        )

    @classmethod
    def tearDownClass(cls):
        for file_id in getattr(cls, "created_file_ids", []):
            try:
                cls.drive_service.files().delete(
                    fileId=file_id,
                    supportsAllDrives=True,
                ).execute()
            except Exception:
                pass

    def create_test_spreadsheet(self, title):
        created = server.create_spreadsheet(title, ctx=self.ctx)
        spreadsheet_id = created["spreadsheetId"]
        self.created_file_ids.append(spreadsheet_id)
        self.assertEqual(created["title"], title)
        self.assertEqual(created["folder"], self.folder_id)
        return spreadsheet_id

    def wait_for_search_result(self, title, spreadsheet_id, timeout_seconds=45):
        deadline = time.time() + timeout_seconds
        last_result = []
        while time.time() < deadline:
            last_result = server.search_spreadsheets(title, max_results=10, ctx=self.ctx)
            if any(sheet.get("id") == spreadsheet_id for sheet in last_result):
                return last_result
            time.sleep(3)
        self.fail(f"search_spreadsheets did not find {spreadsheet_id}: {last_result}")

    def test_all_current_tool_calls_against_google(self):
        suffix = int(time.time())
        primary_title = f"mcp-google-sheets-it-primary-{suffix}"
        copy_target_title = f"mcp-google-sheets-it-copy-target-{suffix}"

        primary_id = self.create_test_spreadsheet(primary_title)
        copy_target_id = self.create_test_spreadsheet(copy_target_title)

        update_result = server.update_cells(
            primary_id,
            "Sheet1",
            "A1:D3",
            [
                ["name", "score", "team", "double"],
                ["Ada", 42, "alpha", "=B2*2"],
                ["Grace", 37, "beta", "=B3*2"],
            ],
            ctx=self.ctx,
        )
        self.assertGreaterEqual(update_result.get("updatedCells", 0), 12)

        data = server.get_sheet_data(primary_id, "Sheet1", "A1:D3", ctx=self.ctx)
        self.assertEqual(data["valueRanges"][0]["values"][1][0], "Ada")
        self.assertEqual(data["valueRanges"][0]["values"][1][1], "42")

        formulas = server.get_sheet_formulas(primary_id, "Sheet1", "D2:D3", ctx=self.ctx)
        self.assertEqual(formulas, [["=B2*2"], ["=B3*2"]])

        batch_cells = server.batch_update_cells(
            primary_id,
            "Sheet1",
            {
                "E1:E2": [["status"], ["ready"]],
                "F1:F2": [["owner"], ["integration"]],
            },
            ctx=self.ctx,
        )
        self.assertGreaterEqual(batch_cells.get("totalUpdatedCells", 0), 4)

        add_rows = server.add_rows(primary_id, "Sheet1", count=1, start_row=10, ctx=self.ctx)
        self.assertIn("replies", add_rows)

        add_columns = server.add_columns(primary_id, "Sheet1", count=1, start_column=10, ctx=self.ctx)
        self.assertIn("replies", add_columns)

        initial_sheets = server.list_sheets(primary_id, ctx=self.ctx)
        self.assertIn("Sheet1", initial_sheets)

        created_sheet = server.create_sheet(primary_id, "CreatedTab", ctx=self.ctx)
        self.assertEqual(created_sheet["title"], "CreatedTab")

        rename_result = server.rename_sheet(primary_id, "CreatedTab", "RenamedTab", ctx=self.ctx)
        self.assertIn("replies", rename_result)
        self.assertIn("RenamedTab", server.list_sheets(primary_id, ctx=self.ctx))

        sheet1_id = server._get_sheet_id(self.sheets_service, primary_id, "Sheet1")
        self.assertIsNotNone(sheet1_id)

        batch_result = server.batch_update(
            primary_id,
            [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet1_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                        },
                        "cell": {"note": "integration-test-note"},
                        "fields": "note",
                    }
                }
            ],
            ctx=self.ctx,
        )
        self.assertIn("replies", batch_result)

        chart_result = server.add_chart(
            primary_id,
            "Sheet1",
            "COLUMN",
            "A1:B3",
            title="Integration Chart",
            x_axis_label="Name",
            y_axis_label="Score",
            ctx=self.ctx,
        )
        self.assertTrue(chart_result.get("success"), chart_result)
        self.assertIsNotNone(chart_result.get("chartId"))

        copy_result = server.copy_sheet(
            primary_id,
            "Sheet1",
            copy_target_id,
            "CopiedSheet",
            ctx=self.ctx,
        )
        self.assertIn("copy", copy_result)
        self.assertIn("CopiedSheet", server.list_sheets(copy_target_id, ctx=self.ctx))

        multi_data = server.get_multiple_sheet_data(
            [
                {"spreadsheet_id": primary_id, "sheet": "Sheet1", "range": "A1:B3"},
                {"spreadsheet_id": copy_target_id, "sheet": "CopiedSheet", "range": "A1:B3"},
            ],
            ctx=self.ctx,
        )
        self.assertEqual(len(multi_data), 2)
        self.assertEqual(multi_data[0]["data"][1][0], "Ada")
        self.assertNotIn("error", multi_data[1])

        summaries = server.get_multiple_spreadsheet_summary(
            [primary_id, copy_target_id],
            rows_to_fetch=3,
            ctx=self.ctx,
        )
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0]["spreadsheet_id"], primary_id)
        self.assertIsNone(summaries[0]["error"])
        self.assertTrue(summaries[0]["sheets"])

        spreadsheets = server.list_spreadsheets(folder_id=self.folder_id, ctx=self.ctx)
        self.assertTrue(any(sheet["id"] == primary_id for sheet in spreadsheets))

        folders = server.list_folders(parent_folder_id=self.folder_id, ctx=self.ctx)
        self.assertIsInstance(folders, list)

        found = self.wait_for_search_result(primary_title, primary_id)
        self.assertTrue(any(sheet.get("id") == primary_id for sheet in found))

        found_cells = server.find_in_spreadsheet(primary_id, "Ada", ctx=self.ctx)
        self.assertTrue(
            any(cell["sheet"] == "Sheet1" and cell["cell"] == "A2" for cell in found_cells),
            found_cells,
        )

        share_email = os.environ.get("GOOGLE_TEST_SHARE_EMAIL")
        if share_email:
            share_result = server.share_spreadsheet(
                primary_id,
                [{"email_address": share_email, "role": "reader"}],
                send_notification=False,
                ctx=self.ctx,
            )
            self.assertTrue(share_result["successes"], share_result)
        else:
            share_result = server.share_spreadsheet(
                primary_id,
                [{"email_address": "nobody@example.invalid", "role": "invalid-role"}],
                send_notification=False,
                ctx=self.ctx,
            )
            self.assertEqual(share_result["successes"], [])
            self.assertEqual(len(share_result["failures"]), 1)


if __name__ == "__main__":
    unittest.main()
