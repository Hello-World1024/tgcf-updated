# tgcf/forward_count.py

import datetime
from tgcf.config import MONGO_CON_STR, MONGO_DB_NAME
from pymongo import MongoClient

FORWARD_COUNT_COL_NAME = "forward_counts"

# In-memory forward counts dictionary for session persistence
forward_counts = {}

if MONGO_CON_STR:
    client = MongoClient(MONGO_CON_STR)
    db = client[MONGO_DB_NAME]
    forward_counts_col = db[FORWARD_COUNT_COL_NAME]
else:
    forward_counts_col = None

def get_forward_count(source_id: int) -> int:
    """Gets the number of forwards for a source on the current day."""
    if forward_counts_col is None:
        return 0
    today = datetime.datetime.utcnow().date()
    today_str = today.isoformat()
    result = forward_counts_col.find_one({"source_id": source_id, "date": today_str})
    if result:
        return result.get("count", 0)
    return 0

def increment_forward_count(source_id: int):
    """Increments the forward count for a source on the current day."""
    if forward_counts_col is None:
        return
    today = datetime.datetime.utcnow().date()
    today_str = today.isoformat()
    forward_counts_col.update_one(
        {"source_id": source_id, "date": today_str},
        {"$inc": {"count": 1}},
        upsert=True,
    )


# Random message daily counter functions (using same date-based approach)

def get_random_message_count(source_id: int) -> int:
    """Gets the number of random messages posted for a source on the current day."""
    if forward_counts_col is None:
        return 0
    today = datetime.datetime.utcnow().date()
    today_str = today.isoformat()
    result = forward_counts_col.find_one({
        "source_id": source_id, 
        "date": today_str, 
        "type": "random"
    })
    if result:
        return result.get("count", 0)
    return 0


def increment_random_message_count(source_id: int):
    """Increments the random message count for a source on the current day."""
    if forward_counts_col is None:
        return
    today = datetime.datetime.utcnow().date()
    today_str = today.isoformat()
    forward_counts_col.update_one(
        {"source_id": source_id, "date": today_str, "type": "random"},
        {"$inc": {"count": 1}},
        upsert=True,
    )


def reset_random_message_counters():
    """Reset random message counters (for manual reset from web UI)."""
    if forward_counts_col is None:
        return
    today = datetime.datetime.utcnow().date()
    today_str = today.isoformat()
    result = forward_counts_col.delete_many({
        "date": today_str,
        "type": "random"
    })
    return result.deleted_count
