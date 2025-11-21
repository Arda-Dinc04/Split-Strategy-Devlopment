# Streamlit Dashboard Setup

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Streamlit app:**
   ```bash
   streamlit run streamlit_app.py
   ```

3. **Access the dashboard:**
   - The app will open in your browser automatically
   - Or visit: `http://localhost:8501`

## Features

- **Recent Reverse Splits Table**: Shows all splits from 3 days ago to future dates
- **Highlighting**: Rows within the last 3 days are highlighted in yellow
- **Rounding Flag**: Shows "Yes" if any EDGAR filing has `rounding_up_flag=True`, otherwise blank
- **Background Processing**: Button to process splits without EDGAR data on-demand
- **Summary Metrics**: Total splits, last 3 days count, and rounding count

## Deploy to Streamlit Cloud (Free)

1. **Push your code to GitHub** (make sure `streamlit_app.py` is in the root)

2. **Go to**: https://share.streamlit.io/

3. **Sign in with GitHub**

4. **Click "New app"** and:
   - Select your repository
   - Main file path: `streamlit_app.py`
   - Branch: `main` (or your default branch)

5. **Add secrets** (if needed):
   - Go to app settings → Secrets
   - Add `MONGODB_URI` if you want to override the default

6. **Deploy!** The app will be live at: `https://your-app-name.streamlit.app`

## Mobile Access

Once deployed, you can access the dashboard from any device:
- Open the Streamlit Cloud URL on your phone
- The dashboard is mobile-responsive
- All features work on mobile browsers

## Notes

- The app caches CIK mappings for 1 hour
- EDGAR processing respects SEC rate limits (5-10 req/sec)
- Processing multiple splits may take a few minutes
- Use the refresh button to update data after processing

