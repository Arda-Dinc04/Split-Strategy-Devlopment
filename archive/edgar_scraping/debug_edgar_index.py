
import requests
import re
from edgar_scraping.edgar_utils import HEADERS

def check_index(date_str):
    url = f"https://www.sec.gov/Archives/edgar/daily-index/2024/QTR2/company.{date_str}.idx"
    print(f"Checking {url}")
    try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"Failed to fetch {url}: {resp.status_code}")
            return False
            
        print(f"fetched size: {len(resp.content)}")
        # Check for our accession
        acc = "0001493152-24-021403"
        if acc in resp.text:
            print(f"FOUND Accession {acc}!")
            # Print the line
            for line in resp.text.splitlines():
                if acc in line:
                    print(line)
            return True
        else:
            print(f"Accession {acc} NOT found in index.")
            
    except Exception as e:
        print(f"Error: {e}")
        
    return False

# Check Friday 24th
if not check_index("20240524"):
    # Check Tue 28th (Memorial Day on 27th)
    check_index("20240528")

