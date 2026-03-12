"""Tests for CSV skill — parse, summarize, export."""

from src.skills.csv.processor import parse_csv, export_csv, summarize_csv


class TestParseCsv:
    def test_basic_parse(self):
        text = "name,age,city\nAlice,30,NYC\nBob,25,SF"
        result = parse_csv(text)
        assert result["headers"] == ["name", "age", "city"]
        assert result["row_count"] == 2
        assert result["column_count"] == 3
        assert result["rows"][0] == ["Alice", "30", "NYC"]
        assert result["rows"][1] == ["Bob", "25", "SF"]

    def test_empty_csv(self):
        text = "name,age\n"
        result = parse_csv(text)
        assert result["headers"] == ["name", "age"]
        assert result["row_count"] == 0

    def test_max_rows(self):
        lines = ["id,val"] + [f"{i},x" for i in range(100)]
        text = "\n".join(lines)
        result = parse_csv(text, max_rows=10)
        assert result["row_count"] == 10
        assert result["truncated"] is True

    def test_single_column(self):
        text = "email\nfoo@bar.com\nbaz@qux.com"
        result = parse_csv(text)
        assert result["column_count"] == 1
        assert result["row_count"] == 2


class TestSummarizeCsv:
    def test_summary_preview(self):
        lines = ["id,val"] + [f"{i},x" for i in range(100)]
        text = "\n".join(lines)
        result = summarize_csv(text)
        assert result["row_count"] == 100
        assert len(result["preview"]) == 50  # MAX_PREVIEW_ROWS
        assert result["truncated"] is True

    def test_small_csv_not_truncated(self):
        text = "a,b\n1,2\n3,4"
        result = summarize_csv(text)
        assert result["truncated"] is False
        assert len(result["preview"]) == 2


class TestExportCsv:
    def test_basic_export(self):
        result = export_csv(
            headers=["name", "epc"],
            rows=[["Project A", "McCarthy"], ["Project B", "Blattner"]],
            filename="test.csv",
        )
        assert result["filename"] == "test.csv"
        assert result["row_count"] == 2
        assert "McCarthy" in result["csv_text"]
        assert "Blattner" in result["csv_text"]
        assert result["csv_text"].startswith("name,epc")

    def test_export_with_commas(self):
        result = export_csv(
            headers=["name", "notes"],
            rows=[["Project A", "large, complex site"]],
        )
        # CSV should properly quote fields with commas
        assert '"large, complex site"' in result["csv_text"]

    def test_export_preserves_headers(self):
        result = export_csv(headers=["a", "b", "c"], rows=[["1", "2", "3"]])
        assert result["headers"] == ["a", "b", "c"]


class TestExportCsvTool:
    async def test_tool_registered(self):
        from src.tools import get_tool_names
        assert "export_csv" in get_tool_names()

    async def test_execute_basic(self):
        from src.tools.export_csv import execute
        result = await execute({
            "headers": ["project", "epc"],
            "rows": [["Alpha Solar", "McCarthy"]],
            "filename": "discoveries.csv",
        })
        assert result["content_type"] == "csv"
        assert result["row_count"] == 1
        assert "Alpha Solar" in result["csv_text"]

    async def test_execute_no_headers(self):
        from src.tools.export_csv import execute
        result = await execute({"headers": [], "rows": [["a"]]})
        assert "error" in result

    async def test_execute_no_rows(self):
        from src.tools.export_csv import execute
        result = await execute({"headers": ["a"], "rows": []})
        assert "error" in result
