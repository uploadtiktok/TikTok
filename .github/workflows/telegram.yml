name: Fetch Telegram Videos

on:
  schedule:
    - cron: '0 3 * * *'  # كل يوم الساعة 3 صباحاً
  workflow_dispatch:

permissions:
  contents: write

jobs:
  fetch-videos:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.PAT_TOKEN }}
          fetch-depth: 0
          
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          
      - name: Install dependencies
        run: |
          pip install telethon requests pytz
          
      - name: Run video fetcher
        env:
          API_ID: ${{ secrets.API_ID }}
          API_HASH: ${{ secrets.API_HASH }}
          STRING_SESSION: ${{ secrets.STRING_SESSION }}
          CHANNEL_USERNAME: ${{ secrets.CHANNEL_USERNAME }}
          BATCH_SIZE: ${{ secrets.BATCH_SIZE }}
          PAT_TOKEN: ${{ secrets.PAT_TOKEN }}
          GITHUB_REPO: ${{ github.repository }}
          GITHUB_BRANCH: ${{ github.ref_name }}
        run: |
          python fetch_videos.py
          
      - name: Commit and push changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          
          # إضافة جميع الملفات المتغيرة
          git add -A
          
          # التحقق من وجود تغييرات
          if ! git diff --cached --quiet; then
            git commit -m "Auto: Update videos and RSS [$(date +'%Y-%m-%d %H:%M:%S')]"
            git fetch origin main
            git rebase origin/main || true
            git push origin main
          else
            echo "No new changes to commit"
          fi
