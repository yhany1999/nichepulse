import os
import re
import datetime
from collections import Counter
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def _build_client():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY not set in .env")
    return build("youtube", "v3", developerKey=api_key)


def _published_after(days: int) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_num(n) -> str:
    try:
        n = int(n)
    except (ValueError, TypeError):
        return "N/A"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_dur(iso: str) -> str:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return "?"
    h, mi, s = (int(x or 0) for x in m.groups())
    return f"{h}:{mi:02d}:{s:02d}" if h else f"{mi}:{s:02d}"


def fetch_trending(keywords: list[str], days: int = 7) -> dict:
    yt = _build_client()
    pub_after = _published_after(days)
    all_vids = {}

    for kw in keywords:
        try:
            items = yt.search().list(
                part="snippet",
                q=kw,
                type="video",
                order="relevance",
                publishedAfter=pub_after,
                maxResults=10,
                relevanceLanguage="en",
            ).execute().get("items", [])
        except HttpError as e:
            print(f"  Skip '{kw}': {e}")
            continue

        ids = [i["id"]["videoId"] for i in items if i["id"].get("videoId")]
        if not ids:
            continue

        try:
            details = {
                d["id"]: d
                for d in yt.videos().list(
                    part="statistics,contentDetails,snippet",
                    id=",".join(ids),
                ).execute().get("items", [])
            }
        except HttpError:
            details = {}

        for item in items:
            vid = item["id"].get("videoId")
            if not vid or vid in all_vids:
                continue
            d = details.get(vid, {})
            s = d.get("statistics", {})
            sn = d.get("snippet", item.get("snippet", {}))
            all_vids[vid] = {
                "id": vid,
                "keyword": kw,
                "title": sn.get("title", "Unknown"),
                "channel": sn.get("channelTitle", "Unknown"),
                "published": sn.get("publishedAt", "")[:10],
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
                "duration": _fmt_dur(d.get("contentDetails", {}).get("duration", "")),
                "url": f"https://youtube.com/watch?v={vid}",
                "engagement": round(
                    int(s.get("likeCount", 0)) / max(int(s.get("viewCount", 1)), 1) * 100, 2
                ),
            }

    return all_vids


def build_report(videos: dict, keywords: list[str]) -> str:
    vids = list(videos.values())
    top10 = sorted(vids, key=lambda v: v["views"], reverse=True)[:10]
    channels = Counter(v["channel"] for v in vids).most_common(5)

    stop = {
        "the", "and", "for", "are", "was", "with", "this", "that", "have",
        "from", "you", "your", "how", "what", "will", "can", "its", "our",
        "use", "using", "into", "about", "get", "all", "new",
    }
    words = Counter(
        w
        for v in vids
        for w in re.findall(r"\b[A-Za-z]{3,}\b", v["title"].lower())
        if w not in stop
    ).most_common(12)

    week = datetime.date.today().strftime("%B %d, %Y")

    lines = [
        "# YouTube Niche Trending Report",
        f"Week of {week}",
        f"Scanned {len(vids)} unique videos across {len(keywords)} keyword searches (last 7 days).",
        "",
        "=" * 60,
        "TOP 10 MOST VIEWED THIS WEEK",
        "=" * 60,
        "",
    ]

    for i, v in enumerate(top10, 1):
        lines += [
            f"{i}. {v['title']}",
            f"   {v['url']}",
            f"   Channel: {v['channel']}",
            f"   Views: {_fmt_num(v['views'])}  Likes: {_fmt_num(v['likes'])}  "
            f"Comments: {_fmt_num(v['comments'])}  Engagement: {v['engagement']}%",
            f"   Duration: {v['duration']}  Published: {v['published']}",
            f"   Found via: {v['keyword']}",
            "",
        ]

    lines += [
        "=" * 60,
        "TOP CHANNELS THIS WEEK",
        "=" * 60,
        "",
    ]
    for ch, n in channels:
        lines.append(f"  {ch}  ({n} video{'s' if n > 1 else ''})")

    lines += [
        "",
        "=" * 60,
        "TRENDING WORDS IN TITLES",
        "=" * 60,
        "",
        "  ".join(f"{w} ({c})" for w, c in words),
        "",
        "=" * 60,
        "PER-KEYWORD BREAKDOWN",
        "=" * 60,
        "",
    ]

    for kw in keywords:
        kv = sorted(
            [v for v in vids if v["keyword"] == kw],
            key=lambda v: v["views"],
            reverse=True,
        )
        lines.append(f"[{kw}]")
        if kv:
            for v in kv[:3]:
                lines.append(f"  - {v['title']}  |  {_fmt_num(v['views'])} views  |  {v['channel']}")
                lines.append(f"    {v['url']}")
        else:
            lines.append("  No results in the last 7 days.")
        lines.append("")

    lines.append(
        f"Generated {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )

    return "\n".join(lines)


def run_report(keywords: list[str], days: int = 7) -> str:
    videos = fetch_trending(keywords, days)
    return build_report(videos, keywords)
