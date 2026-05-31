#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from download_subtitles import fetch_subtitles, gemini_summarize, build_markdown

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


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
            print(f"Gemini summarisation failed: {e}")

    slug, markdown = build_markdown(req.url, data["info"], data["entries"], summary_sections)
    return {"title": slug, "markdown": markdown}
