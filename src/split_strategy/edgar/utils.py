"""
Utility functions for EDGAR processing.
"""
import re
from datetime import datetime, timedelta
from typing import Optional, Dict

def normalize_cik(cik: str) -> str:
    """Normalize CIK to 10 digits"""
    return str(cik).strip().zfill(10)

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
