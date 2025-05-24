import datetime
import requests
import json
import time
import logging
from sqlite_utils.db import AlterError, ForeignKey


def save_items(items, db):
    count = 0
    for item in items:
        count += 1
        logging.debug(f"Processing item {count}: {item.get('item_id', 'unknown')}")
        transform(item)
        authors = item.pop("authors", None)
        items_authors_to_save = []
        if authors:
            authors_to_save = []
            for details in authors.values():
                authors_to_save.append(
                    {
                        "author_id": int(details["author_id"]),
                        "name": details["name"],
                        "url": details["url"],
                    }
                )
                items_authors_to_save.append(
                    {
                        "author_id": int(details["author_id"]),
                        "item_id": int(details["item_id"]),
                    }
                )
            db["authors"].insert_all(authors_to_save, pk="author_id", replace=True)
        db["items"].insert(item, pk="item_id", alter=True, replace=True)
        if items_authors_to_save:
            db["items_authors"].insert_all(
                items_authors_to_save,
                pk=("author_id", "item_id"),
                foreign_keys=("author_id", "item_id"),
                replace=True,
            )


def transform(item):
    for key in (
        "item_id",
        "resolved_id",
        "favorite",
        "status",
        "time_added",
        "time_updated",
        "time_read",
        "time_favorited",
        "is_article",
        "is_index",
        "has_video",
        "has_image",
        "word_count",
        "time_to_read",
        "listen_duration_estimate",
    ):
        if key in item:
            item[key] = int(item[key])

    for key in ("time_read", "time_favorited"):
        if key in item and not item[key]:
            item[key] = None


def ensure_fts(db):
    if "items_fts" not in db.table_names() and "items" in db.table_names():
        db["items"].enable_fts(["resolved_title", "excerpt"], create_triggers=True)


def fetch_stats(auth):
    headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF8"}
    data = {
        "consumer_key": auth["pocket_consumer_key"],
        "access_token": auth["pocket_access_token"],
    }
    response = requests.post("https://getpocket.com/v3/stats", data=data, headers=headers)
    response.raise_for_status()
    return response.json()


class FetchItems:
    def __init__(
        self, auth, since=None, page_size=50, sleep=2, retry_sleep=3, record_since=None
    ):
        self.auth = auth
        self.since = since
        self.page_size = page_size
        self.sleep = sleep
        self.retry_sleep = retry_sleep
        self.record_since = record_since

    def __iter__(self):
        offset = 0
        retries = 0
        logging.debug(f"Starting fetch with since={self.since}, page_size={self.page_size}")
        while True:
            args = {
                "consumer_key": self.auth["pocket_consumer_key"],
                "access_token": self.auth["pocket_access_token"],
                "sort": "oldest",
                "state": "all",
                "detailType": "complete",
                "count": self.page_size,
                "offset": offset,
            }
            if self.since is not None:
                args["since"] = self.since
            
            logging.debug(f"Making API request to /v3/get with offset={offset}")
            headers = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF8"}
            response = requests.post("https://getpocket.com/v3/get", data=args, headers=headers)
            logging.debug(f"API response status: {response.status_code}")
            if response.status_code == 503 and retries < 5:
                print("Got a 503, retrying...")
                retries += 1
                time.sleep(retries * self.retry_sleep)
                continue
            else:
                retries = 0
            response.raise_for_status()
            page = response.json()
            logging.debug(f"API response keys: {list(page.keys())}")
            
            # Check for API errors
            if "error" in page:
                error_msg = page.get('error', 'Unknown error')
                logging.error(f"API returned error: {page}")
                
                # Handle payload too large by reducing page size
                if "413" in str(error_msg) or "Payload Too Large" in str(error_msg):
                    if self.page_size > 10:
                        new_page_size = max(10, self.page_size // 2)
                        logging.warning(f"Payload too large, reducing page size from {self.page_size} to {new_page_size}")
                        self.page_size = new_page_size
                        continue  # Retry with smaller page size
                    else:
                        raise Exception(f"Pocket API error: Even minimum page size (10) is too large: {error_msg}")
                
                raise Exception(f"Pocket API error: {error_msg}")
            
            items = list((page.get("list") or {}).values())
            logging.debug(f"Found {len(items)} items in this page")
            
            next_since = page.get("since")
            logging.debug(f"Next since value: {next_since}")
            if self.record_since and next_since:
                self.record_since(next_since)
            if not items:
                logging.debug("No more items found, breaking from loop")
                break
            logging.debug(f"Yielding {len(items)} items")
            yield from items
            offset += self.page_size
            logging.debug(f"Updated offset to {offset}")
            if self.sleep:
                time.sleep(self.sleep)
