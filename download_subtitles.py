#!/usr/bin/env python3
"""Download Bilibili video subtitles as markdown using LangChain BiliBiliLoader."""

import sys
import re
from pathlib import Path
from langchain_community.document_loaders import BiliBiliLoader


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)


def download_subtitles(url: str, output_dir: str = ".") -> Path:
    print(f"Loading: {url}")
    loader = BiliBiliLoader([url])
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
    if len(sys.argv) < 2:
        print("Usage: python download_subtitles.py <bilibili_url> [output_dir]")
        sys.exit(1)

    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    download_subtitles(url, out)
