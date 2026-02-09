"""
Early EDGAR Scanner for Confirmed Reverse Splits
Scans daily SEC filings for DEFINITIVE reverse split announcements.

Focuses on:
1. 8-K (Items 5.03, 8.01) and 6-K filings
2. Extensive keyword search for "Reverse Split", "Consolidation", "Ratio"
3. LLM Integration (OpenAI) to extract:
   - Effective Date
   - Ratio
   - Rounding Information (Crucial)
   - Summary of the announcement

Output: Saves confirmed splits to 'early_edgar_splits' collection in MongoDB.
"""

import os
import requests
import re
import time
import json
import argparse
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from typing import List, Dict, Optional

import sys

# Add parent directory to path to find load_env.py and edgar_utils.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
try:
    import load_env
except ImportError:
    pass

# Import shared modules
try:
    from edgar_scraping.edgar_utils import (
        HEADERS,
        SEC_ARCHIVES_URL,
        download_filing_text,
        check_items,
        normalize_cik,
        get_cik_mapping
    )
    from edgar_scraping.globals import SPLIT_KEYWORDS, get_analysis_prompt
except ImportError:
    # Fallback if running from within the folder or different context
    try:
        from edgar_utils import (
            HEADERS,
            SEC_ARCHIVES_URL,
            download_filing_text,
            check_items,
            normalize_cik,
            get_cik_mapping
        )
        from globals import SPLIT_KEYWORDS, get_analysis_prompt
    except ImportError:
         print("Warning: Could not import edgar_utils or globals. Make sure you are running from the project root.")

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    print("Warning: MONGODB_URI not set. DB operations will fail.")
MONGODB_DATABASE = "split_strategy"
EARLY_EDGAR_COLLECTION = "early_edgar_splits"

# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Target Forms
TARGET_FORMS_SCAN = ["8-K", "6-K", "8-K/A", "6-K/A"]

def get_daily_index_url(date_obj: datetime) -> str:
    """Construct URL for daily index file"""
    year = date_obj.year
    qtr = (date_obj.month - 1) // 3 + 1
    date_str = date_obj.strftime("%Y%m%d")
    return f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{qtr}/company.{date_str}.idx"

def parse_idx_line(line: str) -> Optional[Dict]:
    """Parse a fixed-width line from company.YYYYMMDD.idx"""
    parts = re.split(r'\s{2,}', line.strip())
    if len(parts) < 5:
        return None
    
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
    """Download and parse daily index"""
    url = get_daily_index_url(date_obj)
    print(f"Fetching Daily Index: {url}")
    
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 404:
            print("  No index found (weekend/holiday?)")
            return []
        response.raise_for_status()
        
        lines = response.text.splitlines()
        filings = []
        
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
        print(f"Error fetching index: {e}")
        return []

def check_keywords_extensive(text: str) -> bool:
    """Check for any split-related keywords"""
    for pattern in SPLIT_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def analyze_with_llm(text: str, company: str, filing_date: str) -> Dict:
    """Use OpenAI to analyze the filing text"""
    if not OPENAI_API_KEY:
        return {"summary": "LLM API Key missing", "confidence": "Low", "rounding_up": None, "effective_date": "Unknown", "ratio": "Unknown"}
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Truncate text to avoid token limits.
        # Strategy: find keyword matches and take context.
        matches = []
        for pattern in SPLIT_KEYWORDS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                start = max(0, m.start() - 1000)
                end = min(len(text), m.end() + 1000)
                matches.append(text[start:end])
                if len(matches) > 3: break 
        
        context = "\n...\n".join(matches) if matches else text[:5000]

        prompt = get_analysis_prompt(company, context, filing_date)
        
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)
        
    except Exception as e:
        print(f"LLM Error: {e}")
        return {"summary": f"Error analyzing: {str(e)}", "confidence": "Error"}

def process_filing(filing: Dict) -> Optional[Dict]:
    """Analyze a single filing"""
    full_url = f"https://www.sec.gov/Archives/{filing['filename']}"
    
    try:
        time.sleep(0.1)
        resp = requests.get(full_url, headers=HEADERS)
        resp.raise_for_status()
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        
        # 1. Quick Keyword Filter
        if not check_keywords_extensive(text):
            return None
            
        print(f"  > Keyword match found for {filing['company_name']}!")
        
        # 2. LLM Analysis
        analysis = analyze_with_llm(text, filing['company_name'], filing['date_filed'])
        
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

CACHE_CIK_TO_TICKER = {}

def load_ticker_mapping():
    try:
        from edgar_scraping.edgar_utils import get_cik_mapping
    except ImportError:
        try:
             from edgar_utils import get_cik_mapping
        except:
             return 

    mapping = get_cik_mapping() 
    for ticker, cik in mapping.items():
        CACHE_CIK_TO_TICKER[cik] = ticker
        CACHE_CIK_TO_TICKER[str(int(cik))] = ticker

def resolve_ticker(cik: str) -> str:
    normalized_cik = str(int(cik))
    return CACHE_CIK_TO_TICKER.get(normalized_cik, "UNKNOWN")

def main():
    parser = argparse.ArgumentParser(description="Early Edgar Scanner")
    parser.add_argument("date", nargs="?", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    target_date = datetime.strptime(args.date, "%Y-%m-%d")
    print(f"Starting Early Edgar Scan for {target_date.strftime('%Y-%m-%d')}...")
    
    load_ticker_mapping()
    filings = fetch_daily_filings(target_date)
    print(f"Found {len(filings)} filings (8-K/6-K)")
    
    hits = []
    
    # Process
    if MONGODB_URI:
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DATABASE]
        collection = db[EARLY_EDGAR_COLLECTION]
    
    for i, filing in enumerate(filings):
        print(f"Scanning {i+1}/{len(filings)}: {filing['company_name']}...", end="\r")
        hit = process_filing(filing)
        if hit:
            hit['ticker'] = resolve_ticker(hit['cik'])
            hits.append(hit)
            
            # Save immediately
            if MONGODB_URI:
                query = {"cik": hit["cik"], "filing_date": hit["filing_date"]}
                collection.update_one(query, {"$set": hit}, upsert=True)
                print(f"[SAVED] {hit['ticker']} - {hit['summary']}")
    
    print(f"\nScan Complete. Found {len(hits)} confirmed splits.")

if __name__ == "__main__":
    main()
