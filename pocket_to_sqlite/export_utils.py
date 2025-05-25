import abc
import sqlite_utils
import csv
import json # Added missing import for KarakeepExporter

class ExportAdapter(abc.ABC):
    """Abstract base class for export adapters."""

    @abc.abstractmethod
    def export_data(self, db_path: str, table_name: str, output_path: str):
        """
        Exports data from the specified table in the SQLite database to the output path.

        Args:
            db_path: Path to the SQLite database file.
            table_name: Name of the table to export.
            output_path: Path to the output file or directory.
        """
        pass


class KarakeepExporter(ExportAdapter):
    """Exporter for Karakeep API."""

    def export_data(self, db_path: str, table_name: str, output_path: str):
        """
        Exports data to Karakeep API.

        (Placeholder implementation)

        Args:
            db_path: Path to the SQLite database file.
            table_name: Name of the table to export.
            output_path: Path to the output file or directory (e.g., Karakeep API endpoint or file).
        """
        db = sqlite_utils.Database(db_path)
        table = db[table_name]
        # Placeholder: In a real implementation, this would interact with the Karakeep API
        print(f"Exporting data from table '{table_name}' in '{db_path}' to Karakeep (placeholder).")
        print(f"Output path: {output_path}")
        print(f"Total rows in table '{table_name}': {table.count}")
        # Example: Write to a JSON file as a placeholder
        with open(output_path, "w") as f:
            json.dump(list(table.rows), f, indent=4)
        print(f"Data (placeholder) written to {output_path}")


class CSVExporter(ExportAdapter):
    """Exporter for CSV files."""

    def export_data(self, db_path: str, table_name: str, output_path: str):
        """
        Exports data from the specified table in the SQLite database to a CSV file.

        Args:
            db_path: Path to the SQLite database file.
            table_name: Name of the table to export.
            output_path: Path to the output CSV file.
        """
        db = sqlite_utils.Database(db_path)
        table = db[table_name]
        rows = list(table.rows)

        if not rows:
            print(f"Table '{table_name}' in '{db_path}' is empty. Nothing to export to CSV.")
            # Create an empty CSV with headers if the table is empty
            with open(output_path, "w", newline="") as f:
                if table.columns: # Ensure columns exist even if no rows
                    writer = csv.writer(f)
                    writer.writerow(table.columns)
            return

        # Get column names from the first row (or table.columns if available and preferred)
        # Using table.columns is generally safer as it reflects the schema
        column_names = table.columns

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=column_names)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"Data from table '{table_name}' in '{db_path}' exported to '{output_path}'")


# Example usage (for testing purposes, can be removed later)
if __name__ == "__main__":
    # This is a placeholder for where the actual export command would be invoked.
    # You would need a sample database and table to test this.
    
    # Create a dummy database for testing
    db_path = "dummy_pocket.db"
    db = sqlite_utils.Database(db_path)
    
    # Create a dummy table 'items' if it doesn't exist
    if "items" not in db.table_names():
        db["items"].insert_all([
            {"item_id": 1, "title": "Test Item 1", "url": "http://example.com/1", "custom_col": "val1"},
            {"item_id": 2, "title": "Test Item 2", "url": "http://example.com/2", "custom_col": "val2"},
        ], pk="item_id")
    
    if "empty_table" not in db.table_names():
        # Create an empty table with defined columns
        db.execute("CREATE TABLE empty_table (id INTEGER PRIMARY KEY, name TEXT, value REAL)")


    print("\nTesting KarakeepExporter...")
    karakeep_exporter = KarakeepExporter()
    karakeep_exporter.export_data(db_path, "items", "karakeep_export.json")

    print("\nTesting CSVExporter with data...")
    csv_exporter = CSVExporter()
    csv_exporter.export_data(db_path, "items", "items_export.csv")

    print("\nTesting CSVExporter with empty table...")
    csv_exporter.export_data(db_path, "empty_table", "empty_export.csv")
    
    # Test with a non-existent table (sqlite-utils will create it)
    # print("\nTesting CSVExporter with non-existent table (will be created empty)...")
    # csv_exporter.export_data(db_path, "new_empty_table", "new_empty_export.csv")
    # db["new_empty_table"].insert({"col1": "data"}) # Add some data to verify
    # csv_exporter.export_data(db_path, "new_empty_table", "new_empty_export_after_insert.csv")

    print(f"\nCheck '{db_path}', 'karakeep_export.json', 'items_export.csv', and 'empty_export.csv' for output.")
