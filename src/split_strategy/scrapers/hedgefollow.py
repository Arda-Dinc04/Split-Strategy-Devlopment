"""
Scraper for HedgeFollow.com using Selenium
"""
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

def get_hedgefollow_data():
    """Scrape reverse stock split data from HedgeFollow.com using Selenium"""
    print("Scraping HedgeFollow.com (this may take a minute)...")
    data = []
    
    driver = None
    try:
        # Setup Chrome options
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Setup the Chrome driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set page load timeout to 4 minutes (240 seconds)
        driver.set_page_load_timeout(240)
        
        # URL of the webpage to scrape
        url = "https://hedgefollow.com/upcoming-stock-splits.php"
        
        # Open the webpage with error handling
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
        
        # Wait for the table to be present and visible
        wait = WebDriverWait(driver, 30)
        table = wait.until(EC.presence_of_element_located((By.ID, "latest_splits")))
        
        # Iterate over the rows in the table
        for row in table.find_elements(By.TAG_NAME, "tr")[1:]:  # Skip header row
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) == 6:
                stock = cols[0].text.strip()
                company_name = cols[2].text.strip()
                split_ratio = cols[3].text.strip()
                ex_date = cols[4].text.strip()
                
                # Filter for reverse splits (where b > a in split ratio a:b)
                try:
                    a, b = map(int, split_ratio.split(':'))
                    if b > a:  # Reverse split
                        # Convert date format from YYYY-MM-DD to MM/DD/YYYY
                        try:
                            if ex_date and ex_date != "N/A":
                                ex_date = datetime.strptime(ex_date, '%Y-%m-%d').strftime('%m/%d/%Y')
                            else:
                                continue
                        except ValueError:
                            pass
                        data.append([ex_date, stock, company_name, split_ratio])
                except (ValueError, AttributeError):
                    continue
        
        print(f"  Found {len(data)} reverse splits from HedgeFollow.com")
        
    except Exception as e:
        print(f"  Error scraping HedgeFollow.com: {e}")
    finally:
        if driver:
            driver.quit()
    
    return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])
