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

## Exporting to Karakeep

You can export your Pocket bookmarks to [Karakeep](https://karakeep.com/) using the `export` command.

First, add your Karakeep credentials to the `auth.json` file created by the `auth` command:

```json
{
  "pocket_consumer_key": "...",
  "pocket_access_token": "...",
  "karakeep_token": "your-karakeep-api-token", 
  "karakeep_base_url": "https://your-karakeep-instance.com"
}
```

Then export your bookmarks:

```bash
pocket-to-sqlite export pocket.db
```

### Export Options

**Filter by status:**
```bash
# Export only unread items
pocket-to-sqlite export pocket.db --filter-status 0

# Export only archived items  
pocket-to-sqlite export pocket.db --filter-status 1

# Export only deleted items
pocket-to-sqlite export pocket.db --filter-status 2
```

**Filter by favorites:**
```bash
pocket-to-sqlite export pocket.db --filter-favorite
```

**Batching and resuming:**
```bash
# Export first 100 items
pocket-to-sqlite export pocket.db --limit 100

# Resume from item 500
pocket-to-sqlite export pocket.db --offset 500 --limit 100
```

**Preview before exporting:**
```bash
# Dry-run to see what would be exported
pocket-to-sqlite export pocket.db --dry-run --limit 10
```

**Other options:**
```bash
# Use custom auth file
pocket-to-sqlite export pocket.db --auth /path/to/auth.json

# Suppress progress output
pocket-to-sqlite export pocket.db --silent

# Enable debug logging
pocket-to-sqlite export pocket.db --debug
```

The export command includes retry logic for network timeouts and rate limiting, progress tracking, and comprehensive error handling.

## Using with Datasette

The SQLite database produced by this tool is designed to be browsed using [Datasette](https://datasette.readthedocs.io/). Use the [datasette-render-timestamps](https://github.com/simonw/datasette-render-timestamps) plugin to improve the display of the timestamp values.
