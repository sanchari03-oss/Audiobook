#!/usr/bin/env python3
"""
Audiobook Maker - Professional Chapter-by-Chapter Audiobook Generator
Converts PDF, EPUB, and TXT files into full audiobooks using high-quality neural voices.
"""

import os
import sys
import time
import json

# Add environment package paths
import os
for extra_p in [
    os.path.expanduser('~/snap/antigravity-cli/common/local/lib/python3.12/dist-packages'),
    '/home/ssk/snap/antigravity-cli/common/local/lib/python3.12/dist-packages',
    '/home/ssk/.kokoro_venv/lib/python3.12/site-packages'
]:
    if os.path.exists(extra_p) and extra_p not in sys.path:
        sys.path.append(extra_p)
import re
import argparse
import asyncio
import socket
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4_first(*args, **kwargs):
    res = _orig_getaddrinfo(*args, **kwargs)
    ipv4 = [r for r in res if r[0] == socket.AF_INET]
    return ipv4 if ipv4 else res
socket.getaddrinfo = _getaddrinfo_ipv4_first
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import pypdf
import edge_tts
from tqdm import tqdm
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TALB, TPE1, TPE2, TCOM, TRCK
from PIL import Image, ImageDraw, ImageFont

# Curated high-quality neural voices
RECOMMENDED_VOICES = {
    "en-US-AndrewMultilingualNeural": "Option 1 (Default) - Male (US) - Warm, engaging, natural American storyteller",
    "en-US-BrianMultilingualNeural": "Option 2 - Male (US) - Deep, dynamic, engaging American narrator",
    "en-GB-RyanNeural": "Option 3 - Male (UK) - Sophisticated, classic British narrator",
    "en-US-ChristopherNeural": "Male (US) - Deep, formal narrator",
    "en-US-GuyNeural": "Male (US) - Casual, clear non-fiction narrator",
    "en-US-JennyNeural": "Female (US) - Expressive, clear, crisp storytelling",
    "en-GB-SoniaNeural": "Female (UK) - Warm, articulate British voice",
    "en-IN-PrabhatNeural": "Male (Indian English) - Clear, natural",
    "en-IN-NeerjaExpressiveNeural": "Female (Indian English) - Warm, expressive",
}

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"

VOICE_ALIASES = {
    "1": "en-US-AndrewMultilingualNeural",
    "andrew": "en-US-AndrewMultilingualNeural",
    "2": "en-US-BrianMultilingualNeural",
    "brian": "en-US-BrianMultilingualNeural",
    "3": "en-GB-RyanNeural",
    "ryan": "en-GB-RyanNeural",
    "british": "en-GB-RyanNeural",
    "adam": "am_adam",
    "george": "bm_george",
    "ava": "en-US-AvaMultilingualNeural",
    "guy": "en-US-GuyNeural",
    "libby": "en-GB-LibbyNeural",
    "sonia": "en-GB-SoniaNeural",
    "thomas": "en-GB-ThomasNeural",
    "christopher": "en-US-ChristopherNeural",
}

def resolve_voice(voice_input: str) -> str:
    cleaned = (voice_input or "").strip()
    return VOICE_ALIASES.get(cleaned.lower(), cleaned or DEFAULT_VOICE)

ROMAN_NUMERALS = {
    'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
    'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15, 'XVI': 16, 'XVII': 17, 'XVIII': 18, 'XIX': 19, 'XX': 20
}

def clean_extracted_text(text: str) -> str:
    """Clean PDF text artifacts, fix line breaks, and normalize whitespace."""
    if not text:
        return ""
    
    # Replace weird unicode quotes, dashes, etc.
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    text = text.replace('—', ' — ').replace('–', ' - ')

    # Fix hyphenation across line breaks (e.g. "com-\nputer" -> "computer")
    text = re.sub(r'(\b\w+)-\n(\w+\b)', r'\1\2', text)

    # Rejoin soft linebreaks
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        # Filter out standalone page numbers (e.g., lines with just "123" or "- 123 -")
        if re.match(r'^-?\s*\d+\s*-?$', stripped):
            continue
        # Filter out URL footers, page stamps like (7 of 71) [2/20/2001 ...]
        if re.search(r'https?://\S+', stripped) or re.search(r'\(\d+\s+of\s+\d+\)\s+\[.*?\]', stripped):
            continue
        # Filter out standalone symbol dividers (e.g. "* * *", "---", "___", "***", "• • •", "=====")
        if re.match(r'^(?:[\*\-_=~#•·]\s*){2,}$', stripped):
            continue
        # Clean repetitive symbol fills like "ENTER PASS-KEY ______" -> "ENTER PASS-KEY"
        stripped = re.sub(r'[_=\-~*]{3,}', '', stripped).strip()
        if not stripped:
            continue

        # Filter out raw cryptographic ciphertext / hash strings (e.g. "JHdja3jKHDhmado/ertwtjlw+jgj328")
        words = stripped.split()
        filtered_words = []
        for w in words:
            # If word is a long unpronounceable random hash (>18 chars, contains letters + digits or slashes)
            if len(w) > 18 and re.search(r'\d', w) and re.search(r'[a-zA-Z]', w) and not re.search(r'https?://', w):
                continue
            filtered_words.append(w)
        stripped = " ".join(filtered_words).strip()
        if not stripped:
            continue

        cleaned_lines.append(stripped)

    # Reconstruct paragraphs
    reconstructed = []
    buffer = ""
    for line in cleaned_lines:
        is_heading = (
            line.upper() in ROMAN_NUMERALS or
            bool(re.match(r'^(?:CHAPTER|Chapter|BOOK|Book|PART|Part|ACT|Act)\s+(?:[0-9]+|[IVXLCDM]+|[A-Za-z]+)', line)) or
            bool(re.match(r'^(?:PROLOGUE|Prologue|EPILOGUE|Epilogue|PREFACE|Preface)', line)) or
            bool(re.match(r'^[0-9]{1,3}\.$', line))
        )
        if is_heading:
            if buffer:
                reconstructed.append(buffer)
                buffer = ""
            reconstructed.append(line)
        elif not line:
            if buffer:
                reconstructed.append(buffer)
                buffer = ""
        else:
            if buffer:
                buffer += " " + line
            else:
                buffer = line
    if buffer:
        reconstructed.append(buffer)

    return "\n\n".join(reconstructed)

def extract_outline_chapters(reader: pypdf.PdfReader) -> List[Tuple[str, int]]:
    """Extract chapter titles and starting page indices from PDF outline/bookmarks if available."""
    chapters = []
    try:
        outline = reader.outline
        if not outline:
            return []

        def traverse(items):
            for item in items:
                if isinstance(item, list):
                    traverse(item)
                elif hasattr(item, 'title') and hasattr(item, 'page'):
                    try:
                        title = str(item.title).strip()
                        # Ignore symbol dividers in outline like "* * *", "---", "..."
                        if re.match(r'^(?:[\*\-_=~#•·\s]){2,}$', title) or not title:
                            continue
                        page_num = reader.get_destination_page_number(item)
                        if page_num is not None and page_num >= 0:
                            chapters.append((title, page_num))
                    except Exception:
                        pass
        traverse(outline)
    except Exception:
        return []

    # If the outline contains clear numbered chapters (e.g. 1..133 or Chapter 1..N),
    # filter out internal sub-bookmarks (like memos, scene dividers) that fall within chapters.
    numbered_chapters = [
        (t, p) for (t, p) in chapters
        if re.match(r'^(?:chapter\s+\d+|\d+|prologue|epilogue|author[’\']?s note|acknowledgments)$', t, re.IGNORECASE)
    ]
    if len(numbered_chapters) >= 10:
        chapters = numbered_chapters

    chapters.sort(key=lambda x: x[1])
    unique_chapters = []
    seen_pages = set()
    for title, page in chapters:
        clean_title = f"Chapter {title}" if title.isdigit() else title
        if page not in seen_pages:
            unique_chapters.append((clean_title, page))
            seen_pages.add(page)

    return unique_chapters

def extract_cover_image(reader: pypdf.PdfReader, output_cover_path: Path) -> bool:
    """Try to extract a cover image from the first 3 pages of the PDF."""
    try:
        max_pages = min(3, len(reader.pages))
        best_image = None
        best_size = 0

        for page_idx in range(max_pages):
            page = reader.pages[page_idx]
            for img_file in page.images:
                data = img_file.data
                if len(data) > best_size:
                    best_size = len(data)
                    best_image = data

        if best_image and best_size > 15000:
            with open(output_cover_path, "wb") as f:
                f.write(best_image)
            return True
    except Exception:
        pass
    return False

def generate_fallback_cover(title: str, author: str, output_cover_path: Path):
    """Generate a clean typographic cover if no image was extracted."""
    try:
        width, height = 800, 1200
        img = Image.new("RGB", (width, height), color=(24, 28, 36))
        draw = ImageDraw.Draw(img)

        # Gold frame border
        draw.rectangle([30, 30, width - 30, height - 30], outline=(200, 160, 50), width=4)
        draw.rectangle([42, 42, width - 42, height - 42], outline=(200, 160, 50), width=1)

        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 44)
            author_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
            sub_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except Exception:
            title_font = ImageFont.load_default()
            author_font = ImageFont.load_default()
            sub_font = ImageFont.load_default()

        # Header badge
        draw.text((width // 2, 120), "AUDIOBOOK EDITION", fill=(200, 160, 50), font=sub_font, anchor="mm")

        # Word wrap title
        words = title.split()
        lines = []
        cur_line = []
        for w in words:
            cur_line.append(w)
            if len(" ".join(cur_line)) > 24:
                lines.append(" ".join(cur_line))
                cur_line = []
        if cur_line:
            lines.append(" ".join(cur_line))

        y_start = height // 2 - (len(lines) * 35)
        for i, line in enumerate(lines[:6]):
            draw.text((width // 2, y_start + (i * 60)), line, fill=(255, 255, 255), font=title_font, anchor="mm")

        if author:
            draw.text((width // 2, height - 160), f"BY {author.upper()}", fill=(200, 200, 200), font=author_font, anchor="mm")

        img.save(output_cover_path, "JPEG", quality=92)
        return True
    except Exception:
        return False

def parse_pdf_into_chapters(pdf_path: str, min_words: int = 100, checkpoint_dir: Optional[Path] = None) -> Tuple[str, str, List[Dict[str, str]]]:
    """Parse PDF into chapters using bookmarks or pattern detection, with checkpoint support."""
    # 0. Checkpoint Stage 2: 02_clean_text.json
    if checkpoint_dir:
        clean_text_ckpt = checkpoint_dir / "02_clean_text.json"
        if clean_text_ckpt.exists():
            try:
                with open(clean_text_ckpt, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    chaps = data.get("chapters", [])
                    if chaps:
                        print(f"📦 Checkpoint 02_clean_text.json loaded! Restored {len(chaps)} cleaned chapters without re-parsing PDF.")
                        return data.get("title", Path(pdf_path).stem), data.get("author", "Unknown Author"), chaps
            except Exception as e:
                print(f"⚠️ Warning reading 02_clean_text.json: {e}")

    print(f"📖 Opening PDF: {pdf_path}")
    reader = pypdf.PdfReader(pdf_path)
    total_pages = len(reader.pages)
    
    meta = reader.metadata or {}
    book_title = meta.title or Path(pdf_path).stem.replace('_', ' ').replace('-', ' ').title()
    book_author = meta.author or "Unknown Author"

    # 1. Outline / bookmarks with Checkpoint Stage 1: 01_outline.json
    outline_chapters = []
    if checkpoint_dir:
        outline_ckpt = checkpoint_dir / "01_outline.json"
        if outline_ckpt.exists():
            try:
                with open(outline_ckpt, "r", encoding="utf-8") as f:
                    outline_data = json.load(f)
                    outline_chapters = [(item["title"], item["page"]) for item in outline_data.get("outline", [])]
                    book_title = outline_data.get("title", book_title)
                    book_author = outline_data.get("author", book_author)
                    print(f"📦 Checkpoint 01_outline.json loaded! Restored {len(outline_chapters)} bookmarks.")
            except Exception as e:
                print(f"⚠️ Warning reading 01_outline.json: {e}")
                outline_chapters = extract_outline_chapters(reader)
        else:
            outline_chapters = extract_outline_chapters(reader)
            if outline_chapters:
                try:
                    outline_payload = {
                        "title": book_title,
                        "author": book_author,
                        "outline": [{"title": t, "page": p} for t, p in outline_chapters]
                    }
                    with open(outline_ckpt, "w", encoding="utf-8") as f:
                        json.dump(outline_payload, f, indent=2, ensure_ascii=False)
                    print(f"💾 Checkpointed stage 1: {outline_ckpt.name} ({len(outline_chapters)} bookmarks saved)")
                except Exception as e:
                    print(f"⚠️ Warning saving 01_outline.json: {e}")
    else:
        outline_chapters = extract_outline_chapters(reader)

    chapters = []

    if outline_chapters:
        print(f"✨ Found {len(outline_chapters)} chapters in PDF table of contents!")
        for i, (title, start_page) in enumerate(outline_chapters):
            end_page = outline_chapters[i + 1][1] if i + 1 < len(outline_chapters) else total_pages
            chapter_text_parts = []
            for p_num in range(start_page, min(end_page, total_pages)):
                try:
                    p_text = reader.pages[p_num].extract_text()
                    if p_text:
                        chapter_text_parts.append(p_text)
                except Exception:
                    pass
            full_text = clean_extracted_text("\n\n".join(chapter_text_parts))
            word_count = len(full_text.split())
            if word_count >= min_words:
                clean_title = re.sub(r'[\\/*?:"<>|]', '', title).strip()
                chapters.append({
                    "title": clean_title,
                    "text": full_text,
                    "word_count": word_count
                })

    # 2. Heuristic regex scanning if outline not present or insufficient
    if len(chapters) < 2:
        print("🔍 Scanning document pages for chapter headings...")
        full_doc_pages = []
        for p_idx in tqdm(range(total_pages), desc="Reading pages"):
            try:
                t = reader.pages[p_idx].extract_text()
                if t:
                    full_doc_pages.append(t)
            except Exception:
                pass

        full_doc_text = "\n\n".join(full_doc_pages)
        full_doc_text = clean_extracted_text(full_doc_text)

        chapter_pattern = re.compile(
            r'(?m)^[ \t]*(?:(?:CHAPTER|Chapter|BOOK|Book|PART|Part|ACT|Act)\s+(?:[0-9]+|[IVXLCDM]+|[A-Za-z]+)|[0-9]{1,3}\.|PROLOGUE|Prologue|EPILOGUE|Epilogue|PREFACE|Preface|INTRODUCTION|Introduction|CONCLUSION|Conclusion)(?:\s*[:\-\—\.\n]\s*[^\n]{1,80})?$',
            re.MULTILINE
        )

        matches = list(chapter_pattern.finditer(full_doc_text))
        
        if len(matches) >= 2:
            print(f"🎯 Detected {len(matches)} chapter divisions via pattern matching.")
            for i, match in enumerate(matches):
                chap_title = match.group(0).strip().replace('\n', ' - ')
                start_pos = match.start()
                end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(full_doc_text)
                chap_body = full_doc_text[start_pos:end_pos].strip()
                word_count = len(chap_body.split())
                if word_count >= min_words:
                    m_num = re.match(r'^\s*(\d+)\.?\s*$', chap_title)
                    m_part = re.match(r'^\s*PART\s+[A-Za-z]+\s*[-–—\s]+\s*(\d+)\.?\s*$', chap_title, re.IGNORECASE)
                    if m_num:
                        clean_title = f"Chapter {m_num.group(1)}"
                    elif m_part:
                        clean_title = f"Chapter {m_part.group(1)}"
                    else:
                        clean_title = re.sub(r'[\\/*?:"<>|]', '', chap_title)
                    chapters.append({
                        "title": clean_title[:60],
                        "text": chap_body,
                        "word_count": word_count
                    })

    # 3. Fallback: Split by ~3,500 words per part
    if not chapters:
        print("ℹ️ No chapter markers found. Splitting book into ~3,500-word logical parts...")
        paragraphs = full_doc_text.split('\n\n')
        cur_chunk = []
        cur_words = 0
        part_num = 1
        
        for p in paragraphs:
            p_words = len(p.split())
            cur_chunk.append(p)
            cur_words += p_words
            if cur_words >= 3500:
                chunk_text = "\n\n".join(cur_chunk)
                chapters.append({
                    "title": f"Part {part_num:02d}",
                    "text": chunk_text,
                    "word_count": len(chunk_text.split())
                })
                cur_chunk = []
                cur_words = 0
                part_num += 1

        if cur_chunk:
            chunk_text = "\n\n".join(cur_chunk)
            chapters.append({
                "title": f"Part {part_num:02d}",
                "text": chunk_text,
                "word_count": len(chunk_text.split())
            })

    if checkpoint_dir and chapters:
        clean_text_ckpt = checkpoint_dir / "02_clean_text.json"
        try:
            clean_payload = {
                "title": book_title,
                "author": book_author,
                "total_chapters": len(chapters),
                "chapters": chapters
            }
            with open(clean_text_ckpt, "w", encoding="utf-8") as f:
                json.dump(clean_payload, f, indent=2, ensure_ascii=False)
            print(f"💾 Checkpointed stage 2: {clean_text_ckpt.name} ({len(chapters)} clean chapters saved)")
        except Exception as e:
            print(f"⚠️ Warning saving 02_clean_text.json: {e}")

    return book_title, book_author, chapters

def chunk_text_for_tts(text: str, max_chars: int = 4000) -> List[str]:
    """Split long chapter text into safe chunks for edge-tts while preserving natural paragraph breaks and pauses."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    cur_chunk = []
    cur_len = 0

    for p in paragraphs:
        p_len = len(p)
        if cur_len + p_len + 2 <= max_chars:
            cur_chunk.append(p)
            cur_len += p_len + 2
        else:
            if cur_chunk:
                chunks.append("\n\n".join(cur_chunk))
                cur_chunk = []
                cur_len = 0
            if p_len > max_chars:
                sentences = re.split(r'(?<=[.!?])\s+', p)
                sub_chunk = []
                sub_len = 0
                for s in sentences:
                    s_len = len(s)
                    if sub_len + s_len + 1 > max_chars and sub_chunk:
                        chunks.append(" ".join(sub_chunk))
                        sub_chunk = [s]
                        sub_len = s_len
                    else:
                        sub_chunk.append(s)
                        sub_len += s_len + 1
                if sub_chunk:
                    cur_chunk.append(" ".join(sub_chunk))
                    cur_len = len(" ".join(sub_chunk))
            else:
                cur_chunk.append(p)
                cur_len = p_len

    if cur_chunk:
        chunks.append("\n\n".join(cur_chunk))

    return chunks

async def synthesize_chunk(text: str, output_path: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz", retries: int = 5, timeout: Optional[float] = None):
    """Synthesize text chunk to MP3 with generous timeout and retry logic to prevent hangs."""
    if timeout is None:
        # Generous timeout: base 90s + 0.1s per char (e.g. 2000 chars = 290s)
        timeout = max(120.0, 90.0 + len(text) * 0.1)

    for attempt in range(retries):
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            await asyncio.wait_for(communicate.save(output_path), timeout=timeout)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return True
        except Exception as e:
            err_name = type(e).__name__
            err_msg = str(e) if str(e) else err_name
            if attempt == retries - 1:
                raise Exception(f"Chunk synthesis failed after {retries} attempts ({err_msg})")
            await asyncio.sleep(2.0 * (attempt + 1))
    return False

async def generate_chapter_audio(
    chapter_text: str,
    output_mp3_path: Path,
    voice: str,
    rate: str,
    pitch: str,
    max_chunk_chars: int = 3800
):
    """Synthesize a complete chapter in parallel chunks with timeout protection and live progress."""
    chunks = chunk_text_for_tts(chapter_text, max_chars=max_chunk_chars)
    total_chunks = len(chunks)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_files = [Path(tmpdir) / f"part_{idx:04d}.mp3" for idx in range(total_chunks)]
        
        # Concurrently process 3 chunks at a time for optimal throughput and reliability
        sem = asyncio.Semaphore(3)
        pbar = tqdm(total=total_chunks, desc=f"   ⚡ Chunks", leave=False, unit="chk")

        async def process_one(idx, text_chunk, out_file):
            async with sem:
                await synthesize_chunk(text_chunk, str(out_file), voice, rate, pitch)
                pbar.update(1)

        tasks = [process_one(i, chk, tmp_files[i]) for i, chk in enumerate(chunks)]
        await asyncio.gather(*tasks)
        pbar.close()
        
        # Concatenate all parts into final chapter MP3
        with open(output_mp3_path, "wb") as outfile:
            for part_file in tmp_files:
                if part_file.exists():
                    with open(part_file, "rb") as infile:
                        outfile.write(infile.read())

def generate_chapter_kokoro(
    chapter_text: str,
    output_mp3_path: Path,
    kokoro_inst,
    voice: str = "am_adam",
    speed: float = 1.0,
    denoise: bool = True
):
    """Synthesize a chapter using local Kokoro AI with denoised studio mastering."""
    import numpy as np
    import soundfile as sf
    import subprocess

    chunks = chunk_text_for_tts(chapter_text, max_chars=1200)
    all_samples = []
    sample_rate = 24000
    lang = "en-gb" if voice.startswith("b") else "en-us"

    for chk in tqdm(chunks, desc=f"   ⚡ Kokoro Chunks", leave=False, unit="chk"):
        chk_clean = chk.strip()
        if not chk_clean:
            continue
        try:
            samples, sr = kokoro_inst.create(chk_clean, voice=voice, speed=speed, lang=lang)
            sample_rate = sr
            all_samples.append(samples)
        except Exception as e:
            print(f"      ⚠️ Kokoro chunk warning: {e}")

    if not all_samples:
        raise Exception("No audio samples produced by Kokoro")

    concat_audio = np.concatenate(all_samples)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        wav_path = tmp_wav.name

    try:
        sf.write(wav_path, concat_audio, sample_rate)
        cmd = ["ffmpeg", "-y", "-i", wav_path]
        if denoise:
            cmd.extend(["-af", "afftdn=nf=-25"])
        cmd.extend(["-b:a", "192k", str(output_mp3_path)])
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

def tag_mp3(
    file_path: Path,
    track_num: int,
    total_tracks: int,
    title: str,
    album: str,
    artist: str,
    voice: str,
    cover_image_path: Optional[Path] = None
):
    """Set standard audiobook ID3 tags and embed cover image."""
    try:
        audio = MP3(file_path, ID3=ID3)
        try:
            audio.add_tags()
        except Exception:
            pass

        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TALB(encoding=3, text=album))
        audio.tags.add(TPE1(encoding=3, text=artist))
        audio.tags.add(TPE2(encoding=3, text=artist))
        audio.tags.add(TCOM(encoding=3, text=f"Narrated by {voice}"))
        audio.tags.add(TRCK(encoding=3, text=f"{track_num}/{total_tracks}"))

        if cover_image_path and cover_image_path.exists():
            with open(cover_image_path, "rb") as img_f:
                audio.tags.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,  # Front cover
                        desc="Cover",
                        data=img_f.read()
                    )
                )

        audio.save(v2_version=3)
    except Exception as e:
        print(f"⚠️ Warning: Could not set all ID3 tags for {file_path.name}: {e}")

async def process_audiobook(args):
    """Main async pipeline for processing the book into an audiobook with idempotent checkpoints."""
    pdf_path = Path(args.input).expanduser().resolve()
    if not pdf_path.exists():
        print(f"❌ Error: File not found: {pdf_path}")
        sys.exit(1)

    # 1. Output directory & .checkpoints setup upfront (DDIA Ch 10)
    meta_title = args.title or pdf_path.stem.replace('_', ' ').replace('-', ' ').title()
    clean_folder_name = re.sub(r'[\\/*?:"<>|]', '', f"{meta_title} - Audiobook").strip()
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    else:
        output_dir = pdf_path.parent / clean_folder_name

    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = output_dir / ".checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Saving audiobook tracks to: {output_dir}")
    print(f"📦 Checkpoint directory: {checkpoint_dir}\n")

    # 2. Parse PDF or restore from checkpoints (01_outline.json, 02_clean_text.json)
    book_title, book_author, chapters = parse_pdf_into_chapters(
        str(pdf_path),
        min_words=args.min_chapter_words,
        checkpoint_dir=checkpoint_dir
    )

    if args.title:
        book_title = args.title
    if args.author:
        book_author = args.author

    print(f"\n📚 Book Title: {book_title}")
    print(f"✍️ Author: {book_author}")
    print(f"🎙️ Narrator Voice: {args.voice}")
    print(f"📑 Total Chapters/Parts: {len(chapters)}")

    total_words = sum(c['word_count'] for c in chapters)
    estimated_mins = int(total_words / 150)
    hours = estimated_mins // 60
    mins = estimated_mins % 60
    print(f"⏱️ Total Words: ~{total_words:,} words (Estimated listening time: {hours}h {mins}m)")

    if args.preview:
        print("\n--- Chapter Preview ---")
        for i, chap in enumerate(chapters, 1):
            print(f"[{i:02d}/{len(chapters):02d}] {chap['title']} ({chap['word_count']:,} words)")
        print("\nPreview mode only. No audio was generated.")
        return

    if not chapters:
        print("❌ Error: Could not extract any readable text or chapters from the document.")
        sys.exit(1)

    # 3. Checkpoint Stage 3: Load track completion status
    tracks_status_ckpt = checkpoint_dir / "03_tracks_status.json"
    tracks_status = {}
    if tracks_status_ckpt.exists():
        try:
            with open(tracks_status_ckpt, "r", encoding="utf-8") as f:
                tracks_status = json.load(f)
            print(f"📦 Loaded checkpoint: 03_tracks_status.json ({len(tracks_status)} tracks previously completed)")
        except Exception as e:
            print(f"⚠️ Warning reading 03_tracks_status.json: {e}")

    # 4. Extract or generate cover art
    cover_path = output_dir / "cover.jpg"
    if not cover_path.exists():
        print("🎨 Generating audiobook cover art...")
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            has_cover = extract_cover_image(reader, cover_path)
        except Exception:
            has_cover = False
        if not has_cover:
            generate_fallback_cover(book_title, book_author, cover_path)

    # 5. Generate audio chapter by chapter
    total_tracks = len(chapters)
    playlist_entries = []
    failed_chapters = []

    kokoro_inst = None
    if getattr(args, 'engine', 'edge') == 'kokoro':
        print("🧠 Initializing Kokoro Neural AI Engine (Adam Denoised)...")
        from kokoro_onnx import Kokoro
        k_model = os.path.expanduser("~/.local/share/kokoro/kokoro-v1.0.int8.onnx")
        k_voices = os.path.expanduser("~/.local/share/kokoro/voices-v1.0.bin")
        kokoro_inst = Kokoro(k_model, k_voices)
        if args.voice in [DEFAULT_VOICE, "en-US-AndrewMultilingualNeural"]:
            args.voice = "am_adam"

    print("🚀 Starting narration generation...\n")
    for i, chap in enumerate(chapters, 1):
        track_filename = f"{i:02d} - {chap['title']}.mp3"
        track_path = output_dir / track_filename
        playlist_entries.append(track_filename)

        if getattr(args, 'start_chapter', None) and i < args.start_chapter:
            continue
        if getattr(args, 'end_chapter', None) and i > args.end_chapter:
            continue

        # Checkpoint resume check (DDIA Ch 10 - Idempotency)
        is_ckpt_done = (
            tracks_status.get(str(i), {}).get("status") == "completed" and
            track_path.exists() and
            track_path.stat().st_size > 1000
        )

        if is_ckpt_done or (track_path.exists() and track_path.stat().st_size > 1000):
            if not is_ckpt_done:
                tracks_status[str(i)] = {
                    "status": "completed",
                    "track_num": i,
                    "title": chap['title'],
                    "filename": track_filename,
                    "size_bytes": track_path.stat().st_size,
                    "completed_at": time.time()
                }
                with open(tracks_status_ckpt, "w", encoding="utf-8") as f:
                    json.dump(tracks_status, f, indent=2, ensure_ascii=False)
            print(f"⏭️ Skipping [{i:02d}/{total_tracks:02d}] (checkpoint verified): {chap['title']}")
            continue

        print(f"🔊 Narrating [{i:02d}/{total_tracks:02d}]: {chap['title']} ({chap['word_count']:,} words)...")
        try:
            if getattr(args, 'engine', 'edge') == 'kokoro':
                generate_chapter_kokoro(
                    chapter_text=chap['text'],
                    output_mp3_path=track_path,
                    kokoro_inst=kokoro_inst,
                    voice=args.voice,
                    speed=1.0,
                    denoise=True
                )
            else:
                await generate_chapter_audio(
                    chapter_text=chap['text'],
                    output_mp3_path=track_path,
                    voice=args.voice,
                    rate=args.rate,
                    pitch=args.pitch,
                    max_chunk_chars=args.max_chunk_chars
                )
            tag_mp3(
                file_path=track_path,
                track_num=i,
                total_tracks=total_tracks,
                title=chap['title'],
                album=book_title,
                artist=book_author,
                voice=args.voice,
                cover_image_path=cover_path if cover_path.exists() else None
            )

            # Record track completion in 03_tracks_status.json checkpoint
            tracks_status[str(i)] = {
                "status": "completed",
                "track_num": i,
                "title": chap['title'],
                "filename": track_filename,
                "size_bytes": track_path.stat().st_size,
                "completed_at": time.time()
            }
            with open(tracks_status_ckpt, "w", encoding="utf-8") as f:
                json.dump(tracks_status, f, indent=2, ensure_ascii=False)

            print(f"   ✅ Done & Checkpointed: {track_filename}")
        except Exception as e:
            print(f"   ❌ Error generating chapter {i}: {e}")
            failed_chapters.append((i, chap, track_filename, track_path))

    # Multi-pass retry for any chapters that failed due to temporary network issues
    retry_pass = 1
    max_retry_passes = 3
    while failed_chapters and retry_pass <= max_retry_passes:
        print(f"\n🔄 [Pass {retry_pass}/{max_retry_passes}] Retrying {len(failed_chapters)} failed chapter(s)...")
        still_failed = []
        for i, chap, track_filename, track_path in failed_chapters:
            print(f"🔊 Retrying [{i:02d}/{total_tracks:02d}]: {chap['title']}...")
            try:
                if getattr(args, 'engine', 'edge') == 'kokoro':
                    generate_chapter_kokoro(
                        chapter_text=chap['text'],
                        output_mp3_path=track_path,
                        kokoro_inst=kokoro_inst,
                        voice=args.voice,
                        speed=1.0,
                        denoise=True
                    )
                else:
                    await generate_chapter_audio(
                        chapter_text=chap['text'],
                        output_mp3_path=track_path,
                        voice=args.voice,
                        rate=args.rate,
                        pitch=args.pitch,
                        max_chunk_chars=args.max_chunk_chars
                    )
                tag_mp3(
                    file_path=track_path,
                    track_num=i,
                    total_tracks=total_tracks,
                    title=chap['title'],
                    album=book_title,
                    artist=book_author,
                    voice=args.voice,
                    cover_image_path=cover_path if cover_path.exists() else None
                )

                # Update checkpoint on successful retry
                tracks_status[str(i)] = {
                    "status": "completed",
                    "track_num": i,
                    "title": chap['title'],
                    "filename": track_filename,
                    "size_bytes": track_path.stat().st_size,
                    "completed_at": time.time()
                }
                with open(tracks_status_ckpt, "w", encoding="utf-8") as f:
                    json.dump(tracks_status, f, indent=2, ensure_ascii=False)

                print(f"   ✅ Done on retry & Checkpointed: {track_filename}")
            except Exception as e:
                print(f"   ❌ Retry failed for chapter {i}: {e}")
                still_failed.append((i, chap, track_filename, track_path))
        failed_chapters = still_failed
        retry_pass += 1
        if failed_chapters:
            await asyncio.sleep(3.0)

    # Count successful tracks
    scope_entries = [
        f"{i:02d} - {chap['title']}.mp3"
        for i, chap in enumerate(chapters, 1)
        if (not getattr(args, 'start_chapter', None) or i >= args.start_chapter) and (not getattr(args, 'end_chapter', None) or i <= args.end_chapter)
    ]
    completed_scope_tracks = [output_dir / f for f in scope_entries if (output_dir / f).exists() and (output_dir / f).stat().st_size > 1000]
    all_completed = [output_dir / f for f in playlist_entries if (output_dir / f).exists() and (output_dir / f).stat().st_size > 1000]

    # 6. Create M3U playlist file
    playlist_path = output_dir / "audiobook.m3u"
    with open(playlist_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for entry in playlist_entries:
            if (output_dir / entry).exists():
                f.write(f"{entry}\n")

    if len(completed_scope_tracks) < len(scope_entries):
        missing = [f for f in scope_entries if not (output_dir / f).exists() or (output_dir / f).stat().st_size <= 1000]
        print("\n" + "="*60)
        print(f"❌ RANGE INCOMPLETE! ({len(completed_scope_tracks)}/{len(scope_entries)} tracks generated)")
        print(f"⚠️ Missing tracks ({len(missing)}): {missing}")
        print(f"📁 Location: {output_dir}")
        print("="*60 + "\n")
        sys.exit(1)

    # 7. Checkpoint Stage 4: Mark pipeline complete
    pipeline_complete_ckpt = checkpoint_dir / "04_pipeline_complete.json"
    with open(pipeline_complete_ckpt, "w", encoding="utf-8") as f:
        json.dump({
            "status": "completed",
            "book_title": book_title,
            "book_author": book_author,
            "total_tracks": total_tracks,
            "completed_at": time.time()
        }, f, indent=2, ensure_ascii=False)

    print("\n" + "="*60)
    print(f"🎉 AUDIOBOOK GENERATION COMPLETE! ({len(all_completed)}/{total_tracks} total tracks on disk, {len(completed_scope_tracks)} in this range)")
    print(f"📁 Location: {output_dir}")
    print(f"🎵 Playlist: {playlist_path.name}")
    print(f"🖼️ Cover: {cover_path.name}")
    print(f"📦 Checkpoints: {checkpoint_dir}")
    print("="*60 + "\n")

def list_voices():
    print("\n🎧 Curated Expressive Narrator Voices:\n")
    print("  ⭐ Option 1 (Default): 1 / andrew -> en-US-AndrewMultilingualNeural (Male US - Warm, natural, expressive American storyteller)")
    print("  ⭐ Option 2:           2 / brian  -> en-US-BrianMultilingualNeural  (Male US - Deep, dynamic, engaging American narrator)")
    print("  ⭐ Option 3:           3 / ryan   -> en-GB-RyanNeural               (Male UK - Sophisticated, classic British narrator)")
    print("\n  Other available voices:")
    for voice, desc in RECOMMENDED_VOICES.items():
        if voice not in ["en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural", "en-GB-RyanNeural"]:
            print(f"  • {voice}: {desc}")
    print("\n💡 Tip: You can select voices using shortcuts: `--voice 1`, `--voice 2`, or `--voice 3`.")
    print("Example: python3 audiobook_maker.py book.pdf --voice 3\n")

def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF/EPUB/TXT books into complete, chapter-by-chapter audiobooks with expressive neural voices and ID3 metadata.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("input", nargs="?", help="Path to the PDF, EPUB, or TXT file.")
    parser.add_argument("-o", "--output-dir", help="Directory where audiobook will be saved (default: alongside input file)")
    parser.add_argument("-v", "--voice", default=DEFAULT_VOICE, help="Narrator voice: 1 / andrew (US default), 2 / brian (US dynamic), 3 / ryan (British), or full name")
    parser.add_argument("--title", help="Override book title in audiobook metadata")
    parser.add_argument("--author", help="Override author name in audiobook metadata")
    parser.add_argument("--engine", default="edge", choices=["edge", "kokoro"], help="TTS engine: 'edge' (cloud neural) or 'kokoro' (local expressive)")
    parser.add_argument("--rate", default="+8%", help="Speed adjustment (e.g. +10%%, -5%%, default: +8%%)")
    parser.add_argument("--pitch", default="+0Hz", help="Pitch adjustment (default: +0Hz)")
    parser.add_argument("--min-chapter-words", type=int, default=100, help="Minimum words for a chapter (default: 100)")
    parser.add_argument("--max-chunk-chars", type=int, default=3800, help="Max characters per TTS request (default: 3800)")
    parser.add_argument("--start-chapter", type=int, default=1, help="Start chapter number (1-indexed, inclusive)")
    parser.add_argument("--end-chapter", type=int, default=None, help="End chapter number (1-indexed, inclusive)")
    parser.add_argument("--preview", action="store_true", help="Preview detected chapters and word counts without generating audio")
    parser.add_argument("--list-voices", action="store_true", help="List recommended narrator voices and exit")

    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        sys.exit(0)

    if not args.input:
        parser.print_help()
        sys.exit(1)

    args.voice = resolve_voice(args.voice)
    asyncio.run(process_audiobook(args))

if __name__ == "__main__":
    main()
