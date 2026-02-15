"""
Scoring logic for filings.
"""
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from .utils import parse_date

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
    candidate_announce_date = None
    if announce_date and filing_date:
        announce_dt = parse_date(announce_date)
        filing_dt = parse_date(filing.get("filing_date", ""))
        if announce_dt and filing_dt:
            if announce_dt <= filing_dt:
                candidate_announce_date = announce_date
    
    if not candidate_announce_date:
        candidate_announce_date = filing.get("filing_date")
    
    return {
        "score": score,
        "tier": tier,
        "candidate_announce_date": candidate_announce_date,
        "reasons": reasons,
        "ratio": (ratio_num, ratio_den) if ratio_num and ratio_den else None
    }
