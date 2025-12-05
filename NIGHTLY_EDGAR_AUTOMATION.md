# Nightly EDGAR Processing Automation

## Overview

The GitHub Actions workflow now automatically processes EDGAR filings for reverse splits every night, eliminating the need to manually run the EDGAR processing from the Streamlit dashboard.

## What Runs Nightly

### 1. Web Scraping (`web_parse_script/web_parse.py`)
- Scrapes StockAnalysis.com and HedgeFollow.com for reverse stock splits
- Pushes new/updated splits to MongoDB `reverse_splits` collection
- Runs at **02:15 UTC** every night

### 2. EDGAR Batch Processing (`batch_process_edgar_nightly.py`)
- Finds all reverse splits in MongoDB that don't have EDGAR filings yet
- Queries SEC EDGAR database for relevant filings (8-K, 6-K, DEF 14A, etc.)
- Extracts and scores filings for reverse split information
- Pushes EDGAR filings to MongoDB `reverse_splits_edgar` collection
- Links filings to splits via `reverse_splits_id` (MongoDB `_id`)

## Workflow File

`.github/workflows/nightly-scrape.yml`

**Schedule:** Runs every night at 02:15 UTC (can be adjusted)

**Manual Trigger:** Can also be triggered manually from GitHub Actions tab

## Required GitHub Secrets

Make sure these secrets are set in your GitHub repository settings:

- `MONGODB_URI` - MongoDB connection string
- `MONGODB_DATABASE` - Database name (default: "split_strategy")
- `MONGODB_COLLECTION` - Collection name (default: "reverse_splits")

## How It Works

1. **Web Scraping Step:**
   - Collects reverse splits from web sources
   - Deduplicates and combines data
   - Upserts to MongoDB (inserts new, updates existing)

2. **EDGAR Processing Step:**
   - Queries MongoDB for splits without EDGAR data
   - For each split:
     - Looks up CIK (Central Index Key) for the company
     - Searches EDGAR for relevant filings around the split date
     - Downloads and parses filings
     - Extracts reverse split details (ratio, dates, compliance flags)
     - Scores filings based on relevance
     - Saves to `reverse_splits_edgar` collection

## Benefits

✅ **Fully Automated** - No manual intervention needed  
✅ **Always Up-to-Date** - New splits automatically get EDGAR data  
✅ **Efficient** - Only processes splits without EDGAR data  
✅ **Reliable** - Runs in GitHub's infrastructure with proper error handling  

## Monitoring

- Check workflow runs in GitHub Actions tab
- View logs for each step to see progress
- EDGAR processing shows:
  - Number of splits processed
  - Number of filings found per split
  - Any errors encountered

## Streamlit Dashboard

The Streamlit dashboard will automatically show:
- New splits from web scraping
- EDGAR filings linked to each split
- Rounding compliance flags from EDGAR filings
- No need to manually click "Process EDGAR Data" button anymore!

