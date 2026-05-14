import base64
import json
import os
import time
import unittest
from types import SimpleNamespace

from google.oauth2 import service_account
from googleapiclient.discovery import build

from mcp_google_sheets import server


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

    def test_create_update_read_and_list_spreadsheet(self):
        title = f"mcp-google-sheets-it-{int(time.time())}"

        created = server.create_spreadsheet(title, ctx=self.ctx)
        spreadsheet_id = created["spreadsheetId"]
        self.created_file_ids.append(spreadsheet_id)

        self.assertEqual(created["title"], title)
        self.assertEqual(created["folder"], self.folder_id)

        update_result = server.update_cells(
            spreadsheet_id,
            "Sheet1",
            "A1:B2",
            [["name", "score"], ["Ada", 42]],
            ctx=self.ctx,
        )
        self.assertGreaterEqual(update_result.get("updatedCells", 0), 4)

        data = server.get_sheet_data(
            spreadsheet_id,
            "Sheet1",
            "A1:B2",
            ctx=self.ctx,
        )
        self.assertEqual(
            data["valueRanges"][0]["values"],
            [["name", "score"], ["Ada", "42"]],
        )

        spreadsheets = server.list_spreadsheets(folder_id=self.folder_id, ctx=self.ctx)
        self.assertTrue(any(sheet["id"] == spreadsheet_id for sheet in spreadsheets))

        found = server.search_spreadsheets(title, max_results=10, ctx=self.ctx)
        self.assertTrue(any(sheet.get("id") == spreadsheet_id for sheet in found))


if __name__ == "__main__":
    unittest.main()
