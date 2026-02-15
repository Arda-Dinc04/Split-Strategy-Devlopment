"""
EDGAR Client for SEC API interaction.
"""
import requests
import time
from typing import Optional, Dict

from ..config import SEC_BASE_URL, SEC_ARCHIVES_URL, REQUEST_DELAY, SEC_USER_AGENT
from .utils import normalize_cik

HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept": "application/json"
}

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

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

def get_daily_index_url(date_obj) -> str:
    """Construct URL for daily index file"""
    year = date_obj.year
    qtr = (date_obj.month - 1) // 3 + 1
    date_str = date_obj.strftime("%Y%m%d")
    return f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{qtr}/company.{date_str}.idx"

def parse_idx_line(line: str) -> Optional[Dict]:
    """Parse a fixed-width line from company.YYYYMMDD.idx"""
    import re
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

def fetch_daily_filings(date_obj, target_forms=None) -> list:
    """Download and parse daily index"""
    url = get_daily_index_url(date_obj)
    print(f"Fetching Daily Index: {url}")
    
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code in [403, 404]:
            print("  No index found (weekend/holiday? or 403 Forbidden)")
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
            if entry:
                if target_forms:
                     if entry["form"] in target_forms:
                        filings.append(entry)
                else:
                    filings.append(entry)
        
        return filings
    except Exception as e:
        print(f"Error fetching index: {e}")
        return []

