"""
Streamlit Dashboard for Recent Reverse Splits
Shows recent reverse splits with rounding flag from EDGAR filings
"""

import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
import os
from bson import ObjectId

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
    
    # Get date range
    today = datetime.now().date()
    three_days_ago = today - timedelta(days=3)
    
    # Query recent splits (from 3 days ago to future)
    splits = list(reverse_collection.find({}).sort("Date", -1))
    
    # Filter and process splits
    recent_splits = []
    for split in splits:
        split_date_str = split.get("Date", "")
        split_date = parse_date(split_date_str)
        
        if not split_date:
            continue
        
        # Only include splits from 3 days ago onwards (including future)
        split_date_only = split_date.date()
        if split_date_only >= three_days_ago:
            reverse_splits_id = str(split.get("_id"))
            
            # Check if has EDGAR data
            has_edgar = has_edgar_data(reverse_splits_id, db)
            
            # Check rounding flag
            rounding = False
            if has_edgar:
                rounding = check_rounding_flag(reverse_splits_id, db)
            
            recent_splits.append({
                "Date": split_date_str,
                "Symbol": split.get("Symbol", ""),
                "Company Name": split.get("Company Name", ""),
                "Split Ratio": split.get("Split Ratio", ""),
                "Rounding": "Yes" if rounding else "",
                "Has EDGAR": has_edgar,
                "reverse_splits_id": reverse_splits_id,
                "split_date_obj": split_date_only,
                "split_doc": split
            })
    
    if not recent_splits:
        st.info("No recent reverse splits found (from 3 days ago to future).")
        client.close()
        return
    
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
    
    # Style the dataframe
    def highlight_recent(row):
        if row.name < len(highlight_mask) and highlight_mask.iloc[row.name]:
            return ['background-color: #fff3cd'] * len(row)  # Light yellow
        return [''] * len(row)
    
    styled_df = df.style.apply(highlight_recent, axis=1)
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
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
    
    # Refresh button
    st.markdown("---")
    if st.button("🔄 Refresh Data"):
        st.rerun()
    
    client.close()

if __name__ == "__main__":
    main()

