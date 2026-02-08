"""
Early Warning Scanner for Reverse Splits
Scans daily SEC filings for:
1. 8-K Item 3.01 (Deficiency Notices/Delisting Warnings)
2. PRE 14A / DEF 14A (Reverse Split Proposals)

Output: Saves potential splits to 'prospective_splits' collection in MongoDB.
"""

import os
import requests
import re
import time
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from typing import List, Dict, Optional

# Load environment variables
try:
    import load_env
except ImportError:
    pass

# Import shared modules
from .edgar_utils import (
    HEADERS,
    SEC_ARCHIVES_URL,
    download_filing_text,
    check_items,
    check_compliance_flag,
    check_split_proposal_flag,
    normalize_cik,
    get_cik_mapping
)

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    # Optional: Log warning instead of raising error to allow importing as module without ENV
    print("Warning: MONGODB_URI not set. DB operations will fail.")
MONGODB_DATABASE = "split_strategy"
PROSPECTIVE_COLLECTION = "prospective_splits"

# Target Forms
TARGET_FORMS_SCAN = ["8-K", "PRE 14A", "DEF 14A", "DEFA14A"]

def get_daily_index_url(date_obj: datetime) -> str:
    """Construct URL for daily index file (quarterly structure)"""
    year = date_obj.year
    qtr = (date_obj.month - 1) // 3 + 1
    date_str = date_obj.strftime("%Y%m%d")
    # URL format: https://www.sec.gov/Archives/edgar/daily-index/2024/QTR2/company.20240531.idx
    return f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{qtr}/company.{date_str}.idx"

def parse_idx_line(line: str) -> Optional[Dict]:
    """Parse a fixed-width line from company.YYYYMMDD.idx"""
    
    parts = re.split(r'\s{2,}', line.strip())
    if len(parts) < 5:
        return None
        
    # Last part is filename (edgar/data/...)
    filename = parts[-1]
    date_str = parts[-2]
    cik = parts[-3]
    form_type = parts[-4]
    company_name = " ".join(parts[:-4])
    
    return {
        "company_name": company_name,
        "form": form_type,
        "cik": cik,
        "date_filed": date_str,
        "filename": filename
    }

def fetch_daily_filings(date_obj: datetime) -> List[Dict]:
    """Download and parse proper daily index to get list of filings"""
    url = get_daily_index_url(date_obj)
    print(f"Fetching Daily Index: {url}")
    
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 404:
            print("  No index found for this date (weekend/holiday?)")
            return []
        response.raise_for_status()
        
        lines = response.text.splitlines()
        filings = []
        
        # Skip header lines (usually top 10 lines)
        start_parsing = False
        for line in lines:
            if "---" in line:
                start_parsing = True
                continue
            if not start_parsing:
                continue
                
            entry = parse_idx_line(line)
            if entry and entry["form"] in TARGET_FORMS_SCAN:
                filings.append(entry)
                
        return filings
        
    except Exception as e:
        print(f"Error fetching daily index: {e}")
        return []

def resolve_ticker(client, cik: str) -> str:
    """
    Resolve CIK to Ticker.
    Priority:
    1. Local Cache (CACHE_CIK_TO_TICKER)
    2. MongoDB 'companies' collection (if available) - passed via 'client' arg
    3. Return 'UNKNOWN' if not found
    """
    if not cik:
        return "UNKNOWN"
        
    # 1. Check Local Cache
    normalized_cik = str(int(cik)) # Remove leading zeros
    zero_padded_cik = cik.zfill(10)
    
    ticker = CACHE_CIK_TO_TICKER.get(zero_padded_cik)
    if not ticker:
        ticker = CACHE_CIK_TO_TICKER.get(normalized_cik)
        
    if ticker:
        return ticker
    
    return "UNKNOWN"

def process_filing(filing: Dict) -> Optional[Dict]:
    """Analyze a single filing for early warning signals"""
    form = filing["form"]
    cik = filing["cik"]
    filename = filing["filename"] # e.g. edgar/data/100000/000000-00-000000.txt
    
    # Construct accession and primary_doc (simplified from filename)
    # The IDX file gives the full path to the .txt file which includes the text content
    # edgar_utils.download_filing_text expects (cik, accession, primary_doc)
    
    full_url = f"https://www.sec.gov/Archives/{filename}"
    
    try:
        # Rate limit
        time.sleep(0.1) 
        resp = requests.get(full_url, headers=HEADERS)
        resp.raise_for_status()
        
        # Clean HTML to text
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        
        signal_found = False
        signal_type = None
        signal_details = {}
        
        # Check for Deficiency Notice (8-K Item 3.01)
        if form == "8-K":
            items = check_items(text, form)
            if "3.01" in items:
                # Confirm it's about price/deficiency
                if check_compliance_flag(text):
                    signal_found = True
                    signal_type = "deficiency_notice"
                    signal_details = {"symptom": "Item 3.01 + Compliance Keywords"}
        
        # Check for Split Proposal (14A)
        elif "14A" in form:
             if check_split_proposal_flag(text):
                 signal_found = True
                 signal_type = "proposal"
                 signal_details = {"symptom": "Reverse Split Proposal Keywords"}
        
        if signal_found:
            return {
                "ticker": "UNKNOWN", # Will be resolved later
                "cik": normalize_cik(cik),
                "company_name": filing["company_name"],
                "fililing_date": filing["date_filed"],
                "form": form,
                "signal_type": signal_type,
                "filing_url": full_url,
                "status": "monitoring",
                "details": signal_details,
                "found_at": datetime.now(timezone.utc)
            }
            
    except Exception as e:
        print(f"Error processing {filename}: {e}")
    
    return None

CACHE_CIK_TO_TICKER = {}

def load_ticker_mapping():
    """Build ticker mapping from SEC data"""
    # Use relative import for edgar_utils
    try:
        # If running as script
        from edgar_scraping.edgar_utils import get_cik_mapping
    except ImportError:
         # If running from inside package
        from .edgar_utils import get_cik_mapping
        
    mapping = get_cik_mapping() 
    for ticker, cik in mapping.items():
        CACHE_CIK_TO_TICKER[cik] = ticker
        # Also handle non-zero-padded lookup
        CACHE_CIK_TO_TICKER[str(int(cik))] = ticker

def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Scan Early Warnings from EDGAR Daily Index")
    parser.add_argument("date", nargs="?", help="Date to scan (YYYY-MM-DD)", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--cik", help="Filter by specific CIK (for testing)")
    args = parser.parse_args()
    
    target_date = datetime.strptime(args.date, "%Y-%m-%d")
        
    print(f"Starting Scan for {target_date.strftime('%Y-%m-%d')}...")
    if args.cik:
        print(f"Filtering for CIK: {args.cik}")
    
    # Load tickers
    print("Loading Ticker Mapping...")
    load_ticker_mapping()
    
    # Fetch Filings
    filings = fetch_daily_filings(target_date)
    print(f"Found {len(filings)} candidate filings ({', '.join(TARGET_FORMS_SCAN)})")
    
    hits = []
    
    # Filter if requested
    if args.cik:
        target_cik = str(int(args.cik)) # normalize to integer string
        filings = [f for f in filings if str(int(f['cik'])) == target_cik]
        print(f"Filtered to {len(filings)} filings for CIK {args.cik}")
    
    client = None
    if MONGODB_URI:
         client = MongoClient(MONGODB_URI)

    for i, filing in enumerate(filings):
        print(f"Checking {i+1}/{len(filings)}: {filing['company_name']} ({filing['form']})...", end="\r")
        hit = process_filing(filing)
        if hit:
            # Resolve Ticker
            ticker = resolve_ticker(client, hit['cik'])
            hit['ticker'] = ticker
            
            hits.append(hit)
            print(f"\n[HIT] {ticker} - {hit['signal_type']} ({hit['form']})")
    
    print(f"\n\nScan Complete. Found {len(hits)} prospective splits.")
    
    # Save to MongoDB
    if hits:
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DATABASE]
        collection = db[PROSPECTIVE_COLLECTION]
        
        inserted = 0
        for h in hits:
            # Duplicate check: same CIK, same Date, same Signal Type
            query = {
                "cik": h["cik"], 
                "fililing_date": h["fililing_date"], 
                "signal_type": h["signal_type"]
            }
            res = collection.update_one(query, {"$set": h}, upsert=True)
            if res.upserted_id:
                inserted += 1
                
        print(f"Saved {inserted} new records to '{PROSPECTIVE_COLLECTION}'")
        client.close()

if __name__ == "__main__":
    main()
