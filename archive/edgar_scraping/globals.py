
"""
Global constants and prompts for the Early Edgar Scanner.
"""

# Extensive Keyword List for Initial Filtering
SPLIT_KEYWORDS = [
    r"reverse\s+stock\s+split",
    r"reverse\s+split",
    r"stock\s+consolidation",
    r"share\s+consolidation",
    r"consolidation\s+of\s+shares",
    r"share\s+combination",
    r"combining\s+outstanding\s+shares",
    r"exchange\s+ratio",
    r"split\s+ratio",
    r"one-for-[0-9]+",
    r"1-for-[0-9]+",
    r"1\s+for\s+[0-9]+",
    r"1:[0-9]+"
]

def get_analysis_prompt(company: str, context: str, filing_date: str) -> str:
    """
    Generates the LLM prompt for analyzing filing text.
    """
    return f"""
    You are a financial analyst specializing in Corporate Actions.
    Analyze this SEC filing text for {company} (Filed on {filing_date}).
    
    GOAL: Determine if this filing confirms a **FUTURE** REVERSE STOCK SPLIT.
    
    CRITICAL RULES:
    1. **Effective Date Check**:
       - Extract the "effective_date" of the reverse split.
       - If the effective date is BEFORE or ON the filing date ({filing_date}), this is a PAST event.
       - If the text says the split "became effective" or "took effect", it is a PAST event.
       
    2. **Confidence Score**:
       - "High": Explicit confirmation of a **FUTURE** reverse split with a specific ratio and date.
       - "Medium": Confirmed future split but missing exact date or ratio.
       - "Low": Ambiguous language, mere proposal, or **PAST/ALREADY EFFECTIVE split**.
    
    Text Context:
    {context}
    
    Return a JSON object with:
    - "is_reverse_split": boolean (True if it IS a reverse split announcement)
    - "is_future_split": boolean (True ONLY if effective date > {filing_date} or explicitly stated as future)
    - "effective_date": string (YYYY-MM-DD or "Unknown")
    - "ratio": string (e.g., "1-for-10")
    - "rounding_up": boolean (True if fractional shares are rounded UP)
    - "confidence": "High", "Medium", "Low" (Downgrade to Low if is_future_split is False)
    - "summary": One sentence summary (e.g. "1-for-10 split effective on [Date]").
    """
