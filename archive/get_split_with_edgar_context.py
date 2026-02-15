"""
Get Reverse Split with EDGAR Context
Fetches a reverse split from reverse_sa and joins all related EDGAR filings.
"""

import json
from pymongo import MongoClient
import os
from datetime import datetime

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is required. Please set it in your .env file or environment.")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"
EDGAR_COLLECTION = "edgar_events"


def get_split_with_edgar_context(symbol: str, date: str = None, reverse_sa_id: str = None):
    """
    Get a reverse split from reverse_sa with all related EDGAR filings.
    
    Args:
        symbol: Stock symbol (e.g., "YDKG")
        date: Split date in MM/DD/YYYY format (optional if reverse_sa_id provided)
        reverse_sa_id: MongoDB _id from reverse_sa (optional if symbol+date provided)
    
    Returns:
        Dict with reverse_sa data and edgar_filings array
    """
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    reverse_collection = db[REVERSE_COLLECTION]
    edgar_collection = db[EDGAR_COLLECTION]
    
    try:
        # Find the reverse split document
        if reverse_sa_id:
            # Convert string to ObjectId if needed
            from bson import ObjectId
            if isinstance(reverse_sa_id, str):
                reverse_split = reverse_collection.find_one({"_id": ObjectId(reverse_sa_id)})
            else:
                reverse_split = reverse_collection.find_one({"_id": reverse_sa_id})
        elif symbol and date:
            reverse_split = reverse_collection.find_one({"Symbol": symbol.upper(), "Date": date})
        elif symbol:
            # Get most recent split for symbol
            reverse_split = reverse_collection.find_one({"Symbol": symbol.upper()}, sort=[("Date", -1)])
        else:
            raise ValueError("Must provide either reverse_sa_id or symbol+date")
        
        if not reverse_split:
            return {
                "error": f"No reverse split found for {symbol} on {date}" if symbol else f"No reverse split found with ID {reverse_sa_id}",
                "reverse_split": None,
                "edgar_filings": []
            }
        
        # Convert ObjectId to string for JSON serialization
        reverse_split_id = str(reverse_split["_id"])
        
        # Get all EDGAR filings linked to this reverse split
        edgar_filings = list(edgar_collection.find({"reverse_sa_id": reverse_split_id}))
        
        # Convert ObjectIds to strings
        for filing in edgar_filings:
            if "_id" in filing:
                filing["_id"] = str(filing["_id"])
        
        # Build combined result
        result = {
            "reverse_split": {
                "_id": reverse_split_id,
                "Date": reverse_split.get("Date"),
                "Symbol": reverse_split.get("Symbol"),
                "Company Name": reverse_split.get("Company Name"),
                "Split Ratio": reverse_split.get("Split Ratio"),
                "type": reverse_split.get("type"),
                "last_updated": reverse_split.get("last_updated")
            },
            "edgar_filings": edgar_filings,
            "edgar_filing_count": len(edgar_filings),
            "summary": {
                "forms": {},
                "flags": {
                    "compliance_flag": 0,
                    "financing_flag": 0,
                    "unregistered_sales_flag": 0,
                    "rounding_up_flag": 0,
                    "share_change_flag": 0,
                    "listing_deficiency_flag": 0
                }
            }
        }
        
        # Build summary statistics
        for filing in edgar_filings:
            # Count forms
            form = filing.get("form", "Unknown")
            result["summary"]["forms"][form] = result["summary"]["forms"].get(form, 0) + 1
            
            # Count flags
            flags = filing.get("flags", {})
            for flag_name in result["summary"]["flags"].keys():
                if flags.get(flag_name):
                    result["summary"]["flags"][flag_name] += 1
        
        return result
        
    except Exception as e:
        return {
            "error": str(e),
            "reverse_split": None,
            "edgar_filings": []
        }
    finally:
        client.close()


def print_split_with_context(result: dict):
    """Pretty print the combined result"""
    if result.get("error"):
        print(f"❌ Error: {result['error']}")
        return
    
    reverse_split = result.get("reverse_split", {})
    edgar_filings = result.get("edgar_filings", [])
    
    print("=" * 70)
    print("REVERSE SPLIT DETAILS")
    print("=" * 70)
    print(f"Symbol: {reverse_split.get('Symbol')}")
    print(f"Company: {reverse_split.get('Company Name')}")
    print(f"Date: {reverse_split.get('Date')}")
    print(f"Split Ratio: {reverse_split.get('Split Ratio')}")
    print(f"ID: {reverse_split.get('_id')}")
    
    print("\n" + "=" * 70)
    print(f"EDGAR FILINGS ({result.get('edgar_filing_count', 0)} total)")
    print("=" * 70)
    
    if not edgar_filings:
        print("No EDGAR filings found for this split.")
        return
    
    for i, filing in enumerate(edgar_filings, 1):
        print(f"\n[{i}] {filing.get('form')} - {filing.get('filing_date')}")
        print(f"    Accession: {filing.get('accession')}")
        print(f"    URL: {filing.get('document_url')}")
        
        if filing.get('announce_date'):
            print(f"    Announce Date: {filing.get('announce_date')}")
        if filing.get('effective_date'):
            print(f"    Effective Date: {filing.get('effective_date')}")
        
        if filing.get('ratio_num'):
            print(f"    Split Ratio: {filing.get('ratio_num')} : {filing.get('ratio_den')} (log: {filing.get('log_ratio')})")
        
        flags = filing.get('flags', {})
        active_flags = [k for k, v in flags.items() if v]
        if active_flags:
            print(f"    Flags: {', '.join(active_flags)}")
        
        if filing.get('text_matches'):
            print(f"    Text Matches:")
            for key, value in filing['text_matches'].items():
                print(f"      {key}: {value[:100]}...")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    summary = result.get("summary", {})
    
    print("\nForms by type:")
    for form, count in sorted(summary.get("forms", {}).items()):
        print(f"  {form}: {count}")
    
    print("\nFlag counts:")
    for flag, count in summary.get("flags", {}).items():
        if count > 0:
            print(f"  {flag}: {count}")
    
    print("=" * 70)


def main():
    """Example usage: Get YDKG split with EDGAR context"""
    print("Fetching YDKG reverse split with EDGAR context...\n")
    
    # Get YDKG split (most recent if multiple)
    result = get_split_with_edgar_context(symbol="YDKG", date="11/14/2025")
    
    # Print results
    print_split_with_context(result)
    
    # Also print as JSON for reference
    print("\n" + "=" * 70)
    print("JSON OUTPUT (for programmatic use)")
    print("=" * 70)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

