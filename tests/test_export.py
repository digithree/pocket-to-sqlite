import pytest
import json
import csv
import pathlib
import sqlite_utils
from click.testing import CliRunner
from pocket_to_sqlite.cli import cli

# Sample data for testing
SAMPLE_ITEMS_DATA = [
    {"item_id": 1, "resolved_title": "Test Item 1", "excerpt": "Excerpt 1", "resolved_url": "http://example.com/1"},
    {"item_id": 2, "resolved_title": "Test Item 2", "excerpt": "Excerpt 2", "resolved_url": "http://example.com/2"},
]

SAMPLE_TAGS_DATA = [
    {"tag_id": 101, "tag_name": "python", "item_id": 1},
    {"tag_id": 102, "tag_name": "sqlite", "item_id": 1},
    {"tag_id": 103, "tag_name": "testing", "item_id": 2},
]

@pytest.fixture
def db_path(tmp_path):
    db_file = tmp_path / "test_pocket.db"
    db = sqlite_utils.Database(db_file)
    db["items"].insert_all(SAMPLE_ITEMS_DATA, pk="item_id")
    db["tags"].insert_all(SAMPLE_TAGS_DATA, pk="tag_id")
    db.execute("CREATE TABLE empty_table (id INTEGER PRIMARY KEY, name TEXT)")
    return db_file

def test_export_items_to_csv(db_path, tmp_path):
    runner = CliRunner()
    output_csv = tmp_path / "items_export.csv"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_csv), "--format", "csv", "--table", "items"]
    )
    assert result.exit_code == 0
    assert output_csv.exists()
    assert "Data from table 'items' successfully exported" in result.output

    with open(output_csv, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == len(SAMPLE_ITEMS_DATA)
        assert reader.fieldnames == ["item_id", "resolved_title", "excerpt", "resolved_url"]
        for i, row in enumerate(rows):
            # Convert item_id to string as CSV reads it as string
            assert row["item_id"] == str(SAMPLE_ITEMS_DATA[i]["item_id"])
            assert row["resolved_title"] == SAMPLE_ITEMS_DATA[i]["resolved_title"]
            assert row["excerpt"] == SAMPLE_ITEMS_DATA[i]["excerpt"]
            assert row["resolved_url"] == SAMPLE_ITEMS_DATA[i]["resolved_url"]

def test_export_custom_table_to_csv(db_path, tmp_path):
    runner = CliRunner()
    output_csv = tmp_path / "tags_export.csv"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_csv), "--format", "csv", "--table", "tags"]
    )
    assert result.exit_code == 0
    assert output_csv.exists()
    assert "Data from table 'tags' successfully exported" in result.output

    with open(output_csv, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == len(SAMPLE_TAGS_DATA)
        assert reader.fieldnames == ["tag_id", "tag_name", "item_id"]
        for i, row in enumerate(rows):
            assert row["tag_id"] == str(SAMPLE_TAGS_DATA[i]["tag_id"])
            assert row["tag_name"] == SAMPLE_TAGS_DATA[i]["tag_name"]
            assert row["item_id"] == str(SAMPLE_TAGS_DATA[i]["item_id"])


def test_export_empty_table_to_csv(db_path, tmp_path):
    runner = CliRunner()
    output_csv = tmp_path / "empty_export.csv"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_csv), "--format", "csv", "--table", "empty_table"]
    )
    assert result.exit_code == 0
    assert output_csv.exists()
    assert "Data from table 'empty_table' successfully exported" in result.output

    with open(output_csv, "r", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
        assert len(rows) == 1  # Header row only
        assert rows[0] == ["id", "name"]

def test_export_items_to_karakeep_json(db_path, tmp_path):
    runner = CliRunner()
    output_json = tmp_path / "items_export.json"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_json), "--format", "karakeep", "--table", "items"]
    )
    assert result.exit_code == 0
    assert output_json.exists()
    assert "Data from table 'items' successfully exported" in result.output

    with open(output_json, "r") as f:
        data = json.load(f)
        assert len(data) == len(SAMPLE_ITEMS_DATA)
        # KarakeepExporter's placeholder currently dumps the list of dicts directly
        # We need to compare content, ensuring order of keys might not be guaranteed by default json dump
        # So, we sort keys for comparison if necessary, or compare item by item
        for i, item in enumerate(data):
            # Convert item_id from int to str for comparison if SAMPLE_ITEMS_DATA has it as str
            # Or ensure SAMPLE_ITEMS_DATA has it as int if JSON stores as int.
            # Current CSV test converts to str, but JSON will keep int.
            db_item = {k: v for k, v in SAMPLE_ITEMS_DATA[i].items()} # Make a copy
            assert item == db_item


def test_export_custom_table_to_karakeep_json(db_path, tmp_path):
    runner = CliRunner()
    output_json = tmp_path / "tags_export.json"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_json), "--format", "karakeep", "--table", "tags"]
    )
    assert result.exit_code == 0
    assert output_json.exists()
    assert "Data from table 'tags' successfully exported" in result.output

    with open(output_json, "r") as f:
        data = json.load(f)
        assert len(data) == len(SAMPLE_TAGS_DATA)
        for i, item in enumerate(data):
            db_item = {k: v for k, v in SAMPLE_TAGS_DATA[i].items()}
            assert item == db_item


def test_export_empty_table_to_karakeep_json(db_path, tmp_path):
    runner = CliRunner()
    output_json = tmp_path / "empty_export.json"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_json), "--format", "karakeep", "--table", "empty_table"]
    )
    assert result.exit_code == 0
    assert output_json.exists()
    assert "Data from table 'empty_table' successfully exported" in result.output

    with open(output_json, "r") as f:
        data = json.load(f)
        assert data == [] # KarakeepExporter placeholder writes an empty list for empty tables

def test_export_non_existent_table(db_path, tmp_path):
    runner = CliRunner()
    output_csv = tmp_path / "non_existent_export.csv"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_csv), "--table", "non_existent_table"]
    )
    assert result.exit_code != 0 # Should fail
    assert "Error: Table 'non_existent_table' not found" in result.output
    assert not output_csv.exists()

def test_export_invalid_format(db_path, tmp_path):
    runner = CliRunner()
    output_file = tmp_path / "invalid_export.txt"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_file), "--format", "invalid_fmt"]
    )
    assert result.exit_code != 0 # Should fail
    assert "Error: Unknown export format 'invalid_fmt'" in result.output # Check new error message
    assert not output_file.exists()

def test_export_db_not_found(tmp_path):
    runner = CliRunner()
    non_existent_db = tmp_path / "not_real.db"
    output_csv = tmp_path / "out.csv"
    result = runner.invoke(cli, ["export", str(non_existent_db), str(output_csv)])
    assert result.exit_code != 0
    assert f"Error: Invalid value for 'DB_PATH': Path '{non_existent_db}' does not exist." in result.output
    assert not output_csv.exists()

# Test for default format (csv) and default table (items)
def test_export_defaults(db_path, tmp_path):
    runner = CliRunner()
    output_file = tmp_path / "default_export.csv"
    result = runner.invoke(
        cli, ["export", str(db_path), str(output_file)] # No --format or --table
    )
    assert result.exit_code == 0
    assert output_file.exists()
    assert "Data from table 'items' successfully exported" in result.output
    assert "in csv format" in result.output # Check if "csv" is mentioned as format

    with open(output_file, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == len(SAMPLE_ITEMS_DATA)
        assert reader.fieldnames == ["item_id", "resolved_title", "excerpt", "resolved_url"]
        for i, row in enumerate(rows):
            assert row["item_id"] == str(SAMPLE_ITEMS_DATA[i]["item_id"])
            assert row["resolved_title"] == SAMPLE_ITEMS_DATA[i]["resolved_title"]

# Test that output_path is required
def test_export_missing_output_path(db_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["export", str(db_path)])
    assert result.exit_code != 0
    assert "Error: Missing argument 'OUTPUT_PATH'." in result.output

# Test that db_path is required
def test_export_missing_db_path():
    runner = CliRunner()
    result = runner.invoke(cli, ["export"])
    assert result.exit_code != 0
    assert "Error: Missing argument 'DB_PATH'." in result.output
