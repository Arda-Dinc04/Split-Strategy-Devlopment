"""
Calculate Returns for Reverse Splits
Simple script to calculate returns for [-1, -3, -5, -10, -20, -40, -60] days using Polygon.io
"""

import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
from polygon import RESTClient
import time

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is required. Please set it in your .env file or environment.")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"

def parse_date(date_str):
    """Parse MM/DD/YYYY to datetime"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except:
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d")
        except:
            return None

def get_polygon_data(ticker, split_date, windows):
    """Get price data from Polygon.io"""
    try:
        api_key = os.environ.get('POLYGON_API_KEY')
        if not api_key:
            print(f"  ⚠ POLYGON_API_KEY not set. Please set it as an environment variable.")
            return None
        
        client = RESTClient(api_key)
        
        # Calculate date range needed
        max_window = max(abs(w) for w in windows)
        start_date = split_date - timedelta(days=max_window + 20)  # Extra buffer
        end_date = split_date + timedelta(days=5)
        
        # Convert to timestamps (milliseconds)
        from_ts = int(start_date.timestamp() * 1000)
        to_ts = int(end_date.timestamp() * 1000)
        
        # Get aggregates (daily bars)
        aggs = []
        for agg in client.list_aggs(
            ticker=ticker,
            multiplier=1,
            timespan="day",
            from_=from_ts,
            to=to_ts,
            limit=50000
        ):
            aggs.append(agg)
        
        if not aggs:
            return None
        
        # Convert to DataFrame
        data = []
        for agg in aggs:
            date = datetime.fromtimestamp(agg.timestamp / 1000)
            data.append({
                'Date': date,
                'Open': agg.open,
                'High': agg.high,
                'Low': agg.low,
                'Close': agg.close,
                'Volume': agg.volume,
                'VWAP': agg.vwap if hasattr(agg, 'vwap') else None
            })
        
        df = pd.DataFrame(data)
        df = df.sort_values('Date').reset_index(drop=True)
        
        return df
        
    except Exception as e:
        print(f"  Error fetching Polygon data for {ticker}: {e}")
        return None

def calculate_returns(ticker, split_date, windows):
    """Calculate close-to-close returns for different windows using Polygon.io"""
    try:
        # Get data from Polygon.io
        df = get_polygon_data(ticker, split_date, windows)
        
        if df is None or df.empty:
            return None
        
        # Find split date index (last trading day <= split date)
        split_df = df[df['Date'] <= split_date]
        if len(split_df) == 0:
            return None
        
        split_row = split_df.iloc[-1]
        split_price = split_row['Close']
        split_date_actual = split_row['Date']
        
        # Calculate returns for each window
        returns = {
            'ticker': ticker, 
            'split_date': split_date.strftime('%Y-%m-%d'),
            'split_date_actual': split_date_actual.strftime('%Y-%m-%d')
        }
        
        for window in windows:
            lookback_date = split_date - timedelta(days=abs(window))
            lookback_df = df[df['Date'] <= lookback_date]
            
            if len(lookback_df) > 0:
                lookback_row = lookback_df.iloc[-1]
                lookback_price = lookback_row['Close']
                ret = (split_price / lookback_price - 1) * 100
                returns[f'return_{abs(window)}d'] = round(ret, 2)
            else:
                returns[f'return_{abs(window)}d'] = None
        
        return returns
        
    except Exception as e:
        print(f"  Error calculating returns for {ticker}: {e}")
        return None

def main():
    """Main function"""
    print("="*70)
    print("REVERSE SPLIT RETURNS CALCULATION")
    print("="*70)
    
    # Connect to MongoDB
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    
    # Priority tickers to search for with their split dates
    # If not in DB, you can manually specify dates here
    priority_tickers_config = {
        'LGHL': '07/13/2023',  # From DB
        'WEAT': None,  # Not in DB - need to specify
        'TSORF': None,  # Not in DB - need to specify
        'ATVVF': None,  # Not in DB - need to specify
        'WTO': '09/11/2024',  # From DB
    }
    
    print("\nSearching for priority tickers...")
    splits = []
    
    # Find splits for priority tickers
    for ticker, manual_date in priority_tickers_config.items():
        split = db[REVERSE_COLLECTION].find_one({'Symbol': ticker})
        if split:
            splits.append(split)
            print(f"  ✓ Found {ticker} in DB - Split Date: {split.get('Date')}")
        elif manual_date:
            # Use manually specified date
            splits.append({'Symbol': ticker, 'Date': manual_date})
            print(f"  ✓ Using manual date for {ticker} - Split Date: {manual_date}")
        else:
            print(f"  ⚠ {ticker} not in DB and no manual date - skipping")
    
    if not splits:
        print("\n⚠ No splits found. Please check ticker symbols or add split dates manually.")
        client.close()
        return
    
    windows = [-1, -3, -5, -10, -20, -40, -60]
    results = []
    
    print(f"\nCalculating returns for windows: {[abs(w) for w in windows]} days")
    print("="*70)
    
    for i, split in enumerate(splits, 1):
        symbol = split.get('Symbol', '')
        date_str = split.get('Date', '')
        split_date = parse_date(date_str)
        
        if not symbol:
            continue
        
        # If no split date in DB, try to estimate or use a recent date
        if not split_date:
            print(f"\n[{i}/{len(splits)}] {symbol} - No split date in DB")
            print(f"  ⚠ Need split date to calculate returns. Skipping...")
            continue
        
        print(f"\n[{i}/{len(splits)}] {symbol} - Split Date: {split_date.strftime('%Y-%m-%d')}")
        
        # Rate limiting for Polygon.io (5 calls/min free tier)
        if i > 1:
            time.sleep(12)  # Wait 12 seconds between calls (5 calls/min = 12 sec/call)
        
        result = calculate_returns(symbol, split_date, windows)
        
        if result:
            results.append(result)
            print(f"  ✓ Calculated returns:")
            if result.get('split_date_actual') != result.get('split_date'):
                print(f"    Actual trading date: {result.get('split_date_actual')}")
            for window in windows:
                ret = result.get(f'return_{abs(window)}d')
                if ret is not None:
                    print(f"    {abs(window):3d}d: {ret:7.2f}%")
                else:
                    print(f"    {abs(window):3d}d: N/A")
        else:
            print(f"  ✗ No data available from Polygon.io")
    
    client.close()
    
    # Print results table
    if results:
        print("\n" + "="*70)
        print("RESULTS SUMMARY")
        print("="*70)
        
        df = pd.DataFrame(results)
        
        # Reorder columns
        cols = ['ticker', 'split_date'] + [f'return_{abs(w)}d' for w in windows]
        df = df[cols]
        
        print("\nReturns Table (%):")
        print(df.to_string(index=False))
        
        # Print statistics
        print("\n" + "="*70)
        print("STATISTICS")
        print("="*70)
        
        for window in windows:
            col = f'return_{abs(window)}d'
            valid_returns = df[col].dropna()
            if len(valid_returns) > 0:
                print(f"\n{abs(window):3d} day returns:")
                print(f"  Count:    {len(valid_returns)}")
                print(f"  Mean:     {valid_returns.mean():.2f}%")
                print(f"  Median:   {valid_returns.median():.2f}%")
                print(f"  Min:      {valid_returns.min():.2f}%")
                print(f"  Max:      {valid_returns.max():.2f}%")
                print(f"  Std Dev:  {valid_returns.std():.2f}%")
        
        # Save to CSV
        df.to_csv('reverse_split_returns.csv', index=False)
        print(f"\n✓ Saved results to: reverse_split_returns.csv")
    else:
        print("\n⚠ No results calculated. Many reverse split stocks may be delisted.")
        print("   Try running with different splits or check ticker availability.")

if __name__ == "__main__":
    main()

