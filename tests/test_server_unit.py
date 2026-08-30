import ast
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mcp_google_sheets import server


class FakeRequest:
    def __init__(self, result):
        self.result = result

    def execute(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class RecordingValuesResource:
    def __init__(self):
        self.calls = []
        self.get_results = {}
        self.update_result = {"updatedCells": 4}
        self.batch_update_result = {"totalUpdatedCells": 4}

    def get(self, **kwargs):
        self.calls.append(("values.get", kwargs))
        result = self.get_results.get(kwargs.get("range"), {"values": []})
        return FakeRequest(result)

    def update(self, **kwargs):
        self.calls.append(("values.update", kwargs))
        return FakeRequest(self.update_result)

    def batchUpdate(self, **kwargs):
        self.calls.append(("values.batchUpdate", kwargs))
        return FakeRequest(self.batch_update_result)


class RecordingSheetsSubresource:
    def __init__(self):
        self.calls = []
        self.copy_result = {"sheetId": 99, "title": "Copy of Sheet1"}

    def copyTo(self, **kwargs):
        self.calls.append(("sheets.copyTo", kwargs))
        return FakeRequest(self.copy_result)


class RecordingSpreadsheetsResource:
    def __init__(self):
        self.calls = []
        self.values_resource = RecordingValuesResource()
        self.sheets_resource = RecordingSheetsSubresource()
        self.metadata = {
            "properties": {"title": "Book"},
            "sheets": [
                {"properties": {"title": "Sheet1", "sheetId": 123}},
                {"properties": {"title": "Data", "sheetId": 456}},
            ],
        }
        self.batch_update_result = {"replies": [{"addChart": {"chart": {"chartId": 7}}}]}

    def get(self, **kwargs):
        self.calls.append(("spreadsheets.get", kwargs))
        return FakeRequest(self.metadata)

    def values(self):
        return self.values_resource

    def sheets(self):
        return self.sheets_resource

    def batchUpdate(self, **kwargs):
        self.calls.append(("spreadsheets.batchUpdate", kwargs))
        return FakeRequest(self.batch_update_result)


class RecordingSheetsService:
    def __init__(self):
        self.spreadsheets_resource = RecordingSpreadsheetsResource()

    def spreadsheets(self):
        return self.spreadsheets_resource


class RecordingFilesResource:
    def __init__(self):
        self.calls = []
        self.create_result = {
            "id": "spreadsheet-id",
            "name": "Created Sheet",
            "parents": ["folder-id"],
        }
        self.list_result = {
            "files": [
                {
                    "id": "one",
                    "name": "Budget 2026",
                    "createdTime": "2026-01-01T00:00:00Z",
                    "modifiedTime": "2026-01-02T00:00:00Z",
                    "owners": [{"emailAddress": "owner@example.com"}],
                    "webViewLink": "https://example.test/sheet",
                    "parents": ["folder-id"],
                }
            ]
        }

    def create(self, **kwargs):
        self.calls.append(("files.create", kwargs))
        return FakeRequest(self.create_result)

    def list(self, **kwargs):
        self.calls.append(("files.list", kwargs))
        return FakeRequest(self.list_result)


class RecordingDriveService:
    def __init__(self):
        self.files_resource = RecordingFilesResource()

    def files(self):
        return self.files_resource


def fake_ctx(sheets_service=None, drive_service=None, folder_id=None):
    lifespan_context = SimpleNamespace(
        sheets_service=sheets_service,
        drive_service=drive_service,
        folder_id=folder_id,
    )
    request_context = SimpleNamespace(lifespan_context=lifespan_context)
    return SimpleNamespace(request_context=request_context)


class ParseEnabledToolsTests(unittest.TestCase):
    def test_cli_include_tools_takes_precedence_over_environment(self):
        with patch.object(sys, "argv", ["mcp-google-sheets", "--include-tools", "a, b"]):
            with patch.dict(os.environ, {"ENABLED_TOOLS": "c"}, clear=False):
                self.assertEqual(server._parse_enabled_tools(), {"a", "b"})

    def test_empty_configuration_enables_all_tools(self):
        with patch.object(sys, "argv", ["mcp-google-sheets"]):
            with patch.dict(os.environ, {}, clear=True):
                self.assertIsNone(server._parse_enabled_tools())


class StdioSafetyTests(unittest.TestCase):
    def test_server_module_does_not_call_print(self):
        source_path = os.path.abspath(server.__file__)
        with open(source_path, "r", encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read(), filename=source_path)

        print_calls = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ]

        self.assertEqual(print_calls, [])

    def test_main_writes_no_diagnostics_to_stdout(self):
        with patch.object(server.mcp, "run") as run:
            with patch.object(server, "_configure_logging"):
                with patch.object(server.logger, "info"):
                    with patch.object(sys, "argv", ["mcp-google-sheets"]):
                        with redirect_stdout(StringIO()) as stdout:
                            server.main()

        self.assertEqual(stdout.getvalue(), "")
        run.assert_called_once_with(transport="stdio")

    def test_main_configures_logging(self):
        with patch.object(server.mcp, "run") as run:
            with patch.object(server, "_configure_logging") as configure_logging:
                with patch.object(server.logger, "info"):
                    with patch.object(sys, "argv", ["mcp-google-sheets"]):
                        server.main()

        configure_logging.assert_called_once_with()
        run.assert_called_once_with(transport="stdio")


class OAuthAuthorizationTests(unittest.TestCase):
    def test_prompt_writes_canonical_url_to_configured_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "oauth-url.txt"
            prompt = server._OAuthAuthorizationPrompt(str(output_path))

            message = prompt.format(url="https://accounts.example.test/oauth?state=abc")

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "https://accounts.example.test/oauth?state=abc\n",
            )
            self.assertIn(str(output_path), message)
            self.assertNotIn("state=abc", message)

    def test_prompt_returns_url_when_no_file_is_configured(self):
        prompt = server._OAuthAuthorizationPrompt(None)

        message = prompt.format(url="https://accounts.example.test/oauth")

        self.assertIn("https://accounts.example.test/oauth", message)

    def test_oauth_flow_keeps_stdout_clean_and_removes_url_file(self):
        credentials = object()

        class FakeFlow:
            def __init__(self):
                self.options = None

            def run_local_server(self, **options):
                self.options = options
                message = options["authorization_prompt_message"].format(
                    url="https://accounts.example.test/oauth?state=abc"
                )
                print(message)
                return credentials

        fake_flow = FakeFlow()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "oauth-url.txt"
            environment = {
                "OAUTH_AUTH_URL_FILE": str(output_path),
                "OAUTH_OPEN_BROWSER": "false",
            }
            with patch.dict(os.environ, environment, clear=False):
                with patch.object(
                    server.InstalledAppFlow,
                    "from_client_secrets_file",
                    return_value=fake_flow,
                ):
                    with redirect_stdout(StringIO()) as stdout:
                        with redirect_stderr(StringIO()) as stderr:
                            result = server._run_oauth_flow()

            self.assertIs(result, credentials)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(str(output_path), stderr.getvalue())
            self.assertFalse(output_path.exists())
            self.assertEqual(fake_flow.options["port"], 0)
            self.assertFalse(fake_flow.options["open_browser"])


class A1HelperTests(unittest.TestCase):
    def test_column_index_to_letter(self):
        self.assertEqual(server._column_index_to_letter(0), "A")
        self.assertEqual(server._column_index_to_letter(25), "Z")
        self.assertEqual(server._column_index_to_letter(26), "AA")
        self.assertEqual(server._column_index_to_letter(701), "ZZ")

    def test_parse_a1_range(self):
        self.assertEqual(
            server._parse_a1_notation("B2:D5"),
            {
                "startColumnIndex": 1,
                "startRowIndex": 1,
                "endColumnIndex": 4,
                "endRowIndex": 5,
            },
        )

    def test_parse_column_range(self):
        self.assertEqual(
            server._parse_a1_notation("A:C"),
            {"startColumnIndex": 0, "endColumnIndex": 3},
        )

    def test_parse_invalid_a1_range_raises(self):
        with self.assertRaises(ValueError):
            server._parse_a1_notation("not a range")

    def test_split_chart_source_ranges_splits_multi_column_table(self):
        source_range = {
            "sheetId": 123,
            "startRowIndex": 0,
            "endRowIndex": 3,
            "startColumnIndex": 0,
            "endColumnIndex": 3,
        }

        domain_range, series_ranges = server._split_chart_source_ranges(source_range)

        self.assertEqual(
            domain_range,
            {
                "sheetId": 123,
                "startRowIndex": 0,
                "endRowIndex": 3,
                "startColumnIndex": 0,
                "endColumnIndex": 1,
            },
        )
        self.assertEqual(
            series_ranges,
            [
                {
                    "sheetId": 123,
                    "startRowIndex": 0,
                    "endRowIndex": 3,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2,
                },
                {
                    "sheetId": 123,
                    "startRowIndex": 0,
                    "endRowIndex": 3,
                    "startColumnIndex": 2,
                    "endColumnIndex": 3,
                },
            ],
        )


class ToolRequestConstructionTests(unittest.TestCase):
    def test_get_sheet_data_uses_values_api_by_default(self):
        sheets_service = RecordingSheetsService()
        values_resource = sheets_service.spreadsheets_resource.values_resource
        values_resource.get_results["Sheet1!A1:B2"] = {"values": [["a", "b"]]}

        result = server.get_sheet_data(
            "spreadsheet-id",
            "Sheet1",
            "A1:B2",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(
            result,
            {
                "spreadsheetId": "spreadsheet-id",
                "valueRanges": [{"range": "Sheet1!A1:B2", "values": [["a", "b"]]}],
            },
        )
        self.assertEqual(
            values_resource.calls[-1],
            (
                "values.get",
                {"spreadsheetId": "spreadsheet-id", "range": "Sheet1!A1:B2"},
            ),
        )

    def test_update_cells_uses_user_entered_values(self):
        sheets_service = RecordingSheetsService()

        result = server.update_cells(
            "spreadsheet-id",
            "Sheet1",
            "A1:B2",
            [[1, 2], [3, 4]],
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result, {"updatedCells": 4})
        self.assertEqual(
            sheets_service.spreadsheets_resource.values_resource.calls[-1],
            (
                "values.update",
                {
                    "spreadsheetId": "spreadsheet-id",
                    "range": "Sheet1!A1:B2",
                    "valueInputOption": "USER_ENTERED",
                    "body": {"values": [[1, 2], [3, 4]]},
                },
            ),
        )

    def test_batch_update_rejects_empty_requests_before_api_call(self):
        sheets_service = RecordingSheetsService()

        result = server.batch_update(
            "spreadsheet-id",
            [],
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result, {"error": "requests list cannot be empty"})
        self.assertEqual(sheets_service.spreadsheets_resource.calls, [])

    def test_batch_update_sends_raw_requests(self):
        sheets_service = RecordingSheetsService()
        requests = [{"updateSheetProperties": {"fields": "title"}}]

        result = server.batch_update(
            "spreadsheet-id",
            requests,
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result, {"replies": [{"addChart": {"chart": {"chartId": 7}}}]})
        self.assertEqual(
            sheets_service.spreadsheets_resource.calls[-1],
            (
                "spreadsheets.batchUpdate",
                {"spreadsheetId": "spreadsheet-id", "body": {"requests": requests}},
            ),
        )

    def test_add_rows_builds_insert_dimension_request(self):
        sheets_service = RecordingSheetsService()

        server.add_rows(
            "spreadsheet-id",
            "Sheet1",
            3,
            start_row=2,
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        _, call = sheets_service.spreadsheets_resource.calls[-1]
        self.assertEqual(call["spreadsheetId"], "spreadsheet-id")
        self.assertEqual(
            call["body"]["requests"][0]["insertDimension"],
            {
                "range": {
                    "sheetId": 123,
                    "dimension": "ROWS",
                    "startIndex": 2,
                    "endIndex": 5,
                },
                "inheritFromBefore": True,
            },
        )

    def test_add_rows_returns_error_for_missing_sheet(self):
        sheets_service = RecordingSheetsService()

        result = server.add_rows(
            "spreadsheet-id",
            "Missing",
            1,
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result, {"error": "Sheet 'Missing' not found"})

    def test_create_spreadsheet_targets_requested_folder(self):
        drive_service = RecordingDriveService()

        with patch.object(server.logger, "info"):
            result = server.create_spreadsheet(
                "Created Sheet",
                folder_id="folder-id",
                ctx=fake_ctx(drive_service=drive_service),
            )

        self.assertEqual(
            result,
            {
                "spreadsheetId": "spreadsheet-id",
                "title": "Created Sheet",
                "folder": "folder-id",
            },
        )
        self.assertEqual(
            drive_service.files_resource.calls[-1],
            (
                "files.create",
                {
                    "supportsAllDrives": True,
                    "body": {
                        "name": "Created Sheet",
                        "mimeType": "application/vnd.google-apps.spreadsheet",
                        "parents": ["folder-id"],
                    },
                    "fields": "id, name, parents",
                },
            ),
        )

    def test_search_spreadsheets_clamps_page_size_and_returns_metadata(self):
        drive_service = RecordingDriveService()

        result = server.search_spreadsheets(
            "budget",
            max_results=500,
            ctx=fake_ctx(drive_service=drive_service),
        )

        self.assertEqual(result[0]["id"], "one")
        self.assertEqual(result[0]["owners"], ["owner@example.com"])
        _, call = drive_service.files_resource.calls[-1]
        self.assertEqual(call["pageSize"], 100)
        self.assertIn("name contains 'budget'", call["q"])
        self.assertIn("fullText contains 'budget'", call["q"])

    def test_find_in_spreadsheet_searches_cells_case_insensitively(self):
        sheets_service = RecordingSheetsService()
        values_resource = sheets_service.spreadsheets_resource.values_resource
        values_resource.get_results["Sheet1"] = {
            "values": [["Name", "Role"], ["Ada Lovelace", "Engineer"]]
        }
        values_resource.get_results["Data"] = {"values": [["Other"]]}

        result = server.find_in_spreadsheet(
            "spreadsheet-id",
            "ada",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result, [{"sheet": "Sheet1", "cell": "A2", "value": "Ada Lovelace"}])

    def test_add_chart_rejects_invalid_chart_type_before_api_call(self):
        sheets_service = RecordingSheetsService()

        result = server.add_chart(
            "spreadsheet-id",
            "Sheet1",
            "BAD",
            "A1:B2",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("Invalid chart type", result["error"])
        self.assertEqual(sheets_service.spreadsheets_resource.calls, [])

    def test_add_chart_builds_batch_update_request(self):
        sheets_service = RecordingSheetsService()

        result = server.add_chart(
            "spreadsheet-id",
            "Sheet1",
            "line",
            "A1:B5",
            title="Trend",
            x_axis_label="Month",
            y_axis_label="Value",
            position_x=10,
            position_y=20,
            width=300,
            height=200,
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertTrue(result["success"])
        _, call = sheets_service.spreadsheets_resource.calls[-1]
        add_chart = call["body"]["requests"][0]["addChart"]["chart"]
        self.assertEqual(call["spreadsheetId"], "spreadsheet-id")
        self.assertEqual(add_chart["spec"]["title"], "Trend")
        self.assertEqual(add_chart["spec"]["basicChart"]["chartType"], "LINE")
        self.assertEqual(
            add_chart["spec"]["basicChart"]["domains"][0]["domain"]["sourceRange"]["sources"],
            [
                {
                    "sheetId": 123,
                    "startColumnIndex": 0,
                    "startRowIndex": 0,
                    "endColumnIndex": 1,
                    "endRowIndex": 5,
                }
            ],
        )
        self.assertEqual(
            add_chart["spec"]["basicChart"]["series"][0]["series"]["sourceRange"]["sources"],
            [
                {
                    "sheetId": 123,
                    "startColumnIndex": 1,
                    "startRowIndex": 0,
                    "endColumnIndex": 2,
                    "endRowIndex": 5,
                }
            ],
        )
        self.assertEqual(
            add_chart["position"]["overlayPosition"],
            {
                "anchorCell": {"sheetId": 123, "rowIndex": 0, "columnIndex": 0},
                "offsetXPixels": 10,
                "offsetYPixels": 20,
                "widthPixels": 300,
                "heightPixels": 200,
            },
        )


if __name__ == "__main__":
    unittest.main()
