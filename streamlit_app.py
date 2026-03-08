"""
Backward-compatible Streamlit entrypoint.

Keeps older deployment configs working while the canonical entrypoint is
`streamlit_entry.py`.
"""
from streamlit_entry import run_dashboard


if __name__ == "__main__":
    run_dashboard()
