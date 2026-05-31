#!/usr/bin/env python3
"""Download Bilibili video subtitles as markdown using LangChain BiliBiliLoader."""

import sys
import re
from pathlib import Path
from langchain_community.document_loaders import BiliBiliLoader


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)


def download_subtitles(
    url: str,
    sessdata: str = "",
    bili_jct: str = "",
    buvid3: str = "",
    output_dir: str = ".",
) -> Path:
    print(f"Loading: {url}")
    loader = BiliBiliLoader([url], sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3)
    docs = loader.load()

    if not docs:
        print("No documents returned.")
        sys.exit(1)

    doc = docs[0]
    meta = doc.metadata
    title = meta.get("title") or meta.get("aid") or "bilibili-video"
    filename = f"{slugify(str(title))}.md"
    output_path = Path(output_dir) / filename

    lines = [f"# {title}\n"]
    if meta.get("description"):
        lines.append(f"> {meta['description']}\n")
    lines.append(f"**URL:** {url}\n")
    if meta.get("view"):
        lines.append(f"**Views:** {meta['view']}  ")
    if meta.get("like"):
        lines.append(f"**Likes:** {meta['like']}  ")
    if meta.get("pubdate"):
        lines.append(f"**Published:** {meta['pubdate']}  ")
    lines.append("\n---\n")
    lines.append("## Subtitles\n")
    lines.append(doc.page_content)

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download Bilibili subtitles as markdown.")
    parser.add_argument("url", help="Bilibili video URL")
    parser.add_argument("--sessdata", default="", help="SESSDATA cookie")
    parser.add_argument("--bili-jct", default="", help="bili_jct cookie")
    parser.add_argument("--buvid3", default="", help="buvid3 cookie")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    args = parser.parse_args()

    download_subtitles(
        args.url,
        sessdata=args.sessdata,
        bili_jct=args.bili_jct,
        buvid3=args.buvid3,
        output_dir=args.output_dir,
    )
