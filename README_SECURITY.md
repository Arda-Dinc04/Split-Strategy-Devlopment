# 🔒 Security Setup

## Quick Start

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your actual credentials:**
   ```bash
   MONGODB_URI=your_actual_mongodb_uri_here
   POLYGON_API_KEY=your_actual_api_key_here  # Optional
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run scripts** - they will automatically load `.env` file

## ⚠️ Important

- ✅ `.env` files are **NOT** committed to git (in `.gitignore`)
- ✅ Never commit files with hardcoded credentials
- ✅ All scripts now require environment variables
- ❌ Don't share `.env` files or credentials

## For Streamlit Cloud

Add secrets in Streamlit Cloud dashboard:
- Go to your app → Settings → Secrets
- Add `MONGODB_URI` and `POLYGON_API_KEY` (if needed)

See `SECURITY.md` for detailed security guidelines.
