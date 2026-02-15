"""
Entry point for the Streamlit dashboard.
"""
import sys
import os
from pathlib import Path

# Add src to path to allow imports from split_strategy package
current_dir = Path(__file__).resolve().parent
src_path = current_dir / 'src'
sys.path.append(str(src_path))

try:
    from split_strategy.ui.dashboard import run_dashboard
except ImportError as e:
    import streamlit as st
    st.error(f"Failed to import dashboard module: {e}")
    st.stop()

if __name__ == "__main__":
    run_dashboard()
