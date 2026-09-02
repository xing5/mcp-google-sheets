import ast
import os
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
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
        self.grid_metadata = None

    def get(self, **kwargs):
        self.calls.append(("spreadsheets.get", kwargs))
        if self.grid_metadata is not None and kwargs.get("includeGridData"):
            return FakeRequest(self.grid_metadata)
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


class BigQueryConfigurationTests(unittest.TestCase):
    def test_bigquery_is_disabled_by_default(self):
        with patch.object(sys, "argv", ["mcp-google-sheets"]):
            with patch.dict(os.environ, {}, clear=True):
                self.assertFalse(server._parse_bigquery_enabled())

    def test_truthy_environment_values_enable_bigquery(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                with patch.object(sys, "argv", ["mcp-google-sheets"]):
                    with patch.dict(os.environ, {"ENABLE_BIGQUERY_TOOLS": value}, clear=True):
                        self.assertTrue(server._parse_bigquery_enabled())

    def test_falsy_environment_values_leave_bigquery_disabled(self):
        for value in ("", "0", "false", "no", "off"):
            with self.subTest(value=value):
                with patch.object(sys, "argv", ["mcp-google-sheets"]):
                    with patch.dict(os.environ, {"ENABLE_BIGQUERY_TOOLS": value}, clear=True):
                        self.assertFalse(server._parse_bigquery_enabled())

    def test_cli_flag_enables_bigquery(self):
        with patch.object(sys, "argv", ["mcp-google-sheets", "--enable-bigquery"]):
            with patch.dict(os.environ, {}, clear=True):
                self.assertTrue(server._parse_bigquery_enabled())

    def test_default_scopes_exclude_bigquery(self):
        self.assertEqual(server._resolve_scopes(False), server.BASE_SCOPES)

    def test_enabling_bigquery_appends_the_readonly_scope(self):
        scopes = server._resolve_scopes(True)

        self.assertEqual(scopes[:2], server.BASE_SCOPES)
        self.assertEqual(scopes[-1], server.BIGQUERY_READONLY_SCOPE)

    def test_resolving_scopes_does_not_mutate_the_base_list(self):
        server._resolve_scopes(True)

        self.assertNotIn(server.BIGQUERY_READONLY_SCOPE, server.BASE_SCOPES)


class BigQueryToolGatingTests(unittest.TestCase):
    """The BigQuery tools stay unregistered until the extra scope is opted into."""

    def _register(self, requires_bigquery, bigquery_enabled, enabled_tools=None):
        def sample_tool():
            return None

        with patch.object(server, "mcp") as mcp:
            with patch.object(server, "BIGQUERY_ENABLED", bigquery_enabled):
                with patch.object(server, "ENABLED_TOOLS", enabled_tools):
                    returned = server.tool(requires_bigquery=requires_bigquery)(sample_tool)
        return mcp, sample_tool, returned

    def test_bigquery_tool_is_not_registered_when_disabled(self):
        mcp, original, returned = self._register(True, False)

        self.assertIs(returned, original)
        mcp.tool.assert_not_called()

    def test_bigquery_tool_is_registered_when_enabled(self):
        mcp, _, _ = self._register(True, True)

        mcp.tool.assert_called_once()

    def test_bigquery_tool_still_honours_the_tool_filter(self):
        mcp, original, returned = self._register(True, True, enabled_tools={"other_tool"})

        self.assertIs(returned, original)
        mcp.tool.assert_not_called()

    def test_regular_tools_are_unaffected_by_the_bigquery_flag(self):
        mcp, _, _ = self._register(False, False)

        mcp.tool.assert_called_once()


class BigQueryToolRequestConstructionTests(unittest.TestCase):
    def test_add_bigquery_data_source_builds_a_table_spec(self):
        sheets_service = RecordingSheetsService()
        spreadsheets = sheets_service.spreadsheets_resource
        spreadsheets.batch_update_result = {
            "replies": [{"addDataSource": {
                "dataSource": {"dataSourceId": "ds-1", "sheetId": 456},
                "dataExecutionStatus": {"state": "RUNNING"},
            }}]
        }

        result = server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            dataset_id="samples",
            table_id="shakespeare",
            table_project_id="bigquery-public-data",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        request = spreadsheets.calls[0][1]["body"]["requests"][0]
        spec = request["addDataSource"]["dataSource"]["spec"]["bigQuery"]
        self.assertEqual(spec["projectId"], "billing-project")
        self.assertEqual(spec["tableSpec"], {
            "tableProjectId": "bigquery-public-data",
            "datasetId": "samples",
            "tableId": "shakespeare",
        })
        self.assertEqual(result["dataSourceId"], "ds-1")
        self.assertEqual(result["dataExecutionStatus"], {"state": "RUNNING"})

    def test_table_project_defaults_to_the_billing_project(self):
        sheets_service = RecordingSheetsService()

        server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            dataset_id="samples",
            table_id="shakespeare",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        request = sheets_service.spreadsheets_resource.calls[0][1]["body"]["requests"][0]
        spec = request["addDataSource"]["dataSource"]["spec"]["bigQuery"]
        self.assertEqual(spec["tableSpec"]["tableProjectId"], "billing-project")

    def test_add_bigquery_data_source_builds_a_query_spec(self):
        sheets_service = RecordingSheetsService()

        server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            query="SELECT 1 AS answer",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        request = sheets_service.spreadsheets_resource.calls[0][1]["body"]["requests"][0]
        spec = request["addDataSource"]["dataSource"]["spec"]["bigQuery"]
        self.assertEqual(spec["querySpec"], {"rawQuery": "SELECT 1 AS answer"})
        self.assertNotIn("tableSpec", spec)

    def test_add_bigquery_data_source_resolves_the_created_sheet(self):
        """The addDataSource reply does not name the sheet Google creates for it."""
        sheets_service = RecordingSheetsService()
        spreadsheets = sheets_service.spreadsheets_resource
        spreadsheets.batch_update_result = {
            "replies": [{"addDataSource": {"dataSource": {"dataSourceId": "ds-1"}}}]
        }
        spreadsheets.metadata = {
            "sheets": [
                {"properties": {"title": "Sheet1", "sheetId": 123}},
                {"properties": {
                    "title": "Connected Sheet 1",
                    "sheetId": 456,
                    "dataSourceSheetProperties": {"dataSourceId": "ds-1"},
                }},
            ]
        }

        result = server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            query="SELECT 1",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result["sheetTitle"], "Connected Sheet 1")
        self.assertEqual(result["sheetId"], 456)

    def test_add_bigquery_data_source_survives_an_unresolvable_sheet(self):
        sheets_service = RecordingSheetsService()
        spreadsheets = sheets_service.spreadsheets_resource
        spreadsheets.batch_update_result = {
            "replies": [{"addDataSource": {"dataSource": {"dataSourceId": "ds-1"}}}]
        }
        spreadsheets.metadata = {"sheets": []}

        result = server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            query="SELECT 1",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result["dataSourceId"], "ds-1")
        self.assertIsNone(result["sheetTitle"])

    def test_add_bigquery_data_source_rejects_a_missing_target(self):
        sheets_service = RecordingSheetsService()

        result = server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("error", result)
        self.assertEqual(sheets_service.spreadsheets_resource.calls, [])

    def test_add_bigquery_data_source_rejects_a_conflicting_target(self):
        sheets_service = RecordingSheetsService()

        result = server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            dataset_id="samples",
            table_id="shakespeare",
            query="SELECT 1",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("error", result)
        self.assertEqual(sheets_service.spreadsheets_resource.calls, [])

    def test_add_bigquery_data_source_rejects_a_table_without_its_dataset(self):
        sheets_service = RecordingSheetsService()

        result = server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            table_id="shakespeare",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("error", result)
        self.assertEqual(sheets_service.spreadsheets_resource.calls, [])

    def test_missing_scope_is_reported_with_a_remediation_hint(self):
        """The raw API message says the scope is missing but not how to fix it."""
        sheets_service = RecordingSheetsService()
        sheets_service.spreadsheets_resource.batch_update_result = Exception(
            "The request scopes are not sufficient for performing this operation. "
            "Please include bigquery.readonly scope."
        )

        result = server.add_bigquery_data_source(
            "spreadsheet-id",
            project_id="billing-project",
            query="SELECT 1",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("error", result)
        self.assertIn("ENABLE_BIGQUERY_TOOLS", result["hint"])

    def test_refresh_data_source_targets_a_single_source(self):
        sheets_service = RecordingSheetsService()
        sheets_service.spreadsheets_resource.batch_update_result = {"replies": [{}]}

        server.refresh_data_source(
            "spreadsheet-id",
            data_source_id="ds-1",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        request = sheets_service.spreadsheets_resource.calls[0][1]["body"]["requests"][0]
        self.assertEqual(request["refreshDataSource"]["dataSourceId"], "ds-1")
        self.assertNotIn("isAll", request["refreshDataSource"])

    def test_refresh_data_source_can_target_every_source(self):
        sheets_service = RecordingSheetsService()
        sheets_service.spreadsheets_resource.batch_update_result = {"replies": [{}]}

        server.refresh_data_source(
            "spreadsheet-id",
            refresh_all=True,
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        request = sheets_service.spreadsheets_resource.calls[0][1]["body"]["requests"][0]
        self.assertTrue(request["refreshDataSource"]["isAll"])
        self.assertNotIn("dataSourceId", request["refreshDataSource"])

    def test_refresh_data_source_rejects_ambiguous_arguments(self):
        sheets_service = RecordingSheetsService()

        result = server.refresh_data_source(
            "spreadsheet-id",
            data_source_id="ds-1",
            refresh_all=True,
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("error", result)
        self.assertEqual(sheets_service.spreadsheets_resource.calls, [])

    def test_refresh_data_source_rejects_missing_arguments(self):
        sheets_service = RecordingSheetsService()

        result = server.refresh_data_source(
            "spreadsheet-id",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("error", result)
        self.assertEqual(sheets_service.spreadsheets_resource.calls, [])

    def test_get_data_source_data_reads_grid_data(self):
        sheets_service = RecordingSheetsService()
        sheets_service.spreadsheets_resource.grid_metadata = {
            "sheets": [{
                "properties": {
                    "title": "shakespeare",
                    "sheetType": "DATA_SOURCE",
                    "dataSourceSheetProperties": {
                        "dataSourceId": "ds-1",
                        "dataExecutionStatus": {"state": "SUCCEEDED"},
                        "columns": [
                            {"reference": {"name": "word"}},
                            {"reference": {"name": "word_count"}},
                        ],
                    },
                },
                "data": [{"rowData": [
                    {"values": [{"formattedValue": "the"}, {"formattedValue": "995"}]},
                    {"values": [{"formattedValue": "and"}, {"formattedValue": "706"}]},
                ]}],
            }]
        }

        result = server.get_data_source_data(
            "spreadsheet-id", "shakespeare",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result["columns"], ["word", "word_count"])
        self.assertEqual(result["rows"], [["the", "995"], ["and", "706"]])
        self.assertEqual(result["dataSourceId"], "ds-1")
        self.assertEqual(result["dataExecutionStatus"], {"state": "SUCCEEDED"})
        self.assertFalse(result["truncated"])

    def test_get_data_source_data_never_uses_the_values_api(self):
        """The values API rejects DATA_SOURCE sheets; that is why this tool exists."""
        sheets_service = RecordingSheetsService()
        sheets_service.spreadsheets_resource.grid_metadata = {
            "sheets": [{
                "properties": {"title": "shakespeare", "sheetType": "DATA_SOURCE"},
                "data": [{"rowData": [{"values": [{"formattedValue": "the"}]}]}],
            }]
        }

        server.get_data_source_data(
            "spreadsheet-id", "shakespeare",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(sheets_service.spreadsheets_resource.values_resource.calls, [])

    def test_get_data_source_data_truncates_to_max_rows(self):
        sheets_service = RecordingSheetsService()
        sheets_service.spreadsheets_resource.grid_metadata = {
            "sheets": [{
                "properties": {"title": "shakespeare", "sheetType": "DATA_SOURCE"},
                "data": [{"rowData": [
                    {"values": [{"formattedValue": str(number)}]}
                    for number in range(10)
                ]}],
            }]
        }

        result = server.get_data_source_data(
            "spreadsheet-id", "shakespeare", max_rows=3,
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(result["rowCount"], 3)
        self.assertTrue(result["truncated"])

    def test_get_data_source_data_rejects_a_regular_sheet(self):
        sheets_service = RecordingSheetsService()
        sheets_service.spreadsheets_resource.grid_metadata = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetType": "GRID"}}]
        }

        result = server.get_data_source_data(
            "spreadsheet-id", "Sheet1",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("error", result)

    def test_get_data_source_data_returns_error_for_missing_sheet(self):
        sheets_service = RecordingSheetsService()
        sheets_service.spreadsheets_resource.grid_metadata = {"sheets": []}

        result = server.get_data_source_data(
            "spreadsheet-id", "absent",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertIn("error", result)


class FindInSpreadsheetDataSourceTests(unittest.TestCase):
    """A data source sheet must not break the search across the other sheets."""

    def test_data_source_sheets_are_skipped_instead_of_failing_the_search(self):
        sheets_service = RecordingSheetsService()
        spreadsheets = sheets_service.spreadsheets_resource
        spreadsheets.metadata = {
            "sheets": [
                {"properties": {"title": "Sheet1", "sheetId": 1, "sheetType": "GRID"}},
                {"properties": {"title": "connected", "sheetId": 2,
                                "sheetType": "DATA_SOURCE"}},
            ]
        }
        values_resource = spreadsheets.values_resource
        values_resource.get_results["Sheet1"] = {"values": [["hello world"]]}
        values_resource.get_results["connected"] = Exception(
            "Unable to parse range: connected"
        )

        results = server.find_in_spreadsheet(
            "spreadsheet-id", "hello",
            ctx=fake_ctx(sheets_service=sheets_service),
        )

        self.assertEqual(results, [{"sheet": "Sheet1", "cell": "A1", "value": "hello world"}])
        queried = [call[1]["range"] for call in values_resource.calls]
        self.assertNotIn("connected", queried)


if __name__ == "__main__":
    unittest.main()
