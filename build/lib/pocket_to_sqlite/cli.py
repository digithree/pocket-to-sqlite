import click
import json
import urllib.parse
import pathlib
import requests
import sqlite_utils
from . import utils
from .export_utils import KarakeepExporter, CSVExporter # Added import

CONSUMER_KEY = "87988-a6fd295a556dbdb47960ec60"


@click.group()
@click.version_option()
def cli():
    "Save Pocket data to a SQLite database"


@cli.command()
@click.option(
    "-a",
    "--auth",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="auth.json",
    help="Path to save tokens to, defaults to auth.json",
)
def auth(auth):
    "Save authentication credentials to a JSON file"
    response = requests.post(
        "https://getpocket.com/v3/oauth/request",
        {
            "consumer_key": CONSUMER_KEY,
            "redirect_uri": "https://getpocket.com/connected_applications",
        },
    )
    request_token = dict(urllib.parse.parse_qsl(response.text))["code"]
    click.echo("Visit this page and sign in with your Pocket account:\n")
    click.echo(
        "https://getpocket.com/auth/authorize?request_token={}&redirect_uri={}\n".format(
            request_token, "https://getpocket.com/connected_applications"
        )
    )
    input("Once you have signed in there, hit <enter> to continue")
    # Now exchange the request_token for an access_token
    response2 = requests.post(
        "https://getpocket.com/v3/oauth/authorize",
        {"consumer_key": CONSUMER_KEY, "code": request_token},
    )
    codes = dict(urllib.parse.parse_qsl(response2.text))

    codes["consumer_key"] = CONSUMER_KEY

    auth_data = {}
    auth_path = pathlib.Path(auth)
    if auth_path.exists():
        auth_data = json.loads(auth_path.read_text())

    auth_data.update(
        {
            "pocket_consumer_key": CONSUMER_KEY,
            "pocket_username": codes["username"],
            "pocket_access_token": codes["access_token"],
        }
    )

    open(auth, "w").write(json.dumps(auth_data, indent=4) + "\n")
    click.echo("Authentication tokens written to {}".format(auth))


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False, exists=True), # Added exists=True
    required=True,
)
@click.option(
    "-a",
    "--auth",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False, exists=True), # Added exists=True
    default="auth.json",
    help="Path to auth tokens, defaults to auth.json",
)
@click.option("--all", is_flag=True, help="Fetch all items (not just new ones)")
@click.option("-s", "--silent", is_flag=True, help="Don't show progress bar")
@click.option("--debug", is_flag=True, help="Enable debug logging")
def fetch(db_path, auth, all, silent, debug):
    "Save Pocket data to a SQLite database"
    if debug:
        import logging
        logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
        print("Debug logging enabled")
    
    auth_content = json.load(open(auth)) # Renamed variable to avoid conflict
    db = sqlite_utils.Database(db_path)
    
    # For incremental fetch, start from the number of items already in DB
    start_offset = 0
    if not all and "items" in db.table_names():
        start_offset = db["items"].count
        if debug:
            print(f"Found {start_offset} existing items, starting from offset {start_offset}")
    
    fetch_items_iter = utils.FetchItems(auth_content, start_offset=start_offset) # Renamed variable
    if (all or start_offset == 0) and not silent:
        try:
            # Try to get total_items, might fail if API is down or no items
            total_items = utils.fetch_stats(auth_content)["count_list"]
            with click.progressbar(fetch_items_iter, length=total_items, show_pos=True) as bar:
                utils.save_items(bar, db)
        except requests.exceptions.RequestException as e:
            click.echo(f"Could not fetch total item count from Pocket API: {e}", err=True)
            click.echo("Continuing without progress bar...")
            utils.save_items(fetch_items_iter, db)
        except KeyError:
            click.echo("Could not determine total item count from Pocket API response (KeyError).", err=True)
            click.echo("Continuing without progress bar...")
            utils.save_items(fetch_items_iter, db)

    else:
        # No progress bar
        if not silent: # Only print if not silent
            click.echo("Fetching items from offset {}".format(start_offset))
        utils.save_items(fetch_items_iter, db)
    utils.ensure_fts(db)


@cli.command()
@click.argument(
    "db_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False, exists=True),
    required=True,
)
@click.argument(
    "output_path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.option(
    "--format",
    "export_format", # Use a different name for the variable to avoid conflict with the module
    type=click.Choice(["csv", "karakeep"], case_sensitive=False),
    default="csv",
    help="The export format (csv or karakeep). Defaults to csv.",
)
@click.option(
    "--table",
    default="items",
    help="The name of the table to export. Defaults to 'items'.",
)
def export(db_path, output_path, export_format, table):
    """Export data from the SQLite database to the specified format."""
    
    exporters = {
        "csv": CSVExporter,
        "karakeep": KarakeepExporter,
    }

    ExporterClass = exporters.get(export_format.lower())

    if not ExporterClass:
        click.echo(f"Error: Unknown export format '{export_format}'. Supported formats are: {', '.join(exporters.keys())}", err=True)
        return

    # Check if table exists
    db = sqlite_utils.Database(db_path)
    if table not in db.table_names():
        click.echo(f"Error: Table '{table}' not found in database '{db_path}'.", err=True)
        available_tables = db.table_names()
        if available_tables:
            click.echo(f"Available tables are: {', '.join(available_tables)}")
        else:
            click.echo("The database has no tables.")
        return

    exporter = ExporterClass()
    try:
        exporter.export_data(db_path, table, output_path)
        click.echo(f"Data from table '{table}' successfully exported to '{output_path}' in {export_format} format.")
    except Exception as e:
        click.echo(f"An error occurred during export: {e}", err=True)
