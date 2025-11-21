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
        print(f"⚠️  No .env file found at {env_path}")
        print("   Please create .env file from .env.example template")
except ImportError:
    # python-dotenv not installed, skip loading
    pass

