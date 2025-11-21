"""
Comprehensive Analysis of Reverse Splits Data
Generates graphs and statistics from MongoDB collections
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
import math
from collections import Counter

# MongoDB Configuration
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://RS:01SDcSCdulMJREai@cluster0.wauawr1.mongodb.net/?appName=Cluster0")
MONGODB_DATABASE = "split_strategy"
REVERSE_COLLECTION = "reverse_sa"
EDGAR_COLLECTION = "edgar_events"

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10

def connect_db():
    """Connect to MongoDB"""
    client = MongoClient(MONGODB_URI)
    db = client[MONGODB_DATABASE]
    return client, db

def parse_date(date_str):
    """Parse MM/DD/YYYY to datetime"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except:
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d")
        except:
            return None

def parse_ratio(ratio_str):
    """Parse '1 : 20' to (num, den)"""
    if not ratio_str:
        return None, None
    try:
        parts = ratio_str.split(':')
        if len(parts) == 2:
            num = int(parts[0].strip())
            den = int(float(parts[1].strip()))
            return num, den
    except:
        pass
    return None, None

def calculate_log_ratio(num, den):
    """Calculate log ratio"""
    if num and den and num > 0 and den > 0:
        return math.log(den / num)
    return None

def load_data():
    """Load all data from MongoDB"""
    client, db = connect_db()
    
    # Load reverse_sa splits
    reverse_splits = list(db[REVERSE_COLLECTION].find({}))
    df_splits = pd.DataFrame(reverse_splits)
    
    # Load edgar_events
    edgar_events = list(db[EDGAR_COLLECTION].find({}))
    df_edgar = pd.DataFrame(edgar_events)
    
    client.close()
    
    return df_splits, df_edgar

def plot_reverse_splits_per_year(df_splits):
    """1. Reverse splits per year (bar chart)"""
    print("\n1. Reverse Splits Per Year")
    print("=" * 70)
    
    # Extract year from Date
    df_splits['year'] = df_splits['Date'].apply(lambda x: parse_date(x).year if parse_date(x) else None)
    df_splits = df_splits.dropna(subset=['year'])
    
    year_counts = df_splits['year'].value_counts().sort_index()
    
    print(f"Total splits: {len(df_splits)}")
    print(f"Year range: {year_counts.index.min()} - {year_counts.index.max()}")
    print("\nTop 10 years:")
    print(year_counts.head(10))
    
    plt.figure(figsize=(14, 6))
    year_counts.plot(kind='bar', color='steelblue', edgecolor='black')
    plt.title('Reverse Splits Per Year', fontsize=14, fontweight='bold')
    plt.xlabel('Year', fontsize=12)
    plt.ylabel('Number of Splits', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig('1_reverse_splits_per_year.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 1_reverse_splits_per_year.png")
    plt.close()

def plot_split_ratio_distribution(df_splits):
    """2. Split ratio distribution (histogram / log-histogram)"""
    print("\n2. Split Ratio Distribution")
    print("=" * 70)
    
    # Parse ratios
    ratios = []
    log_ratios = []
    for _, row in df_splits.iterrows():
        num, den = parse_ratio(row.get('Split Ratio', ''))
        if num and den:
            ratios.append(den / num)
            log_ratios.append(calculate_log_ratio(num, den))
    
    df_ratios = pd.DataFrame({'ratio': ratios, 'log_ratio': log_ratios})
    df_ratios = df_ratios.dropna()
    
    print(f"Total ratios parsed: {len(df_ratios)}")
    print(f"Ratio range: {df_ratios['ratio'].min():.2f} - {df_ratios['ratio'].max():.2f}")
    print(f"Log ratio range: {df_ratios['log_ratio'].min():.2f} - {df_ratios['log_ratio'].max():.2f}")
    
    # Define bins
    bins = [1.5, 2, 5, 10, 20, 50, 200, float('inf')]
    bin_labels = ['1.5-2', '2-5', '5-10', '10-20', '20-50', '50-200', '200+']
    
    # Histogram (linear scale)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    ax1.hist(df_ratios['ratio'], bins=50, color='steelblue', edgecolor='black', alpha=0.7)
    ax1.set_title('Split Ratio Distribution (Linear Scale)', fontsize=12, fontweight='bold')
    ax1.set_xlabel('Ratio (den/num)', fontsize=11)
    ax1.set_ylabel('Frequency', fontsize=11)
    ax1.grid(alpha=0.3)
    
    # Histogram (log scale)
    ax2.hist(df_ratios['log_ratio'], bins=50, color='coral', edgecolor='black', alpha=0.7)
    ax2.set_title('Split Ratio Distribution (Log Scale)', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Log Ratio (ln(den/num))', fontsize=11)
    ax2.set_ylabel('Frequency', fontsize=11)
    ax2.grid(alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('2_split_ratio_distribution.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 2_split_ratio_distribution.png")
    plt.close()
    
    # Binned histogram
    df_ratios['ratio_bin'] = pd.cut(df_ratios['ratio'], bins=bins, labels=bin_labels, right=False)
    bin_counts = df_ratios['ratio_bin'].value_counts().sort_index()
    
    plt.figure(figsize=(12, 6))
    bin_counts.plot(kind='bar', color='steelblue', edgecolor='black')
    plt.title('Split Ratio Distribution (Binned)', fontsize=14, fontweight='bold')
    plt.xlabel('Ratio Range', fontsize=12)
    plt.ylabel('Number of Splits', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig('2_split_ratio_binned.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 2_split_ratio_binned.png")
    plt.close()

def plot_lead_time_distribution(df_splits):
    """3. Lead time: earliest announcement vs execution (histogram)"""
    print("\n3. Lead Time Distribution")
    print("=" * 70)
    
    lead_times = []
    for _, row in df_splits.iterrows():
        split_date = parse_date(row.get('Date', ''))
        announce_date = None
        
        if row.get('earliest_announcement_date'):
            try:
                announce_date = datetime.fromisoformat(row['earliest_announcement_date'].replace('Z', '+00:00'))
            except:
                try:
                    announce_date = datetime.strptime(row['earliest_announcement_date'], '%Y-%m-%d')
                except:
                    pass
        
        if split_date and announce_date:
            lead_days = (split_date - announce_date).days
            if lead_days >= 0:  # Only positive lead times
                lead_times.append(lead_days)
    
    if not lead_times:
        print("⚠ No lead time data available")
        return
    
    df_lead = pd.DataFrame({'lead_days': lead_times})
    
    print(f"Total splits with lead time: {len(df_lead)}")
    print(f"Lead time range: {df_lead['lead_days'].min()} - {df_lead['lead_days'].max()} days")
    print(f"Mean lead time: {df_lead['lead_days'].mean():.1f} days")
    print(f"Median lead time: {df_lead['lead_days'].median():.1f} days")
    
    # Define bins
    bins = [0, 1, 4, 8, 15, 31, 61, 121, float('inf')]
    bin_labels = ['0', '1-3', '4-7', '8-14', '15-30', '31-60', '61-120', '120+']
    
    df_lead['lead_bin'] = pd.cut(df_lead['lead_days'], bins=bins, labels=bin_labels, right=False)
    bin_counts = df_lead['lead_bin'].value_counts().sort_index()
    
    plt.figure(figsize=(12, 6))
    bin_counts.plot(kind='bar', color='steelblue', edgecolor='black')
    plt.title('Lead Time Distribution (Announcement to Execution)', fontsize=14, fontweight='bold')
    plt.xlabel('Lead Time (days)', fontsize=12)
    plt.ylabel('Number of Splits', fontsize=12)
    plt.xticks(rotation=0)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig('3_lead_time_distribution.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 3_lead_time_distribution.png")
    plt.close()

def plot_lead_time_by_tier(df_splits):
    """4. Lead time by tier (box plot)"""
    print("\n4. Lead Time by Tier")
    print("=" * 70)
    
    tier_data = []
    for _, row in df_splits.iterrows():
        split_date = parse_date(row.get('Date', ''))
        announce_date = None
        tier = row.get('earliest_announcement_tier', 'Unknown')
        
        if row.get('earliest_announcement_date'):
            try:
                announce_date = datetime.fromisoformat(row['earliest_announcement_date'].replace('Z', '+00:00'))
            except:
                try:
                    announce_date = datetime.strptime(row['earliest_announcement_date'], '%Y-%m-%d')
                except:
                    pass
        
        if split_date and announce_date and tier != 'Unknown':
            lead_days = (split_date - announce_date).days
            if lead_days >= 0:
                tier_data.append({'tier': tier, 'lead_days': lead_days})
    
    if not tier_data:
        print("⚠ No tier data available")
        return
    
    df_tier = pd.DataFrame(tier_data)
    
    print(f"Total splits with tier data: {len(df_tier)}")
    print("\nLead time by tier:")
    print(df_tier.groupby('tier')['lead_days'].describe())
    
    plt.figure(figsize=(12, 6))
    df_tier.boxplot(column='lead_days', by='tier', ax=plt.gca())
    plt.title('Lead Time Distribution by Tier', fontsize=14, fontweight='bold')
    plt.suptitle('')  # Remove default title
    plt.xlabel('Tier', fontsize=12)
    plt.ylabel('Lead Time (days)', fontsize=12)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig('4_lead_time_by_tier.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 4_lead_time_by_tier.png")
    plt.close()

def plot_form_mix(df_splits):
    """5. Form mix for earliest announcements (stacked bar)"""
    print("\n5. Form Mix for Earliest Announcements")
    print("=" * 70)
    
    forms = df_splits['earliest_announcement_form'].dropna()
    form_counts = forms.value_counts()
    
    print(f"Total splits with form data: {len(forms)}")
    print("\nForm distribution:")
    print(form_counts)
    
    plt.figure(figsize=(12, 6))
    form_counts.plot(kind='bar', color='steelblue', edgecolor='black')
    plt.title('Form Mix for Earliest Announcements', fontsize=14, fontweight='bold')
    plt.xlabel('Form Type', fontsize=12)
    plt.ylabel('Number of Splits', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig('5_form_mix.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 5_form_mix.png")
    plt.close()

def plot_flag_rates(df_edgar):
    """6. Flag rates (bar chart)"""
    print("\n6. Flag Rates")
    print("=" * 70)
    
    if len(df_edgar) == 0:
        print("⚠ No EDGAR data available")
        return
    
    total_filings = len(df_edgar)
    
    flag_counts = {
        'compliance_flag': df_edgar['flags'].apply(lambda x: x.get('compliance_flag', False) if isinstance(x, dict) else False).sum(),
        'financing_flag': df_edgar['flags'].apply(lambda x: x.get('financing_flag', False) if isinstance(x, dict) else False).sum(),
        'rounding_up_flag': df_edgar['flags'].apply(lambda x: x.get('rounding_up_flag', False) if isinstance(x, dict) else False).sum(),
        'unregistered_sales_flag': df_edgar['flags'].apply(lambda x: x.get('unregistered_sales_flag', False) if isinstance(x, dict) else False).sum(),
    }
    
    flag_rates = {k: (v / total_filings * 100) for k, v in flag_counts.items()}
    
    print(f"Total filings: {total_filings}")
    print("\nFlag rates:")
    for flag, rate in flag_rates.items():
        print(f"  {flag}: {rate:.1f}% ({flag_counts[flag]} filings)")
    
    plt.figure(figsize=(12, 6))
    flags_df = pd.DataFrame({'Flag': list(flag_rates.keys()), 'Rate (%)': list(flag_rates.values())})
    flags_df.plot(x='Flag', y='Rate (%)', kind='bar', color='steelblue', edgecolor='black', legend=False)
    plt.title('Flag Rates in EDGAR Filings', fontsize=14, fontweight='bold')
    plt.xlabel('Flag Type', fontsize=12)
    plt.ylabel('Percentage of Filings', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig('6_flag_rates.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 6_flag_rates.png")
    plt.close()

def plot_lead_time_vs_ratio(df_splits):
    """7. Lead time vs ratio (heatmap)"""
    print("\n7. Lead Time vs Ratio Heatmap")
    print("=" * 70)
    
    data = []
    for _, row in df_splits.iterrows():
        split_date = parse_date(row.get('Date', ''))
        announce_date = None
        num, den = parse_ratio(row.get('Split Ratio', ''))
        
        if row.get('earliest_announcement_date'):
            try:
                announce_date = datetime.fromisoformat(row['earliest_announcement_date'].replace('Z', '+00:00'))
            except:
                try:
                    announce_date = datetime.strptime(row['earliest_announcement_date'], '%Y-%m-%d')
                except:
                    pass
        
        if split_date and announce_date and num and den:
            lead_days = (split_date - announce_date).days
            if lead_days >= 0:
                ratio = den / num
                data.append({'lead_days': lead_days, 'ratio': ratio})
    
    if not data:
        print("⚠ No data available for heatmap")
        return
    
    df_heat = pd.DataFrame(data)
    
    # Define bins
    ratio_bins = [0, 2, 5, 10, 20, 50, 200, float('inf')]
    ratio_labels = ['<2', '2-5', '5-10', '10-20', '20-50', '50-200', '200+']
    lead_bins = [0, 1, 4, 8, 15, 31, 61, 121, float('inf')]
    lead_labels = ['0', '1-3', '4-7', '8-14', '15-30', '31-60', '61-120', '120+']
    
    df_heat['ratio_bin'] = pd.cut(df_heat['ratio'], bins=ratio_bins, labels=ratio_labels, right=False)
    df_heat['lead_bin'] = pd.cut(df_heat['lead_days'], bins=lead_bins, labels=lead_labels, right=False)
    
    heatmap_data = df_heat.groupby(['lead_bin', 'ratio_bin']).size().unstack(fill_value=0)
    
    plt.figure(figsize=(14, 8))
    sns.heatmap(heatmap_data, annot=True, fmt='d', cmap='YlOrRd', cbar_kws={'label': 'Number of Splits'})
    plt.title('Lead Time vs Split Ratio Heatmap', fontsize=14, fontweight='bold')
    plt.xlabel('Split Ratio Range', fontsize=12)
    plt.ylabel('Lead Time (days)', fontsize=12)
    plt.tight_layout()
    plt.savefig('7_lead_time_vs_ratio_heatmap.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 7_lead_time_vs_ratio_heatmap.png")
    plt.close()

def plot_tier_vs_ratio(df_splits):
    """8. Tier × Ratio (grouped bar)"""
    print("\n8. Tier vs Ratio")
    print("=" * 70)
    
    tier_ratios = []
    for _, row in df_splits.iterrows():
        tier = row.get('earliest_announcement_tier', 'Unknown')
        num, den = parse_ratio(row.get('Split Ratio', ''))
        
        if tier != 'Unknown' and num and den:
            ratio = den / num
            tier_ratios.append({'tier': tier, 'ratio': ratio})
    
    if not tier_ratios:
        print("⚠ No tier/ratio data available")
        return
    
    df_tier_ratio = pd.DataFrame(tier_ratios)
    
    print("\nAverage ratio by tier:")
    print(df_tier_ratio.groupby('tier')['ratio'].describe())
    
    plt.figure(figsize=(12, 6))
    df_tier_ratio.boxplot(column='ratio', by='tier', ax=plt.gca())
    plt.title('Split Ratio Distribution by Tier', fontsize=14, fontweight='bold')
    plt.suptitle('')  # Remove default title
    plt.xlabel('Tier', fontsize=12)
    plt.ylabel('Split Ratio (den/num)', fontsize=12)
    plt.yscale('log')  # Log scale for ratios
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig('8_tier_vs_ratio.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 8_tier_vs_ratio.png")
    plt.close()

def plot_filings_per_split(df_splits, df_edgar):
    """9. Filings per split (histogram)"""
    print("\n9. Filings Per Split")
    print("=" * 70)
    
    if len(df_edgar) == 0:
        print("⚠ No EDGAR data available")
        return
    
    filings_per_split = df_edgar['reverse_sa_id'].value_counts()
    
    print(f"Total splits with filings: {len(filings_per_split)}")
    print(f"Total filings: {len(df_edgar)}")
    print(f"Average filings per split: {filings_per_split.mean():.1f}")
    print(f"Median filings per split: {filings_per_split.median():.1f}")
    print(f"Max filings per split: {filings_per_split.max()}")
    
    plt.figure(figsize=(12, 6))
    filings_per_split.hist(bins=30, color='steelblue', edgecolor='black', alpha=0.7)
    plt.title('Filings Per Split Distribution', fontsize=14, fontweight='bold')
    plt.xlabel('Number of Filings', fontsize=12)
    plt.ylabel('Number of Splits', fontsize=12)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig('9_filings_per_split.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 9_filings_per_split.png")
    plt.close()

def plot_announcement_cadence(df_splits):
    """10. Announcement cadence (line chart)"""
    print("\n10. Announcement Cadence")
    print("=" * 70)
    
    cadence_data = []
    for _, row in df_splits.iterrows():
        split_date = parse_date(row.get('Date', ''))
        announce_date = None
        
        if row.get('earliest_announcement_date'):
            try:
                announce_date = datetime.fromisoformat(row['earliest_announcement_date'].replace('Z', '+00:00'))
            except:
                try:
                    announce_date = datetime.strptime(row['earliest_announcement_date'], '%Y-%m-%d')
                except:
                    pass
        
        if split_date and announce_date:
            days_before = (split_date - announce_date).days
            if 0 <= days_before <= 120:
                cadence_data.append(days_before)
    
    if not cadence_data:
        print("⚠ No cadence data available")
        return
    
    df_cadence = pd.DataFrame({'days_before': cadence_data})
    
    # Create bins for cumulative count
    bins = list(range(0, 61, 5))  # 0, 5, 10, ..., 60
    df_cadence['bin'] = pd.cut(df_cadence['days_before'], bins=bins, right=False)
    cumulative = df_cadence.groupby('bin').size().cumsum()
    
    plt.figure(figsize=(14, 6))
    cumulative.plot(kind='line', marker='o', color='steelblue', linewidth=2, markersize=6)
    plt.title('Cumulative Announcement Cadence (Days Before Execution)', fontsize=14, fontweight='bold')
    plt.xlabel('Days Before Execution', fontsize=12)
    plt.ylabel('Cumulative Count of Announcements', fontsize=12)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig('10_announcement_cadence.png', dpi=300, bbox_inches='tight')
    print("✓ Saved: 10_announcement_cadence.png")
    plt.close()

def plot_ratio_counts(df_splits):
    """11. Count of each unique split ratio (histogram)"""
    print("\n11. Split Ratio Counts")
    print("=" * 70)
    
    # Extract and normalize ratios
    ratio_counts = {}
    for _, row in df_splits.iterrows():
        ratio_str = row.get('Split Ratio', '')
        if ratio_str:
            # Normalize format: "1 : 10" -> "1:10"
            ratio_normalized = ratio_str.replace(' ', '').replace(':', ':')
            ratio_counts[ratio_normalized] = ratio_counts.get(ratio_normalized, 0) + 1
    
    # Convert to DataFrame and sort
    df_ratio_counts = pd.DataFrame({
        'ratio': list(ratio_counts.keys()),
        'count': list(ratio_counts.values())
    }).sort_values('count', ascending=False)
    
    print(f"Total unique ratios: {len(df_ratio_counts)}")
    print(f"Total splits: {df_ratio_counts['count'].sum()}")
    print("\nTop 20 most common ratios:")
    print(df_ratio_counts.head(20).to_string(index=False))
    
    # Plot all ratios (or top N if too many)
    if len(df_ratio_counts) > 50:
        # Show top 50 most common
        plot_data = df_ratio_counts.head(50)
        title_suffix = " (Top 50)"
    else:
        plot_data = df_ratio_counts
        title_suffix = ""
    
    plt.figure(figsize=(16, 8))
    plt.bar(range(len(plot_data)), plot_data['count'], color='steelblue', edgecolor='black')
    plt.xticks(range(len(plot_data)), plot_data['ratio'], rotation=90, ha='right', fontsize=8)
    plt.title(f'Split Ratio Counts{title_suffix}', fontsize=14, fontweight='bold')
    plt.xlabel('Split Ratio', fontsize=12)
    plt.ylabel('Number of Splits', fontsize=12)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig('11_split_ratio_counts.png', dpi=300, bbox_inches='tight')
    print(f"✓ Saved: 11_split_ratio_counts.png")
    plt.close()
    
    # Also create a version showing ratios with count >= threshold
    threshold = 5  # Only show ratios that appear at least 5 times
    filtered_data = df_ratio_counts[df_ratio_counts['count'] >= threshold]
    
    if len(filtered_data) > 0:
        plt.figure(figsize=(16, 8))
        plt.bar(range(len(filtered_data)), filtered_data['count'], color='coral', edgecolor='black')
        plt.xticks(range(len(filtered_data)), filtered_data['ratio'], rotation=90, ha='right', fontsize=9)
        plt.title(f'Split Ratio Counts (Ratios with ≥{threshold} occurrences)', fontsize=14, fontweight='bold')
        plt.xlabel('Split Ratio', fontsize=12)
        plt.ylabel('Number of Splits', fontsize=12)
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        plt.savefig('11_split_ratio_counts_filtered.png', dpi=300, bbox_inches='tight')
        print(f"✓ Saved: 11_split_ratio_counts_filtered.png (ratios with ≥{threshold} occurrences)")
        plt.close()

def main():
    """Main analysis function"""
    print("=" * 70)
    print("REVERSE SPLITS DATA ANALYSIS")
    print("=" * 70)
    
    # Load data
    print("\nLoading data from MongoDB...")
    df_splits, df_edgar = load_data()
    print(f"✓ Loaded {len(df_splits)} splits and {len(df_edgar)} EDGAR filings")
    
    # Generate all plots
    plot_reverse_splits_per_year(df_splits)
    plot_split_ratio_distribution(df_splits)
    plot_lead_time_distribution(df_splits)
    plot_lead_time_by_tier(df_splits)
    plot_form_mix(df_splits)
    plot_flag_rates(df_edgar)
    plot_lead_time_vs_ratio(df_splits)
    plot_tier_vs_ratio(df_splits)
    plot_filings_per_split(df_splits, df_edgar)
    plot_announcement_cadence(df_splits)
    plot_ratio_counts(df_splits)
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE!")
    print("=" * 70)
    print("\nGenerated files:")
    for i in range(1, 12):
        print(f"  {i}_*.png")

if __name__ == "__main__":
    main()

