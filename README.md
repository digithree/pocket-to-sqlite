# pocket-to-sqlite

[![PyPI](https://img.shields.io/pypi/v/pocket-to-sqlite.svg)](https://pypi.org/project/pocket-to-sqlite/)
[![Changelog](https://img.shields.io/github/v/release/dogsheep/pocket-to-sqlite?include_prereleases&label=changelog)](https://github.com/dogsheep/pocket-to-sqlite/releases)
[![Tests](https://github.com/dogsheep/pocket-to-sqlite/workflows/Test/badge.svg)](https://github.com/dogsheep/pocket-to-sqlite/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/dogsheep/pocket-to-sqlite/blob/main/LICENSE)

Create a SQLite database containing data from your [Pocket](https://getpocket.com/) account.

## How to install
```bash
pip install pocket-to-sqlite
```
## Usage

You will need to first obtain a valid OAuth token for your Pocket account. You can do this by running the `auth` command and following the prompts:
```bash
pocket-to-sqlite auth
```
Which looks like this:
```
Visit this page and sign in with your Pocket account:

https://getpocket.com/auth/author...

Once you have signed in there, hit <enter> to continue
Authentication tokens written to auth.json
```

Now you can fetch all of your items from Pocket like this:

```bash
pocket-to-sqlite fetch pocket.db
```

The first time you run this command it will fetch all of your items, and display a progress bar while it does it.

On subsequent runs it will only fetch new items.

You can force it to fetch everything from the beginning again using `--all`. Use `--silent` to disable the progress bar.

## Using with Datasette

The SQLite database produced by this tool is designed to be browsed using [Datasette](https://datasette.readthedocs.io/). Use the [datasette-render-timestamps](https://github.com/simonw/datasette-render-timestamps) plugin to improve the display of the timestamp values.

## Exporting Data

The `export` command allows you to export data from your Pocket SQLite database to various formats.

**Arguments:**

*   `DB_PATH`: Path to your SQLite database file (e.g., `pocket.db`). This argument is required.
*   `OUTPUT_PATH`: Path where the exported file will be saved. This argument is required.

**Options:**

*   `--format FORMAT`: Specifies the export format.
    *   Available formats: `csv`, `karakeep` (exports as JSON, placeholder for Karakeep API).
    *   Default: `csv`.
    *   The format name is case-insensitive.
*   `--table TABLE_NAME`: Specifies the name of the table to export.
    *   Default: `items`.

**Usage Examples:**

1.  **Export the `items` table to a CSV file (default behavior):**
    ```bash
    pocket-to-sqlite export pocket.db items_export.csv
    ```

2.  **Export the `items` table to a CSV file (explicitly specifying format):**
    ```bash
    pocket-to-sqlite export pocket.db items_export.csv --format csv
    ```

3.  **Export a custom table (e.g., `tags`) to a CSV file:**
    ```bash
    pocket-to-sqlite export pocket.db tags_export.csv --table tags
    ```

4.  **Export the `items` table to a Karakeep (JSON) file:**
    ```bash
    pocket-to-sqlite export pocket.db items_export.json --format karakeep
    ```

5.  **Export a custom table (e.g., `another_table`) to Karakeep (JSON):**
    ```bash
    pocket-to-sqlite export pocket.db another_table_export.json --format karakeep --table another_table
    ```
This command provides flexibility in accessing your Pocket data outside of the SQLite database.
The Karakeep format currently produces a JSON file; future updates might integrate directly with the Karakeep API.
