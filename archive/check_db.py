
import os
from pymongo import MongoClient
from datetime import datetime
import sys

# Add parent directory to path to find load_env.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import load_env
except ImportError:
    pass

MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    print("MONGODB_URI not set")
    sys.exit(1)

client = MongoClient(MONGODB_URI)
db = client["split_strategy"]
collection = db["early_edgar_splits"]

# Check for splits filed on 2026-02-06
splits = list(collection.find({"filing_date": "20260206"}))

print(f"Found {len(splits)} splits for 2026-02-06:")
for s in splits:
    print(f"- {s.get('ticker', 'UNKNOWN')} ({s.get('company_name')}) - Ratio: {s.get('ratio')} - Rounding: {s.get('rounding_up')}")
