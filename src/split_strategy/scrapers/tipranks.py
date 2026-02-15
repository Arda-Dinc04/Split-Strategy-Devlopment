"""
Scraper for TipRanks.com
"""
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from .utils import HEADERS

def get_tipranks_data():
    """Scrape reverse stock split data from TipRanks.com"""
    print("Scraping TipRanks.com...")
    url = 'https://www.tipranks.com/calendars/stock-splits/upcoming'
    data = []
    
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all('td')
                    if len(cells) > 1:
                        split_date = cells[0].text.strip()
                        try:
                            dt = datetime.strptime(split_date, "%b %d, %Y")
                            split_date = dt.strftime("%m/%d/%Y")
                        except ValueError:
                            pass
                        symbol = cells[1].text.strip()
                        company_name = cells[2].text.strip()
                        split_type = cells[3].text.strip()
                        split_ratio = cells[4].text.strip().replace(" for ", " : ")
                        # Only include reverse splits (not forward splits)
                        if "forward" not in split_type.lower():
                            data.append([split_date, symbol, company_name, split_ratio])
            print(f"  Found {len(data)} reverse splits from TipRanks.com")
        else:
            print(f"  Failed to retrieve data. Status code: {response.status_code}")
    except Exception as e:
        print(f"  Error scraping TipRanks.com: {e}")
    
    return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])
