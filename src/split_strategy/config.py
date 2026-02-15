"""
Configuration settings for the Split Strategy application.
Handles environment variables and constant definitions.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
# Try to find .env file in project root (3 levels up from this file)
# src/split_strategy/config.py -> src/split_strategy -> src -> root
ROOT_DIR = Path(__file__).parent.parent.parent.absolute()
ENV_PATH = ROOT_DIR / '.env'

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    # Warning or Error? For now, we'll let it be None and fail at connection time if needed
    pass

MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "split_strategy")
REVERSE_SPLITS_COLLECTION = os.environ.get("MONGODB_COLLECTION", "reverse_splits") # Default to reverse_splits
EDGAR_COLLECTION = "reverse_splits_edgar"
EARLY_WARNINGS_COLLECTION = "early_edgar_splits"

# EDGAR Configuration
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "Split Strategy Analysis contact@splitstrategy.com")
SEC_BASE_URL = "https://data.sec.gov"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
REQUEST_DELAY = 0.2

# Logging
LOG_DIR = ROOT_DIR / "logs"
# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# HTTP Headers
HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept": "application/json, text/html"
}

