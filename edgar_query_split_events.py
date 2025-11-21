"""
EDGAR Query System for Stock Split Events
Processes a sample of reverse splits from MongoDB and enriches with EDGAR filings.
"""

import requests
import re
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from pymongo import MongoClient
import time
from bs4 import BeautifulSoup
import os

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://RS:01SDcSCdulMJREai@cluster0.wauawr1.mongodb.net/?appName=Cluster0")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"
EDGAR_COLLECTION = "edgar_events"

# SEC API Configuration
SEC_BASE_URL = "https://data.sec.gov"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Rate limiting: 5-10 req/sec max
REQUEST_DELAY = 0.2  # 200ms = ~5 req/sec
HEADERS = {
    "User-Agent": "Split Strategy Analysis contact@splitstrategy.com",
    "Accept": "application/json"
}

# Forms to include
TARGET_FORMS = ["8-K", "6-K", "DEF 14A", "PRE 14A", "DEFA14A", "14C", "PRE 14C", 
                "S-3", "S-1", "424B5", "424B3", "FWP"]
CONTEXT_FORMS = ["10-Q", "10-K", "20-F"]

# Items to highlight
TARGET_ITEMS = ["3.01", "5.03", "8.01", "1.01", "3.02"]


def get_cik_mapping() -> Dict[str, str]:
    """Fetch and cache CIK mapping from SEC"""
    try:
        response = requests.get(COMPANY_TICKERS_URL, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        # Convert to ticker -> CIK mapping
        mapping = {}
        for entry in data.values():
            ticker = entry.get("ticker", "").upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            if ticker and cik:
                mapping[ticker] = cik
        
        return mapping
    except Exception as e:
        print(f"Error fetching CIK mapping: {e}")
        return {}


def normalize_cik(cik: str) -> str:
    """Normalize CIK to 10 digits"""
    return str(cik).strip().zfill(10)


def get_company_filings(cik: str) -> Optional[Dict]:
    """Fetch recent filings for a CIK"""
    cik_normalized = normalize_cik(cik)
    url = f"{SEC_BASE_URL}/submissions/CIK{cik_normalized}.json"
    
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching filings for CIK {cik_normalized}: {e}")
        return None


def parse_date(date_str: str) -> Optional[str]:
    """Parse date string to YYYY-MM-DD format"""
    if not date_str:
        return None
    
    try:
        # Try MM/DD/YYYY format
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        try:
            # Try other formats
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d")
        except:
            return None


def get_date_window(split_date_str: Optional[str]) -> tuple:
    """Calculate EDGAR query window: [T-180d, T+15d] or [today-365d, today]"""
    if split_date_str:
        split_date = parse_date(split_date_str)
        if split_date:
            try:
                split_dt = datetime.strptime(split_date, "%Y-%m-%d")
                start = (split_dt - timedelta(days=180)).strftime("%Y-%m-%d")
                end = (split_dt + timedelta(days=15)).strftime("%Y-%m-%d")
                return start, end
            except:
                pass
    
    # Fallback: last 365 days
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    return start, end


def filter_filings_by_window(filings: Dict, start_date: str, end_date: str) -> List[Dict]:
    """Filter filings by date window and form type"""
    if not filings or "filings" not in filings:
        return []
    
    recent = filings.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    
    filtered = []
    for i, form in enumerate(forms):
        if i >= len(filing_dates):
            break
        
        filing_date = filing_dates[i]
        if not filing_date or filing_date < start_date or filing_date > end_date:
            continue
        
        if form in TARGET_FORMS or form in CONTEXT_FORMS:
            filtered.append({
                "form": form,
                "filingDate": filing_date,
                "accessionNumber": accessions[i] if i < len(accessions) else None,
                "primaryDocument": primary_docs[i] if i < len(primary_docs) else None
            })
    
    return filtered


def download_filing_text(cik: str, accession: str, primary_doc: str) -> Optional[str]:
    """Download and return filing text"""
    cik_normalized = normalize_cik(cik)
    accession_clean = accession.replace("-", "")
    url = f"{SEC_ARCHIVES_URL}/{cik_normalized}/{accession_clean}/{primary_doc}"
    
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error downloading filing {accession}: {e}")
        return None


def extract_reverse_split_ratio(text: str) -> Optional[Dict]:
    """Extract reverse split ratio from text"""
    if not text:
        return None
    
    # Pattern: "1-for-20", "1 for 20", "1/20", "1 : 20"
    patterns = [
        r"(\d+)\s*[-/]\s*for\s*[-/]\s*(\d+)",
        r"(\d+)\s+for\s+(\d+)",
        r"(\d+)\s*:\s*(\d+)",
        r"(\d+)\s*/\s*(\d+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            den = int(match.group(2))
            if num > 0 and den > num:  # Reverse split, ensure num > 0
                return {
                    "ratio_num": num,
                    "ratio_den": den,
                    "log_ratio": math.log(den / num),
                    "ratio_text": match.group(0)
                }
    
    return None


def extract_announcement_date(text: str, filing_date: str) -> Optional[str]:
    """Extract announcement date from 'On <Month DD, YYYY>' pattern"""
    pattern = r"On\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})"
    match = re.search(pattern, text)
    if match:
        try:
            date_str = match.group(1)
            dt = datetime.strptime(date_str, "%B %d, %Y")
            announce_date = dt.strftime("%Y-%m-%d")
            # Ensure announcement date <= filing date
            if announce_date <= filing_date:
                return announce_date
        except:
            pass
    
    return None


def extract_effective_date(text: str) -> Optional[Dict]:
    """Extract effective date and time from text"""
    patterns = [
        r"effective\s+at\s+12:01\s*a\.?m\.?\s+on\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        r"effective\s+on\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        r"effective\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(1)
                dt = datetime.strptime(date_str, "%B %d, %Y")
                effective_date = dt.strftime("%Y-%m-%d")
                effective_time = "12:01 a.m." if "12:01" in match.group(0) else None
                return {
                    "effective_date": effective_date,
                    "effective_time_text": effective_time
                }
            except:
                pass
    
    return None


def check_compliance_flag(text: str) -> bool:
    """Check if compliance-related keywords are present"""
    keywords = [
        r"regain\s+compliance",
        r"maintain\s+compliance",
        r"minimum\s+bid",
        r"deficiency\s+notice",
        r"\bNasdaq\b",
        r"\bNYSE\b"
    ]
    
    for pattern in keywords:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def check_financing_flag(text: str) -> bool:
    """Check if financing-related keywords are present"""
    keywords = [
        r"registered\s+direct",
        r"at-the-market",
        r"\bATM\b",
        r"\bS-3\b",
        r"\b424B5\b",
        r"\b424B3\b",
        r"\bwarrant\b",
        r"securities\s+purchase\s+agreement"
    ]
    
    for pattern in keywords:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def check_unregistered_sales_flag(text: str, items: List[str]) -> bool:
    """Check if unregistered sales are mentioned"""
    if "3.02" in items:
        return True
    
    # Check for "unregistered" and "sale" in proximity
    unreg_match = re.search(r"unregistered", text, re.IGNORECASE)
    sale_match = re.search(r"sales?", text, re.IGNORECASE)
    
    if unreg_match and sale_match:
        # Check if within 200 characters
        pos1 = unreg_match.start()
        pos2 = sale_match.start()
        if abs(pos1 - pos2) < 200:
            return True
    
    return False


def check_rounding_up_flag(text: str) -> bool:
    """Check if fractional shares are rounded UP (not just rounded)"""
    # Patterns that specifically indicate rounding UP
    rounding_up_patterns = [
        r"rounded\s+up",
        r"round\s+up",
        r"rounding\s+up",
        r"rounded\s+upward",
        r"rounds\s+up",
        r"rounding\s+upward"
    ]
    
    # Context keywords that should be nearby (fractional shares, split context)
    context_keywords = [
        r"fractional\s+shares?",
        r"fractional\s+share",
        r"treatment\s+of\s+fractional",
        r"adjustments?\s+resulting\s+from",
        r"reverse\s+split",
        r"stock\s+split",
        r"split\s+adjustment"
    ]
    
    # Check for rounding up patterns
    for pattern in rounding_up_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Check if context keywords are nearby (within 300 characters)
            match_pos = match.start()
            context_found = False
            
            for context_pattern in context_keywords:
                context_match = re.search(context_pattern, text, re.IGNORECASE)
                if context_match:
                    # Check proximity
                    if abs(match_pos - context_match.start()) < 300:
                        context_found = True
                        break
            
            # If context found, or if "fractional" appears in the same sentence
            if context_found:
                return True
            
            # Also check if "fractional" appears within 100 chars of rounding up
            fractional_match = re.search(r"fractional", text[match_pos-100:match_pos+100], re.IGNORECASE)
            if fractional_match:
                return True
    
    return False


def check_items(text: str, form: str) -> List[str]:
    """Extract relevant items from filing"""
    items_found = []
    for item in TARGET_ITEMS:
        # More flexible patterns to catch various formats:
        # "Item 3.01", "ITEM 3.01", "Item 3.01.", "Item 3.01 -", etc.
        patterns = [
            rf"Item\s+{re.escape(item)}\b",  # "Item 3.01"
            rf"ITEM\s+{re.escape(item)}\b",   # "ITEM 3.01"
            rf"Item\s+{re.escape(item)}\.",   # "Item 3.01."
            rf"Item\s+{re.escape(item)}\s*-", # "Item 3.01 -"
            rf"Item\s+{re.escape(item)}\s+:", # "Item 3.01:"
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if item not in items_found:
                    items_found.append(item)
                break  # Found this item, move to next
    
    return items_found


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
    
    # Parse HTML if needed
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
    
    # Build result (removed redundant fields that come from reverse_sa join)
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
        "last_updated": datetime.now(timezone.utc)
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
    
    # Print detailed results
    print("\n" + "=" * 70)
    print("DETAILED RESULTS")
    print("=" * 70)
    
    for i, result in enumerate(all_results, 1):
        print(f"\n[{i}] {result['form']} - {result['filing_date']}")
        print(f"    CIK: {result['cik']}")
        print(f"    Accession: {result['accession']}")
        print(f"    URL: {result['document_url']}")
        
        if 'announce_date' in result:
            print(f"    Announce Date: {result['announce_date']}")
        if 'effective_date' in result:
            print(f"    Effective Date: {result['effective_date']}")
            if 'effective_time_text' in result:
                print(f"    Effective Time: {result['effective_time_text']}")
        
        if 'ratio_num' in result:
            print(f"    Split Ratio: {result['ratio_num']} : {result['ratio_den']} (log: {result['log_ratio']:.4f})")
        
        flags = result.get('flags', {})
        active_flags = [k for k, v in flags.items() if v]
        if active_flags:
            print(f"    Flags: {', '.join(active_flags)}")
        
        if result.get('items'):
            print(f"    Items: {', '.join(result['items'])}")
        
        if result.get('text_matches'):
            print(f"    Text Matches:")
            for key, value in result['text_matches'].items():
                print(f"      {key}: {value[:150]}...")
        
        if result.get('reverse_sa_id'):
            print(f"    Reverse SA ID: {result['reverse_sa_id']}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total filings processed: {len(all_results)}")
    print(f"Symbols processed: {len(splits)}")
    
    # Count by form type
    form_counts = {}
    for result in all_results:
        form = result['form']
        form_counts[form] = form_counts.get(form, 0) + 1
    
    print(f"\nFilings by form type:")
    for form, count in sorted(form_counts.items()):
        print(f"  {form}: {count}")
    
    # Count flags
    flag_counts = {
        "compliance_flag": 0,
        "financing_flag": 0,
        "unregistered_sales_flag": 0,
        "rounding_up_flag": 0,
        "share_change_flag": 0,
        "listing_deficiency_flag": 0
    }
    for result in all_results:
        for flag in flag_counts.keys():
            if result.get('flags', {}).get(flag):
                flag_counts[flag] += 1
    
    print(f"\nFlag counts:")
    for flag, count in flag_counts.items():
        if count > 0:
            print(f"  {flag}: {count}")
    
    print("=" * 70)
    
    # Print sample JSON for reference
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

