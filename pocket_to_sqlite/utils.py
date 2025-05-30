import datetime
import requests
import json
import time
import logging
import hashlib
import uuid
from sqlite_utils.db import AlterError, ForeignKey
from requests.exceptions import RequestException, Timeout, HTTPError


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
                # Handle both numeric and string author_ids
                author_id_raw = details["author_id"]
                try:
                    # Try to use as integer (normal case)
                    author_id = int(author_id_raw)
                    author_name = details["name"]
                except ValueError:
                    # String author_id - treat it as the name and generate unique ID
                    author_name = author_id_raw
                    # Generate deterministic integer ID from the string
                    author_id = int(hashlib.md5(author_id_raw.encode()).hexdigest()[:8], 16)
                
                authors_to_save.append(
                    {
                        "author_id": author_id,
                        "name": author_name,
                        "url": details["url"],
                    }
                )
                items_authors_to_save.append(
                    {
                        "author_id": author_id,
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
        self, auth, start_offset=0, page_size=50, sleep=2, retry_sleep=3
    ):
        self.auth = auth
        self.start_offset = start_offset
        self.page_size = page_size
        self.sleep = sleep
        self.retry_sleep = retry_sleep

    def __iter__(self):
        offset = self.start_offset
        retries = 0
        logging.debug(f"Starting fetch with start_offset={self.start_offset}, page_size={self.page_size}")
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
            
            # Check for API errors (error key present AND has a non-None value)
            error_msg = page.get('error')
            if error_msg is not None:
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
            if not items:
                logging.debug("No more items found, breaking from loop")
                break
            logging.debug(f"Yielding {len(items)} items")
            yield from items
            offset += self.page_size
            logging.debug(f"Updated offset to {offset}")
            if self.sleep:
                time.sleep(self.sleep)


class KarakeepClient:
    """Client for exporting bookmarks to Karakeep via REST API."""
    
    def __init__(self, auth, sleep=1, retry_sleep=3):
        """
        Initialize Karakeep client.
        
        Args:
            auth: Dict containing karakeep_token and karakeep_base_url
            sleep: Seconds to sleep between API calls
            retry_sleep: Base seconds for retry backoff
        """
        self.auth = auth
        self.sleep = sleep
        self.retry_sleep = retry_sleep
        self.base_url = auth.get("karakeep_base_url", "https://try.karakeep.app")
        self.token = auth["karakeep_token"]
        self._tags_cache = None
        
    def create_bookmark(self, title, summary, url):
        """
        Create a bookmark in Karakeep.
        
        Args:
            title: Bookmark title
            summary: Bookmark summary/description
            url: Bookmark URL
            
        Returns:
            Response data from Karakeep API
            
        Raises:
            Exception: If API call fails after retries
        """
        payload = {
            "title": title,
            "summary": summary,
            "type": "link",
            "url": url,
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        
        retries = 0
        while retries < 5:
            try:
                logging.debug(f"Creating bookmark: {title[:50]}...")
                response = requests.post(
                    f"{self.base_url}/api/v1/bookmarks",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                
                logging.debug(f"Karakeep API response status: {response.status_code}")
                
                # Handle rate limiting and server errors with retry
                if response.status_code in [429, 503, 504] and retries < 5:
                    error_type = {
                        429: "rate limited",
                        503: "service unavailable", 
                        504: "gateway timeout"
                    }.get(response.status_code, "server error")
                    
                    logging.info(f"Got {response.status_code} ({error_type}), retrying in {retries + 1}s...")
                    retries += 1
                    time.sleep(retries * self.retry_sleep)
                    continue
                
                # Handle client errors (400-level) without retry
                if 400 <= response.status_code < 500:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('message', f'HTTP {response.status_code} error')
                        error_code = error_data.get('code', 'unknown')
                        raise Exception(f"Karakeep API error ({error_code}): {error_msg}")
                    except ValueError:  # JSON decode error
                        raise Exception(f"Karakeep API error: HTTP {response.status_code} - {response.text}")
                
                response.raise_for_status()
                
                if self.sleep and retries == 0:  # Only sleep on successful calls, not retries
                    time.sleep(self.sleep)
                
                result = response.json()
                
                # Log successful creation with bookmark ID
                if response.status_code == 201 and 'id' in result:
                    logging.debug(f"Successfully created bookmark with ID: {result['id']}")
                    
                return result
                
            except (Timeout, RequestException) as e:
                if retries < 5:
                    logging.info(f"Request timeout/error, retrying in {retries + 1}s...")
                    retries += 1
                    time.sleep(retries * self.retry_sleep)
                    continue
                else:
                    raise Exception(f"Karakeep API request failed after 5 retries: {e}")
        
        raise Exception(f"Karakeep API request failed after 5 retries")
    
    def get_all_tags(self):
        """
        Fetch all tags from Karakeep.
        
        Returns:
            Dict with tag names as keys and tag data as values
            
        Raises:
            Exception: If API call fails
        """
        if self._tags_cache is not None:
            return self._tags_cache
            
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        
        try:
            logging.debug("Fetching all tags from Karakeep")
            response = requests.get(
                f"{self.base_url}/api/v1/tags",
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Convert to dict with tag names as keys for easy lookup
            self._tags_cache = {tag["name"]: tag for tag in data.get("tags", [])}
            logging.debug(f"Fetched {len(self._tags_cache)} tags from Karakeep")
            
            return self._tags_cache
            
        except Exception as e:
            raise Exception(f"Failed to fetch tags from Karakeep: {e}")
    
    def add_tags_to_bookmark(self, bookmark_id, tag_names):
        """
        Add tags to a bookmark in Karakeep.
        
        Args:
            bookmark_id: The ID of the bookmark to tag
            tag_names: List of tag names to add
            
        Returns:
            Response data from Karakeep API
            
        Raises:
            Exception: If API call fails
        """
        if not tag_names:
            return {"attached": []}
            
        # Get existing tags to check which ones already exist
        existing_tags = self.get_all_tags()
        
        # Prepare tags payload
        tags_payload = []
        for tag_name in tag_names:
            if tag_name in existing_tags:
                # Use existing tag
                tag_data = existing_tags[tag_name]
                tags_payload.append({
                    "tagId": tag_data["id"],
                    "tagName": tag_data["name"]
                })
            else:
                # Create new tag with random ID
                tag_id = str(uuid.uuid4()).replace("-", "")[:16]  # 16 char random ID
                tags_payload.append({
                    "tagId": tag_id,
                    "tagName": tag_name
                })
                # Add to cache so subsequent uses in same session will find it
                existing_tags[tag_name] = {"id": tag_id, "name": tag_name}
        
        payload = {"tags": tags_payload}
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        
        try:
            logging.debug(f"Adding {len(tags_payload)} tags to bookmark {bookmark_id}")
            response = requests.post(
                f"{self.base_url}/api/v1/bookmarks/{bookmark_id}/tags",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            logging.debug(f"Successfully added tags to bookmark {bookmark_id}: {result.get('attached', [])}")
            return result
            
        except Exception as e:
            raise Exception(f"Failed to add tags to bookmark {bookmark_id}: {e}")


def export_items_to_karakeep(db, auth, limit=None, offset=0, filter_status=None, filter_favorite=False):
    """
    Export items from SQLite database to Karakeep.
    
    Args:
        db: sqlite_utils.Database instance
        auth: Auth dict with Karakeep credentials
        limit: Maximum number of items to export (None for all)
        offset: Number of items to skip
        filter_status: Only export items with this status (0=unread, 1=archived, 2=deleted)
        filter_favorite: Only export favorited items if True
        
    Yields:
        Dict for each item with export result
    """
    client = KarakeepClient(auth)
    
    # Pre-fetch tags from Karakeep to enable tag matching
    try:
        client.get_all_tags()
        logging.debug("Successfully pre-fetched tags from Karakeep")
    except Exception as e:
        logging.warning(f"Failed to pre-fetch tags from Karakeep: {e}")
    
    # Build query conditions
    conditions = []
    params = []
    
    if filter_status is not None:
        conditions.append("status = ?")
        params.append(filter_status)
        
    if filter_favorite:
        conditions.append("favorite = 1")
    
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Check if tags column exists 
    columns = [col[1] for col in db.execute("PRAGMA table_info(items)")]
    has_tags_column = "tags" in columns
    
    # Build query with or without tags column
    if has_tags_column:
        sql = f"""
            SELECT 
                item_id, 
                resolved_title, 
                given_title, 
                resolved_url, 
                given_url, 
                excerpt,
                tags
            FROM items
            {where_clause}
            ORDER BY item_id
            LIMIT ? OFFSET ?
        """
    else:
        sql = f"""
            SELECT 
                item_id, 
                resolved_title, 
                given_title, 
                resolved_url, 
                given_url, 
                excerpt,
                NULL as tags
            FROM items
            {where_clause}
            ORDER BY item_id
            LIMIT ? OFFSET ?
        """
    
    # Add limit and offset to params
    final_limit = limit if limit is not None else -1  # SQLite uses -1 for no limit
    params.extend([final_limit, offset])
    
    logging.debug(f"Export query: {sql}")
    logging.debug(f"Export params: {params}")
    
    count = 0
    success_count = 0
    
    for row in db.execute(sql, params):
        count += 1
        
        # Convert row to dict for easier access
        row_dict = dict(row) if hasattr(row, 'keys') else dict(zip([
            'item_id', 'resolved_title', 'given_title', 'resolved_url', 'given_url', 'excerpt', 'tags'
        ], row))
        
        # Map Pocket item to Karakeep bookmark
        title = row_dict["resolved_title"] or row_dict["given_title"] or "Untitled"
        url = row_dict["resolved_url"] or row_dict["given_url"]
        summary = row_dict["excerpt"] or ""
        
        # Skip items without URLs
        if not url:
            logging.warning(f"Skipping item {row_dict['item_id']} - no URL found")
            yield {
                "item_id": row_dict["item_id"],
                "status": "skipped",
                "reason": "no_url"
            }
            continue
        
        try:
            result = client.create_bookmark(title, summary, url)
            success_count += 1
            logging.debug(f"Successfully exported item {row_dict['item_id']}")
            
            # Handle tags if they exist
            tags_result = None
            bookmark_id = result.get("id")
            tags_data = row_dict.get("tags")
            
            logging.debug(f"Item {row_dict['item_id']}: bookmark_id={bookmark_id}, tags_data={tags_data}")
            
            if bookmark_id and tags_data:
                # Parse tags from Pocket format: {"programming": {"tag": "programming", "item_id": "131375573"}, ...}
                tag_names = []
                try:
                    if tags_data.startswith('{'):
                        # JSON format from Pocket API
                        tags_obj = json.loads(tags_data)
                        # Extract tag names from the nested structure
                        tag_names = [tag_info.get("tag", tag_key) for tag_key, tag_info in tags_obj.items() if isinstance(tag_info, dict)]
                        # Fallback to keys if tag field not found
                        if not tag_names:
                            tag_names = list(tags_obj.keys())
                    else:
                        # Comma-separated format (fallback)
                        tag_names = [tag.strip() for tag in tags_data.split(",") if tag.strip()]
                except (json.JSONDecodeError, AttributeError, TypeError):
                    # Fallback to comma-separated
                    tag_names = [tag.strip() for tag in str(tags_data).split(",") if tag.strip()]
                
                logging.debug(f"Item {row_dict['item_id']}: parsed {len(tag_names)} tags: {tag_names}")
                
                if tag_names:
                    try:
                        tags_result = client.add_tags_to_bookmark(bookmark_id, tag_names)
                        logging.debug(f"Successfully added {len(tag_names)} tags to bookmark {bookmark_id}")
                    except Exception as e:
                        logging.warning(f"Failed to add tags to bookmark {bookmark_id}: {e}")
                else:
                    logging.debug(f"Item {row_dict['item_id']}: no valid tags found after parsing")
            else:
                if not bookmark_id:
                    logging.debug(f"Item {row_dict['item_id']}: no bookmark_id from Karakeep response")
                if not tags_data:
                    logging.debug(f"Item {row_dict['item_id']}: no tags data in database")
            
            yield {
                "item_id": row_dict["item_id"],
                "status": "success",
                "title": title,
                "url": url,
                "karakeep_response": result,
                "tags_response": tags_result
            }
            
        except Exception as e:
            logging.error(f"Failed to export item {row_dict['item_id']}: {e}")
            yield {
                "item_id": row_dict["item_id"],
                "status": "error",
                "title": title,
                "url": url,
                "error": str(e)
            }
    
    logging.info(f"Export completed: {success_count}/{count} items successfully exported")


def preview_export_items(db, limit=None, offset=0, filter_status=None, filter_favorite=False):
    """
    Preview items that would be exported to Karakeep (dry-run mode).
    
    Args:
        db: sqlite_utils.Database instance
        limit: Maximum number of items to preview (None for all)
        offset: Number of items to skip
        filter_status: Only preview items with this status (0=unread, 1=archived, 2=deleted)
        filter_favorite: Only preview favorited items if True
        
    Yields:
        Dict for each item that would be exported
    """
    # Build query conditions
    conditions = []
    params = []
    
    if filter_status is not None:
        conditions.append("status = ?")
        params.append(filter_status)
        
    if filter_favorite:
        conditions.append("favorite = 1")
    
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Check if tags column exists 
    columns = [col[1] for col in db.execute("PRAGMA table_info(items)")]
    has_tags_column = "tags" in columns
    
    # Build query with or without tags column
    if has_tags_column:
        sql = f"""
            SELECT 
                item_id, 
                resolved_title, 
                given_title, 
                resolved_url, 
                given_url, 
                excerpt,
                tags
            FROM items
            {where_clause}
            ORDER BY item_id
            LIMIT ? OFFSET ?
        """
    else:
        sql = f"""
            SELECT 
                item_id, 
                resolved_title, 
                given_title, 
                resolved_url, 
                given_url, 
                excerpt,
                NULL as tags
            FROM items
            {where_clause}
            ORDER BY item_id
            LIMIT ? OFFSET ?
        """
    
    # Add limit and offset to params
    final_limit = limit if limit is not None else -1  # SQLite uses -1 for no limit
    params.extend([final_limit, offset])
    
    for row in db.execute(sql, params):
        # Convert row to dict for easier access
        row_dict = dict(row) if hasattr(row, 'keys') else dict(zip([
            'item_id', 'resolved_title', 'given_title', 'resolved_url', 'given_url', 'excerpt', 'tags'
        ], row))
        
        # Map Pocket item to Karakeep bookmark
        title = row_dict["resolved_title"] or row_dict["given_title"] or "Untitled"
        url = row_dict["resolved_url"] or row_dict["given_url"]
        
        # Skip items without URLs
        if not url:
            yield {
                "item_id": row_dict["item_id"],
                "status": "skipped", 
                "reason": "no_url"
            }
        else:
            tags_data = row_dict.get("tags")
            tag_names = []
            if tags_data:
                try:
                    if tags_data.startswith('{'):
                        # JSON format from Pocket API: {"programming": {"tag": "programming", "item_id": "131375573"}, ...}
                        tags_obj = json.loads(tags_data)
                        # Extract tag names from the nested structure
                        tag_names = [tag_info.get("tag", tag_key) for tag_key, tag_info in tags_obj.items() if isinstance(tag_info, dict)]
                        # Fallback to keys if tag field not found
                        if not tag_names:
                            tag_names = list(tags_obj.keys())
                    else:
                        # Comma-separated format (fallback)
                        tag_names = [tag.strip() for tag in tags_data.split(",") if tag.strip()]
                except (json.JSONDecodeError, AttributeError, TypeError):
                    # Fallback to comma-separated
                    tag_names = [tag.strip() for tag in str(tags_data).split(",") if tag.strip()]
            
            yield {
                "item_id": row_dict["item_id"],
                "status": "preview",
                "title": title,
                "url": url,
                "tags": tag_names
            }
