"""
Financial analysis and return calculations.
"""
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import traceback

def get_stock_price_data(ticker: str, days: int = 7):
    """Get recent stock price data using yfinance"""
    try:
        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(period=f"{days}d")
        
        if hist.empty:
            # Fallback to 1mo
            hist = ticker_obj.history(period="1mo")
        
        if hist.empty:
            return None
            
        return pd.DataFrame({
            'Price': hist['Close'].values
        }, index=hist.index)
        
    except Exception as e:
        print(f"Error getting stock data for {ticker}: {e}")
        return None

def get_current_price(ticker: str):
    """Get current/last available price for a ticker"""
    try:
        ticker_obj = yf.Ticker(ticker)
        # Try info first
        try:
            info = ticker_obj.info
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
            if current_price:
                return float(current_price)
        except:
            pass
        
        # Fallback to history
        try:
            hist = ticker_obj.history(period="5d")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except:
            pass
        
        return None
    except:
        return None

def get_stock_price_data_around_split(ticker: str, split_date: datetime, days_before: int = 30, days_after: int = 10):
    """Get price data around split date and calculate returns"""
    try:
        ticker_obj = yf.Ticker(ticker)
        
        # Calculate date range
        start_date = split_date - timedelta(days=days_before)
        end_date = split_date + timedelta(days=days_after)
        
        # Get historical data
        hist = ticker_obj.history(start=start_date, end=end_date)
        
        if hist.empty:
            # Try longer period
            hist = ticker_obj.history(period="3mo")
            if not hist.empty:
                # Filter to our date range
                hist = hist[(hist.index >= start_date) & (hist.index <= end_date)]
        
        if hist.empty:
            return None, None
        
        # Format for chart
        chart_df = pd.DataFrame({
            'Price': hist['Close'].values
        }, index=hist.index)
        
        # Calculate returns relative to split date
        # Find closest trading day <= split date
        split_date_only = split_date.date() if isinstance(split_date, datetime) else split_date
        split_trading_days = hist.index[hist.index.date <= split_date_only]
        
        if len(split_trading_days) == 0:
            return chart_df, None
        
        split_idx = split_trading_days[-1]
        split_price = hist.loc[split_idx, 'Close']
        
        # Calculate returns for windows before split
        return_windows = [-20, -10, -5, -3, -1]
        returns = {}
        
        for window in return_windows:
            lookback_date = split_date - timedelta(days=abs(window))
            lookback_days = hist.index[hist.index.date <= lookback_date.date()]
            
            if len(lookback_days) > 0:
                lookback_idx = lookback_days[-1]
                lookback_price = hist.loc[lookback_idx, 'Close']
                ret = (split_price / lookback_price - 1) * 100
                returns[f'{abs(window)}d_before'] = round(ret, 2)
            else:
                returns[f'{abs(window)}d_before'] = None
        
        # Calculate returns after split (if data available)
        after_split_days = hist.index[hist.index.date > split_date_only]
        if len(after_split_days) > 0:
            # Try 1d, 3d, 5d, 10d after
            for days_after_window in [1, 3, 5, 10]:
                target_date = split_date + timedelta(days=days_after_window)
                target_days = hist.index[hist.index.date <= target_date.date()]
                
                if len(target_days) > 0:
                    target_idx = target_days[-1]
                    target_price = hist.loc[target_idx, 'Close']
                    ret = (target_price / split_price - 1) * 100
                    returns[f'{days_after_window}d_after'] = round(ret, 2)
                else:
                    returns[f'{days_after_window}d_after'] = None
        
        returns['split_date'] = split_date.strftime('%Y-%m-%d')
        returns['split_price'] = round(split_price, 4)
        
        return chart_df, returns
        
    except Exception as e:
        print(f"Error getting price data for {ticker}: {str(e)[:200]}")
        return None, None
