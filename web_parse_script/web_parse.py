"""
Web Parse Script - Consolidated Stock Split Data Collector
Collects reverse stock split data from 3 web sources and combines into a single dataset.
Pushes results to MongoDB Atlas instead of saving to CSV.
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
from webdriver_manager.chrome import ChromeDriverManager
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from urllib.parse import quote_plus
import os

# MongoDB Configuration - Use environment variables for security
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is required")

MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "split_strategy")
MONGODB_COLLECTION = os.environ.get("MONGODB_COLLECTION", "reverse_splits")

# Headers for web scraping
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def get_stockanalysis_data():
    """Scrape reverse stock split data from StockAnalysis.com"""
    print("Scraping StockAnalysis.com...")
    url = 'https://stockanalysis.com/actions/splits/'
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
                        date_str = cells[0].text.strip()
                        try:
                            dt = datetime.strptime(date_str, "%b %d, %Y")
                            date = dt.strftime("%m/%d/%Y")
                        except ValueError:
                            date = date_str
                        symbol = cells[1].text.strip()
                        company_name = cells[2].text.strip()
                        split_type = cells[3].text.strip()
                        split_ratio = cells[4].text.strip().replace(" for ", " : ")
                        # Only include reverse splits (not forward splits)
                        if "forward" not in split_type.lower():
                            data.append([date, symbol, company_name, split_ratio])
            print(f"  Found {len(data)} reverse splits from StockAnalysis.com")
        else:
            print(f"  Failed to retrieve data. Status code: {response.status_code}")
    except Exception as e:
        print(f"  Error scraping StockAnalysis.com: {e}")
    
    return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])


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


def get_hedgefollow_data():
    """Scrape reverse stock split data from HedgeFollow.com using Selenium"""
    print("Scraping HedgeFollow.com (this may take a minute)...")
    data = []
    
    try:
        # Setup Chrome options
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Setup the Chrome driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # URL of the webpage to scrape
        url = "https://hedgefollow.com/upcoming-stock-splits.php"
        
        # Open the webpage
        driver.get(url)
        
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
        
        # Close the browser
        driver.quit()
        print(f"  Found {len(data)} reverse splits from HedgeFollow.com")
    except Exception as e:
        print(f"  Error scraping HedgeFollow.com: {e}")
    
    return pd.DataFrame(data, columns=['Date', 'Symbol', 'Company Name', 'Split Ratio'])


def convert_to_datetime(date_str):
    """Convert date format from MM/DD/YYYY to datetime object"""
    if pd.isna(date_str) or not date_str:
        return None
    
    # Use pandas to_datetime which handles multiple formats flexibly
    try:
        return pd.to_datetime(date_str, format='%m/%d/%Y', errors='coerce')
    except (ValueError, TypeError):
        return None


def combine_and_deduplicate_dataframes(dataframes):
    """Combine multiple DataFrames and keep only the most recent date for each symbol"""
    print("\nCombining and deduplicating data...")
    
    # Combine all DataFrames
    combined_df = pd.concat(dataframes, ignore_index=True)
    print(f"  Total rows before deduplication: {len(combined_df)}")
    
    if combined_df.empty:
        print("  No data to combine")
        return combined_df
    
    # Convert Date column to datetime for comparison
    combined_df['Date'] = combined_df['Date'].apply(convert_to_datetime)
    
    # Remove rows with invalid dates
    combined_df = combined_df[combined_df['Date'].notna()]
    
    if combined_df.empty:
        print("  No valid dates found")
        return combined_df
    
    # Get the most recent date for each unique symbol
    most_recent_df = combined_df.loc[combined_df.groupby('Symbol')['Date'].idxmax()]
    
    # Sort by Date in descending order
    most_recent_df = most_recent_df.sort_values(by='Date', ascending=False)
    
    # Convert Date column back to MM/DD/YYYY format
    most_recent_df['Date'] = most_recent_df['Date'].dt.strftime('%m/%d/%Y')
    
    print(f"  Total rows after deduplication: {len(most_recent_df)}")
    print(f"  Unique symbols: {most_recent_df['Symbol'].nunique()}")
    
    return most_recent_df


def push_to_mongodb(df):
    """Push DataFrame data to MongoDB Atlas"""
    print("\nConnecting to MongoDB Atlas...")
    
    try:
        # Connect to MongoDB
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        print("✓ Successfully connected to MongoDB Atlas")
        
        # Get database and collection
        db = client[MONGODB_DATABASE]
        collection = db[MONGODB_COLLECTION]
        
        # Convert DataFrame to list of dictionaries
        records = df.to_dict('records')
        
        # Insert/Update records (upsert based on Symbol and Date)
        inserted_count = 0
        updated_count = 0
        
        for record in records:
            # Create filter for upsert (unique combination of Symbol and Date)
            filter_query = {
                'Symbol': record['Symbol'],
                'Date': record['Date']
            }
            
            # Add timestamp for when record was last updated
            record['last_updated'] = datetime.utcnow()
            
            # Upsert the record
            result = collection.update_one(
                filter_query,
                {'$set': record},
                upsert=True
            )
            
            if result.upserted_id:
                inserted_count += 1
            else:
                updated_count += 1
        
        print(f"\n✓ Successfully pushed data to MongoDB:")
        print(f"  Database: {MONGODB_DATABASE}")
        print(f"  Collection: {MONGODB_COLLECTION}")
        print(f"  New records inserted: {inserted_count}")
        print(f"  Existing records updated: {updated_count}")
        print(f"  Total records processed: {len(records)}")
        
        # Close connection
        client.close()
        return True
        
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(f"\n✗ Failed to connect to MongoDB Atlas: {e}")
        print("  Please check your connection string and network access.")
        return False
    except Exception as e:
        print(f"\n✗ Error pushing data to MongoDB: {e}")
        return False


def main():
    """Main function to collect data from all sources and save combined result"""
    print("=" * 70)
    print("Stock Split Data Collector - Starting data collection")
    print("=" * 70)
    
    # Collect data from all sources (keep in memory, no intermediate saves)
    dataframes = []
    
    # 1. StockAnalysis.com
    df_stockanalysis = get_stockanalysis_data()
    if not df_stockanalysis.empty:
        dataframes.append(df_stockanalysis)
    
    # 2. TipRanks.com
    df_tipranks = get_tipranks_data()
    if not df_tipranks.empty:
        dataframes.append(df_tipranks)
    
    # 3. HedgeFollow.com
    df_hedgefollow = get_hedgefollow_data()
    if not df_hedgefollow.empty:
        dataframes.append(df_hedgefollow)
    
    # Combine and deduplicate
    if not dataframes:
        print("\nNo data collected from any source!")
        return
    
    final_df = combine_and_deduplicate_dataframes(dataframes)
    
    # Push to MongoDB instead of saving to CSV
    if not final_df.empty:
        print(f"\nFinal dataset summary:")
        print(f"  Total rows: {len(final_df)}")
        print(f"  Date range: {final_df['Date'].min()} to {final_df['Date'].max()}")
        
        # Push to MongoDB
        success = push_to_mongodb(final_df)
        
        if not success:
            print("\n⚠ Warning: Failed to push to MongoDB. Consider saving to CSV as backup.")
            # Optional: Save to CSV as backup if MongoDB fails
            backup_path = '/Users/ardadinc/Desktop/Market-Insight/DiscordBot/RevSplitBotVersion/web_parse_script/ALL_RS_SPLITS_backup.csv'
            final_df.to_csv(backup_path, index=False)
            print(f"  Backup saved to: {backup_path}")
    else:
        print("\nNo data to push - final DataFrame is empty")
    
    print("\n" + "=" * 70)
    print("Data collection complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()

