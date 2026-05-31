#!/usr/bin/env python3
"""Download Bilibili video subtitles as timestamped markdown."""

import sys
import re
import json
import requests
from pathlib import Path

BV_PATTERN = re.compile(r"BV\w+")
AV_PATTERN = re.compile(r"av[0-9]+")
PAGE_PATTERN = re.compile(r"[?&]p=(\d+)")


def slugify(text: str) -> str:
    return re.sub(r"[\s_-]+", "-", re.sub(r"[^\w\s-]", "", text).strip().lower())


def fmt_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def video_url_at(base_url: str, t: float) -> str:
    clean = base_url.split("?")[0].rstrip("/")
    return f"{clean}?t={int(t)}"


def download_subtitles(
    url: str,
    sessdata: str,
    bili_jct: str,
    buvid3: str,
    output_dir: str = ".",
) -> Path:
    from bilibili_api import sync, video

    credential = video.Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3)

    bvid = BV_PATTERN.search(url)
    if bvid:
        v = video.Video(bvid=bvid.group(), credential=credential)
    else:
        aid = AV_PATTERN.search(url)
        if aid:
            v = video.Video(aid=int(aid.group()[2:]), credential=credential)
        else:
            print(f"No valid video ID in URL: {url}")
            sys.exit(1)

    print("Fetching video info...")
    info = sync(v.get_info())

    page_match = PAGE_PATTERN.search(url)
    cid = info["pages"][int(page_match.group(1)) - 1]["cid"] if page_match else info["cid"]

    print("Fetching subtitles...")
    sub = sync(v.get_subtitle(cid))
    sub_list = sub.get("subtitles", [])
    if not sub_list:
        print("No subtitles found for this video.")
        sys.exit(1)

    sub_url = sub_list[0].get("subtitle_url", "")
    if not sub_url.startswith("http"):
        sub_url = "https:" + sub_url

    entries = json.loads(requests.get(sub_url, timeout=15).content).get("body", [])

    title = info.get("title", "Untitled")
    output_path = Path(output_dir) / f"{slugify(title)}.md"

    lines = [f"# {title}\n"]
    if info.get("desc"):
        lines.append(f"> {info['desc']}\n")
    lines.append(f"**URL:** {url}  ")
    if info.get("stat", {}).get("view"):
        lines.append(f"**Views:** {info['stat']['view']}  ")
    if info.get("stat", {}).get("like"):
        lines.append(f"**Likes:** {info['stat']['like']}  ")
    lines.append("\n---\n")

    current_minute = -1
    for entry in entries:
        t = entry.get("from", 0)
        minute = int(t) // 60
        content = entry.get("content", "").strip()
        if not content:
            continue
        if minute != current_minute:
            current_minute = minute
            section_t = minute * 60
            lines.append(f"\n## [{fmt_time(section_t)}]({video_url_at(url, section_t)})\n")
        lines.append(f"[{fmt_time(t)}]({video_url_at(url, t)}) {content}  ")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Bilibili subtitles as timestamped markdown.")
    parser.add_argument("url", help="Bilibili video URL")
    parser.add_argument("--sessdata", required=True, help="SESSDATA cookie")
    parser.add_argument("--bili-jct", required=True, help="bili_jct cookie")
    parser.add_argument("--buvid3", required=True, help="buvid3 cookie")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    args = parser.parse_args()

    download_subtitles(args.url, args.sessdata, args.bili_jct, args.buvid3, args.output_dir)
