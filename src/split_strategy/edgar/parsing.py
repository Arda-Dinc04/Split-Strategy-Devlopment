"""
EDGAR parsing logic.
"""
import re
import math
from datetime import datetime
from typing import Optional, List, Dict

# Forms to include
TARGET_FORMS = ["8-K", "6-K", "DEF 14A", "PRE 14A", "DEFA14A", "14C", "PRE 14C", 
                "S-3", "S-1", "424B5", "424B3", "FWP"]
CONTEXT_FORMS = ["10-Q", "10-K", "20-F"]

TARGET_ITEMS = ["3.01", "5.03", "8.01", "1.01", "3.02"]

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
    
    # Helper to avoid "year-like" ratios (e.g. 2023 for 2024)
    def is_year_like_ratio(num, den):
        current_year = datetime.now().year
        return (2000 <= num <= current_year + 2) and (2000 <= den <= current_year + 2)

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

