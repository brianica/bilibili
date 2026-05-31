#!/usr/bin/env python3
"""Download Bilibili video subtitles as timestamped markdown, with optional Gemini summary."""

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


def fetch_subtitles(url: str, sessdata: str, bili_jct: str, buvid3: str) -> dict:
    """Fetch video info and subtitle entries from Bilibili.

    Returns {"info": dict, "entries": list[dict]} where each entry has
    "from" (seconds), "to", and "content" keys.
    """
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
            raise ValueError(f"No valid video ID found in URL: {url}")

    info = sync(v.get_info())

    page_match = PAGE_PATTERN.search(url)
    cid = info["pages"][int(page_match.group(1)) - 1]["cid"] if page_match else info["cid"]

    sub = sync(v.get_subtitle(cid))
    sub_list = sub.get("subtitles", [])
    if not sub_list:
        raise ValueError("No subtitles found for this video.")

    sub_url = sub_list[0].get("subtitle_url", "")
    if not sub_url.startswith("http"):
        sub_url = "https:" + sub_url

    entries = json.loads(requests.get(sub_url, timeout=15).content).get("body", [])
    return {"info": info, "entries": entries}


def gemini_summarize(entries: list, video_url: str, api_key: str) -> list[dict]:
    """Ask Gemini to split the transcript into topic sections and summarise each.

    Returns a list of {"title": str, "start_time": float, "summary": str}.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite")

    transcript_lines = [
        f"[{e['from']:.1f}s] {e['content']}"
        for e in entries
        if e.get("content", "").strip()
    ]
    prompt = f"""You are given a video transcript with timestamps in seconds.
Divide it into logical topic sections and write a thorough, detailed summary for each section.

Return ONLY a JSON array — no markdown fences, no explanation. Each object must have:
- "title": short section title (5-8 words)
- "start_time": timestamp in seconds (float) where this section begins
- "summary": a thorough bullet-point summary (5-15 bullets). Each bullet covers one key point, argument, example, or conclusion. Preserve specific details such as names, numbers, technical terms, and quoted phrases. Explain the reasoning or context behind each point, not just what was said.

Transcript:
{chr(10).join(transcript_lines)}
"""
    response = model.generate_content(prompt)
    raw = re.sub(r"^```[a-z]*\n?", "", response.text.strip()).rstrip("` \n")
    return json.loads(raw)


def build_markdown(url: str, info: dict, entries: list, summary_sections: list | None = None) -> str:
    """Assemble the full markdown string.

    If summary_sections is provided it is rendered before the raw transcript.
    Returns (slug, markdown_text).
    """
    title = info.get("title", "Untitled")
    slug = slugify(title)

    lines = [f"# {title}\n"]
    if info.get("desc"):
        lines.append(f"> {info['desc']}\n")
    lines.append(f"**URL:** {url}  ")
    if info.get("stat", {}).get("view"):
        lines.append(f"**Views:** {info['stat']['view']}  ")
    if info.get("stat", {}).get("like"):
        lines.append(f"**Likes:** {info['stat']['like']}  ")
    lines.append("\n---\n")

    if summary_sections:
        lines.append("## Summary\n")
        for sec in summary_sections:
            t = sec.get("start_time", 0)
            link = video_url_at(url, t)
            lines.append(f"### [{sec.get('title', 'Section')}]({link}) `{fmt_time(t)}`\n")
            summary = sec.get("summary", "")
            if isinstance(summary, list):
                summary = "\n".join(f"- {item}" for item in summary)
            lines.append(summary)
            lines.append("")
        lines.append("\n---\n")

    lines.append("## Transcript\n")

    # Group consecutive subtitle entries into paragraphs.
    # A new paragraph starts when the gap to the previous entry exceeds PAUSE_THRESHOLD.
    PAUSE_THRESHOLD = 0.8  # seconds

    valid = [e for e in entries if e.get("content", "").strip()]
    para_words: list[str] = []
    para_start_t: float = 0.0
    prev_end_t: float = 0.0

    def flush_para(lines: list, para_words: list, para_start_t: float, url: str) -> None:
        if para_words:
            link = video_url_at(url, para_start_t)
            ts = fmt_time(para_start_t)
            lines.append(f"[{ts}]({link}) {' '.join(para_words)}\n")

    for entry in valid:
        t = entry["from"]
        end_t = entry.get("to", t)
        content = entry["content"].strip()

        if not para_words:
            para_start_t = t
            para_words.append(content)
        elif t - prev_end_t > PAUSE_THRESHOLD:
            flush_para(lines, para_words, para_start_t, url)
            para_words = [content]
            para_start_t = t
        else:
            para_words.append(content)

        prev_end_t = end_t

    flush_para(lines, para_words, para_start_t, url)

    return slug, "\n".join(lines)


def save_markdown(slug: str, markdown: str, output_dir: str = ".") -> Path:
    path = Path(output_dir) / f"{slug}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


if __name__ == "__main__":
    import os
    import argparse

    parser = argparse.ArgumentParser(description="Download Bilibili subtitles as timestamped markdown.")
    parser.add_argument("url", help="Bilibili video URL")
    parser.add_argument("--sessdata", required=True, help="SESSDATA cookie")
    parser.add_argument("--bili-jct", required=True, help="bili_jct cookie")
    parser.add_argument("--buvid3", required=True, help="buvid3 cookie")
    parser.add_argument("--gemini-api-key", default="", help="Gemini API key (overrides GEMINI_API_KEY env var)")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    args = parser.parse_args()

    gemini_key = args.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")

    print("Fetching subtitles...")
    data = fetch_subtitles(args.url, args.sessdata, args.bili_jct, args.buvid3)

    summary_sections = None
    if gemini_key:
        print("Summarising with Gemini...")
        try:
            summary_sections = gemini_summarize(data["entries"], args.url, gemini_key)
        except Exception as e:
            print(f"Gemini summarisation failed: {e}")

    slug, markdown = build_markdown(args.url, data["info"], data["entries"], summary_sections)
    path = save_markdown(slug, markdown, args.output_dir)
    print(f"Saved: {path}")
