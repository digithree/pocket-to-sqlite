import click
import json
import urllib.parse
import pathlib
import requests
import sqlite_utils
from . import utils

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
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.option(
    "-a",
    "--auth",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
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
    
    auth = json.load(open(auth))
    db = sqlite_utils.Database(db_path)
    
    # For incremental fetch, start from the number of items already in DB
    start_offset = 0
    if not all and "items" in db.table_names():
        start_offset = db["items"].count
        if debug:
            print(f"Found {start_offset} existing items, starting from offset {start_offset}")
    
    fetch = utils.FetchItems(auth, start_offset=start_offset)
    if (all or start_offset == 0) and not silent:
        total_items = utils.fetch_stats(auth)["count_list"]
        with click.progressbar(fetch, length=total_items, show_pos=True) as bar:
            utils.save_items(bar, db)
    else:
        # No progress bar
        print("Fetching items from offset {}".format(start_offset))
        utils.save_items(fetch, db)
    utils.ensure_fts(db)


@cli.command()
@click.argument("database")
@click.option(
    "-a",
    "--auth",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="auth.json",
    help="Path to auth tokens, defaults to auth.json",
)
@click.option("--limit", type=int, help="Maximum number of items to export")
@click.option("--offset", type=int, default=0, help="Number of items to skip")
@click.option("--filter-status", type=click.Choice(['0', '1', '2']), help="Only export items with status (0=unread, 1=archived, 2=deleted)")
@click.option("--filter-favorite", is_flag=True, help="Only export favorited items")
@click.option("--dry-run", is_flag=True, help="Show what would be exported without making API calls")
@click.option("-s", "--silent", is_flag=True, help="Suppress progress output")
@click.option("--debug", is_flag=True, help="Enable debug logging")
def export(database, auth, limit, offset, filter_status, filter_favorite, dry_run, silent, debug):
    """Export bookmarks from SQLite database to Karakeep"""
    if debug:
        import logging
        logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
        print("Debug logging enabled")
    
    # Load auth file
    try:
        auth_data = json.load(open(auth))
    except FileNotFoundError:
        raise click.ClickException(f"Auth file not found: {auth}")
    except json.JSONDecodeError:
        raise click.ClickException(f"Invalid JSON in auth file: {auth}")
    
    # Validate Karakeep credentials
    if "karakeep_token" not in auth_data:
        raise click.ClickException(f"Missing 'karakeep_token' in auth file: {auth}")
    
    # Open database
    try:
        db = sqlite_utils.Database(database)
    except Exception as e:
        raise click.ClickException(f"Could not open database: {e}")
    
    # Check if items table exists
    if "items" not in db.table_names():
        raise click.ClickException("No 'items' table found in database. Run 'fetch' command first.")
    
    # Convert filter_status to int if provided
    filter_status_int = int(filter_status) if filter_status is not None else None
    
    # Get total count for progress tracking
    count_conditions = []
    count_params = []
    
    if filter_status_int is not None:
        count_conditions.append("status = ?")
        count_params.append(filter_status_int)
        
    if filter_favorite:
        count_conditions.append("favorite = 1")
    
    count_where = " WHERE " + " AND ".join(count_conditions) if count_conditions else ""
    count_result = list(db.execute(f"SELECT COUNT(*) as count FROM items{count_where}", count_params))[0]
    total_items = count_result[0] if isinstance(count_result, tuple) else count_result["count"]
    
    if not silent:
        print(f"Found {total_items} items to export")
        if filter_status_int is not None:
            status_names = {0: "unread", 1: "archived", 2: "deleted"}
            print(f"Filtering by status: {status_names.get(filter_status_int, filter_status_int)}")
        if filter_favorite:
            print("Filtering by favorites only")
        if limit:
            print(f"Limiting to {limit} items")
        if offset:
            print(f"Starting from offset {offset}")
        if dry_run:
            print("DRY RUN - No actual API calls will be made")
    
    if dry_run:
        # Show what would be exported
        for result in utils.preview_export_items(
            db, limit=limit, offset=offset, 
            filter_status=filter_status_int, filter_favorite=filter_favorite
        ):
            if result["status"] == "skipped":
                print(f"[SKIP] Item {result['item_id']}: {result['reason']}")
            else:
                print(f"[EXPORT] Item {result['item_id']}: {result.get('title', 'No title')[:60]}...")
                print(f"         URL: {result.get('url', 'No URL')}")
    else:
        # Actual export with progress bar
        success_count = 0
        error_count = 0
        skip_count = 0
        
        export_iter = utils.export_items_to_karakeep(
            db, auth_data, limit=limit, offset=offset,
            filter_status=filter_status_int, filter_favorite=filter_favorite
        )
        
        if not silent:
            # Determine progress bar length
            progress_length = min(limit, total_items - offset) if limit else (total_items - offset)
            
            with click.progressbar(export_iter, length=progress_length, show_pos=True, 
                                 label="Exporting") as bar:
                for result in bar:
                    if result["status"] == "success":
                        success_count += 1
                    elif result["status"] == "error":
                        error_count += 1
                        if debug:
                            print(f"\nError exporting item {result['item_id']}: {result['error']}")
                    elif result["status"] == "skipped":
                        skip_count += 1
        else:
            # No progress bar
            for result in export_iter:
                if result["status"] == "success":
                    success_count += 1
                elif result["status"] == "error":
                    error_count += 1
                elif result["status"] == "skipped":
                    skip_count += 1
        
        if not silent:
            print(f"\nExport completed:")
            print(f"  Successfully exported: {success_count}")
            if skip_count > 0:
                print(f"  Skipped: {skip_count}")
            if error_count > 0:
                print(f"  Errors: {error_count}")
        
        if error_count > 0:
            raise click.ClickException(f"Export completed with {error_count} errors")
