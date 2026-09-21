#!/usr/bin/env python3
import os
import re
import json
import urllib.parse
from pathlib import Path

try:
    from mutagen.mp3 import MP3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent

def clean_chapter_name(filename_stem: str) -> str:
    name = filename_stem
    name = re.sub(r'^\d+\s*[-–—.]\s*', '', name)
    name = re.sub(r'\s*[-–—]\s*[-–—]\s*', ': ', name)
    name = re.sub(r'\s*[-–—]\s*', ': ', name)
    name = re.sub(r':\s*:\s*', ': ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def get_audio_duration(file_path: Path) -> float:
    if MUTAGEN_AVAILABLE and file_path.suffix.lower() == ".mp3":
        try:
            return round(MP3(str(file_path)).info.length, 1)
        except Exception:
            pass
    size_bytes = file_path.stat().st_size
    return round((size_bytes * 8) / 64000, 1)

def scan():
    books = []
    ignored = {'.git', '.github', '__pycache__', 'node_modules', 'scratch'}

    for item in sorted(BASE_DIR.iterdir()):
        if not item.is_dir() or item.name in ignored or item.name.startswith('.'):
            continue

        audio_files = sorted(
            [f for f in item.iterdir() if f.suffix.lower() in [".mp3", ".m4a", ".wav", ".aac", ".ogg"]],
            key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', x.name)]
        )

        if not audio_files:
            continue

        title = item.name
        book_id = re.sub(r'[^a-zA-Z0-9_\-]+', '-', title.lower()).strip('-')

        cover_rel = None
        for c_name in ["cover.jpg", "cover.jpeg", "cover.png", "Cover.jpg", "Cover.jpeg", "Cover.png"]:
            if (item / c_name).exists():
                cover_rel = f"{urllib.parse.quote(item.name)}/{urllib.parse.quote(c_name)}"
                break

        chapters = []
        total_duration = 0.0

        for idx, af in enumerate(audio_files):
            clean_name = clean_chapter_name(af.stem)
            duration = get_audio_duration(af)
            total_duration += duration

            stream_rel = f"{urllib.parse.quote(item.name)}/{urllib.parse.quote(af.name)}"

            chapters.append({
                "index": idx,
                "name": clean_name,
                "file_size": af.stat().st_size,
                "duration": duration,
                "stream_url": stream_rel
            })

        books.append({
            "id": book_id,
            "title": title,
            "author": "Audiobook",
            "cover_url": cover_rel,
            "cover_version": "1",
            "chapters": chapters,
            "total_tracks": len(chapters),
            "total_duration": total_duration
        })

    output_file = BASE_DIR / "books.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"books": books}, f, indent=2, ensure_ascii=False)

    print(f"Generated {output_file} with {len(books)} book(s) and {sum(len(b['chapters']) for b in books)} chapter(s).")

if __name__ == "__main__":
    scan()
