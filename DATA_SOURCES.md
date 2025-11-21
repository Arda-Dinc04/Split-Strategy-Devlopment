# Alternative Data Sources for Stock Price Data

Since yfinance doesn't support many OTC/pink sheet and delisted stocks, here are alternative options:

## Free/Cheap Options

### 1. **Alpha Vantage** (Free tier: 5 calls/min, 500 calls/day)
- **API**: https://www.alphavantage.co/
- **Coverage**: Good for OTC stocks
- **Python library**: `alpha_vantage`
- **Example**:
```python
from alpha_vantage.timeseries import TimeSeries
ts = TimeSeries(key='YOUR_API_KEY', output_format='pandas')
data, meta = ts.get_daily_adjusted(symbol='LGHL', outputsize='full')
```

### 2. **Polygon.io** (Free tier: 5 calls/min)
- **API**: https://polygon.io/
- **Coverage**: Excellent for OTC/pink sheets
- **Python library**: `polygon-api-client`
- **Example**:
```python
from polygon import RESTClient
client = RESTClient('YOUR_API_KEY')
aggs = client.get_aggs('LGHL', multiplier=1, timespan='day', 
                       from_='2023-01-01', to='2023-12-31')
```

### 3. **Quandl/Nasdaq Data Link** (Some free datasets)
- **API**: https://data.nasdaq.com/
- **Coverage**: Good historical data
- **Python library**: `quandl`

### 4. **Finnhub** (Free tier: 60 calls/min)
- **API**: https://finnhub.io/
- **Coverage**: Good for OTC stocks
- **Python library**: `finnhub-python`
- **Example**:
```python
import finnhub
finnhub_client = finnhub.Client(api_key="YOUR_API_KEY")
data = finnhub_client.stock_candles('LGHL', 'D', 1672531200, 1696118400)
```

### 5. **IEX Cloud** (Free tier: 50,000 messages/month)
- **API**: https://iexcloud.io/
- **Coverage**: Good for US stocks
- **Python library**: `iexfinance` or `pyEX`

## Broker APIs (If you have accounts)

### 6. **Interactive Brokers (IBKR)**
- **API**: TWS API or IB Gateway
- **Coverage**: Excellent for OTC/pink sheets
- **Python library**: `ib_insync` or `ibapi`
- **Note**: Requires IB account and TWS/Gateway running

### 7. **TD Ameritrade** (Now Schwab)
- **API**: TD Ameritrade API
- **Coverage**: Good for OTC stocks
- **Python library**: `tda-api`

### 8. **Alpaca Markets**
- **API**: https://alpaca.markets/
- **Coverage**: Good for US stocks
- **Python library**: `alpaca-trade-api`

## Paid Professional Options

### 9. **Bloomberg Terminal API**
- **Coverage**: Comprehensive
- **Cost**: Very expensive
- **Python library**: `blpapi`

### 10. **Refinitiv (formerly Thomson Reuters)**
- **Coverage**: Comprehensive
- **Cost**: Expensive
- **Python library**: `refinitiv-data`

### 11. **Yahoo Finance Premium** (via RapidAPI)
- **API**: https://rapidapi.com/apidojo/api/yahoo-finance1
- **Coverage**: Better than free yfinance
- **Cost**: Pay-per-use

## Direct Exchange Data

### 12. **OTC Markets**
- **Website**: https://www.otcmarkets.com/
- **API**: OTC Markets API (paid)
- **Coverage**: Best for OTC stocks specifically

### 13. **SEC EDGAR** (For historical filings)
- **API**: Free SEC API
- **Coverage**: Historical data in filings
- **Note**: You already use this for EDGAR data

## Recommended Approach

For your use case (reverse splits, many OTC/delisted stocks):

1. **Start with Polygon.io** - Best free tier for OTC stocks
2. **Add Alpha Vantage** - Good backup, free tier
3. **Consider IBKR API** - If you have an account, best for OTC
4. **Use multiple sources** - Fallback chain for reliability

## Implementation Example

I can help you integrate any of these. Here's a quick example structure:

```python
def get_price_data_multi_source(ticker, start_date, end_date):
    # Try Polygon first
    try:
        return get_polygon_data(ticker, start_date, end_date)
    except:
        pass
    
    # Fallback to Alpha Vantage
    try:
        return get_alphavantage_data(ticker, start_date, end_date)
    except:
        pass
    
    # Fallback to Finnhub
    try:
        return get_finnhub_data(ticker, start_date, end_date)
    except:
        pass
    
    return None
```

Would you like me to:
1. Integrate Polygon.io API?
2. Integrate Alpha Vantage API?
3. Set up a multi-source fallback system?
4. Help you get API keys for any of these?


