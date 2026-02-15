"""
EDGAR Query System for Stock Split Events
Processes a sample of reverse splits from MongoDB and enriches with EDGAR filings.
"""

import os
import json
import re
from datetime import datetime
from typing import Optional, List, Dict
from pymongo import MongoClient

# Import shared modules
from edgar_scraping.edgar_utils import (
    SEC_ARCHIVES_URL,
    get_cik_mapping,
    normalize_cik,
    get_company_filings,
    get_date_window,
    filter_filings_by_window,
    download_filing_text,
    extract_reverse_split_ratio,
    extract_announcement_date,
    extract_effective_date,
    check_compliance_flag,
    check_financing_flag,
    check_unregistered_sales_flag,
    check_rounding_up_flag,
    check_items
)

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is required. Please set it in your .env file or environment.")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"
EDGAR_COLLECTION = "edgar_events"


def parse_filing(cik: str, ticker: str, filing: Dict, split_date: Optional[str]) -> Optional[Dict]:
    """Parse a single filing and extract relevant information"""
    form = filing.get("form")
    filing_date = filing.get("filingDate")
    accession = filing.get("accessionNumber")
    primary_doc = filing.get("primaryDocument")
    
    if not accession or not primary_doc:
        return None
    
    # Download filing text
    text = download_filing_text(cik, accession, primary_doc)
    if not text:
        return None
    
    # Parse HTML not strictly needed if we regex raw text, but soup extracts clean text
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, 'html.parser')
    text_content = soup.get_text()
    
    # Extract items
    items = check_items(text_content, form)
    
    # Extract ratio
    ratio_data = extract_reverse_split_ratio(text_content)
    
    # Extract dates
    announce_date = extract_announcement_date(text_content, filing_date)
    effective_data = extract_effective_date(text_content)
    
    # Check flags
    compliance_flag = check_compliance_flag(text_content)
    financing_flag = check_financing_flag(text_content)
    unregistered_sales_flag = check_unregistered_sales_flag(text_content, items)
    rounding_up_flag = check_rounding_up_flag(text_content)
    share_change_flag = "3.02" in items
    listing_deficiency_flag = "3.01" in items
    
    # Build result
    result = {
        "cik": normalize_cik(cik),
        "form": form,
        "filing_date": filing_date,
        "accession": accession,
        "document_url": f"{SEC_ARCHIVES_URL}/{normalize_cik(cik)}/{accession.replace('-', '')}/{primary_doc}",
        "flags": {
            "compliance_flag": compliance_flag,
            "financing_flag": financing_flag,
            "unregistered_sales_flag": unregistered_sales_flag,
            "rounding_up_flag": rounding_up_flag,
            "share_change_flag": share_change_flag,
            "listing_deficiency_flag": listing_deficiency_flag
        },
        "items": items,
        "last_updated": datetime.utcnow()
    }
    
    # Add optional fields
    if announce_date:
        result["announce_date"] = announce_date
    else:
        result["announce_date"] = filing_date
    
    if effective_data:
        result["effective_date"] = effective_data.get("effective_date")
        if effective_data.get("effective_time_text"):
            result["effective_time_text"] = effective_data["effective_time_text"]
    
    if ratio_data:
        result.update({
            "ratio_num": ratio_data["ratio_num"],
            "ratio_den": ratio_data["ratio_den"],
            "log_ratio": round(ratio_data["log_ratio"], 4)
        })
        result["text_matches"] = {
            "ratio_text": ratio_data["ratio_text"][:200]
        }
    
    # Add text snippets
    text_matches = result.get("text_matches", {})
    if compliance_flag:
        match = re.search(r".{0,100}(regain|maintain|minimum bid|deficiency|Nasdaq|NYSE).{0,100}", 
                        text_content, re.IGNORECASE)
        if match:
            text_matches["compliance_text"] = match.group(0)[:200]
    if financing_flag:
        match = re.search(r".{0,100}(registered direct|ATM|S-3|424B5|warrant).{0,100}", 
                        text_content, re.IGNORECASE)
        if match:
            text_matches["financing_text"] = match.group(0)[:200]
    if rounding_up_flag:
        match = re.search(r".{0,150}(rounded\s+up|round\s+up|rounding\s+up).{0,150}", 
                        text_content, re.IGNORECASE)
        if match:
            text_matches["rounding_text"] = match.group(0)[:200]
    result["text_matches"] = text_matches
    
    return result


def edgar_enrich_split_event(symbol: str, split_effective_date: Optional[str]) -> List[Dict]:
    """Main function: enrich a split event with EDGAR filings"""
    # Get CIK mapping
    cik_mapping = get_cik_mapping()
    cik = cik_mapping.get(symbol.upper())
    
    if not cik:
        print(f"No CIK found for symbol {symbol}")
        return []
    
    # Get date window
    start_date, end_date = get_date_window(split_effective_date)
    print(f"  Querying EDGAR for {symbol} (CIK: {cik}) from {start_date} to {end_date}")
    
    # Fetch company filings
    filings_data = get_company_filings(cik)
    if not filings_data:
        return []
    
    # Filter filings
    filtered_filings = filter_filings_by_window(filings_data, start_date, end_date)
    print(f"  Found {len(filtered_filings)} relevant filings")
    
    # Parse each filing
    results = []
    for filing in filtered_filings[:10]:  # Limit to 10 filings per symbol
        parsed = parse_filing(cik, symbol, filing, split_effective_date)
        if parsed:
            results.append(parsed)
    
    return results


def get_sample_splits() -> List[Dict]:
    """Get sample of 5-10 reverse splits from MongoDB (prioritize 2025)"""
    try:
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DATABASE]
        collection = db[REVERSE_COLLECTION]
        
        # Get 2025 splits first (dates ending in /2025)
        results_2025 = list(collection.find({"Date": {"$regex": "/2025$"}}).limit(5))
        
        if len(results_2025) < 5:
            # Get more from other dates to reach 10 total
            results_other = list(collection.find().limit(10 - len(results_2025)))
            results_2025.extend(results_other)
        
        client.close()
        return results_2025[:10]
    except Exception as e:
        print(f"Error fetching from MongoDB: {e}")
        return []


def main():
    """Main execution: process sample splits"""
    print("=" * 70)
    print("EDGAR Query System - Sample Processing")
    print("=" * 70)
    
    # Get sample splits
    splits = get_sample_splits()
    print(f"\nProcessing {len(splits)} sample reverse splits...\n")
    
    all_results = []
    
    for split in splits:
        symbol = split.get("Symbol", "")
        split_date = split.get("Date", "")
        split_ratio = split.get("Split Ratio", "")
        
        print(f"\nProcessing: {symbol} - Split: {split_ratio} on {split_date}")
        
        # Query EDGAR
        edgar_results = edgar_enrich_split_event(symbol, split_date)
        
        # Get reverse_sa document ID for O(1) lookup
        reverse_sa_id = split.get("_id")
        
        for result in edgar_results:
            result["reverse_sa_id"] = str(reverse_sa_id)  # Add reference for O(1) lookup
            all_results.append(result)
            print(f"  ✓ Found {result['form']} filing on {result['filing_date']}")
    
    # Save to MongoDB
    if all_results:
        try:
            client = MongoClient(MONGODB_URI)
            db = client[MONGODB_DATABASE]
            collection = db[EDGAR_COLLECTION]
            
            inserted = 0
            for result in all_results:
                # Upsert based on accession number
                filter_query = {"accession": result["accession"]}
                collection.update_one(filter_query, {"$set": result}, upsert=True)
                inserted += 1
            
            # Create indexes for O(1) lookups from reverse_sa
            try:
                collection.create_index([("reverse_sa_id", 1)])
                collection.create_index([("cik", 1), ("filing_date", -1)])
                collection.create_index([("filing_date", -1)])
                print(f"  ✓ Created indexes for efficient lookups")
            except Exception as idx_error:
                print(f"  ⚠ Index creation note: {idx_error}")
            
            print(f"\n✓ Saved {inserted} EDGAR events to MongoDB ({EDGAR_COLLECTION})")
            client.close()
        except Exception as e:
            print(f"\n✗ Error saving to MongoDB: {e}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total filings processed: {len(all_results)}")
    
    if all_results:
        print("\n" + "=" * 70)
        print("SAMPLE JSON (First Filing)")
        print("=" * 70)
        # Convert datetime to ISO string for JSON serialization
        sample_result = all_results[0].copy()
        if 'last_updated' in sample_result:
            sample_result['last_updated'] = sample_result['last_updated'].isoformat()
        print(json.dumps(sample_result, indent=2, default=str))


if __name__ == "__main__":
    main()

