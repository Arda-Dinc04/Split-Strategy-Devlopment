"""
Streamlit Dashboard for Recent Reverse Splits
Shows recent reverse splits with rounding flag from EDGAR filings
"""

import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
import os
import sys
from bson import ObjectId
import yfinance as yf
import time

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use environment variables directly

# Import EDGAR processing functions
from edgar_workflow_complete import get_cik_mapping_with_names
from process_reverse_splits_edgar import process_reverse_split_with_edgar

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    st.error("❌ MONGODB_URI environment variable is required!")
    st.info("💡 For local development: Create a `.env` file with `MONGODB_URI=your_connection_string`")
    st.info("💡 For Streamlit Cloud: Add `MONGODB_URI` in app settings → Secrets")
    st.stop()
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_splits"  # Changed from reverse_sa
EDGAR_COLLECTION = "reverse_splits_edgar"  # Changed from edgar_events

# Cache CIK mapping
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_cik_mappings():
    """Get CIK mappings (cached)"""
    return get_cik_mapping_with_names()

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

def check_rounding_flag(reverse_splits_id: str, db) -> bool:
    """Check if any EDGAR filing has rounding_up_flag=True"""
    edgar_filings = list(db[EDGAR_COLLECTION].find({"reverse_splits_id": reverse_splits_id}))
    
    for filing in edgar_filings:
        flags = filing.get("flags", {})
        if flags.get("rounding_up_flag", False):
            return True
    
    return False

def get_rounding_filings(reverse_splits_id: str, db) -> list:
    """Get all EDGAR filings with rounding_up_flag=True"""
    edgar_filings = list(db[EDGAR_COLLECTION].find({"reverse_splits_id": reverse_splits_id}))
    
    rounding_filings = []
    for filing in edgar_filings:
        flags = filing.get("flags", {})
        if flags.get("rounding_up_flag", False):
            rounding_filings.append({
                "form": filing.get("form", "Unknown"),
                "filing_date": filing.get("filing_date", ""),
                "document_url": filing.get("document_url", ""),
                "rounding_text": filing.get("text_matches", {}).get("rounding_text", ""),
                "accession": filing.get("accession", ""),
                "cik": filing.get("cik", "")
            })
    
    return rounding_filings

def get_stock_price_data_around_split(ticker: str, split_date: datetime, days_before: int = 30, days_after: int = 10):
    """Get price data around split date and calculate returns"""
    import traceback
    
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

# TEMP: Disable cache to debug yfinance issues - cache might be caching None/empty results
# @st.cache_data(ttl=300)  # Cache for 5 minutes
def get_stock_price_data(ticker: str, days: int = 7):
    """Get recent stock price data using yfinance (free)"""
    import traceback
    
    print(f"\n{'='*60}")
    print(f"🔍 FETCHING DATA FOR {ticker}")
    print(f"{'='*60}")
    
    try:
        print(f"Step 1: Creating Ticker object...")
        ticker_obj = yf.Ticker(ticker)
        print(f"   ✅ Ticker object created: {type(ticker_obj)}")
        
        print(f"Step 2: Calling history(period='{days}d')...")
        hist = ticker_obj.history(period=f"{days}d")
        print(f"   ✅ History call returned")
        print(f"   - Type: {type(hist)}")
        print(f"   - Is DataFrame: {isinstance(hist, pd.DataFrame)}")
        
        if isinstance(hist, pd.DataFrame):
            print(f"   - Empty: {hist.empty}")
            print(f"   - Shape: {hist.shape}")
            print(f"   - Columns: {list(hist.columns) if not hist.empty else 'N/A'}")
            
            if not hist.empty:
                print(f"   - First date: {hist.index[0]}")
                print(f"   - Last date: {hist.index[-1]}")
                print(f"   - Sample Close values: {hist['Close'].head(3).tolist()}")
        
        if hist.empty or not isinstance(hist, pd.DataFrame):
            print(f"Step 3: Trying 1mo fallback...")
            try:
                hist = ticker_obj.history(period="1mo")
                print(f"   ✅ 1mo history retrieved")
                print(f"   - Empty: {hist.empty}")
                print(f"   - Shape: {hist.shape}")
            except Exception as e2:
                print(f"   ❌ 1mo failed: {str(e2)}")
                print(f"   Traceback: {traceback.format_exc()[:400]}")
                return None
        
        if hist.empty or not isinstance(hist, pd.DataFrame):
            print(f"   ⚠️  History is empty or not a DataFrame")
            # Try to get info to see if ticker exists
            try:
                print(f"Step 4: Checking ticker info...")
                info = ticker_obj.info
                print(f"   ✅ Info available: symbol={info.get('symbol', 'N/A')}")
            except Exception as e_info:
                print(f"   ❌ Info failed: {str(e_info)[:200]}")
            return None
        
        print(f"Step 5: Formatting DataFrame...")
        # Return DataFrame with Close column, properly formatted for Streamlit
        result = pd.DataFrame({
            'Price': hist['Close'].values
        }, index=hist.index)
        
        print(f"   ✅ Formatted DataFrame created")
        print(f"   - Shape: {result.shape}")
        print(f"   - Columns: {list(result.columns)}")
        print(f"   - Data points: {len(result)}")
        print(f"   - Price range: ${result['Price'].min():.2f} - ${result['Price'].max():.2f}")
        print(f"✅ SUCCESS [{ticker}]: Got {len(result)} data points")
        return result
        
    except Exception as e:
        print(f"   ❌ FATAL ERROR: {str(e)}")
        print(f"   Full traceback:")
        print(traceback.format_exc()[:800])
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
        except Exception as e1:
            pass  # Info failed, try history
        
        # Fallback to history
        try:
            hist = ticker_obj.history(period="5d")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception as e2:
            pass  # History also failed
        
        return None
    except Exception as e:
        # Log but don't show warning for every ticker (too noisy)
        return None

def has_edgar_data(reverse_splits_id: str, db) -> bool:
    """Check if split has any EDGAR filings"""
    count = db[EDGAR_COLLECTION].count_documents({"reverse_splits_id": reverse_splits_id})
    return count > 0

def process_splits_without_edgar(splits_to_process, cik_mappings):
    """Process splits without EDGAR data"""
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, split_info in enumerate(splits_to_process):
        symbol = split_info["Symbol"]
        status_text.text(f"Processing {symbol} ({i+1}/{len(splits_to_process)})...")
        
        try:
            result = process_reverse_split_with_edgar(
                split_info["split_doc"], 
                cik_mappings["ticker"], 
                cik_mappings["name"],
                skip_existing=False
            )
            results.append({"symbol": symbol, "status": "success", "result": result})
        except Exception as e:
            results.append({"symbol": symbol, "status": "error", "error": str(e)})
        
        progress_bar.progress((i + 1) / len(splits_to_process))
    
    progress_bar.empty()
    status_text.empty()
    return results

def main():
    st.set_page_config(
        page_title="Reverse Splits Dashboard",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Recent Reverse Splits Dashboard")
    
    # Add refresh button to clear cache
    col1, col2 = st.columns([1, 10])
    with col1:
        if st.button("🔄 Refresh", help="Clear cache and reload data from MongoDB"):
            st.cache_data.clear()
            st.rerun()
    
    # DEBUG: Environment check
    with st.expander("🔍 Environment Debug Info", expanded=False):
        st.code(f"PYTHON EXECUTABLE: {sys.executable}")
        st.code(f"PYTHON VERSION: {sys.version}")
        st.code(f"PYTHON PATH (first 5): {sys.path[:5]}")
        try:
            st.code(f"YFINANCE VERSION: {yf.__version__}")
        except:
            st.code("YFINANCE VERSION: Unable to get version")
        
        # Test direct yfinance call
        st.markdown("**Direct yfinance Test:**")
        try:
            test_ticker = yf.Ticker("AAPL")
            test_hist = test_ticker.history(period="7d")
            if not test_hist.empty:
                st.success(f"✅ Direct yfinance test PASSED - Got {len(test_hist)} data points")
                st.dataframe(test_hist[['Close']].tail(3))
            else:
                st.error("❌ Direct yfinance test FAILED - Empty DataFrame")
        except Exception as e:
            st.error(f"❌ Direct yfinance test FAILED - Error: {str(e)[:300]}")
            import traceback
            st.code(traceback.format_exc()[:500])
    
    st.markdown("---")
    
    # Connect to MongoDB
    try:
        client = MongoClient(MONGODB_URI)
        db = client[MONGODB_DATABASE]
        reverse_collection = db[REVERSE_COLLECTION]
        edgar_collection = db[EDGAR_COLLECTION]
    except Exception as e:
        st.error(f"Error connecting to MongoDB: {e}")
        return
    
    # Get date range - Show splits from 3 days ago onwards (including all future dates)
    today = datetime.now().date()
    three_days_ago = today - timedelta(days=3)
    
    # Query ALL splits (we'll filter by date below)
    splits = list(reverse_collection.find({}).sort("Date", -1))
    
    # Filter and process splits
    recent_splits = []
    for split in splits:
        split_date_str = split.get("Date", "")
        split_date = parse_date(split_date_str)
        
        if not split_date:
            continue
        
        # Only include splits from 3 days ago onwards (including ALL future dates)
        split_date_only = split_date.date()
        if split_date_only >= three_days_ago:
            reverse_splits_id = str(split.get("_id"))
            
            # Check if has EDGAR data
            has_edgar = has_edgar_data(reverse_splits_id, db)
            
            # Check rounding flag
            rounding = False
            if has_edgar:
                rounding = check_rounding_flag(reverse_splits_id, db)
            
            # Get rounding filings if rounding flag is True
            rounding_filings = []
            if rounding:
                rounding_filings = get_rounding_filings(reverse_splits_id, db)
            
            recent_splits.append({
                "Date": split_date_str,
                "Symbol": split.get("Symbol", ""),
                "Company Name": split.get("Company Name", ""),
                "Split Ratio": split.get("Split Ratio", ""),
                "Rounding": "Yes" if rounding else "",
                "Has EDGAR": has_edgar,
                "reverse_splits_id": reverse_splits_id,
                "split_date_obj": split_date_only,
                "split_doc": split,
                "rounding_filings": rounding_filings  # Store filings for display
            })
    
    # Debug: Show what we found
    with st.expander("🔍 Debug: MongoDB Query Results", expanded=False):
        st.write(f"**Total splits in collection:** {reverse_collection.count_documents({})}")
        st.write(f"**Splits after date filter (>= {three_days_ago}):** {len(recent_splits)}")
        st.write(f"**Date range filter:** {three_days_ago} to future")
        
        # Show sample dates from MongoDB
        sample_docs = list(reverse_collection.find({}, {"Date": 1, "Symbol": 1}).sort("Date", -1).limit(10))
        st.write("**Sample dates from MongoDB (most recent 10):**")
        for doc in sample_docs:
            st.write(f"  - {doc.get('Date', 'N/A')} | {doc.get('Symbol', 'N/A')}")
    
    # Create tabs for different views
    tab1, tab2 = st.tabs(["📉 Confirmed Splits", "⚠️ Early Warnings"])
    
    with tab1:
        if not recent_splits:
            st.info("No recent reverse splits found (from 3 days ago to future).")
        else:
            # Sort by date (most recent first)
            recent_splits.sort(key=lambda x: x["split_date_obj"], reverse=True)
            
            # Identify splits that need EDGAR processing
            splits_to_process = [s for s in recent_splits if not s["Has EDGAR"]]
            
            # Process splits without EDGAR data
            if splits_to_process:
                st.warning(f"⚠️ Found {len(splits_to_process)} split(s) without EDGAR data.")
                
                if st.button(f"🔍 Process EDGAR Data for {len(splits_to_process)} Split(s)", type="primary"):
                    cik_mappings = get_cik_mappings()
                    results = process_splits_without_edgar(splits_to_process, cik_mappings)
                    
                    # Show results
                    success_count = sum(1 for r in results if r["status"] == "success")
                    st.success(f"✅ Processed {success_count}/{len(results)} splits successfully!")
                    
                    # Refresh to show updated data
                    st.rerun()
                
                # Show which splits need processing
                with st.expander(f"View {len(splits_to_process)} splits needing EDGAR processing"):
                    missing_df = pd.DataFrame([
                        {
                            "Symbol": s["Symbol"],
                            "Date": s["Date"],
                            "Company Name": s["Company Name"]
                        }
                        for s in splits_to_process
                    ])
                    st.dataframe(missing_df, use_container_width=True, hide_index=True)
            
            # Prepare DataFrame for display
            display_data = []
            for split_info in recent_splits:
                # Determine if should highlight (within last 3 days)
                is_recent = split_info["split_date_obj"] >= three_days_ago and split_info["split_date_obj"] <= today
                
                display_data.append({
                    "Date": split_info["Date"],
                    "Symbol": split_info["Symbol"],
                    "Company Name": split_info["Company Name"],
                    "Split Ratio": split_info["Split Ratio"],
                    "Rounding": split_info["Rounding"],
                    "_highlight": is_recent
                })
            
            df = pd.DataFrame(display_data)
            
            # Remove highlight column before display
            highlight_mask = df.pop("_highlight")
            
            # Display table with highlighting
            st.subheader(f"Recent Reverse Splits ({len(recent_splits)} total)")
            st.caption(f"Showing splits from {three_days_ago.strftime('%Y-%m-%d')} onwards. Highlighted rows are within the last 3 days.")
            
            # Style the dataframe with better contrast and readability
            def highlight_recent(row):
                if row.name < len(highlight_mask) and highlight_mask.iloc[row.name]:
                    # Highlight recent rows with a subtle blue background and bold black text
                    return ['background-color: #e3f2fd; color: #000000; font-weight: 600'] * len(row)
                # Non-highlighted rows: white background with normal black text
                return ['background-color: #ffffff; color: #212121'] * len(row)
            
            # Apply styling with better table display
            styled_df = df.style.apply(highlight_recent, axis=1).set_properties(**{
                'text-align': 'left',
                'padding': '8px'
            })
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=400)
            
            # Show EDGAR filings for rows with rounding
            rounding_splits = [s for s in recent_splits if s["Rounding"] == "Yes" and s["rounding_filings"]]
            if rounding_splits:
                st.markdown("---")
                st.subheader("📄 EDGAR Filings with Rounding Compliance")
                st.caption("Click to expand and view the actual EDGAR filings that contain rounding language")
                
                for split_info in rounding_splits:
                    symbol = split_info["Symbol"]
                    company_name = split_info["Company Name"]
                    split_date = split_info["Date"]
                    filings = split_info["rounding_filings"]
                    
                    with st.expander(f"🔍 {symbol} - {company_name} ({split_date}) - {len(filings)} filing(s)"):
                        for i, filing in enumerate(filings, 1):
                            st.markdown(f"**Filing {i}: {filing['form']}**")
                            
                            col1, col2 = st.columns([2, 1])
                            with col1:
                                st.write(f"**Filing Date:** {filing['filing_date']}")
                                st.write(f"**Accession:** {filing['accession']}")
                            with col2:
                                if filing['document_url']:
                                    st.markdown(f"[📄 View Filing]({filing['document_url']})")
                            
                            # Show rounding text snippet
                            if filing.get('rounding_text'):
                                st.markdown("**Relevant Text:**")
                                st.code(filing['rounding_text'], language=None)
                            
                            if i < len(filings):
                                st.markdown("---")
            
            # Summary stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Recent Splits", len(recent_splits))
            with col2:
                recent_count = sum(1 for s in recent_splits if s["split_date_obj"] >= three_days_ago and s["split_date_obj"] <= today)
                st.metric("Last 3 Days", recent_count)
            with col3:
                rounding_count = sum(1 for s in recent_splits if s["Rounding"] == "Yes")
                st.metric("With Rounding", rounding_count)
            
    with tab2:
        st.header("⚠️ Early Warning Signals")
        st.markdown("""
        Scanning daily 8-K (Deficiency Notices) and 14A (Proxy Statements) filings for early indications of reverse splits.
        - **Deficiency Notices**: Companies trading under $1.00 who received a Nasdaq warning.
        - **Proposals**: Companies asking shareholders to vote on a potential reverse split.
        """)
        
        PROSPECTIVE_COLLECTION = "prospective_splits"
        try:
            prospective_collection = db[PROSPECTIVE_COLLECTION]
            # Fetch all prospective splits, sorted by date (newest first)
            prospective_splits = list(prospective_collection.find({}).sort("fililing_date", -1))
            
            if not prospective_splits:
                st.info("No early warning signals found yet. Run the scanner to populate this list.")
            else:
                st.info(f"Checking {len(prospective_splits)} potential future splits...")
                
                start_data = []
                for p in prospective_splits:
                    start_data.append({
                        "Date": p.get("fililing_date"),
                        "Ticker": p.get("ticker", "UNKNOWN"),
                        "Company": p.get("company_name"),
                        "Signal": p.get("signal_type", "").replace("_", " ").title(),
                        "Form": p.get("form"),
                        "Details": p.get("details", {}).get("symptom", ""),
                        "Link": p.get("filing_url")
                    })
                
                p_df = pd.DataFrame(start_data)
                
                # Convert Date column to datetime objects for column_config.DateColumn
                if not p_df.empty and "Date" in p_df.columns:
                    p_df["Date"] = pd.to_datetime(p_df["Date"])

                # Make the Link column actually clickable
                st.data_editor(
                    p_df,
                    column_config={
                        "Link": st.column_config.LinkColumn("Filing URL", display_text="View Filing"),
                        "Date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
        except Exception as e:
            st.error(f"Error fetching early warnings: {e}")

    # Refresh button
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh Data"):
            st.rerun()
    with col2:
        if st.button("🗑️ Clear Cache"):
            st.cache_data.clear()
            st.success("Cache cleared! Refresh the page.")
    
    client.close()

if __name__ == "__main__":
    main()

