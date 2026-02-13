"""
Shared EDGAR Utilities
Contains reusable logic for fetching, parsing, and analyzing SEC filings.
"""

import requests
import re
import math
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union
from bs4 import BeautifulSoup

# SEC API Configuration
SEC_BASE_URL = "https://data.sec.gov"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

import os

# Rate limiting
REQUEST_DELAY = 0.2  

# Use environment variable for User-Agent if available, otherwise default
# IMPORTANT: SEC requires a specific User-Agent format: "AppName ContactEmail"
default_ua = "Split Strategy Analysis contact@splitstrategy.com"
user_agent = os.environ.get("SEC_USER_AGENT", default_ua)

HEADERS = {
    "User-Agent": user_agent,
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov"
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
        
        # Convert to ticker 
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


def normalize_cik(cik: Union[str, int]) -> str:
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
        # More flexible patterns to catch various formats
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


def check_split_proposal_flag(text: str) -> bool:
    """Check for reverse split proposals (e.g. in PRE 14A)"""
    # High confidence patterns
    split_patterns = [
        r"proposal\s+to\s+authorize\s+.*\s+reverse\s+stock\s+split",
        r"approve\s+an\s+amendment\s+.*\s+reverse\s+stock\s+split",
        r"effect\s+a\s+reverse\s+stock\s+split",
        r"grant\s+.*discretion\s+to\s+effect\s+a\s+reverse\s+stock\s+split",
        r"reverse\s+split\s+ratio\s+of",
    ]
    
    for pattern in split_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False
