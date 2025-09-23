from __future__ import annotations
from typing import List, Dict, Any
import os, time
from pymongo import MongoClient, ASCENDING
from src.config.settings import get_settings

class MongoSTM:
    def __init__(self, uri: str | None = None, db_name: str = "agentic", coll_name: str = "stm"):
        if uri is None:
            settings = get_settings()
            self.uri = settings.mongo_uri
        else:
            self.uri = uri
        self.client = MongoClient(self.uri)
        self.db = self.client[db_name]
        self.coll = self.db[coll_name]
        self.coll.create_index([("session_id", ASCENDING), ("ts", ASCENDING)])

    def add(self, session_id: str, role: str, content: str, meta: Dict[str,Any] | None = None):
        self.coll.insert_one({"session_id":session_id,"role":role,"content":content,"meta":meta or {}, "ts": time.time()})

    def recent(self, session_id: str, limit: int = 10) -> List[Dict[str,Any]]:
        cur=self.coll.find({"session_id":session_id}).sort("ts",-1).limit(limit)
        return list(cur)[::-1]
