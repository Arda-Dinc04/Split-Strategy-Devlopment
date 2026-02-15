"""
Shared utilities for scrapers.
"""
import pandas as pd
from datetime import datetime

# Headers for web scraping
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

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
    if not dataframes:
        print("\nNo data to combine")
        return pd.DataFrame()

    print("\nCombining and deduplicating data...")
    
    # Combine all DataFrames
    combined_df = pd.concat(dataframes, ignore_index=True)
    print(f"  Total rows before deduplication: {len(combined_df)}")
    
    if combined_df.empty:
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
