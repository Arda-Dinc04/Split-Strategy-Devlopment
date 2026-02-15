#!/usr/bin/env python3
"""
Early EDGAR Scanner for Confirmed Reverse Splits
Scans daily SEC filings for DEFINITIVE reverse split announcements.
"""

import sys
import os
import argparse
import concurrent.futures
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
current_dir = Path(__file__).resolve().parent
src_path = current_dir.parent / 'src'
sys.path.append(str(src_path))

from pymongo import MongoClient
import requests
from bs4 import BeautifulSoup

from split_strategy.config import MONGODB_URI, MONGODB_DATABASE, OPENAI_API_KEY, HEADERS, SEC_ARCHIVES_URL
from split_strategy.database import get_collection, EARLY_WARNINGS_COLLECTION
from split_strategy.edgar.client import (
    fetch_daily_filings, 
    download_filing_text, 
    get_cik_mapping_with_names
)
from split_strategy.edgar.utils import normalize_cik
from split_strategy.edgar.llm_analysis import analyze_with_llm, check_keywords_extensive


# Target Forms
TARGET_FORMS_SCAN = ["8-K", "6-K", "8-K/A", "6-K/A"]

CACHE_CIK_TO_TICKER = {}

def load_ticker_mapping():
    """Load CIK to Ticker mapping"""
    mappings = get_cik_mapping_with_names()
    ticker_map = mappings.get("ticker", {})
    
    for ticker, cik in ticker_map.items():
        CACHE_CIK_TO_TICKER[cik] = ticker
        CACHE_CIK_TO_TICKER[str(int(cik))] = ticker

def resolve_ticker(cik: str) -> str:
    normalized_cik = str(int(cik))
    return CACHE_CIK_TO_TICKER.get(normalized_cik, "UNKNOWN")

def process_filing(filing: dict) -> dict:
    """Analyze a single filing"""
    full_url = f"https://www.sec.gov/Archives/{filing['filename']}"
    
    try:
        # Rate limiting handled by client/requests usually, but adding small safety here
        time.sleep(0.1) 
        
        # Filings are also on www.sec.gov/Archives
        # We can use requests directly here or client.download_filing_text
        # Since we have the partial filename (e.g. edgar/data/...), we can construct URL
        
        resp = requests.get(full_url, headers=HEADERS)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        
        # 1. Quick Keyword Filter
        if not check_keywords_extensive(text):
            return None
            
        print(f"  > Keyword match found for {filing['company_name']}!")
        
        # 2. LLM Analysis
        analysis = analyze_with_llm(
            text, 
            filing['company_name'], 
            filing['date_filed'],
            openai_api_key=OPENAI_API_KEY
        )
        
        if not analysis.get("is_reverse_split", False):
            print("    LLM says: Not a reverse split.")
            return None
        
        # Filter out past splits based on confidence or explicit logic
        if analysis.get("is_future_split") is False:
             print(f"    LLM says: Past split (is_future_split=False). Skipping.")
             return None

        if analysis.get("confidence") == "Low" and "already effective" in analysis.get("summary", "").lower():
             print("    LLM says: Past split (Low Confidence). Skipping.")
             return None

        print(f"    Confirmed! Date: {analysis.get('effective_date')}, Ratio: {analysis.get('ratio')}")
        
        return {
            "ticker": "UNKNOWN", # Resolved later
            "cik": normalize_cik(filing["cik"]),
            "company_name": filing["company_name"],
            "filing_date": filing["date_filed"],
            "form": filing["form"],
            "filing_url": full_url,
            "effective_date": analysis.get("effective_date"),
            "ratio": analysis.get("ratio"),
            "rounding_up": analysis.get("rounding_up"),
            "summary": analysis.get("summary"),
            "confidence": analysis.get("confidence"),
            "found_at": datetime.now(timezone.utc)
        }

    except Exception as e:
        print(f"Error processing {filing['filename']}: {e}")
    
    return None

def main():
    parser = argparse.ArgumentParser(description="Early Edgar Scanner")
    parser.add_argument("date", nargs="?", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    try:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
        sys.exit(1)
        
    print(f"Starting Early Edgar Scan for {target_date.strftime('%Y-%m-%d')}...")
    
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not found in environment variables.")
        sys.exit(1)
    
    print("Loading ticker mappings...")
    load_ticker_mapping()
    
    filings = fetch_daily_filings(target_date, target_forms=TARGET_FORMS_SCAN)
    print(f"Found {len(filings)} filings ({', '.join(TARGET_FORMS_SCAN)})")
    
    hits = []
    
    # Process
    collection = None
    if MONGODB_URI:
        collection = get_collection(EARLY_WARNINGS_COLLECTION)
    else:
        print("Warning: MONGODB_URI not set. Results will not be saved to DB.")
    
    # Use ThreadPoolExecutor for parallel processing
    # Adjust max_workers as needed, staying mindful of SEC rate limits (10 req/sec)
    # We have 0.1s sleep inside process_filing + request time, so 5-10 workers is safe-ish
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks
        future_to_filing = {executor.submit(process_filing, filing): filing for filing in filings}
        
        count = 0
        total = len(filings)
        
        for future in concurrent.futures.as_completed(future_to_filing):
            count += 1
            filing = future_to_filing[future]
            # Simple progress indicator
            print(f"Scanning {count}/{total}: {filing['company_name']}...      ", end="\r")
            
            try:
                hit = future.result()
                if hit:
                    hit['ticker'] = resolve_ticker(hit['cik'])
                    hits.append(hit)
                    
                    # Save immediately
                    if collection:
                        query = {"cik": hit["cik"], "filing_date": hit["filing_date"]}
                        collection.update_one(query, {"$set": hit}, upsert=True)
                        print(f"\n[SAVED] {hit['ticker']} - {hit['summary']}")
            except Exception as e:
                print(f"\nError processing {filing['company_name']}: {e}")
    
    print(f"\nScan Complete. Found {len(hits)} confirmed splits.")

if __name__ == "__main__":
    main()
