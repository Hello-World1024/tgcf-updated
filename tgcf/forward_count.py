# tgcf/forward_count.py

import datetime
from tgcf.config import MONGO_CON_STR, MONGO_DB_NAME
from pymongo import MongoClient

FORWARD_COUNT_COL_NAME = "forward_counts"

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
