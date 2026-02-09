from edgar_scraping.edgar_utils import get_company_filings, HEADERS
import json

cik = "0001589149"
print(f"Fetching filings for CIK {cik}...")
data = get_company_filings(cik)

if data:
    recent = data['filings']['recent']
    for i in range(len(recent['accessionNumber'])):
        form = recent['form'][i]
        date = recent['filingDate'][i]
        acc = recent['accessionNumber'][i]
        if "14A" in form or "8-K" in form:
            print(f"{date}: {form} - {acc}")
            # Identify the one around May 2024
