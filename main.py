#!/usr/bin/env python3
import re
import json
import requests as req_lib
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

BV_PATTERN = re.compile(r"BV\w+")
AV_PATTERN = re.compile(r"av[0-9]+")
PAGE_PATTERN = re.compile(r"[?&]p=(\d+)")


def fmt_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def video_url_at(base_url: str, t: float) -> str:
    clean = base_url.split("?")[0].rstrip("/")
    return f"{clean}?t={int(t)}"


def fetch_subtitles(url: str, sessdata: str, bili_jct: str, buvid3: str) -> dict:
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

    resp = req_lib.get(sub_url, timeout=15)
    resp.raise_for_status()
    entries = json.loads(resp.content).get("body", [])

    return {"info": info, "entries": entries}


def gemini_summarize(entries: list, video_url: str, api_key: str) -> list[dict]:
    """Ask Gemini to split the transcript into topic sections and summarize each.

    Returns a list of {"title": str, "start_time": float, "summary": str}.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    transcript_lines = [
        f"[{entry['from']:.1f}s] {entry['content']}"
        for entry in entries
        if entry.get("content", "").strip()
    ]
    transcript_text = "\n".join(transcript_lines)

    prompt = f"""You are given a video transcript with timestamps in seconds.
Divide it into logical topic sections and write a concise summary for each section.

Return ONLY a JSON array — no markdown fences, no explanation. Each object must have:
- "title": short section title (5-8 words)
- "start_time": timestamp in seconds (float) where this section begins
- "summary": 2-4 sentence summary of what is discussed

Transcript:
{transcript_text}
"""

    response = model.generate_content(prompt)
    raw = response.text.strip()
    # Strip accidental markdown code fences
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("` \n")
    return json.loads(raw)


def build_markdown(url: str, info: dict, entries: list, summary_sections: list | None) -> tuple[str, str]:
    title = info.get("title", "Untitled")
    slug = re.sub(r"[\s_-]+", "-", re.sub(r"[^\w\s-]", "", title).strip().lower())

    lines = [f"# {title}\n"]
    if info.get("desc"):
        lines.append(f"> {info['desc']}\n")
    lines.append(f"**URL:** {url}  ")
    if info.get("stat", {}).get("view"):
        lines.append(f"**Views:** {info['stat']['view']}  ")
    if info.get("stat", {}).get("like"):
        lines.append(f"**Likes:** {info['stat']['like']}  ")
    lines.append("\n---\n")

    # Summary block (before raw transcript)
    if summary_sections:
        lines.append("## Summary\n")
        for sec in summary_sections:
            t = sec.get("start_time", 0)
            sec_title = sec.get("title", "Section")
            summary = sec.get("summary", "")
            link = video_url_at(url, t)
            ts = fmt_time(t)
            lines.append(f"### [{sec_title}]({link}) `{ts}`\n")
            lines.append(f"{summary}\n")
        lines.append("\n---\n")

    # Raw transcript grouped by minute
    lines.append("## Transcript\n")
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
            lines.append(f"\n### [{fmt_time(section_t)}]({video_url_at(url, section_t)})\n")
        lines.append(f"[{fmt_time(t)}]({video_url_at(url, t)}) {content}  ")

    return slug, "\n".join(lines)


class SubtitleRequest(BaseModel):
    url: str
    sessdata: str = ""
    bili_jct: str = ""
    buvid3: str = ""
    gemini_api_key: str = ""


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/subtitles")
def get_subtitles(req: SubtitleRequest):
    if not req.sessdata or not req.bili_jct or not req.buvid3:
        raise HTTPException(status_code=400, detail="SESSDATA, bili_jct, and buvid3 are all required.")

    try:
        data = fetch_subtitles(req.url, req.sessdata, req.bili_jct, req.buvid3)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    summary_sections = None
    if req.gemini_api_key:
        try:
            summary_sections = gemini_summarize(data["entries"], req.url, req.gemini_api_key)
        except Exception as e:
            # Non-fatal: proceed without summary if Gemini fails
            summary_sections = None
            print(f"Gemini summarization failed: {e}")

    slug, markdown = build_markdown(req.url, data["info"], data["entries"], summary_sections)
    return {"title": slug, "markdown": markdown}
