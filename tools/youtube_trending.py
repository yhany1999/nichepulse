#!/usr/bin/env python3
"""Fetch trending YouTube videos for AI automation niche and generate weekly report."""

import os
import re
import sys
import datetime
import argparse
from pathlib import Path
from collections import Counter

# Ensure stdout handles Unicode on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: google-api-python-client not installed.")
    print("Run: pip install google-api-python-client python-dotenv")
    sys.exit(1)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GMAIL_FROM = os.getenv("GMAIL_FROM", "yhany6846@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
REPORT_EMAIL = os.getenv("REPORT_EMAIL", "yhany6846@gmail.com")
OUTPUT_DIR = Path(__file__).parent.parent / ".tmp"

SEARCH_KEYWORDS = [
    "AI automation",
    "n8n workflow automation",
    "Claude code AI",
    "MCP model context protocol",
    "n8n Claude",
    "AI agent workflow",
    "n8n tutorial 2025",
    "Claude AI automation",
]

MAX_RESULTS_PER_KEYWORD = 10
DAYS_BACK = 7


def validate_api_key():
    if not YOUTUBE_API_KEY:
        print("ERROR: YOUTUBE_API_KEY not set.")
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. Enable 'YouTube Data API v3'")
        print("3. Create an API Key")
        print("4. Add YOUTUBE_API_KEY=your_key to .env")
        sys.exit(1)


def get_published_after(days_back):
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def search_videos(youtube, keyword, published_after):
    try:
        response = youtube.search().list(
            part="snippet",
            q=keyword,
            type="video",
            order="relevance",
            publishedAfter=published_after,
            maxResults=MAX_RESULTS_PER_KEYWORD,
            relevanceLanguage="en",
        ).execute()
        return response.get("items", [])
    except HttpError as e:
        print(f"  Warning: API error for '{keyword}': {e}")
        return []


def get_video_details(youtube, video_ids):
    if not video_ids:
        return {}
    try:
        response = youtube.videos().list(
            part="statistics,contentDetails,snippet",
            id=",".join(video_ids),
        ).execute()
        return {item["id"]: item for item in response.get("items", [])}
    except HttpError as e:
        print(f"  Warning: Failed to fetch video details: {e}")
        return {}


def format_number(n):
    try:
        n = int(n)
    except (ValueError, TypeError):
        return "N/A"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def parse_duration(iso_duration):
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not match:
        return "?"
    h, m, s = (int(x or 0) for x in match.groups())
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def engagement_rate(stats):
    views = int(stats.get("viewCount", 0))
    likes = int(stats.get("likeCount", 0))
    if views == 0:
        return 0.0
    return round(likes / views * 100, 2)


def fetch_all_trending(youtube, published_after):
    all_videos = {}

    for keyword in SEARCH_KEYWORDS:
        print(f"  Searching: '{keyword}'...")
        items = search_videos(youtube, keyword, published_after)
        video_ids = [item["id"]["videoId"] for item in items if item["id"].get("videoId")]
        details = get_video_details(youtube, video_ids)

        for item in items:
            vid_id = item["id"].get("videoId")
            if not vid_id or vid_id in all_videos:
                continue

            detail = details.get(vid_id, {})
            stats = detail.get("statistics", {})
            content = detail.get("contentDetails", {})
            snippet = detail.get("snippet", item.get("snippet", {}))

            all_videos[vid_id] = {
                "id": vid_id,
                "keyword": keyword,
                "title": snippet.get("title", "Unknown"),
                "channel": snippet.get("channelTitle", "Unknown"),
                "published": snippet.get("publishedAt", "")[:10],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration": parse_duration(content.get("duration", "")),
                "url": f"https://youtube.com/watch?v={vid_id}",
                "engagement": engagement_rate(stats),
            }

    return all_videos


def generate_report(videos, week_of):
    sorted_videos = sorted(videos.values(), key=lambda v: v["views"], reverse=True)
    top_overall = sorted_videos[:10]

    channel_counts = Counter(v["channel"] for v in videos.values())
    top_channels = channel_counts.most_common(5)

    stop_words = {
        "the", "and", "for", "are", "was", "with", "this", "that", "have",
        "from", "you", "your", "how", "what", "will", "can", "its", "our",
        "use", "using", "into", "about", "their", "them", "has", "get", "all",
    }
    all_words = []
    for v in videos.values():
        words = re.findall(r"\b[A-Za-z][A-Za-z]{2,}\b", v["title"].lower())
        all_words.extend(w for w in words if w not in stop_words)
    trending_words = Counter(all_words).most_common(12)

    lines = [
        "# YouTube Niche Trending Report",
        f"**Week of {week_of}**  |  Niche: AI Automation · N8N · Claude Code · MCP",
        "",
        f"Scanned **{len(videos)}** unique videos across {len(SEARCH_KEYWORDS)} keyword searches (last 7 days).",
        "",
        "---",
        "",
        "## Top 10 Most Viewed This Week",
        "",
    ]

    for i, v in enumerate(top_overall, 1):
        lines.append(f"**{i}. [{v['title']}]({v['url']})**")
        lines.append(
            f"   Channel: **{v['channel']}** | "
            f"Views: {format_number(v['views'])} | "
            f"Likes: {format_number(v['likes'])} | "
            f"Comments: {format_number(v['comments'])}"
        )
        lines.append(
            f"   Duration: {v['duration']} | "
            f"Published: {v['published']} | "
            f"Engagement: {v['engagement']}%"
        )
        lines.append(f"   *Found via: `{v['keyword']}`*")
        lines.append("")

    lines += [
        "---",
        "",
        "## Top Channels This Week",
        "",
    ]
    for ch, count in top_channels:
        lines.append(f"- **{ch}** — {count} video(s) in results")

    lines += [
        "",
        "---",
        "",
        "## Trending Words in Titles",
        "",
        "  ".join(f"`{w}` ({c})" for w, c in trending_words),
        "",
        "---",
        "",
        "## Per-Keyword Breakdown",
        "",
    ]

    for keyword in SEARCH_KEYWORDS:
        kw_videos = sorted(
            [v for v in videos.values() if v["keyword"] == keyword],
            key=lambda v: v["views"],
            reverse=True,
        )
        if not kw_videos:
            lines.append(f"### `{keyword}`")
            lines.append("*No results in the last 7 days.*")
            lines.append("")
            continue

        lines.append(f"### `{keyword}`")
        for v in kw_videos[:3]:
            lines.append(
                f"- [{v['title']}]({v['url']})  "
                f"— {format_number(v['views'])} views | **{v['channel']}**"
            )
        lines.append("")

    lines += [
        "---",
        f"*Generated {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by youtube_trending.py*",
    ]

    return "\n".join(lines)


def send_email(subject, body, to_addr, from_addr, app_password):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(from_addr, app_password)
        server.sendmail(from_addr, to_addr, msg.as_string())


def main():
    parser = argparse.ArgumentParser(description="Fetch trending YouTube videos for AI niche")
    parser.add_argument("--days", type=int, default=DAYS_BACK, help="Look back N days (default: 7)")
    parser.add_argument("--output", type=str, help="Override output file path")
    args = parser.parse_args()

    validate_api_key()

    week_of = datetime.date.today().strftime("%B %d, %Y")
    published_after = get_published_after(args.days)

    print(f"Fetching YouTube trending videos (last {args.days} days)...")
    print(f"Keywords: {', '.join(SEARCH_KEYWORDS)}")
    print()

    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    videos = fetch_all_trending(youtube, published_after)

    print(f"\nFound {len(videos)} unique videos. Generating report...")

    report = generate_report(videos, week_of)

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = args.output or str(
        OUTPUT_DIR / f"youtube_trending_{datetime.date.today().isoformat()}.md"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report saved to: {output_path}")

    if GMAIL_APP_PASSWORD:
        subject = f"YouTube Niche Trending Report — {week_of}"
        print(f"Sending email to {REPORT_EMAIL}...")
        send_email(subject, report, REPORT_EMAIL, GMAIL_FROM, GMAIL_APP_PASSWORD)
        print("Email sent.")
    else:
        print("(Set GMAIL_APP_PASSWORD in .env to enable automatic email delivery)")

    print()
    print(report)
    return output_path


if __name__ == "__main__":
    main()
