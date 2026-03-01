import sys
from pathlib import Path
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
import time

current_dir = Path(__file__).resolve().parent
csv_path = current_dir.parent / 'DATA' / 'split_performance.csv'

def main():
    if not csv_path.exists():
        print(f"No tracking CSV found at {csv_path}. Nothing to update.")
        return
        
    print(f"Loading {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # Ensure tracking columns exist
    if 'price_announce_close' not in df.columns:
        df['price_announce_close'] = pd.NA
    if 'price_next_open' not in df.columns:
        df['price_next_open'] = pd.NA
    if 'split_happened' not in df.columns:
        df['split_happened'] = pd.NA
    if 'execution_date_accurate' not in df.columns:
        df['execution_date_accurate'] = pd.NA
        
    updated = False
    
    for index, row in df.iterrows():
        ticker = row['ticker']
        filing_date = row['filing_date']
        effective_date = row.get('effective_date')
        
        # Skip unknown tickers
        if pd.isna(ticker) or ticker == "UNKNOWN":
            continue
            
        ticker_obj = yf.Ticker(ticker)
        
        # Update Prices if missing
        needs_price = pd.isna(row['price_announce_close']) or pd.isna(row['price_next_open'])
        if needs_price:
            try:
                print(f"Fetching price history for {ticker} starting {filing_date}...")
                hist = ticker_obj.history(start=filing_date, period="5d")
                
                if not hist.empty and len(hist) >= 2:
                    announce_close = hist.iloc[0]['Close']
                    next_open = hist.iloc[1]['Open']
                    
                    df.at[index, 'price_announce_close'] = round(announce_close, 4)
                    df.at[index, 'price_next_open'] = round(next_open, 4)
                    updated = True
                    print(f"  -> Discovered prices: Close {announce_close:.2f} | Next Open {next_open:.2f}")
                else:
                    print(f"  -> Not enough historical data available yet for {ticker}.")
            except Exception as e:
                print(f"  -> Error fetching prices for {ticker}: {e}")
                
        # Update Split boolean and Accuracy
        if pd.isna(row['split_happened']) or pd.isna(row.get('execution_date_accurate')):
            try:
                splits = ticker_obj.splits
                if not splits.empty:
                    filing_dt = pd.to_datetime(filing_date).tz_localize(splits.index.tz)
                    recent_splits = splits[splits.index >= filing_dt]
                    
                    if not recent_splits.empty:
                        df.at[index, 'split_happened'] = True
                        updated = True
                        
                        # Check if it happened exactly on our predicted effective_date
                        if pd.notna(effective_date) and effective_date != "UNKNOWN":
                            try:
                                actual_split_date = recent_splits.index[0].strftime("%m/%d/%Y") 
                                proj_dt = pd.to_datetime(effective_date)
                                proj_date_str = proj_dt.strftime("%m/%d/%Y")
                                
                                is_accurate = (actual_split_date == proj_date_str)
                                df.at[index, 'execution_date_accurate'] = is_accurate
                                print(f"  -> Verified split execution for {ticker}! (On Time: {is_accurate})")
                            except Exception as date_e:
                                print(f"  -> Split happened, but could not parse effective_date format: {effective_date}")
                                print(f"  -> Verified split execution for {ticker}!")
                        else:
                            print(f"  -> Verified split execution for {ticker}!")
            except Exception as e:
                print(f"  -> Error checking split history for {ticker}: {e}")
                
        time.sleep(0.5)  # Rate limiting safety
        
    if updated:
        df.to_csv(csv_path, index=False)
        print(f"\nSaved updated metrics to {csv_path}")
    else:
        print("\nAll metrics are up to date.")

if __name__ == "__main__":
    main()
