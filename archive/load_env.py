"""
Load environment variables from .env file
Import this at the top of your scripts to auto-load .env file
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    
    # Load .env file from project root
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment variables from {env_path}")
    else:
        # No .env file found, assuming environment variables are set externally
        pass
except ImportError:
    # python-dotenv not installed, skip loading
    pass

