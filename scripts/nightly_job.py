#!/usr/bin/env python3
"""
Batch process reverse splits without EDGAR data
Run nightly via GitHub Actions to automatically process new splits
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to path
current_dir = Path(__file__).resolve().parent
src_path = current_dir.parent / 'src'
sys.path.append(str(src_path))

from split_strategy.database import get_collection, REVERSE_SPLITS_COLLECTION, EDGAR_COLLECTION
from split_strategy.edgar.processing import process_reverse_split_with_edgar
from split_strategy.edgar.client import get_cik_mapping_with_names

def get_splits_without_edgar(limit=None):
    """Get all reverse splits that don't have EDGAR data yet"""
    reverse_collection = get_collection(REVERSE_SPLITS_COLLECTION)
    edgar_collection = get_collection(EDGAR_COLLECTION)
    
    # Get all reverse splits
    # Sort by date descending to process recent ones first
    all_splits = list(reverse_collection.find({}).sort("Date", -1))
    
    # Filter to only those without EDGAR data
    splits_to_process = []
    for split in all_splits:
        # reverse_splits_id is the MongoDB _id converted to string
        reverse_splits_id = str(split.get("_id"))
        
        # Check if already processed
        count = edgar_collection.count_documents({"reverse_splits_id": reverse_splits_id})
        if count == 0:
            splits_to_process.append(split)
    
    # Limit if specified (for testing)
    if limit:
        splits_to_process = splits_to_process[:limit]
    
    return splits_to_process


def main():
    """Main batch processing function"""
    print("=" * 70)
    print("BATCH EDGAR PROCESSING - Nightly Run")
    print("=" * 70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Get CIK mappings
    print("Fetching CIK mappings...")
    cik_mappings = get_cik_mapping_with_names()
    cik_mapping = cik_mappings.get("ticker", {})
    name_mapping = cik_mappings.get("name", {})
    print(f"Loaded {len(cik_mapping)} ticker mappings and {len(name_mapping)} company name mappings")
    print()
    
    # Get splits without EDGAR data
    print("Finding splits without EDGAR data...")
    splits_to_process = get_splits_without_edgar()
    print(f"Found {len(splits_to_process)} split(s) without EDGAR data")
    print()
    
    if not splits_to_process:
        print("All splits already have EDGAR data. Nothing to process.")
        return
    
    # Process each split
    success_count = 0
    error_count = 0
    total_filings = 0
    
    for idx, split in enumerate(splits_to_process, 1):
        symbol = split.get("Symbol", "UNKNOWN")
        date_str = split.get("Date", "")
        company_name = split.get("Company Name", "")
        
        print(f"[{idx}/{len(splits_to_process)}] Processing {symbol} ({company_name}) - Split Date: {date_str}")
        
        try:
            result = process_reverse_split_with_edgar(
                split,
                cik_mapping,
                name_mapping,
                skip_existing=True
            )
            
            status = result.get("status")
            if status == "success":
                filings_count = result.get("filings_processed", 0)
                total_filings += filings_count
                success_count += 1
                print(f"  [OK] Success - Found {filings_count} EDGAR filing(s)")
            elif status == "already_processed":
                print(f"  [SKIP] Already processed")
            else:
                error_count += 1
                error_msg = result.get("error", status)
                print(f"  [FAIL] Failed - {error_msg}")
        
        except Exception as e:
            error_count += 1
            print(f"  [FAIL] Error: {str(e)[:200]}")
        
        print()
    
    # Summary
    print("=" * 70)
    print("BATCH PROCESSING SUMMARY")
    print("=" * 70)
    print(f"Total splits processed: {len(splits_to_process)}")
    print(f"  Successful: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"Total EDGAR filings found: {total_filings}")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
