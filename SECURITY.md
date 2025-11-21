# Security Guide

## 🔒 Protecting Secrets in Public Repository

This repository is **public**, so we must never commit secrets or credentials.

## Required Environment Variables

All scripts require the following environment variables:

### MongoDB URI (Required)
```bash
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?appName=AppName
```

### Polygon.io API Key (Optional - for calculate_returns.py)
```bash
POLYGON_API_KEY=your_api_key_here
```

## Setup Instructions

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your actual values:**
   ```bash
   # Never commit this file!
   MONGODB_URI=your_actual_mongodb_uri
   POLYGON_API_KEY=your_actual_api_key
   ```

3. **Load environment variables:**
   ```bash
   # Option 1: Use python-dotenv (recommended)
   pip install python-dotenv
   # Then scripts will auto-load .env file
   
   # Option 2: Export manually
   export MONGODB_URI="your_uri"
   export POLYGON_API_KEY="your_key"
   ```

## For Streamlit Cloud Deployment

1. Go to your app settings on Streamlit Cloud
2. Click "Secrets" 
3. Add:
   ```
   MONGODB_URI = "your_mongodb_uri_here"
   POLYGON_API_KEY = "your_api_key_here"
   ```

## ⚠️ Important Security Notes

- ✅ `.env` files are in `.gitignore` - they will NOT be committed
- ✅ Never commit files with hardcoded credentials
- ✅ Use environment variables or Streamlit secrets
- ✅ Rotate credentials if accidentally exposed
- ❌ Don't put secrets in code comments
- ❌ Don't commit `.env` files
- ❌ Don't share credentials in issues or PRs

## If Secrets Are Exposed

If you accidentally commit secrets:

1. **Immediately rotate/change the exposed credentials**
2. **Remove from git history** (if recent):
   ```bash
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch file_with_secret.py" \
     --prune-empty --tag-name-filter cat -- --all
   ```
3. **Force push** (be careful - this rewrites history)
4. **Consider making repo private** temporarily

## Current Status

✅ All scripts now require environment variables (no hardcoded defaults)
✅ `.env.example` template provided
✅ `.gitignore` configured to ignore `.env` files
✅ Documentation updated

