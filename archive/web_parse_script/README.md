# Web Parse Script

Consolidated Python script for collecting reverse stock split data from multiple sources.

## Overview

This script replaces the Jupyter notebook workflow by:

- Collecting data from 3 sources: StockAnalysis.com, TipRanks.com, and HedgeFollow.com
- Combining all data in memory (no intermediate CSV files)
- Deduplicating by keeping the most recent date for each symbol
- Saving only the final combined CSV file

## Requirements

Install required packages:

```bash
pip install requests beautifulsoup4 pandas selenium webdriver-manager
```

## Usage

Run the script:

```bash
python web_parse.py
```

## Output

The script saves only one file:

- `Parsed_Data/Combined_Split_Data.csv` - Final combined and deduplicated reverse stock split data

## Data Sources

1. **StockAnalysis.com** - Web scraping via requests/BeautifulSoup
2. **TipRanks.com** - Web scraping via requests/BeautifulSoup
3. **HedgeFollow.com** - Web scraping via Selenium (headless Chrome)

## Configuration

Edit the following variable in `web_parse.py`:

- `OUTPUT_FILE_PATH` - Path where the final CSV will be saved
