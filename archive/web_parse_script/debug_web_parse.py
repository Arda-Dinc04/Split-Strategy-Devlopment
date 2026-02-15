"""
Debug Web Parse Script
Modified from web_parse.py to only print results and errors, not write to DB.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import os
import sys

# Headers for web scraping
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_stockanalysis_data():
    """Scrape reverse stock split data from StockAnalysis.com"""
    print("\n[TEST] Scraping StockAnalysis.com...")
    url = 'https://stockanalysis.com/actions/splits/'
    data = []
    
    try:
        response = requests.get(url, headers=HEADERS)
        print(f"  Status Code: {response.status_code}")
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all('td')
                    if len(cells) > 1:
                        date_str = cells[0].text.strip()
                        # Just printing first 5 rows for debug
                        if len(data) < 5:
                             print(f"  Sample row: {date_str} - {cells[1].text.strip()}")
                        
                        try:
                            dt = datetime.strptime(date_str, "%b %d, %Y")
                            date = dt.strftime("%m/%d/%Y")
                        except ValueError:
                            date = date_str
                        symbol = cells[1].text.strip()
                        company_name = cells[2].text.strip()
                        split_type = cells[3].text.strip()
                        split_ratio = cells[4].text.strip().replace(" for ", " : ")
                        if "forward" not in split_type.lower():
                            data.append([date, symbol, company_name, split_ratio])
            print(f"  Found {len(data)} reverse splits from StockAnalysis.com")
        else:
            print(f"  Failed to retrieve data. Content snippet: {response.text[:200]}")
    except Exception as e:
        print(f"  Error scraping StockAnalysis.com: {e}")
    
    return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])


def get_tipranks_data():
    """Scrape reverse stock split data from TipRanks.com"""
    print("\n[TEST] Scraping TipRanks.com...")
    url = 'https://www.tipranks.com/calendars/stock-splits/upcoming'
    data = []
    
    try:
        response = requests.get(url, headers=HEADERS)
        print(f"  Status Code: {response.status_code}")
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all('td')
                    if len(cells) > 1:
                        split_date = cells[0].text.strip()
                        if len(data) < 5:
                            print(f"  Sample row: {split_date} - {cells[1].text.strip()}")
                        
                        try:
                            dt = datetime.strptime(split_date, "%b %d, %Y")
                            split_date = dt.strftime("%m/%d/%Y")
                        except ValueError:
                            pass
                        symbol = cells[1].text.strip()
                        company_name = cells[2].text.strip()
                        split_type = cells[3].text.strip()
                        split_ratio = cells[4].text.strip().replace(" for ", " : ")
                        if "forward" not in split_type.lower():
                            data.append([split_date, symbol, company_name, split_ratio])
            print(f"  Found {len(data)} reverse splits from TipRanks.com")
        else:
             print(f"  Failed to retrieve data. Content snippet: {response.text[:200]}")
    except Exception as e:
        print(f"  Error scraping TipRanks.com: {e}")
    
    return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])


def get_hedgefollow_data():
    """Scrape reverse stock split data from HedgeFollow.com using Selenium"""
    print("\n[TEST] Scraping HedgeFollow.com...")
    data = []
    
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set page load timeout to 4 minutes (240 seconds)
        driver.set_page_load_timeout(240)
        
        url = "https://hedgefollow.com/upcoming-stock-splits.php"
        
        try:
            driver.get(url)
        except TimeoutException:
            print("  Timeout loading HedgeFollow.com after 240 seconds")
            driver.quit()
            return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])
        except Exception as e:
            print(f"  Error loading Page: {e}")
            driver.quit()
            return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])
        
        wait = WebDriverWait(driver, 30)
        table = wait.until(EC.presence_of_element_located((By.ID, "latest_splits")))
        
        rows = table.find_elements(By.TAG_NAME, "tr")
        print(f"  Table found with {len(rows)} rows")
        
        for row in rows[1:]:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) == 6:
                stock = cols[0].text.strip()
                split_ratio = cols[3].text.strip()
                ex_date = cols[4].text.strip()
                
                # Check 5 samples
                if len(data) < 5:
                    print(f"  Sample: {stock} {split_ratio} {ex_date}")

                try:
                    a, b = map(int, split_ratio.split(':'))
                    if b > a:
                        try:
                            if ex_date and ex_date != "N/A":
                                ex_date = datetime.strptime(ex_date, '%Y-%m-%d').strftime('%m/%d/%Y')
                            else:
                                continue
                        except ValueError:
                            pass
                        data.append([ex_date, stock, cols[2].text.strip(), split_ratio])
                except (ValueError, AttributeError):
                    continue
        
        driver.quit()
        print(f"  Found {len(data)} reverse splits from HedgeFollow.com")
    except Exception as e:
        print(f"  Error scraping HedgeFollow.com: {e}")
    
    return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])

def main():
    print("STARTING DEBUG RUN")
    
    try:
        get_stockanalysis_data()
    except Exception as e:
        print(f"Error in StockAnalysis: {e}")
        
    try:
        get_tipranks_data()
    except Exception as e:
        print(f"Error in TipRanks: {e}")
        
    try:
        get_hedgefollow_data()
    except Exception as e:
        print(f"Error in HedgeFollow: {e}")
        
    print("DEBUG RUN COMPLETE")

if __name__ == "__main__":
    main()
