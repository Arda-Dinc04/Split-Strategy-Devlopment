"""
Complete EDGAR Workflow
1. Query EDGAR for all reverse_sa splits
2. Score each filing during parsing
3. Store scored filings in edgar_events
4. Find earliest announcement for each split
5. Update reverse_sa with earliest_announcement_date
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
from bson import ObjectId

# Import scoring functions
from find_earliest_announcement import (
    score_filing, parse_sa_ratio, parse_date, 
    is_year_like_ratio, has_rs_keyword
)

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://RS:01SDcSCdulMJREai@cluster0.wauawr1.mongodb.net/?appName=Cluster0")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"
EDGAR_COLLECTION = "edgar_events"

# SEC API Configuration
SEC_BASE_URL = "https://data.sec.gov"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Rate limiting
REQUEST_DELAY = 0.2
HEADERS = {
    "User-Agent": "Split Strategy Analysis contact@splitstrategy.com",
    "Accept": "application/json"
}

# Forms to include
TARGET_FORMS = ["8-K", "6-K", "DEF 14A", "PRE 14A", "DEFA14A", "14C", "PRE 14C", 
                "S-3", "S-1", "424B5", "424B3", "FWP"]
CONTEXT_FORMS = ["10-Q", "10-K", "20-F"]

TARGET_ITEMS = ["3.01", "5.03", "8.01", "1.01", "3.02"]


def get_cik_mapping() -> Dict[str, str]:
    """Fetch and cache CIK mapping from SEC (ticker -> CIK)"""
    try:
        response = requests.get(COMPANY_TICKERS_URL, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
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


def get_cik_mapping_with_names() -> Dict[str, Dict[str, str]]:
    """Fetch CIK mapping with both ticker and company name lookups"""
    try:
        response = requests.get(COMPANY_TICKERS_URL, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        ticker_mapping = {}
        name_mapping = {}
        
        for entry in data.values():
            ticker = entry.get("ticker", "").upper()
            title = entry.get("title", "").upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            
            if ticker and cik:
                ticker_mapping[ticker] = cik
            
            if title and cik:
                # Store normalized company name -> CIK
                clean_title = title
                for suffix in [" INC", " INC.", " CORPORATION", " CORP", " CORP.", " LLC", " LTD", " LTD.", " COMPANY", " CO", " CO."]:
                    if clean_title.endswith(suffix):
                        clean_title = clean_title[:-len(suffix)].strip()
                if clean_title:
                    name_mapping[clean_title] = cik
        
        return {"ticker": ticker_mapping, "name": name_mapping}
    except Exception as e:
        print(f"Error fetching CIK mapping: {e}")
        return {"ticker": {}, "name": {}}


def search_cik_by_company_name(company_name: str, name_mapping: Dict[str, str] = None) -> Optional[str]:
    """Fallback: Search for CIK by company name"""
    if not company_name:
        return None
    
    # Clean company name
    clean_name = company_name.strip().upper()
    # Remove common suffixes for better matching
    for suffix in [" INC", " INC.", " CORPORATION", " CORP", " CORP.", " LLC", " LTD", " LTD.", " COMPANY", " CO", " CO."]:
        if clean_name.endswith(suffix):
            clean_name = clean_name[:-len(suffix)].strip()
    
    # Try direct lookup if mapping provided
    if name_mapping:
        if clean_name in name_mapping:
            return name_mapping[clean_name]
        # Try partial match
        for mapped_name, cik in name_mapping.items():
            if clean_name in mapped_name or mapped_name in clean_name:
                return cik
    
    return None


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
        print(f"  Error fetching filings for CIK {cik_normalized}: {e}")
        return None


def parse_date(date_str: str) -> Optional[str]:
    """Parse date string to YYYY-MM-DD format"""
    if not date_str:
        return None
    
    try:
        dt = datetime.strptime(date_str.strip(), "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        try:
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
        print(f"    Error downloading filing {accession}: {e}")
        return None


def extract_reverse_split_ratio(text: str) -> Optional[Dict]:
    """Extract reverse split ratio from text"""
    if not text:
        return None
    
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
            if num > 0 and den > num and not is_year_like_ratio(num, den):
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
    
    unreg_match = re.search(r"unregistered", text, re.IGNORECASE)
    sale_match = re.search(r"sales?", text, re.IGNORECASE)
    
    if unreg_match and sale_match:
        pos1 = unreg_match.start()
        pos2 = sale_match.start()
        if abs(pos1 - pos2) < 200:
            return True
    
    return False


def check_rounding_up_flag(text: str) -> bool:
    """Check if fractional shares are rounded UP"""
    rounding_up_patterns = [
        r"rounded\s+up",
        r"round\s+up",
        r"rounding\s+up",
        r"rounded\s+upward",
        r"rounds\s+up",
        r"rounding\s+upward"
    ]
    
    context_keywords = [
        r"fractional\s+shares?",
        r"fractional\s+share",
        r"treatment\s+of\s+fractional",
        r"adjustments?\s+resulting\s+from",
        r"reverse\s+split",
        r"stock\s+split",
        r"split\s+adjustment"
    ]
    
    for pattern in rounding_up_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            match_pos = match.start()
            context_found = False
            
            for context_pattern in context_keywords:
                context_match = re.search(context_pattern, text, re.IGNORECASE)
                if context_match:
                    if abs(match_pos - context_match.start()) < 300:
                        context_found = True
                        break
            
            if context_found:
                return True
            
            fractional_match = re.search(r"fractional", text[match_pos-100:match_pos+100], re.IGNORECASE)
            if fractional_match:
                return True
    
    return False


def check_items(text: str, form: str) -> List[str]:
    """Extract relevant items from filing"""
    items_found = []
    for item in TARGET_ITEMS:
        patterns = [
            rf"Item\s+{re.escape(item)}\b",
            rf"ITEM\s+{re.escape(item)}\b",
            rf"Item\s+{re.escape(item)}\.",
            rf"Item\s+{re.escape(item)}\s*-",
            rf"Item\s+{re.escape(item)}\s+:",
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if item not in items_found:
                    items_found.append(item)
                break
    
    return items_found


def parse_filing_with_scoring(cik: str, ticker: str, filing: Dict, split_date: Optional[str], 
                              sa_ratio: Optional[tuple], sa_effective_date: Optional[datetime]) -> Optional[Dict]:
    """Parse a single filing, extract info, and score it"""
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
    
    # Parse HTML
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
    
    # Build result document
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
    
    # Score the filing
    scoring_result = score_filing(result, sa_ratio, sa_effective_date)
    result["score"] = scoring_result["score"]
    result["tier"] = scoring_result["tier"]
    result["candidate_announce_date"] = scoring_result["candidate_announce_date"]
    
    return result


def check_already_processed(symbol: str, split_date: str) -> bool:
    """Check if this split already has EDGAR filings"""
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    reverse_collection = db[REVERSE_COLLECTION]
    edgar_collection = db[EDGAR_COLLECTION]
    
    # Find reverse_sa document
    reverse_split = reverse_collection.find_one({"Symbol": symbol, "Date": split_date})
    if not reverse_split:
        client.close()
        return False
    
    reverse_sa_id = str(reverse_split["_id"])
    
    # Check if filings exist
    count = edgar_collection.count_documents({"reverse_sa_id": reverse_sa_id})
    
    client.close()
    return count > 0


def process_split_with_edgar(split: Dict, cik_mapping: Dict[str, str], name_mapping: Dict[str, str] = None, skip_existing: bool = True) -> Dict:
    """Process a single reverse split: query EDGAR, parse, score, and store"""
    symbol = split.get("Symbol", "")
    split_date = split.get("Date", "")
    split_ratio_str = split.get("Split Ratio", "")
    company_name = split.get("Company Name", "")
    reverse_sa_id = str(split.get("_id"))
    
    # Skip if already processed
    if skip_existing and check_already_processed(symbol, split_date):
        return {"symbol": symbol, "status": "already_processed", "filings_processed": 0}
    
    print(f"\nProcessing: {symbol} - Split: {split_ratio_str} on {split_date}")
    
    # Get CIK - try ticker first, then company name
    cik = cik_mapping.get(symbol.upper())
    if not cik and name_mapping:
        cik = search_cik_by_company_name(company_name, name_mapping)
        if cik:
            print(f"  ✓ Found CIK via company name: {cik}")
    
    if not cik:
        print(f"  ✗ No CIK found for {symbol} ({company_name})")
        return {"symbol": symbol, "status": "no_cik", "filings_processed": 0}
    
    # Parse SA data for scoring
    sa_ratio = parse_sa_ratio(split_ratio_str)
    sa_effective_date = None
    if split_date:
        sa_date_parsed = parse_date(split_date)
        if sa_date_parsed:
            sa_effective_date = datetime.strptime(sa_date_parsed, "%Y-%m-%d")
    
    # Get date window
    start_date, end_date = get_date_window(split_date)
    print(f"  Querying EDGAR (CIK: {cik}) from {start_date} to {end_date}")
    
    # Fetch company filings
    filings_data = get_company_filings(cik)
    if not filings_data:
        print(f"  ⚠ No filings data returned from SEC for CIK {cik}")
        return {
            "symbol": symbol, 
            "status": "no_filings_data", 
            "filings_processed": 0,
            "cik": cik,
            "company_name": company_name,
            "split_date": split_date,
            "date_window": (start_date, end_date)
        }
    
    # Filter filings
    filtered_filings = filter_filings_by_window(filings_data, start_date, end_date)
    print(f"  Found {len(filtered_filings)} relevant filings")
    
    if len(filtered_filings) == 0:
        # Check how many total filings exist and what forms
        total_filings_count = 0
        forms_in_window = {}
        all_forms = {}
        earliest_filing_date = None
        latest_filing_date = None
        is_historical_split = False
        
        if filings_data and "filings" in filings_data:
            recent = filings_data.get("filings", {}).get("recent", {})
            if recent:
                forms = recent.get("form", [])
                filing_dates = recent.get("filingDate", [])
                total_filings_count = len(forms)
                
                # Get date range of available filings
                if filing_dates:
                    valid_dates = [d for d in filing_dates if d]
                    if valid_dates:
                        earliest_filing_date = min(valid_dates)
                        latest_filing_date = max(valid_dates)
                        
                        # Check if split date is before earliest available filing
                        if split_date:
                            split_date_parsed = parse_date(split_date)
                            if split_date_parsed and split_date_parsed < earliest_filing_date:
                                is_historical_split = True
                
                # Count forms in date window (even if not target forms)
                for i, form in enumerate(forms):
                    if i < len(filing_dates):
                        filing_date = filing_dates[i]
                        if filing_date and start_date <= filing_date <= end_date:
                            forms_in_window[form] = forms_in_window.get(form, 0) + 1
                    
                    # Count all forms
                    if i < len(filing_dates) and filing_dates[i]:
                        all_forms[form] = all_forms.get(form, 0) + 1
        
        reason = "No filings in date window"
        if is_historical_split:
            reason = f"Historical split: SEC API only returns filings from {earliest_filing_date} onwards (split date: {split_date})"
        
        print(f"  ⚠ {reason}")
        print(f"     Date window: [{start_date} to {end_date}]")
        print(f"     Total filings available for CIK: {total_filings_count}")
        if earliest_filing_date and latest_filing_date:
            print(f"     Filing date range available: {earliest_filing_date} to {latest_filing_date}")
        if forms_in_window:
            print(f"     Forms in date window (not matching target forms): {dict(list(forms_in_window.items())[:10])}")
        elif all_forms and not is_historical_split:
            print(f"     All forms (top 10): {dict(list(sorted(all_forms.items(), key=lambda x: x[1], reverse=True)[:10]))}")
        
        return {
            "symbol": symbol,
            "status": "no_filings_in_window",
            "filings_processed": 0,
            "cik": cik,
            "company_name": company_name,
            "split_date": split_date,
            "date_window": (start_date, end_date),
            "total_filings_for_cik": total_filings_count,
            "forms_in_window": forms_in_window,
            "all_forms": all_forms,
            "is_historical_split": is_historical_split,
            "earliest_filing_date": earliest_filing_date,
            "latest_filing_date": latest_filing_date,
            "reason": reason
        }
    
    # Parse and score each filing
    results = []
    for filing in filtered_filings[:10]:  # Limit to 10 filings per symbol
        parsed = parse_filing_with_scoring(cik, symbol, filing, split_date, sa_ratio, sa_effective_date)
        if parsed:
            parsed["reverse_sa_id"] = reverse_sa_id
            results.append(parsed)
            print(f"    ✓ {parsed['form']} on {parsed['filing_date']} - Score: {parsed['score']} (Tier {parsed['tier']})")
    
    # Save to MongoDB
    if results:
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DATABASE]
        collection = db[EDGAR_COLLECTION]
        
        inserted = 0
        for result in results:
            filter_query = {"accession": result["accession"]}
            collection.update_one(filter_query, {"$set": result}, upsert=True)
            inserted += 1
        
        client.close()
        print(f"  ✓ Saved {inserted} scored filings to MongoDB")
    
    return {
        "symbol": symbol,
        "status": "success",
        "filings_processed": len(results)
    }


def batch_find_earliest_announcements(limit: int = None):
    """Phase 2: Find earliest announcement for reverse_sa splits"""
    from find_earliest_announcement import find_earliest_announcement
    
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    reverse_collection = db[REVERSE_COLLECTION]
    
    print("\n" + "=" * 70)
    print("PHASE 2: Finding Earliest Announcements" + (f" (Limited to {limit} splits)" if limit else " for All Splits"))
    print("=" * 70)
    
    # Get reverse_sa splits (limited if specified, prioritize 2025)
    if limit:
        # Get most recent 2025 splits first
        all_splits = list(reverse_collection.find({"Date": {"$regex": "/2025$"}})
                         .sort("Date", -1)
                         .limit(limit))
        
        # If we need more, fill with other recent splits
        if len(all_splits) < limit:
            remaining = limit - len(all_splits)
            other_splits = list(reverse_collection.find({"Date": {"$not": {"$regex": "/2025$"}}})
                               .sort("Date", -1)
                               .limit(remaining))
            all_splits.extend(other_splits)
    else:
        all_splits = list(reverse_collection.find({}))
    
    print(f"\nProcessing {len(all_splits)} reverse splits...")
    
    updated_count = 0
    skipped_count = 0
    
    for i, split in enumerate(all_splits, 1):
        reverse_sa_id = str(split["_id"])
        symbol = split.get("Symbol")
        
        if i % 10 == 0:
            print(f"\nProgress: {i}/{len(all_splits)}")
        
        # Find earliest announcement
        result = find_earliest_announcement(reverse_sa_id)
        
        if result.get("error"):
            print(f"  ✗ {symbol}: {result['error']}")
            skipped_count += 1
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
            
            if i % 10 == 0 or i <= 3:
                print(f"  ✓ {symbol}: {announcement_date} (Tier {best_filing.get('tier') if best_filing else 'N/A'})")
        else:
            skipped_count += 1
    
    client.close()
    
    print(f"\n✓ Updated {updated_count} reverse_sa documents with earliest announcement dates")
    print(f"  Skipped: {skipped_count} (no announcement found)")
    
    return updated_count, skipped_count


def generate_summary_table(limit: int = None):
    """Generate summary statistics table of processed data"""
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    reverse_collection = db[REVERSE_COLLECTION]
    edgar_collection = db[EDGAR_COLLECTION]
    
    # Get splits (limited if specified)
    query = {}
    if limit:
        all_splits = list(reverse_collection.find(query).limit(limit))
    else:
        all_splits = list(reverse_collection.find(query))
    
    total_splits = len(all_splits)
    
    # Count splits with EDGAR filings
    splits_with_edgar = 0
    total_edgar_filings = 0
    splits_with_announcement = 0
    
    # Tier breakdown
    tier_counts = {"A": 0, "B": 0, "C": 0, "F": 0}
    form_counts = {}
    flag_counts = {
        "compliance_flag": 0,
        "financing_flag": 0,
        "rounding_up_flag": 0,
        "unregistered_sales_flag": 0
    }
    
    for split in all_splits:
        reverse_sa_id = str(split["_id"])
        filings = list(edgar_collection.find({"reverse_sa_id": reverse_sa_id}))
        
        if filings:
            splits_with_edgar += 1
            total_edgar_filings += len(filings)
            
            # Check if has earliest_announcement_date
            if split.get("earliest_announcement_date"):
                splits_with_announcement += 1
            
            # Count tiers, forms, flags
            for filing in filings:
                tier = filing.get("tier", "F")
                if tier in tier_counts:
                    tier_counts[tier] += 1
                
                form = filing.get("form", "Unknown")
                form_counts[form] = form_counts.get(form, 0) + 1
                
                flags = filing.get("flags", {})
                for flag_name in flag_counts.keys():
                    if flags.get(flag_name):
                        flag_counts[flag_name] += 1
    
    client.close()
    
    return {
        "total_splits": total_splits,
        "splits_with_edgar": splits_with_edgar,
        "splits_without_edgar": total_splits - splits_with_edgar,
        "splits_with_announcement": splits_with_announcement,
        "total_edgar_filings": total_edgar_filings,
        "tier_counts": tier_counts,
        "form_counts": form_counts,
        "flag_counts": flag_counts,
        "avg_filings_per_split": round(total_edgar_filings / splits_with_edgar, 2) if splits_with_edgar > 0 else 0
    }


def print_summary_table(summary: Dict):
    """Print a formatted summary table"""
    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    
    print(f"\n📊 SPLITS PROCESSED:")
    print(f"  Total Splits: {summary['total_splits']}")
    print(f"  Splits with EDGAR Filings: {summary['splits_with_edgar']} ({summary['splits_with_edgar']/summary['total_splits']*100:.1f}%)")
    print(f"  Splits without EDGAR: {summary['splits_without_edgar']} ({summary['splits_without_edgar']/summary['total_splits']*100:.1f}%)")
    print(f"  Splits with Earliest Announcement: {summary['splits_with_announcement']}")
    
    print(f"\n📄 EDGAR FILINGS:")
    print(f"  Total Filings: {summary['total_edgar_filings']}")
    print(f"  Avg Filings per Split: {summary['avg_filings_per_split']}")
    
    print(f"\n🏆 TIER BREAKDOWN:")
    total_tiered = sum(summary['tier_counts'].values())
    for tier, count in sorted(summary['tier_counts'].items()):
        pct = (count / total_tiered * 100) if total_tiered > 0 else 0
        print(f"  Tier {tier}: {count} ({pct:.1f}%)")
    
    print(f"\n📋 FORM TYPES (Top 10):")
    sorted_forms = sorted(summary['form_counts'].items(), key=lambda x: x[1], reverse=True)[:10]
    for form, count in sorted_forms:
        print(f"  {form}: {count}")
    
    print(f"\n🚩 FLAG COUNTS:")
    for flag, count in summary['flag_counts'].items():
        if count > 0:
            print(f"  {flag}: {count}")
    
    print("=" * 70)


def main(limit: int = None, force_reprocess: bool = False):
    """Complete workflow: Query EDGAR + Score + Find Earliest Announcements"""
    print("=" * 70)
    print("COMPLETE EDGAR WORKFLOW" + (f" (TEST MODE: {limit} splits)" if limit else ""))
    if force_reprocess:
        print("⚠ FORCE REPROCESSING MODE: Will reprocess already-processed splits")
    print("=" * 70)
    
    # Phase 1: Query EDGAR and score filings
    print("\n" + "=" * 70)
    print("PHASE 1: Query EDGAR for Reverse Splits & Score Filings")
    print("=" * 70)
    
    # Get reverse_sa splits (limited if specified, prioritize 2025)
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    reverse_collection = db[REVERSE_COLLECTION]
    
    if limit:
        # Get most recent 2025 splits first
        all_splits = list(reverse_collection.find({"Date": {"$regex": "/2025$"}})
                         .sort("Date", -1)
                         .limit(limit))
        
        # If we need more, fill with other recent splits
        if len(all_splits) < limit:
            remaining = limit - len(all_splits)
            other_splits = list(reverse_collection.find({"Date": {"$not": {"$regex": "/2025$"}}})
                               .sort("Date", -1)
                               .limit(remaining))
            all_splits.extend(other_splits)
    else:
        all_splits = list(reverse_collection.find({}))
    
    client.close()
    
    print(f"\nFound {len(all_splits)} reverse splits to process" + (f" (limited to {limit}, prioritizing 2025)" if limit else ""))
    
    # Get CIK mapping once (with both ticker and name lookups)
    print("\nFetching CIK mapping...")
    cik_mappings = get_cik_mapping_with_names()
    cik_mapping = cik_mappings.get("ticker", {})
    name_mapping = cik_mappings.get("name", {})
    print(f"✓ Loaded {len(cik_mapping)} ticker mappings and {len(name_mapping)} company name mappings")
    
    # Process each split
    total_filings = 0
    processed_count = 0
    skipped_count = 0
    already_processed_count = 0
    no_cik_count = 0
    no_filings_data = []
    no_filings_in_window = []
    
    for i, split in enumerate(all_splits, 1):
        if i % 50 == 0:
            print(f"\nProgress: {i}/{len(all_splits)} splits processed")
            print(f"  Processed: {processed_count}, Skipped: {skipped_count}, Already done: {already_processed_count}, No CIK: {no_cik_count}")
        
        result = process_split_with_edgar(split, cik_mapping, name_mapping, skip_existing=not force_reprocess)
        
        if result["status"] == "success":
            processed_count += 1
            total_filings += result["filings_processed"]
        elif result["status"] == "already_processed":
            already_processed_count += 1
        elif result["status"] == "no_cik":
            no_cik_count += 1
        elif result["status"] == "no_filings_data":
            skipped_count += 1
            no_filings_data.append(result)
        elif result["status"] == "no_filings_in_window":
            skipped_count += 1
            no_filings_in_window.append(result)
        else:
            skipped_count += 1
    
    print(f"\n✓ Phase 1 Complete:")
    print(f"  Processed: {processed_count} splits")
    print(f"  Already processed: {already_processed_count} splits")
    print(f"  No CIK found: {no_cik_count} splits")
    print(f"  Skipped (no filings): {skipped_count} splits")
    print(f"  Total filings processed: {total_filings}")
    
    # Display splits with CIK but no filings
    if no_filings_data or no_filings_in_window:
        print("\n" + "=" * 70)
        print("SPLITS WITH CIK BUT NO EDGAR FILINGS")
        print("=" * 70)
        
        if no_filings_data:
            print(f"\n⚠ {len(no_filings_data)} splits: No filings data returned from SEC")
            for r in no_filings_data:
                print(f"  • {r['symbol']} ({r.get('company_name', 'N/A')})")
                print(f"    CIK: {r.get('cik', 'N/A')}, Split Date: {r.get('split_date', 'N/A')}")
                print(f"    Date Window: {r.get('date_window', ('N/A', 'N/A'))[0]} to {r.get('date_window', ('N/A', 'N/A'))[1]}")
        
        if no_filings_in_window:
            print(f"\n⚠ {len(no_filings_in_window)} splits: No filings in date window")
            
            # Separate historical vs other issues
            historical_splits = [r for r in no_filings_in_window if r.get('is_historical_split')]
            other_issues = [r for r in no_filings_in_window if not r.get('is_historical_split')]
            
            if historical_splits:
                print(f"\n  📅 {len(historical_splits)} Historical Splits (SEC API limitation):")
                print("     The SEC /submissions/ endpoint only returns recent filings.")
                print("     Historical filings from 2010-2015 may not be accessible via this API.")
                for r in historical_splits[:10]:  # Show first 10
                    print(f"  • {r['symbol']} ({r.get('company_name', 'N/A')})")
                    print(f"    Split Date: {r.get('split_date', 'N/A')}")
                    print(f"    CIK: {r.get('cik', 'N/A')}")
                    print(f"    Reason: {r.get('reason', 'Historical split')}")
                    if r.get('earliest_filing_date'):
                        print(f"    Earliest filing available: {r.get('earliest_filing_date')}")
                    print()
            
            if other_issues:
                print(f"\n  ⚠ {len(other_issues)} Other Issues:")
                for r in other_issues[:10]:  # Show first 10
                    total = r.get('total_filings_for_cik', 0)
                    date_window = r.get('date_window', ('N/A', 'N/A'))
                    forms_in_window = r.get('forms_in_window', {})
                    all_forms = r.get('all_forms', {})
                    print(f"  • {r['symbol']} ({r.get('company_name', 'N/A')})")
                    print(f"    CIK: {r.get('cik', 'N/A')}, Split Date: {r.get('split_date', 'N/A')}")
                    print(f"    Date Window: {date_window[0]} to {date_window[1]}")
                    print(f"    Total filings for CIK: {total}")
                    if forms_in_window:
                        print(f"    Forms in date window (not matching target forms): {forms_in_window}")
                    elif all_forms:
                        top_forms = dict(list(sorted(all_forms.items(), key=lambda x: x[1], reverse=True)[:5]))
                        print(f"    Top forms (all time): {top_forms}")
                    print()
        
        print("=" * 70)
    
    # Phase 2: Find earliest announcements
    print("\n" + "=" * 70)
    print("PHASE 2: Finding Earliest Announcements")
    print("=" * 70)
    
    updated, skipped = batch_find_earliest_announcements(limit=limit)
    
    # Generate and print summary table
    print("\n" + "=" * 70)
    print("GENERATING SUMMARY TABLE")
    print("=" * 70)
    
    summary = generate_summary_table(limit=limit)
    print_summary_table(summary)
    
    # Final summary
    print("\n" + "=" * 70)
    print("WORKFLOW COMPLETE")
    print("=" * 70)
    print(f"Phase 1: Processed {processed_count} splits, {total_filings} filings scored")
    print(f"Phase 2: Updated {updated} reverse_sa documents with earliest announcement dates")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    
    # Check for limit argument
    limit = None
    force_reprocess = False
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            if sys.argv[1] == "--force":
                force_reprocess = True
            else:
                print(f"Invalid limit: {sys.argv[1]}. Using default (all splits)")
    
    if len(sys.argv) > 2 and sys.argv[2] == "--force":
        force_reprocess = True
    
    main(limit=limit, force_reprocess=force_reprocess)

