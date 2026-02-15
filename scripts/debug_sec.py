
import requests
import os

# Test URLs
URL_TICKERS = "https://www.sec.gov/files/company_tickers.json"
URL_ARCHIVES = "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR1/company.20260215.idx" # Test non-existent date (weekend)

# Test User-Agents
UA_SIMPLE = "Python-requests/2.31.0"
UA_CONTACT = "Split Strategy Analysis contact@splitstrategy.com"
UA_HYBRID = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 (Split Strategy Analysis contact@splitstrategy.com)"
UA_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

def test_url(name, url, ua):
    headers = {
        "User-Agent": ua,
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov"
    }
    try:
        print(f"Testing {name} with UA: {ua[:50]}...")
        response = requests.get(url, headers=headers, timeout=10)
        print(f"  Status: {response.status_code}")
        if response.status_code == 200:
            print(f"  Success! Size: {len(response.text)} bytes")
        else:
            print(f"  Failed. Reason: {response.reason}")
    except Exception as e:
        print(f"  Error: {e}")

print("--- DIAGNOSTIC START ---")

# 1. Test Tickers (API)
print("\n[Test 1] Company Tickers API (data.sec.gov equivalent)")
test_url("Tickers (Hybrid)", URL_TICKERS, UA_HYBRID)

# 2. Test Archives (Daily Index) with Hybrid UA
print("\n[Test 2] Daily Index (Archives) with Hybrid UA")
test_url("Archives (Hybrid)", URL_ARCHIVES, UA_HYBRID)

# 3. Test Archives with Plain Chrome (No Contact) - violations?
# Only running one request to see if contact info is the blocker
print("\n[Test 3] Daily Index (Archives) with Plain Chrome UA")
test_url("Archives (Chrome)", URL_ARCHIVES, UA_CHROME)

# 4. Test Archives with Simple Contact UA
print("\n[Test 4] Daily Index (Archives) with Simple Contact UA")
test_url("Archives (Contact)", URL_ARCHIVES, UA_CONTACT)

print("\n--- DIAGNOSTIC END ---")
