"""
Analyze Reverse Split Metrics using yfinance
Calculates returns, volatility, volume, gaps, MAs, and event flags
"""

import yfinance as yf
import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
from scipy import stats
from sklearn.linear_model import LinearRegression

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is required. Please set it in your .env file or environment.")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"
EDGAR_COLLECTION = "edgar_events"

def connect_db():
    """Connect to MongoDB"""
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    return client, db

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

def get_price_data(ticker, split_date, lookback_days=120):
    """Get price data from yfinance with auto-adjustment"""
    try:
        # Get data from lookback_days before split to split date
        start_date = split_date - timedelta(days=lookback_days)
        end_date = split_date + timedelta(days=5)  # Include a few days after
        
        # Download with auto-adjustment for returns, but keep raw for gaps
        ticker_obj = yf.Ticker(ticker)
        
        # Try to get data, handle various error cases
        try:
            hist = ticker_obj.history(start=start_date, end=end_date, auto_adjust=True, timeout=10)
        except:
            # Try without date restrictions
            hist = ticker_obj.history(period="1y", auto_adjust=True, timeout=10)
            if not hist.empty:
                # Filter to our date range
                hist = hist[(hist.index >= start_date) & (hist.index <= end_date)]
        
        if hist.empty:
            # Try getting more data
            hist = ticker_obj.history(period="2y", auto_adjust=True, timeout=10)
            if not hist.empty:
                hist = hist[hist.index <= end_date]
        
        if hist.empty:
            return None, None
        
        # Also get raw data for gap calculations
        try:
            hist_raw = ticker_obj.history(start=start_date, end=end_date, auto_adjust=False, timeout=10)
        except:
            hist_raw = ticker_obj.history(period="1y", auto_adjust=False, timeout=10)
            if not hist_raw.empty:
                hist_raw = hist_raw[(hist_raw.index >= start_date) & (hist_raw.index <= end_date)]
        
        if hist_raw.empty:
            hist_raw = hist  # Use adjusted as fallback
        
        return hist, hist_raw
    except Exception as e:
        print(f"  Error fetching data for {ticker}: {e}")
        return None, None

def calculate_returns(prices, split_date, windows):
    """Calculate close-to-close returns for different windows"""
    if prices.empty:
        return {}
    
    # Find split date index
    split_idx = prices.index[prices.index <= split_date]
    if len(split_idx) == 0:
        return {}
    
    split_idx = split_idx[-1]  # Last trading day <= split date
    split_price = prices.loc[split_idx, 'Close']
    
    returns = {}
    for window in windows:
        lookback_date = split_date - timedelta(days=abs(window))
        lookback_idx = prices.index[prices.index <= lookback_date]
        
        if len(lookback_idx) > 0:
            lookback_idx = lookback_idx[-1]
            lookback_price = prices.loc[lookback_idx, 'Close']
            ret = (split_price / lookback_price - 1) * 100
            returns[f'return_{abs(window)}d'] = ret
    
    return returns

def calculate_benchmarked_returns(prices, split_date, windows, benchmark_ticker='IWM'):
    """Calculate market-adjusted returns"""
    try:
        benchmark = yf.Ticker(benchmark_ticker)
        start_date = split_date - timedelta(days=max(abs(w) for w in windows) + 10)
        bench_hist = benchmark.history(start=start_date, end=split_date + timedelta(days=5), auto_adjust=True)
        
        if bench_hist.empty:
            return {}
        
        returns = {}
        split_idx = prices.index[prices.index <= split_date]
        if len(split_idx) == 0:
            return {}
        
        split_idx = split_idx[-1]
        split_price = prices.loc[split_idx, 'Close']
        bench_split_idx = bench_hist.index[bench_hist.index <= split_date]
        if len(bench_split_idx) == 0:
            return {}
        bench_split_price = bench_hist.loc[bench_split_idx[-1], 'Close']
        
        for window in windows:
            lookback_date = split_date - timedelta(days=abs(window))
            lookback_idx = prices.index[prices.index <= lookback_date]
            bench_lookback_idx = bench_hist.index[bench_hist.index <= lookback_date]
            
            if len(lookback_idx) > 0 and len(bench_lookback_idx) > 0:
                lookback_idx = lookback_idx[-1]
                bench_lookback_idx = bench_lookback_idx[-1]
                
                stock_ret = (split_price / prices.loc[lookback_idx, 'Close'] - 1) * 100
                bench_ret = (bench_split_price / bench_hist.loc[bench_lookback_idx, 'Close'] - 1) * 100
                returns[f'return_{abs(window)}d_adj'] = stock_ret - bench_ret
        
        return returns
    except Exception as e:
        print(f"  Error calculating benchmarked returns: {e}")
        return {}

def calculate_trend_slope(prices, split_date, windows):
    """Calculate OLS slope of log-price"""
    if prices.empty:
        return {}
    
    split_idx = prices.index[prices.index <= split_date]
    if len(split_idx) == 0:
        return {}
    
    split_idx = split_idx[-1]
    split_pos = prices.index.get_loc(split_idx)
    
    slopes = {}
    for window in windows:
        if split_pos >= window:
            window_data = prices.iloc[split_pos - window:split_pos + 1]
            log_prices = np.log(window_data['Close'].values)
            X = np.arange(len(log_prices)).reshape(-1, 1)
            
            model = LinearRegression()
            model.fit(X, log_prices)
            slopes[f'slope_{window}d'] = model.coef_[0] * 100  # Convert to percentage
    
    return slopes

def calculate_volatility(prices, split_date):
    """Calculate realized volatility and ATR"""
    if prices.empty:
        return {}
    
    split_idx = prices.index[prices.index <= split_date]
    if len(split_idx) == 0:
        return {}
    
    split_idx = split_idx[-1]
    split_pos = prices.index.get_loc(split_idx)
    
    metrics = {}
    
    # Realized volatility (stdev of returns)
    for window in [5, 20]:
        if split_pos >= window:
            window_data = prices.iloc[split_pos - window:split_pos + 1]
            returns = window_data['Close'].pct_change().dropna()
            vol = returns.std() * np.sqrt(252) * 100  # Annualized %
            metrics[f'vol_{window}d'] = vol
    
    # ATR(14)
    if split_pos >= 14:
        window_data = prices.iloc[split_pos - 14:split_pos + 1]
        high_low = window_data['High'] - window_data['Low']
        high_close = abs(window_data['High'] - window_data['Close'].shift())
        low_close = abs(window_data['Low'] - window_data['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.mean()
        metrics['atr_14'] = atr
    
    return metrics

def calculate_volume_metrics(prices, split_date):
    """Calculate volume z-score, ADTV, dollar volume"""
    if prices.empty:
        return {}
    
    split_idx = prices.index[prices.index <= split_date]
    if len(split_idx) == 0:
        return {}
    
    split_idx = split_idx[-1]
    split_pos = prices.index.get_loc(split_idx)
    
    metrics = {}
    
    # Volume z-score vs 20d mean
    if split_pos >= 20:
        window_data = prices.iloc[split_pos - 20:split_pos + 1]
        vol_mean = window_data['Volume'].iloc[:-1].mean()
        vol_std = window_data['Volume'].iloc[:-1].std()
        current_vol = window_data['Volume'].iloc[-1]
        
        if vol_std > 0:
            metrics['vol_z20'] = (current_vol - vol_mean) / vol_std
        else:
            metrics['vol_z20'] = 0
        
        # ADTV(20) - Average Daily Trading Volume
        metrics['adtv_20'] = vol_mean
        
        # Dollar volume 20d
        dollar_vol = (window_data['Close'] * window_data['Volume']).iloc[:-1].mean()
        metrics['dollar_vol_20d'] = dollar_vol
    
    return metrics

def calculate_runup_drawdown(prices, split_date):
    """Calculate max run-up and maximum drawdown"""
    if prices.empty:
        return {}
    
    split_idx = prices.index[prices.index <= split_date]
    if len(split_idx) == 0:
        return {}
    
    split_idx = split_idx[-1]
    split_pos = prices.index.get_loc(split_idx)
    
    metrics = {}
    
    if split_pos >= 20:
        window_data = prices.iloc[split_pos - 20:split_pos + 1]
        close_price = window_data['Close'].iloc[-1]
        
        # Max run-up (peak/close - 1)
        peak = window_data['Close'].max()
        max_runup = (peak / close_price - 1) * 100
        metrics['max_runup_20'] = max_runup
        
        # Maximum drawdown
        cumulative = (1 + window_data['Close'].pct_change()).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative / running_max - 1) * 100
        mdd = drawdown.min()
        metrics['mdd_20'] = mdd
    
    return metrics

def calculate_gap_activity(prices_raw, split_date):
    """Calculate gap activity"""
    if prices_raw is None or prices_raw.empty:
        return {}
    
    split_idx = prices_raw.index[prices_raw.index <= split_date]
    if len(split_idx) == 0:
        return {}
    
    split_idx = split_idx[-1]
    split_pos = prices_raw.index.get_loc(split_idx)
    
    metrics = {}
    
    # Gap-ups in last 10 days
    if split_pos >= 10:
        window_data = prices_raw.iloc[split_pos - 10:split_pos + 1]
        gaps = (window_data['Open'] - window_data['Close'].shift(1)) / window_data['Close'].shift(1) * 100
        gap_ups = (gaps > 0).sum()
        metrics['gap_ups_10d'] = gap_ups
    
    # Average gap% last 5 days
    if split_pos >= 5:
        window_data = prices_raw.iloc[split_pos - 5:split_pos + 1]
        gaps = (window_data['Open'] - window_data['Close'].shift(1)) / window_data['Close'].shift(1) * 100
        avg_gap = gaps.mean()
        metrics['avg_gap_pct_5d'] = avg_gap
    
    return metrics

def calculate_ma_distance(prices, split_date):
    """Calculate distance to moving averages"""
    if prices.empty:
        return {}
    
    split_idx = prices.index[prices.index <= split_date]
    if len(split_idx) == 0:
        return {}
    
    split_idx = split_idx[-1]
    split_pos = prices.index.get_loc(split_idx)
    
    metrics = {}
    current_price = prices.loc[split_idx, 'Close']
    
    for ma_period in [10, 20, 50]:
        if split_pos >= ma_period:
            ma = prices['Close'].iloc[split_pos - ma_period:split_pos + 1].mean()
            distance = ((current_price / ma - 1) * 100)
            metrics[f'ma{ma_period}_distance'] = distance
    
    return metrics

def check_event_flags(symbol, split_date, db):
    """Check for financing, compliance, earnings flags"""
    flags = {
        'financing_flag': False,
        'compliance_flag': False,
        'earnings_flag': False
    }
    
    # Get EDGAR events for this symbol
    split_doc = db[REVERSE_COLLECTION].find_one({'Symbol': symbol, 'Date': split_date.strftime('%m/%d/%Y')})
    if not split_doc:
        return flags
    
    reverse_sa_id = str(split_doc['_id'])
    filings = list(db[EDGAR_COLLECTION].find({'reverse_sa_id': reverse_sa_id}))
    
    # Check filings in lookback window (60 days)
    lookback_start = split_date - timedelta(days=60)
    
    for filing in filings:
        filing_date = datetime.fromisoformat(filing['filing_date'])
        if filing_date >= lookback_start and filing_date <= split_date:
            # Financing flags
            if filing.get('form') in ['S-3', '424B5', '424B3']:
                flags['financing_flag'] = True
            if filing.get('flags', {}).get('financing_flag'):
                flags['financing_flag'] = True
            
            # Compliance flags
            if filing.get('flags', {}).get('compliance_flag'):
                flags['compliance_flag'] = True
    
    # Earnings flag (check if earnings date is within ±5 days)
    # This would require earnings calendar data - placeholder for now
    # flags['earnings_flag'] = check_earnings_date(symbol, split_date)
    
    return flags

def analyze_split(symbol, split_date, db):
    """Analyze a single reverse split"""
    print(f"\n{'='*70}")
    print(f"Analyzing: {symbol} - Split Date: {split_date.strftime('%Y-%m-%d')}")
    print(f"{'='*70}")
    
    # Get price data
    print("  Fetching price data...")
    prices, prices_raw = get_price_data(symbol, split_date)
    
    if prices is None or prices.empty:
        print(f"  ✗ No price data available for {symbol}")
        return None
    
    print(f"  ✓ Got {len(prices)} days of data")
    
    # Calculate all metrics
    results = {
        'symbol': symbol,
        'split_date': split_date.strftime('%Y-%m-%d')
    }
    
    # Returns
    print("  Calculating returns...")
    windows = [-1, -3, -5, -10, -20, -40, -60]
    returns = calculate_returns(prices, split_date, windows)
    results.update(returns)
    
    # Benchmarked returns
    print("  Calculating benchmarked returns...")
    bench_returns = calculate_benchmarked_returns(prices, split_date, windows)
    results.update(bench_returns)
    
    # Trend slopes
    print("  Calculating trend slopes...")
    slopes = calculate_trend_slope(prices, split_date, [20, 60])
    results.update(slopes)
    
    # Volatility
    print("  Calculating volatility...")
    vol_metrics = calculate_volatility(prices, split_date)
    results.update(vol_metrics)
    
    # Volume metrics
    print("  Calculating volume metrics...")
    vol_metrics = calculate_volume_metrics(prices, split_date)
    results.update(vol_metrics)
    
    # Run-up/drawdown
    print("  Calculating run-up/drawdown...")
    runup_metrics = calculate_runup_drawdown(prices, split_date)
    results.update(runup_metrics)
    
    # Gap activity
    print("  Calculating gap activity...")
    gap_metrics = calculate_gap_activity(prices_raw, split_date)
    results.update(gap_metrics)
    
    # MA distances
    print("  Calculating MA distances...")
    ma_metrics = calculate_ma_distance(prices, split_date)
    results.update(ma_metrics)
    
    # Event flags
    print("  Checking event flags...")
    event_flags = check_event_flags(symbol, split_date, db)
    results.update(event_flags)
    
    # Borrowability (placeholder - would need broker API)
    results['borrow_available'] = None
    results['borrow_fee_bps'] = None
    
    return results

def main():
    """Main function"""
    print("="*70)
    print("REVERSE SPLIT METRICS ANALYSIS")
    print("="*70)
    
    # Connect to MongoDB
    client, db = connect_db()
    
    # Get splits from multiple years to find ones with data
    today = datetime.now()
    print(f"\nFetching reverse splits (today: {today.strftime('%Y-%m-%d')})...")
    
    # Try splits from 2023, 2022, 2021 (more likely to have data)
    all_splits = []
    for year in [2023, 2022, 2021, 2024]:
        year_splits = list(db[REVERSE_COLLECTION].find(
            {'Date': {'$regex': f'/{year}$'}}
        ).sort('Date', -1).limit(10))
        all_splits.extend(year_splits)
        print(f"  Found {len(year_splits)} splits from {year}")
    
    splits = all_splits[:30]  # Try up to 30 splits
    print(f"Total splits to try: {len(splits)}")
    
    if not splits:
        print("No splits found!")
        client.close()
        return
    
    print(f"Found {len(splits)} splits to try")
    
    # Analyze each split until we get 5 successful ones
    all_results = []
    for split in splits:
        if len(all_results) >= 5:
            break
            
        symbol = split.get('Symbol', '')
        date_str = split.get('Date', '')
        split_date = parse_date(date_str)
        
        if symbol and split_date:
            result = analyze_split(symbol, split_date, db)
            if result:
                all_results.append(result)
    
    client.close()
    
    # Print results table
    if all_results:
        print("\n" + "="*70)
        print("RESULTS SUMMARY")
        print("="*70)
        
        df = pd.DataFrame(all_results)
        
        # Print key metrics
        print("\nRETURNS (%):")
        return_cols = [col for col in df.columns if col.startswith('return_')]
        print(df[['symbol', 'split_date'] + return_cols].to_string(index=False))
        
        print("\nVOLATILITY & TREND:")
        vol_cols = [col for col in df.columns if 'vol' in col or 'slope' in col or 'atr' in col]
        print(df[['symbol'] + vol_cols].to_string(index=False))
        
        print("\nVOLUME METRICS:")
        volume_cols = [col for col in df.columns if 'vol' in col.lower() and 'return' not in col.lower()]
        print(df[['symbol'] + volume_cols].to_string(index=False))
        
        print("\nRUN-UP / DRAWDOWN:")
        runup_cols = [col for col in df.columns if 'runup' in col or 'mdd' in col]
        print(df[['symbol'] + runup_cols].to_string(index=False))
        
        print("\nGAP ACTIVITY:")
        gap_cols = [col for col in df.columns if 'gap' in col]
        print(df[['symbol'] + gap_cols].to_string(index=False))
        
        print("\nMA DISTANCES (%):")
        ma_cols = [col for col in df.columns if 'ma' in col and 'distance' in col]
        print(df[['symbol'] + ma_cols].to_string(index=False))
        
        print("\nEVENT FLAGS:")
        flag_cols = [col for col in df.columns if 'flag' in col]
        print(df[['symbol'] + flag_cols].to_string(index=False))
        
        # Save to CSV
        df.to_csv('split_metrics_results.csv', index=False)
        print(f"\n✓ Saved full results to: split_metrics_results.csv")

if __name__ == "__main__":
    main()

