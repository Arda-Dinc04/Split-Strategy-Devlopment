"""
Find Earliest Announcement Date from EDGAR Filings
Implements ranking and selection logic to determine the best announcement date.
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pymongo import MongoClient
import os
from bson import ObjectId

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://RS:01SDcSCdulMJREai@cluster0.wauawr1.mongodb.net/?appName=Cluster0")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"
EDGAR_COLLECTION = "edgar_events"


def parse_sa_ratio(ratio_str: str) -> Optional[Tuple[int, int]]:
    """Parse SA ratio string like '1 : 100' to (num, den)"""
    if not ratio_str:
        return None
    
    # Match patterns like "1 : 100", "1:100", "1 for 100"
    match = re.search(r"(\d+)\s*[:]\s*(\d+)", ratio_str)
    if match:
        num = int(match.group(1))
        den = int(match.group(2))
        if num > 0 and den > 0:
            return (num, den)
    return None


def is_year_like_ratio(num: int, den: int) -> bool:
    """Check if ratio looks like a year range (e.g., 2018:2019)"""
    # Check if both numbers are 4-digit years
    if 1900 <= num <= 2100 and 1900 <= den <= 2100:
        return True
    return False


def has_rs_keyword(text: str) -> bool:
    """Check if text contains reverse split keywords"""
    patterns = [
        r"reverse\s+stock\s+split",
        r"reverse\s+split"
    ]
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def get_business_days_diff(date1: datetime, date2: datetime) -> int:
    """Calculate business days difference (excluding weekends)"""
    if date1 > date2:
        date1, date2 = date2, date1
    
    business_days = 0
    current = date1
    while current <= date2:
        if current.weekday() < 5:  # Monday = 0, Friday = 4
            business_days += 1
        current += timedelta(days=1)
    
    return business_days - 1  # Subtract 1 to get difference


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string to datetime"""
    if not date_str:
        return None
    
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.split('T')[0], fmt)
        except:
            continue
    return None


def score_filing(filing: Dict, sa_ratio: Optional[Tuple[int, int]], sa_effective_date: Optional[datetime]) -> Dict:
    """
    Score a filing based on content and alignment with SA data.
    Returns: {score, tier, candidate_announce_date, reasons}
    """
    score = 0
    reasons = []
    
    # Hard gate: Must have RS keyword or ratio
    # Since filings are already in edgar_events (pre-filtered for RS), we relax the check
    text_matches = filing.get("text_matches", {})
    combined_text = " ".join([v for v in text_matches.values() if isinstance(v, str)])
    
    # Check if ratio exists (strong indicator of RS filing)
    ratio_num = filing.get("ratio_num")
    ratio_den = filing.get("ratio_den")
    has_ratio = ratio_num and ratio_den and ratio_num > 0 and ratio_den > 0
    
    # Check for RS keywords in text matches, or if filing has ratio/effective_date (indicates RS context)
    has_rs_keyword_in_text = has_rs_keyword(combined_text)
    has_effective_date = bool(filing.get("effective_date"))
    has_compliance_flag = filing.get("flags", {}).get("compliance_flag", False)
    
    # If filing is in edgar_events, it's likely RS-related, so be lenient
    # Pass if: has RS keyword, has ratio, has effective_date, or has compliance_flag
    has_rs = has_rs_keyword_in_text or has_ratio or has_effective_date or has_compliance_flag
    
    if not has_rs:
        return {
            "score": 0,
            "tier": "F",
            "candidate_announce_date": None,
            "reasons": ["No RS keyword or ratio"]
        }
    
    form = filing.get("form", "")
    
    # Base prior (by form)
    if form in ["8-K", "6-K"]:
        score += 3
        reasons.append(f"Form {form} (+3)")
    elif form in ["DEF 14A", "PRE 14A", "DEFA14A", "14C", "PRE 14C"]:
        score += 2
        reasons.append(f"Form {form} (+2)")
    elif form in ["S-1", "S-3", "424B5", "424B3", "FWP"]:
        score += 1
        reasons.append(f"Form {form} (+1)")
    elif form in ["10-K", "10-Q", "20-F"]:
        score += 0
        reasons.append(f"Form {form} (context only)")
    
    # Content markers
    ratio_num = filing.get("ratio_num")
    ratio_den = filing.get("ratio_den")
    
    # Ratio extracted (valid, not year-like)
    if ratio_num and ratio_den and ratio_num > 0 and ratio_den > 0:
        if not is_year_like_ratio(ratio_num, ratio_den):
            score += 2
            reasons.append(f"Valid ratio {ratio_num}:{ratio_den} (+2)")
    
    # Effective date/time extracted
    if filing.get("effective_date"):
        score += 1
        reasons.append("Effective date extracted (+1)")
    
    # Announce sentence date (extracted from "On <Month DD, YYYY>")
    announce_date = filing.get("announce_date")
    filing_date = parse_date(filing.get("filing_date", ""))
    
    if announce_date and filing_date:
        announce_dt = parse_date(announce_date)
        if announce_dt:
            # Check if announce_date is different from filing_date (indicates extracted)
            if announce_dt != filing_date:
                # Only check if announce_date is reasonable (not in the future, not too old)
                if announce_dt <= filing_date:  # Announcement can't be after filing
                    score += 1
                    reasons.append(f"Announce sentence date extracted (+1)")
    
    # Compliance/listing cue
    flags = filing.get("flags", {})
    items = filing.get("items", [])
    if flags.get("compliance_flag") or "3.01" in items:
        score += 1
        reasons.append("Compliance/listing cue (+1)")
    
    # Share-change cue
    if "3.02" in items:
        score += 1
        reasons.append("Item 3.02 share-change (+1)")
    
    # SA alignment: ratio matches SA
    if sa_ratio and ratio_num and ratio_den:
        if (ratio_num, ratio_den) == sa_ratio:
            score += 1
            reasons.append("Ratio matches SA (+1)")
    
    # Effective date near SA (±5 business days)
    if sa_effective_date and filing.get("effective_date"):
        filing_effective_dt = parse_date(filing.get("effective_date"))
        if filing_effective_dt:
            bdays_diff = get_business_days_diff(filing_effective_dt, sa_effective_date)
            if abs(bdays_diff) <= 5:
                score += 1
                reasons.append("Effective date near SA (±5 bdays) (+1)")
    
    # Financing mention only (penalty)
    if flags.get("financing_flag") and not (ratio_num and ratio_den) and not filing.get("effective_date"):
        score -= 1
        reasons.append("Financing only, no RS ratio/date (-1)")
    
    # Determine tier
    if score >= 5:
        tier = "A"
    elif score >= 3:
        tier = "B"
    else:
        tier = "C"
    
    # Compute candidate_announce_date
    # Prefer announce_date if it exists and is valid (not after filing_date)
    candidate_announce_date = None
    if announce_date and filing_date:
        announce_dt = parse_date(announce_date)
        filing_dt = parse_date(filing.get("filing_date", ""))
        if announce_dt and filing_dt:
            # Use announce_date if it's not after filing_date (reasonable check)
            if announce_dt <= filing_dt:
                candidate_announce_date = announce_date
    
    # Fallback to filing_date if no valid announce_date
    if not candidate_announce_date:
        candidate_announce_date = filing.get("filing_date")
    
    return {
        "score": score,
        "tier": tier,
        "candidate_announce_date": candidate_announce_date,
        "reasons": reasons,
        "ratio": (ratio_num, ratio_den) if ratio_num and ratio_den else None
    }


def find_earliest_announcement(reverse_sa_id: str) -> Dict:
    """
    Find the earliest valid announcement date from all EDGAR filings for a split.
    
    Args:
        reverse_sa_id: MongoDB _id from reverse_sa collection
    
    Returns:
        Dict with best filing info and announcement date
    """
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    reverse_collection = db[REVERSE_COLLECTION]
    edgar_collection = db[EDGAR_COLLECTION]
    
    try:
        # Get reverse_sa document
        reverse_split = reverse_collection.find_one({"_id": ObjectId(reverse_sa_id)})
        if not reverse_split:
            return {"error": f"No reverse split found with ID {reverse_sa_id}"}
        
        # Parse SA data
        sa_ratio_str = reverse_split.get("Split Ratio", "")
        sa_ratio = parse_sa_ratio(sa_ratio_str)
        sa_date_str = reverse_split.get("Date", "")
        sa_effective_date = parse_date(sa_date_str)
        
        # Get all EDGAR filings for this split
        edgar_filings = list(edgar_collection.find({"reverse_sa_id": reverse_sa_id}))
        
        if not edgar_filings:
            return {
                "reverse_sa_id": reverse_sa_id,
                "symbol": reverse_split.get("Symbol"),
                "announcement_date": None,
                "best_filing": None,
                "message": "No EDGAR filings found"
            }
        
        # Score all filings
        scored_filings = []
        for filing in edgar_filings:
            scoring_result = score_filing(filing, sa_ratio, sa_effective_date)
            scored_filings.append({
                "filing": filing,
                **scoring_result
            })
        
        # Filter by tier and score
        tier_a = [sf for sf in scored_filings if sf["tier"] == "A" and sf["score"] >= 5]
        tier_b = [sf for sf in scored_filings if sf["tier"] == "B" and 3 <= sf["score"] <= 4]
        tier_c = [sf for sf in scored_filings if sf["tier"] == "C" and sf["score"] >= 3 
                  and sf["ratio"] is not None and sf["filing"].get("effective_date")]
        
        # Select best candidate - prioritize earliest announcement date
        best_filing_info = None
        announcement_date = None
        
        # Combine all valid candidates and sort by earliest announcement date
        all_candidates = []
        if tier_a:
            all_candidates.extend(tier_a)
        if tier_b:
            all_candidates.extend(tier_b)
        if tier_c:
            all_candidates.extend(tier_c)
        
        if all_candidates:
            # Filter out candidates with announcement dates too far from SA date (sanity check)
            # Announcement should be within ±1 year of SA effective date
            valid_candidates = []
            for candidate in all_candidates:
                candidate_date = candidate["candidate_announce_date"]
                if candidate_date and sa_effective_date:
                    candidate_dt = parse_date(candidate_date)
                    if candidate_dt:
                        # Check if within ±365 days of SA date
                        days_diff = abs((candidate_dt - sa_effective_date).days)
                        if days_diff <= 365:
                            valid_candidates.append(candidate)
                        # Also allow if candidate_date is after SA date (up to 30 days) - future announcement
                        elif candidate_dt > sa_effective_date and days_diff <= 30:
                            valid_candidates.append(candidate)
                else:
                    valid_candidates.append(candidate)
            
            if not valid_candidates:
                # Fallback: use all candidates if none pass sanity check
                valid_candidates = all_candidates
            
            # Sort by announcement date (earliest first), then by score (highest first)
            valid_candidates.sort(key=lambda x: (
                x["candidate_announce_date"] or "9999-99-99",
                -x["score"]  # Negative for descending score
            ))
            best_filing_info = valid_candidates[0]
            announcement_date = best_filing_info["candidate_announce_date"]
        
        # Prepare detailed breakdown of all filings by tier
        all_filings_by_tier = {
            "tier_a": [{
                "accession": sf["filing"]["accession"],
                "form": sf["filing"]["form"],
                "filing_date": sf["filing"]["filing_date"],
                "announce_date": sf["filing"].get("announce_date"),
                "candidate_announce_date": sf["candidate_announce_date"],
                "score": sf["score"],
                "reasons": sf["reasons"]
            } for sf in tier_a],
            "tier_b": [{
                "accession": sf["filing"]["accession"],
                "form": sf["filing"]["form"],
                "filing_date": sf["filing"]["filing_date"],
                "announce_date": sf["filing"].get("announce_date"),
                "candidate_announce_date": sf["candidate_announce_date"],
                "score": sf["score"],
                "reasons": sf["reasons"]
            } for sf in tier_b],
            "tier_c": [{
                "accession": sf["filing"]["accession"],
                "form": sf["filing"]["form"],
                "filing_date": sf["filing"]["filing_date"],
                "announce_date": sf["filing"].get("announce_date"),
                "candidate_announce_date": sf["candidate_announce_date"],
                "score": sf["score"],
                "reasons": sf["reasons"]
            } for sf in tier_c],
            "tier_f": [{
                "accession": sf["filing"]["accession"],
                "form": sf["filing"]["form"],
                "filing_date": sf["filing"]["filing_date"],
                "score": sf["score"],
                "reasons": sf["reasons"]
            } for sf in scored_filings if sf["tier"] == "F"]
        }
        
        result = {
            "reverse_sa_id": reverse_sa_id,
            "symbol": reverse_split.get("Symbol"),
            "sa_ratio": sa_ratio_str,
            "sa_date": sa_date_str,
            "announcement_date": announcement_date,
            "best_filing": {
                "accession": best_filing_info["filing"]["accession"] if best_filing_info else None,
                "form": best_filing_info["filing"]["form"] if best_filing_info else None,
                "filing_date": best_filing_info["filing"]["filing_date"] if best_filing_info else None,
                "score": best_filing_info["score"] if best_filing_info else None,
                "tier": best_filing_info["tier"] if best_filing_info else None,
                "reasons": best_filing_info["reasons"] if best_filing_info else None,
                "document_url": best_filing_info["filing"]["document_url"] if best_filing_info else None
            } if best_filing_info else None,
            "summary": {
                "total_filings": len(edgar_filings),
                "tier_a_count": len(tier_a),
                "tier_b_count": len(tier_b),
                "tier_c_count": len(tier_c),
                "tier_f_count": len([sf for sf in scored_filings if sf["tier"] == "F"])
            },
            "all_filings_by_tier": all_filings_by_tier
        }
        
        return result
        
    except Exception as e:
        return {"error": str(e)}
    finally:
        client.close()


def main():
    """Example: Find earliest announcement for YDKG"""
    # Get YDKG reverse_sa_id
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    reverse_collection = db[REVERSE_COLLECTION]
    
    ydkg_split = reverse_collection.find_one({"Symbol": "YDKG", "Date": "11/14/2025"})
    if ydkg_split:
        reverse_sa_id = str(ydkg_split["_id"])
        client.close()
        
        result = find_earliest_announcement(reverse_sa_id)
        
        print("=" * 70)
        print("EARLIEST ANNOUNCEMENT DATE FINDER")
        print("=" * 70)
        print(f"\nSymbol: {result.get('symbol')}")
        print(f"SA Ratio: {result.get('sa_ratio')}")
        print(f"SA Date: {result.get('sa_date')}")
        print(f"\nAnnouncement Date: {result.get('announcement_date')}")
        
        if result.get('best_filing'):
            bf = result['best_filing']
            print(f"\nBest Filing:")
            print(f"  Form: {bf.get('form')}")
            print(f"  Filing Date: {bf.get('filing_date')}")
            print(f"  Accession: {bf.get('accession')}")
            print(f"  Score: {bf.get('score')}")
            print(f"  Tier: {bf.get('tier')}")
            print(f"  Reasons: {', '.join(bf.get('reasons', []))}")
            print(f"  URL: {bf.get('document_url')}")
        
        print(f"\nSummary:")
        summary = result.get('summary', {})
        print(f"  Total Filings: {summary.get('total_filings')}")
        print(f"  Tier A: {summary.get('tier_a_count')}")
        print(f"  Tier B: {summary.get('tier_b_count')}")
        print(f"  Tier C: {summary.get('tier_c_count')}")
        print(f"  Tier F (filtered out): {summary.get('tier_f_count', 0)}")
        
        # Show detailed breakdown
        all_filings = result.get('all_filings_by_tier', {})
        
        print(f"\n{'=' * 70}")
        print("TIER A FILINGS (Score ≥ 5):")
        print("=" * 70)
        for i, filing in enumerate(all_filings.get('tier_a', []), 1):
            print(f"\n[{i}] {filing['form']} - {filing['filing_date']}")
            print(f"    Accession: {filing['accession']}")
            print(f"    Score: {filing['score']}")
            print(f"    Announce Date: {filing.get('announce_date', 'N/A')}")
            print(f"    Candidate Announce Date: {filing['candidate_announce_date']}")
            print(f"    Reasons: {', '.join(filing['reasons'])}")
        
        print(f"\n{'=' * 70}")
        print("TIER B FILINGS (Score 3-4):")
        print("=" * 70)
        for i, filing in enumerate(all_filings.get('tier_b', []), 1):
            print(f"\n[{i}] {filing['form']} - {filing['filing_date']}")
            print(f"    Accession: {filing['accession']}")
            print(f"    Score: {filing['score']}")
            print(f"    Announce Date: {filing.get('announce_date', 'N/A')}")
            print(f"    Candidate Announce Date: {filing['candidate_announce_date']}")
            print(f"    Reasons: {', '.join(filing['reasons'])}")
        
        print(f"\n{'=' * 70}")
        print("TIER C FILINGS (Score ≤ 2, but ≥ 3 with ratio):")
        print("=" * 70)
        for i, filing in enumerate(all_filings.get('tier_c', []), 1):
            print(f"\n[{i}] {filing['form']} - {filing['filing_date']}")
            print(f"    Accession: {filing['accession']}")
            print(f"    Score: {filing['score']}")
            print(f"    Announce Date: {filing.get('announce_date', 'N/A')}")
            print(f"    Candidate Announce Date: {filing['candidate_announce_date']}")
            print(f"    Reasons: {', '.join(filing['reasons'])}")
        
        if all_filings.get('tier_f'):
            print(f"\n{'=' * 70}")
            print("TIER F FILINGS (Filtered out - no RS keyword/ratio):")
            print("=" * 70)
            for i, filing in enumerate(all_filings.get('tier_f', []), 1):
                print(f"\n[{i}] {filing['form']} - {filing['filing_date']}")
                print(f"    Accession: {filing['accession']}")
                print(f"    Score: {filing['score']}")
                print(f"    Reasons: {', '.join(filing['reasons'])}")
        
        print("=" * 70)


if __name__ == "__main__":
    main()

