# Workflow: YouTube Niche Trending Report

## Objective
Every Sunday morning, fetch the most-viewed YouTube videos published in the last 7 days for the AI Automation / N8N / Claude Code / MCP niche. Deliver a ranked report to yhany6846@gmail.com so the week's content planning starts with real data.

## Trigger
Scheduled — every Sunday morning via `/schedule`.

## Inputs
| Input | Source |
|---|---|
| `YOUTUBE_API_KEY` | `.env` file |
| Search keywords | Hardcoded in `tools/youtube_trending.py` — update there |
| Lookback window | 7 days (default) |
| Recipient email | yhany6846@gmail.com |

## Keywords Searched
- "AI automation"
- "n8n workflow automation"
- "Claude code AI"
- "MCP model context protocol"
- "n8n Claude"
- "AI agent workflow"
- "n8n tutorial 2025"
- "Claude AI automation"

To add/remove keywords, edit the `SEARCH_KEYWORDS` list in `tools/youtube_trending.py`.

## Steps

### 1. Run the tool
```bash
cd "c:/Users/youssef hany/Downloads/files"
python tools/youtube_trending.py
```

### 2. Report is saved to
`.tmp/youtube_trending_YYYY-MM-DD.md`

### 3. Email the report
Read the generated `.md` file and send it to yhany6846@gmail.com via Gmail with subject:
`YouTube Niche Trending Report — [current date]`

## Outputs Per Report
- **Top 10 most-viewed videos** this week (title, channel, views, likes, comments, engagement %, duration, URL)
- **Top channels** dominating the niche
- **Trending words** in video titles
- **Per-keyword breakdown** — top 3 per search term

## YouTube API Details
- API: YouTube Data API v3
- Quota cost per run: ~900 units (8 keywords × 100 units search + 8 units for stats calls)
- Daily quota: 10,000 units (free tier) — well within limit
- Dashboard: https://console.cloud.google.com/apis/credentials

## One-Time Setup
1. Go to https://console.cloud.google.com
2. Create or select a project
3. Enable **YouTube Data API v3**
4. Go to Credentials → Create Credentials → API Key
5. Add to `.env`:
   ```
   YOUTUBE_API_KEY=your_key_here
   ```
6. Install dependencies:
   ```bash
   pip install google-api-python-client python-dotenv
   ```

## Edge Cases
- Duplicate videos across keywords: deduplicated, attributed to the first keyword that found them
- Keywords with zero results in the window: shown as "No results" in breakdown section
- API quota exceeded: `HttpError` printed as warning, keyword skipped — report still generates with partial data
- Videos with no stats (rare): included with 0 views, appear at bottom of rankings

## Improvement Loop
- If a keyword consistently returns irrelevant results → update `SEARCH_KEYWORDS`
- If you want to look back further (e.g. 14 days) → pass `--days 14` flag
- If you want the report in a Google Sheet instead of email → build `tools/youtube_to_sheet.py`
