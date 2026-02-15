"""
Database connection and helper functions.
"""
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from typing import Optional

from .config import (
    MONGODB_URI, 
    MONGODB_DATABASE, 
    REVERSE_SPLITS_COLLECTION, 
    EDGAR_COLLECTION, 
    EARLY_WARNINGS_COLLECTION
)

def get_db_client() -> MongoClient:
    """Get a MongoDB client instance."""
    if not MONGODB_URI:
        raise ValueError("MONGODB_URI environment variable is not set.")
    return MongoClient(MONGODB_URI)

def get_db(client: Optional[MongoClient] = None) -> Database:
    """Get the database instance."""
    if client is None:
        client = get_db_client()
    return client[MONGODB_DATABASE]

def get_collection(collection_name: str, client: Optional[MongoClient] = None) -> Collection:
    """Get a collection from the database."""
    db = get_db(client)
    return db[collection_name]
