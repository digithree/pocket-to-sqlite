from pocket_to_sqlite import utils
import pytest
import json
import sqlite_utils
from sqlite_utils.db import ForeignKey
import pathlib


def load():
    json_path = pathlib.Path(__file__).parent / "pocket.json"
    return json.load(open(json_path, "r"))


@pytest.fixture(scope="session")
def converted():
    db = sqlite_utils.Database(":memory:")
    utils.save_items(load(), db)
    utils.ensure_fts(db)
    return db


def test_tables(converted):
    assert {
        "items_authors",
        "items_fts",
        "authors",
        "items",
        "items_fts_config",
        "items_fts_idx",
        "items_fts_data",
        "items_fts_docsize",
    } == set(converted.table_names())


def test_item(converted):
    item = list(converted["items"].rows)[0]
    assert {
        "item_id": 2746847510,
        "resolved_id": 2746847510,
        "given_url": "http://people.idsia.ch/~juergen/deep-learning-miraculous-year-1990-1991.html",
        "given_title": "Deep Learning: Our Miraculous Year 1990-1991",
        "favorite": 0,
        "status": 0,
        "time_added": 1570303854,
        "time_updated": 1570303854,
        "time_read": None,
        "time_favorited": None,
        "sort_id": 206,
        "resolved_title": "Deep Learning: Our Miraculous Year 1990-1991",
        "resolved_url": "http://people.idsia.ch/~juergen/deep-learning-miraculous-year-1990-1991.html",
        "excerpt": "The Deep Learning (DL) Neural Networks (NNs) of our team have revolutionised Pattern Recognition and Machine Learning, and are now heavily used in academia and industry [DL4].",
        "is_article": 1,
        "is_index": 0,
        "has_video": 0,
        "has_image": 1,
        "word_count": 11415,
        "lang": "en",
        "time_to_read": 52,
        "top_image_url": "http://people.idsia.ch/~juergen/miraculous-year754x395.png",
        "image": '{"item_id": "2746847510", "src": "http://people.idsia.ch/~juergen/lstmagfa288.gif", "width": "0", "height": "0"}',
        "images": '{"1": {"item_id": "2746847510", "image_id": "1", "src": "http://people.idsia.ch/~juergen/lstmagfa288.gif", "width": "0", "height": "0", "credit": "", "caption": ""}, "2": {"item_id": "2746847510", "image_id": "2", "src": "http://people.idsia.ch/~juergen/deepoverview466x288-6border.gif", "width": "0", "height": "0", "credit": "", "caption": ""}}',
        "listen_duration_estimate": 4419,
    } == item


def test_authors(converted):
    authors = list(converted["authors"].rows)
    assert [
        {
            "author_id": 120590166,
            "name": "Link.",
            "url": "http://people.idsia.ch/~juergen/heatexchanger/heatexchanger.html",
        }
    ] == authors


def test_fetch_items_handles_missing_list_key():
    """Test that FetchItems handles API responses missing the 'list' key gracefully."""
    from unittest.mock import Mock, patch
    
    # Mock auth
    auth = {
        "pocket_consumer_key": "test_key",
        "pocket_access_token": "test_token"
    }
    
    # Mock response without 'list' key
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"since": 1234567890}  # Missing 'list' key
    mock_response.raise_for_status.return_value = None
    
    with patch('requests.post', return_value=mock_response):
        fetcher = utils.FetchItems(auth, page_size=1)
        items = list(fetcher)
        
        # Should return empty list instead of raising KeyError
        assert items == []


def test_fetch_items_handles_missing_since_key():
    """Test that FetchItems handles API responses missing the 'since' key gracefully."""
    from unittest.mock import Mock, patch
    
    # Mock auth
    auth = {
        "pocket_consumer_key": "test_key",
        "pocket_access_token": "test_token"
    }
    
    # Mock response without 'since' key
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"list": {}}  # Missing 'since' key
    mock_response.raise_for_status.return_value = None
    
    with patch('requests.post', return_value=mock_response):
        fetcher = utils.FetchItems(auth, page_size=1)
        items = list(fetcher)
        
        # Should handle missing 'since' key gracefully
        assert items == []


def test_fetch_items_handles_api_error():
    """Test that FetchItems handles API error responses properly."""
    from unittest.mock import Mock, patch
    import pytest
    
    # Mock auth
    auth = {
        "pocket_consumer_key": "test_key",
        "pocket_access_token": "test_token"
    }
    
    # Mock response with error
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"error": "Invalid request"}
    mock_response.raise_for_status.return_value = None
    
    with patch('requests.post', return_value=mock_response):
        fetcher = utils.FetchItems(auth, page_size=1)
        
        # Should raise exception with the API error
        with pytest.raises(Exception, match="Pocket API error: Invalid request"):
            list(fetcher)


def test_fetch_items_handles_payload_too_large():
    """Test that FetchItems handles 413 Payload Too Large errors by reducing page size."""
    from unittest.mock import Mock, patch
    
    # Mock auth
    auth = {
        "pocket_consumer_key": "test_key",
        "pocket_access_token": "test_token"
    }
    
    # Mock response sequence: first 413 error, then success
    mock_response_error = Mock()
    mock_response_error.status_code = 200
    mock_response_error.json.return_value = {"error": "HTTP fetch failed from 'curated-corpus': 413: Payload Too Large"}
    mock_response_error.raise_for_status.return_value = None
    
    mock_response_success = Mock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {"list": {"1": {"item_id": "1", "title": "Test"}}, "since": 123}
    mock_response_success.raise_for_status.return_value = None
    
    # Mock empty response to end iteration
    mock_response_empty = Mock()
    mock_response_empty.status_code = 200
    mock_response_empty.json.return_value = {"list": {}, "since": 124}
    mock_response_empty.raise_for_status.return_value = None
    
    with patch('requests.post', side_effect=[mock_response_error, mock_response_success, mock_response_empty]):
        fetcher = utils.FetchItems(auth, page_size=100)
        items = list(fetcher)
        
        # Should successfully fetch items after reducing page size
        assert len(items) == 1
        assert items[0]["item_id"] == "1"
        # Page size should have been reduced
        assert fetcher.page_size == 50  # 100 // 2


def test_fetch_items_handles_error_none_success():
    """Test that FetchItems handles responses with error: None as success."""
    from unittest.mock import Mock, patch
    
    # Mock auth
    auth = {
        "pocket_consumer_key": "test_key",
        "pocket_access_token": "test_token"
    }
    
    # Mock response with error: None (this is actually success)
    mock_response_success = Mock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {
        "error": None,
        "list": {"1": {"item_id": "1", "title": "Test"}}, 
        "since": 123
    }
    mock_response_success.raise_for_status.return_value = None
    
    # Mock empty response to end iteration
    mock_response_empty = Mock()
    mock_response_empty.status_code = 200
    mock_response_empty.json.return_value = {"error": None, "list": {}, "since": 124}
    mock_response_empty.raise_for_status.return_value = None
    
    with patch('requests.post', side_effect=[mock_response_success, mock_response_empty]):
        fetcher = utils.FetchItems(auth, page_size=50)
        items = list(fetcher)
        
        # Should successfully fetch items despite error key being present
        assert len(items) == 1
        assert items[0]["item_id"] == "1"


def test_ensure_fts_with_no_items_table():
    """Test that ensure_fts handles case when items table doesn't exist."""
    db = sqlite_utils.Database(":memory:")
    
    # Call ensure_fts on empty database (no items table)
    utils.ensure_fts(db)
    
    # Should not crash and should not create FTS table
    assert "items_fts" not in db.table_names()
    assert "items" not in db.table_names()


def test_ensure_fts_with_items_table_creates_fts():
    """Test that ensure_fts creates FTS when items table exists."""
    db = sqlite_utils.Database(":memory:")
    
    # Create items table first
    db["items"].insert({"item_id": 1, "resolved_title": "Test", "excerpt": "Test excerpt"})
    
    # Call ensure_fts
    utils.ensure_fts(db)
    
    # Should create FTS table
    assert "items_fts" in db.table_names()
    assert "items" in db.table_names()


def test_ensure_fts_skips_when_fts_already_exists():
    """Test that ensure_fts skips creation when FTS already exists."""
    db = sqlite_utils.Database(":memory:")
    
    # Create items table and FTS
    db["items"].insert({"item_id": 1, "resolved_title": "Test", "excerpt": "Test excerpt"})
    db["items"].enable_fts(["resolved_title", "excerpt"], create_triggers=True)
    
    # Track table count before
    table_count_before = len(db.table_names())
    
    # Call ensure_fts
    utils.ensure_fts(db)
    
    # Should not create additional tables
    assert len(db.table_names()) == table_count_before
    assert "items_fts" in db.table_names()
