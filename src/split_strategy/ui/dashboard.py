"""
Main dashboard logic for Streamlit.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys

# Import from package
from ..database import get_collection, REVERSE_SPLITS_COLLECTION, EDGAR_COLLECTION, EARLY_WARNINGS_COLLECTION
from ..edgar.client import get_cik_mapping_with_names
from ..edgar.processing import process_reverse_split_with_edgar
from ..edgar.utils import parse_date
from ..analysis.returns import get_stock_price_data_around_split, get_current_price
from .utils import check_rounding_flag, get_rounding_filings, has_edgar_data

# Cache CIK mapping
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_cik_mappings():
    """Get CIK mappings (cached)"""
    return get_cik_mapping_with_names()

@st.cache_data(ttl=600)  # Cache for 10 minutes
def fetch_recent_splits():
    """Fetch and process recent splits from MongoDB with caching"""
    try:
        reverse_collection = get_collection(REVERSE_SPLITS_COLLECTION)
    except Exception:
        return []
    
    today = datetime.now().date()
    three_days_ago = today - timedelta(days=3)
    
    splits = list(reverse_collection.find({}).sort("Date", -1))
    
    recent_splits = []
    for split in splits:
        split_date_str = split.get("Date", "")
        split_date = parse_date(split_date_str)
        
        if not split_date:
            continue
        
        try:
            split_date_obj = datetime.strptime(split_date, "%Y-%m-%d").date()
        except:
            continue
            
        if split_date_obj >= three_days_ago:
            reverse_splits_id = str(split.get("_id"))
            
            has_edgar = has_edgar_data(reverse_splits_id)
            
            rounding = False
            if has_edgar:
                rounding = check_rounding_flag(reverse_splits_id)
            
            rounding_filings = []
            if rounding:
                rounding_filings = get_rounding_filings(reverse_splits_id)
            
            # Clean non-serializable ObjectId
            split_doc_clean = {k: v for k, v in split.items() if k != "_id"}
            
            recent_splits.append({
                "Date": split_date_str,
                "Symbol": split.get("Symbol", ""),
                "Company Name": split.get("Company Name", ""),
                "Split Ratio": split.get("Split Ratio", ""),
                "Rounding": "Yes" if rounding else "",
                "Has EDGAR": has_edgar,
                "reverse_splits_id": reverse_splits_id,
                "split_date_obj_str": split_date_obj.strftime("%Y-%m-%d"),
                "split_doc": split_doc_clean,
                "rounding_filings": rounding_filings
            })
    return recent_splits

@st.cache_data(ttl=600)  # Cache for 10 minutes
def fetch_early_splits():
    """Fetch all early EDGAR split warnings from MongoDB with caching"""
    try:
        early_collection = get_collection(EARLY_WARNINGS_COLLECTION)
    except Exception:
        return []
        
    early_splits = list(early_collection.find({}).sort("filing_date", -1))
    
    cleaned_splits = []
    for split in early_splits:
        clean = {k: v for k, v in split.items() if k != "_id"}
        clean["_id"] = str(split["_id"])
        cleaned_splits.append(clean)
        
    return cleaned_splits

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

def run_dashboard():
    st.set_page_config(
        page_title="Reverse Splits Dashboard",
        page_icon=None,
        layout="wide"
    )
    
    st.title("Recent Reverse Splits Dashboard")
    
    # Add refresh button to clear cache
    col1, col2 = st.columns([1, 10])
    with col1:
        if st.button("Refresh", help="Clear cache and reload data from MongoDB"):
            st.cache_data.clear()
            st.rerun()
    
    st.markdown("---")
    
    # Fetch recent splits using cached function
    try:
        raw_recent_splits = fetch_recent_splits()
    except Exception as e:
        st.error(f"Error fetching splits from database: {e}")
        return
    
    # Reconstruct date objects in memory for compatibility
    recent_splits = []
    for s in raw_recent_splits:
        try:
            split_date_obj = datetime.strptime(s["split_date_obj_str"], "%Y-%m-%d").date()
            s_copy = dict(s)
            s_copy["split_date_obj"] = split_date_obj
            recent_splits.append(s_copy)
        except Exception:
            continue

    # Get date range - Show splits from 3 days ago onwards (including all future dates)
    today = datetime.now().date()
    three_days_ago = today - timedelta(days=3)
    
    # Create tabs for different views
    tab1, tab2 = st.tabs(["Confirmed Splits", "Early Warnings"])
    
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
                st.warning(f"Found {len(splits_to_process)} split(s) without EDGAR data.")
                
                if st.button(f"Process EDGAR Data for {len(splits_to_process)} Split(s)", type="primary"):
                    cik_mappings = get_cik_mappings()
                    results = process_splits_without_edgar(splits_to_process, cik_mappings)
                    
                    # Show results
                    success_count = sum(1 for r in results if r["status"] == "success")
                    st.success(f"Processed {success_count}/{len(results)} splits successfully!")
                    
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
                    return ['background-color: #e3f2fd; color: #000000; font-weight: 600'] * len(row)
                return ['background-color: #ffffff; color: #212121'] * len(row)
            
            styled_df = df.style.apply(highlight_recent, axis=1).set_properties(**{
                'text-align': 'left',
                'padding': '8px'
            })
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=400)
            
            # Show EDGAR filings for rows with rounding
            rounding_splits = [s for s in recent_splits if s["Rounding"] == "Yes" and s["rounding_filings"]]
            if rounding_splits:
                st.markdown("---")
                st.subheader("EDGAR Filings with Rounding Compliance")
                st.caption("Click to expand and view the actual EDGAR filings that contain rounding language")
                
                for split_info in rounding_splits:
                    symbol = split_info["Symbol"]
                    company_name = split_info["Company Name"]
                    split_date = split_info["Date"]
                    filings = split_info["rounding_filings"]
                    
                    with st.expander(f"{symbol} - {company_name} ({split_date}) - {len(filings)} filing(s)"):
                        for i, filing in enumerate(filings, 1):
                            st.markdown(f"**Filing {i}: {filing['form']}**")
                            
                            col1, col2 = st.columns([2, 1])
                            with col1:
                                st.write(f"**Filing Date:** {filing['filing_date']}")
                                st.write(f"**Accession:** {filing['accession']}")
                            with col2:
                                if filing['document_url']:
                                    st.markdown(f"[View Filing]({filing['document_url']})")
                            
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
        st.header("Early EDGAR (Announced Splits)")
        st.markdown("""
        Real-time feed of **confirmed** reverse split announcements detected in 8-K/6-K filings.
        - **Rounding**: Indicates if fractional shares will be rounded up (Major Opportunity).
        - **Confidence**: AI analysis confidence level.
        """)
        
        try:
            # Fetch early splits using cached function
            early_splits = fetch_early_splits()
            
            if not early_splits:
                st.info("No announced splits found yet. Run the `scan_early_edgar.py` script to populate.")
            else:
                # 1. Clean, Premium Filtering Layout
                st.markdown("### Filter Announcements")
                
                rounding_options = ["YES", "NO", "?"]
                confidence_options = ["HIGH", "MEDIUM", "LOW", "N/A"]
                
                col_search, col_round, col_conf, col_reset = st.columns([2, 1.5, 1.5, 1])
                
                with col_search:
                    search_query = st.text_input(
                        "Search Ticker or Company", 
                        value="", 
                        placeholder="e.g. ZOOZW",
                        key="early_search"
                    )
                
                with col_round:
                    selected_rounding = st.multiselect(
                        "Rounding", 
                        options=rounding_options, 
                        default=rounding_options,
                        key="early_round"
                    )
                
                with col_conf:
                    # Get unique confidences present, or fallback to default options
                    unique_confs = sorted(list(set([str(p.get("confidence", "N/A")).upper() for p in early_splits if p.get("confidence")])))
                    if not unique_confs:
                        unique_confs = confidence_options
                    
                    selected_confidence = st.multiselect(
                        "AI Confidence", 
                        options=unique_confs, 
                        default=unique_confs,
                        key="early_conf"
                    )
                
                with col_reset:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("Reset Filters", use_container_width=True):
                        st.session_state.early_search = ""
                        st.session_state.early_round = rounding_options
                        st.session_state.early_conf = unique_confs
                        st.rerun()

                # 2. Process Raw Data
                display_data = []
                for p in early_splits:
                    rounding = "?"
                    if p.get("rounding_up") is True:
                        rounding = "YES"
                    elif p.get("rounding_up") is False:
                        rounding = "NO"
                        
                    display_data.append({
                        "Filing Date": p.get("filing_date"),
                        "Ticker": p.get("ticker", "UNKNOWN"),
                        "Company": p.get("company_name"),
                        "Effective Date": p.get("effective_date", "Pending"),
                        "Ratio": p.get("ratio", "?"),
                        "Rounding": rounding,
                        "Summary": p.get("summary", ""),
                        "Confidence": str(p.get("confidence", "N/A")).upper(),
                        "Link": p.get("filing_url")
                    })
                
                # 3. Apply Filters in Python
                filtered_data = []
                for row in display_data:
                    # Search Filter
                    query = search_query.strip().lower()
                    if query:
                        ticker_match = query in row["Ticker"].lower()
                        company_match = query in (row["Company"] or "").lower()
                        if not (ticker_match or company_match):
                            continue
                    
                    # Rounding Filter
                    if row["Rounding"] not in selected_rounding:
                        continue
                    
                    # Confidence Filter
                    if row["Confidence"] not in selected_confidence:
                        continue
                    
                    filtered_data.append(row)
                
                st.success(f"Showing {len(filtered_data)} of {len(early_splits)} confirmed announcements.")
                
                if not filtered_data:
                    st.info("No announcements match the selected filter criteria.")
                else:
                    # Put Rounding == YES at the top (stable sort preserves filing_date desc order within groups)
                    filtered_data.sort(key=lambda x: 0 if x["Rounding"] == "YES" else 1)
                    
                    e_df = pd.DataFrame(filtered_data)
                    
                    if "Filing Date" in e_df.columns:
                        try:
                            e_df["Filing Date"] = pd.to_datetime(e_df["Filing Date"])
                        except:
                            pass
                    
                    st.dataframe(
                        e_df,
                        column_config={
                            "Link": st.column_config.LinkColumn("Filing URL", display_text="View Filing"),
                            "Filing Date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
                            "Summary": st.column_config.TextColumn("AI Summary", width="large", help="Full summary available on hover"),
                            "Rounding": st.column_config.TextColumn("Rounding Up?", help="Does the filing explicitly state fractional shares are rounded up?"),
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=400
                    )
                
        except Exception as e:
            st.error(f"Error fetching Early EDGAR data: {e}")

    # Refresh button
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Refresh Data"):
            st.rerun()
    with col2:
        if st.button("Clear Cache"):
            st.cache_data.clear()
            st.success("Cache cleared! Refresh the page.")
