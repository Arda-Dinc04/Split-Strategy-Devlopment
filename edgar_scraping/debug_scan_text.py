
import requests
import re
from bs4 import BeautifulSoup
from edgar_scraping.edgar_utils import HEADERS, check_split_proposal_flag

url = "https://www.sec.gov/Archives/edgar/data/1589149/0001493152-24-012440.txt"
print(f"Fetching {url}...")
resp = requests.get(url, headers=HEADERS)
soup = BeautifulSoup(resp.text, 'html.parser')
text = soup.get_text(separator=' ', strip=True)

print(f"Text length: {len(text)}")
print("-" * 20)
print("Running check_split_proposal_flag...")
result = check_split_proposal_flag(text)
print(f"Result: {result}")

if not result:
    print("-" * 20)
    print("Searching for 'reverse' keywords manually:")
    # Print context around "reverse stock split"
    matches = list(re.finditer(r"reverse\s+stock\s+split", text, re.IGNORECASE))
    print(f"Found {len(matches)} occurrences of 'reverse stock split'")
    for i, m in enumerate(matches[:5]):
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 100)
        print(f"Match {i+1}: ...{text[start:end]}...")
        
    print("-" * 20)
    print("Searching for 'Proposal' headers:")
    matches = list(re.finditer(r"Proposal\s+\d", text, re.IGNORECASE))
    for i, m in enumerate(matches[:5]):
        start = max(0, m.start() - 50)
        end = min(len(text), m.end() + 200)
        print(f"Proposal {i+1}: ...{text[start:end]}...")
