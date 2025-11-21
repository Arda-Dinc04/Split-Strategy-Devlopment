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

## Deploy to Streamlit Cloud (Free & Public)

1. **Make sure your GitHub repo is public** (or keep it private - Streamlit supports both)

2. **Go to**: https://share.streamlit.io/

3. **Sign in with GitHub** and authorize Streamlit Cloud

4. **Click "New app"** and configure:
   - **Repository**: Select `Arda-Dinc04/Split-Strategy-Devlopment`
   - **Branch**: `main`
   - **Main file path**: `streamlit_app.py`
   - **App URL**: Choose a custom name (e.g., `split-strategy-dashboard`)

5. **Add secrets** (optional - if you want to override default MongoDB URI):
   - Click "Advanced settings" → "Secrets"
   - Add:
     ```
     MONGODB_URI = mongodb+srv://RS:01SDcSCdulMJREai@cluster0.wauawr1.mongodb.net/?appName=Cluster0
     ```

6. **Click "Deploy!"** 
   - First deployment takes 2-3 minutes
   - Your app will be live at: `https://split-strategy-dashboard.streamlit.app` (or your chosen name)

7. **Make app public** (if repo is private):
   - Go to app settings → "Sharing"
   - Toggle "Public app" to ON
   - Now anyone with the link can access it

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

