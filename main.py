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
    if page_match:
        cid = info["pages"][int(page_match.group(1)) - 1]["cid"]
    else:
        cid = info["cid"]

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


def build_markdown(url: str, info: dict, entries: list) -> str:
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

    # Group entries into per-minute sections
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
            ts = fmt_time(section_t)
            link = video_url_at(url, section_t)
            lines.append(f"\n## [{ts}]({link})\n")

        ts = fmt_time(t)
        link = video_url_at(url, t)
        lines.append(f"[{ts}]({link}) {content}  ")

    return slug, "\n".join(lines)


class SubtitleRequest(BaseModel):
    url: str
    sessdata: str = ""
    bili_jct: str = ""
    buvid3: str = ""


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

    slug, markdown = build_markdown(req.url, data["info"], data["entries"])
    return {"title": slug, "markdown": markdown}
