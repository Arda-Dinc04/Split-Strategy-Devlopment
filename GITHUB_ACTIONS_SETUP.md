# GitHub Actions Setup Guide

This guide will help you set up automated nightly runs of the stock split collector using GitHub Actions.

## ✅ What's Been Set Up

1. ✅ **Updated `web_parse.py`** - Now uses environment variables instead of hardcoded credentials
2. ✅ **Created `requirements.txt`** - Lists all Python dependencies
3. ✅ **Created `.github/workflows/nightly-scrape.yml`** - GitHub Actions workflow file

## 🔐 Step 1: Add GitHub Secrets

Go to your GitHub repository and add these secrets:

**Path:** `Repository → Settings → Secrets and variables → Actions → New repository secret`

Add these 3 secrets:

1. **MONGODB_URI**
   - Value: `mongodb+srv://RS:01SDcSCdulMJREai@cluster0.wauawr1.mongodb.net/?appName=Cluster0`
   - (Your full MongoDB Atlas connection string)

2. **MONGODB_DATABASE**
   - Value: `split_strategy`
   - (Or your preferred database name)

3. **MONGODB_COLLECTION**
   - Value: `reverse_splits`
   - (Or your preferred collection name)

## 🌐 Step 2: Configure MongoDB Atlas Network Access

Since GitHub Actions runners have dynamic IPs, you need to allow all IPs (for development):

1. Go to **MongoDB Atlas Dashboard**
2. Navigate to **Security → Network Access**
3. Click **Add IP Address**
4. Add `0.0.0.0/0` (allows all IPs)
5. Add a comment: "GitHub Actions - Development"
6. Click **Confirm**

⚠️ **Security Note:** `0.0.0.0/0` allows access from anywhere. For production, consider:
- Using MongoDB Atlas Data API (more secure)
- Or restricting to specific GitHub Actions IP ranges (more complex)

## 🚀 Step 3: Test the Workflow

### Manual Test Run

1. Go to your GitHub repository
2. Click **Actions** tab
3. Select **Nightly Split Collector** workflow
4. Click **Run workflow** button (top right)
5. Select branch (usually `main`)
6. Click **Run workflow**

### Check Logs

- Click on the running workflow
- Click on the **scrape** job
- Watch the logs to see if it runs successfully

## ⏰ Schedule

The workflow runs automatically at **02:15 UTC every night**.

To change the schedule, edit `.github/workflows/nightly-scrape.yml` and modify the cron expression:

```yaml
schedule:
  - cron: "15 2 * * *"   # 02:15 UTC
```

**Cron format:** `minute hour day month weekday`
- Example: `"0 3 * * *"` = 3:00 AM UTC daily
- Example: `"0 0 * * 1"` = Midnight UTC every Monday

## 📋 Workflow Details

- **Runs on:** Ubuntu Latest
- **Python version:** 3.11
- **Chrome:** Installed automatically (headless mode)
- **Dependencies:** Installed from `requirements.txt`
- **Script:** Runs `web_parse_script/web_parse.py`

## 🔍 Troubleshooting

### Workflow fails with "MONGODB_URI environment variable is required"
- Check that you've added the `MONGODB_URI` secret in GitHub
- Verify the secret name matches exactly (case-sensitive)

### Connection timeout to MongoDB
- Verify Network Access in MongoDB Atlas allows `0.0.0.0/0`
- Check that your MongoDB URI is correct
- Ensure your MongoDB user has read/write permissions

### Selenium/Chrome errors
- The workflow automatically installs Chrome
- If issues persist, check the workflow logs for specific errors

### Script path issues
- Ensure `web_parse_script/web_parse.py` exists in your repository
- The workflow runs from the repository root

## 📝 Next Steps

1. ✅ Add GitHub Secrets (Step 1)
2. ✅ Configure MongoDB Network Access (Step 2)
3. ✅ Test manually (Step 3)
4. ✅ Wait for first scheduled run (or adjust cron if needed)

## 🔄 Updating the Script

When you update `web_parse.py`:
- Push changes to your repository
- The next scheduled run will use the updated script
- Or trigger manually via "Run workflow"

---

**Note:** The workflow will run automatically every night. You can also trigger it manually anytime from the Actions tab.

