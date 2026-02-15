"""
Runner for all scrapers.
"""
from datetime import datetime
from pymongo import MongoClient
import pandas as pd

from ..database import get_collection, REVERSE_SPLITS_COLLECTION, MONGODB_DATABASE, MONGODB_URI
from .stockanalysis import get_stockanalysis_data
from .tipranks import get_tipranks_data
from .hedgefollow import get_hedgefollow_data
from .utils import combine_and_deduplicate_dataframes

def push_to_mongodb(df):
    """Push DataFrame data to MongoDB Atlas"""
    print("\nConnecting to MongoDB Atlas...")
    
    try:
        # Get collection using database module
        collection = get_collection(REVERSE_SPLITS_COLLECTION)
        
        # Convert DataFrame to list of records
        records = df.to_dict('records')
        
        # Insert/Update records (upsert based on Symbol and Date)
        inserted_count = 0
        updated_count = 0
        
        for record in records:
            # Create filter for upsert
            filter_query = {
                'Symbol': record['Symbol'],
                'Date': record['Date']
            }
            
            # Add timestamp
            record['last_updated'] = datetime.utcnow()
            
            # Upsert
            result = collection.update_one(
                filter_query,
                {'$set': record},
                upsert=True
            )
            
            if result.upserted_id:
                inserted_count += 1
            else:
                updated_count += 1
        
        print(f"\nSuccessfully pushed data to MongoDB:")
        print(f"  Database: {MONGODB_DATABASE}")
        print(f"  Collection: {REVERSE_SPLITS_COLLECTION}")
        print(f"  New records inserted: {inserted_count}")
        print(f"  Existing records updated: {updated_count}")
        print(f"  Total records processed: {len(records)}")
        return True
        
    except Exception as e:
        print(f"\nError pushing data to MongoDB: {e}")
        return False

def run_all_scrapers():
    """Run all scrapers and update the database"""
    print("=" * 70)
    print("Stock Split Data Collector - Starting data collection")
    print("=" * 70)
    
    dataframes = []
    
    # 1. StockAnalysis.com
    try:
        df_stockanalysis = get_stockanalysis_data()
        if not df_stockanalysis.empty:
            dataframes.append(df_stockanalysis)
    except Exception as e:
        print(f"Critical Error in StockAnalysis scraper: {e}")
    
    # 2. TipRanks.com
    try:
        df_tipranks = get_tipranks_data()
        if not df_tipranks.empty:
            dataframes.append(df_tipranks)
    except Exception as e:
        print(f"Critical Error in TipRanks scraper: {e}")
    
    # 3. HedgeFollow.com
    try:
        df_hedgefollow = get_hedgefollow_data()
        if not df_hedgefollow.empty:
            dataframes.append(df_hedgefollow)
    except Exception as e:
        print(f"Critical Error in HedgeFollow scraper: {e}")
    
    # Combine
    if not dataframes:
        print("\nNo data collected from any source!")
        return
    
    final_df = combine_and_deduplicate_dataframes(dataframes)
    
    # Push to DB
    if not final_df.empty:
        success = push_to_mongodb(final_df)
        if not success:
             print("\n⚠ Warning: Failed to push to MongoDB.")
    else:
        print("\nNo data to push - final DataFrame is empty")

if __name__ == "__main__":
    run_all_scrapers()
