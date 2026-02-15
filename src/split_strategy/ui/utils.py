"""
Helper functions for the UI dashboard.
"""
from ..database import EDGAR_COLLECTION, REVERSE_SPLITS_COLLECTION, get_collection

def has_edgar_data(reverse_splits_id: str) -> bool:
    """Check if split has any EDGAR filings"""
    collection = get_collection(EDGAR_COLLECTION)
    count = collection.count_documents({"reverse_splits_id": reverse_splits_id})
    return count > 0

def check_rounding_flag(reverse_splits_id: str) -> bool:
    """Check if any EDGAR filing has rounding_up_flag=True"""
    collection = get_collection(EDGAR_COLLECTION)
    edgar_filings = list(collection.find({"reverse_splits_id": reverse_splits_id}))
    
    for filing in edgar_filings:
        flags = filing.get("flags", {})
        if flags.get("rounding_up_flag", False):
            return True
    
    return False

def get_rounding_filings(reverse_splits_id: str) -> list:
    """Get all EDGAR filings with rounding_up_flag=True"""
    collection = get_collection(EDGAR_COLLECTION)
    edgar_filings = list(collection.find({"reverse_splits_id": reverse_splits_id}))
    
    rounding_filings = []
    for filing in edgar_filings:
        flags = filing.get("flags", {})
        if flags.get("rounding_up_flag", False):
            rounding_filings.append({
                "form": filing.get("form", "Unknown"),
                "filing_date": filing.get("filing_date", ""),
                "document_url": filing.get("document_url", ""),
                "rounding_text": filing.get("text_matches", {}).get("rounding_text", ""),
                "accession": filing.get("accession", ""),
                "cik": filing.get("cik", "")
            })
    
    return rounding_filings
