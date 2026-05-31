#!/usr/bin/env python3
import re
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langchain_community.document_loaders import BiliBiliLoader

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


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
    try:
        loader = BiliBiliLoader(
            [req.url],
            sessdata=req.sessdata,
            bili_jct=req.bili_jct,
            buvid3=req.buvid3,
        )
        docs = loader.load()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not docs:
        raise HTTPException(status_code=404, detail="No subtitles found for this URL.")

    doc = docs[0]
    meta = doc.metadata
    title = meta.get("title") or meta.get("aid") or "bilibili-video"
    slug = re.sub(r"[\s_-]+", "-", re.sub(r"[^\w\s-]", "", str(title)).strip().lower())

    lines = [f"# {title}\n"]
    if meta.get("description"):
        lines.append(f"> {meta['description']}\n")
    lines.append(f"**URL:** {req.url}\n")
    if meta.get("view"):
        lines.append(f"**Views:** {meta['view']}  ")
    if meta.get("like"):
        lines.append(f"**Likes:** {meta['like']}  ")
    if meta.get("pubdate"):
        lines.append(f"**Published:** {meta['pubdate']}  ")
    lines.append("\n---\n\n## Subtitles\n")
    lines.append(doc.page_content)

    return {"title": slug, "markdown": "\n".join(lines)}
