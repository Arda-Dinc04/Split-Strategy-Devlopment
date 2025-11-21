"""
Batch Process EDGAR Workflow
Processes reverse_sa splits in batches of 1000 to avoid long-running processes
Ensures no duplicates by processing sequentially
"""

import sys
import os
from pymongo import MongoClient
from edgar_workflow_complete import (
    get_cik_mapping_with_names, process_split_with_edgar,
    batch_find_earliest_announcements, generate_summary_table, print_summary_table
)

BATCH_SIZE = 1000
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://RS:01SDcSCdulMJREai@cluster0.wauawr1.mongodb.net/?appName=Cluster0")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"
EDGAR_COLLECTION = "edgar_events"

def batch_process_all():
    """Process all splits in batches sequentially"""
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    reverse_collection = db[REVERSE_COLLECTION]
    
    total_count = reverse_collection.count_documents({})
    
    print("=" * 70)
    print(f"BATCH PROCESSING EDGAR WORKFLOW")
    print(f"Total splits: {total_count}")
    print(f"Batch size: {BATCH_SIZE}")
    print("=" * 70)
    
    # Get CIK mapping once
    print("\nFetching CIK mapping...")
    cik_mappings = get_cik_mapping_with_names()
    cik_mapping = cik_mappings.get("ticker", {})
    name_mapping = cik_mappings.get("name", {})
    print(f"✓ Loaded {len(cik_mapping)} ticker mappings and {len(name_mapping)} company name mappings")
    
    batch_num = 1
    skip_count = 0
    
    while skip_count < total_count:
        print(f"\n{'=' * 70}")
        print(f"BATCH {batch_num}: Processing next {BATCH_SIZE} splits")
        print(f"{'=' * 70}\n")
        
        # Get next batch of splits (sorted by date, newest first, but skip already processed)
        all_splits = list(reverse_collection.find({}).sort("Date", -1).skip(skip_count).limit(BATCH_SIZE))
        
        if not all_splits:
            print("No more splits to process!")
            break
        
        print(f"Found {len(all_splits)} splits to process in this batch")
        
        # Process Phase 1: Query EDGAR
        total_filings = 0
        processed_count = 0
        already_processed_count = 0
        no_cik_count = 0
        no_filings_data = []
        no_filings_in_window = []
        
        for i, split in enumerate(all_splits, 1):
            if i % 50 == 0:
                print(f"\nProgress: {i}/{len(all_splits)} splits processed")
            
            result = process_split_with_edgar(split, cik_mapping, name_mapping, skip_existing=True)
            
            if result["status"] == "success":
                processed_count += 1
                total_filings += result["filings_processed"]
            elif result["status"] == "already_processed":
                already_processed_count += 1
            elif result["status"] == "no_cik":
                no_cik_count += 1
            elif result["status"] == "no_filings_data":
                no_filings_data.append(result)
            elif result["status"] == "no_filings_in_window":
                no_filings_in_window.append(result)
        
        print(f"\n✓ Batch {batch_num} Phase 1 Complete:")
        print(f"  Processed: {processed_count} splits")
        print(f"  Already processed: {already_processed_count} splits")
        print(f"  No CIK found: {no_cik_count} splits")
        print(f"  Skipped (no filings): {len(no_filings_data) + len(no_filings_in_window)} splits")
        print(f"  Total filings processed: {total_filings}")
        
        # Process Phase 2: Find earliest announcements for this batch
        print(f"\n{'=' * 70}")
        print(f"BATCH {batch_num} PHASE 2: Finding Earliest Announcements")
        print(f"{'=' * 70}")
        
        # Process Phase 2 for the same batch of splits
        from find_earliest_announcement import find_earliest_announcement
        
        updated_count = 0
        skipped_count_phase2 = 0
        
        print(f"\nProcessing {len(all_splits)} reverse splits for Phase 2...")
        for i, split in enumerate(all_splits, 1):
            if i % 50 == 0:
                print(f"Progress: {i}/{len(all_splits)}")
            
            reverse_sa_id = str(split["_id"])
            symbol = split.get("Symbol")
            
            result = find_earliest_announcement(reverse_sa_id)
            
            if result.get("error"):
                skipped_count_phase2 += 1
                continue
            
            announcement_date = result.get("announcement_date")
            best_filing = result.get("best_filing")
            
            if announcement_date:
                # Update reverse_sa with earliest announcement data
                update_fields = {
                    "earliest_announcement_date": announcement_date
                }
                
                if best_filing:
                    update_fields["earliest_announcement_source"] = best_filing.get("accession")
                    update_fields["earliest_announcement_score"] = best_filing.get("score")
                    update_fields["earliest_announcement_tier"] = best_filing.get("tier")
                    update_fields["earliest_announcement_form"] = best_filing.get("form")
                
                reverse_collection.update_one(
                    {"_id": split["_id"]},
                    {"$set": update_fields}
                )
                updated_count += 1
            else:
                skipped_count_phase2 += 1
        
        print(f"\n✓ Batch {batch_num} Phase 2 Complete:")
        print(f"  Updated: {updated_count} reverse_sa documents with earliest announcement dates")
        print(f"  Skipped: {skipped_count_phase2} (no announcement found)")
        
        skip_count += len(all_splits)
        batch_num += 1
        
        print(f"\n{'=' * 70}")
        print(f"BATCH {batch_num - 1} COMPLETE")
        print(f"Total splits processed so far: {skip_count}/{total_count}")
        print(f"{'=' * 70}\n")
        
        if skip_count >= total_count:
            break
    
    client.close()
    
    # Final summary
    print("\n" + "=" * 70)
    print("ALL BATCHES COMPLETE - GENERATING FINAL SUMMARY")
    print("=" * 70)
    
    summary = generate_summary_table(limit=None)
    print_summary_table(summary)
    
    print("\n" + "=" * 70)
    print("ALL BATCHES COMPLETE!")
    print("=" * 70)

if __name__ == "__main__":
    batch_process_all()

