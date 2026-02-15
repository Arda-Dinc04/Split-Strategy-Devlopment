#!/usr/bin/env python3
"""
Check database for early EDGAR splits.
"""
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
current_dir = Path(__file__).resolve().parent
src_path = current_dir.parent / 'src'
sys.path.append(str(src_path))

try:
    from split_strategy.database import get_collection, EARLY_WARNINGS_COLLECTION
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def main():
    try:
        collection = get_collection(EARLY_WARNINGS_COLLECTION)
        
        # Check for splits filed on 2026-02-06 (example) or just recent ones
        filing_date = "2026-02-06"
        splits = list(collection.find({}).sort("filing_date", -1).limit(10))
        
        print(f"Found {len(splits)} recent splits:")
        for s in splits:
            print(f"- {s.get('filing_date')} | {s.get('ticker', 'UNKNOWN')} ({s.get('company_name')}) - Ratio: {s.get('ratio')} - Rounding: {s.get('rounding_up')}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
