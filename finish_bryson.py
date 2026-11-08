#!/usr/bin/env python3
import asyncio
import os
import re
import shutil
import subprocess
import edge_tts

BASE_DIR = "/home/ssk/Desktop/audiobook-website/A Short History of Nearly Everything"
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "transcripts")
VOICE = "en-US-AndrewMultilingualNeural"

# Target mapping: transcript_filename -> output_mp3_name
CHAPTER_FILES = [
    ("20 - Small World.txt", "20 - Chapter 20 - Small World.mp3"),
    ("21 - Life Goes On.txt", "21 - Chapter 21 - Life Goes On.mp3"),
    ("22 - Good-bye to All That.txt", "22 - Chapter 22 - Good-bye to All That.mp3"),
    ("23 - The Richness of Being.txt", "23 - Chapter 23 - The Richness of Being.mp3"),
    ("24 - Cells.txt", "24 - Chapter 24 - Cells.mp3"),
    ("25 - Darwin's Singular Notion.txt", "25 - Chapter 25 - Darwin's Singular Notion.mp3"),
    ("26 - The Stuff of Life.txt", "26 - Chapter 26 - The Stuff of Life.mp3"),
    ("27 - Ice Time.txt", "27 - Chapter 27 - Ice Time.mp3"),
    ("28 - The Mysterious Biped.txt", "28 - Chapter 28 - The Mysterious Biped.mp3"),
    ("29 - The Restless Ape.txt", "29 - Chapter 29 - The Restless Ape.mp3"),
    ("30 - Good-bye.txt", "30 - Chapter 30 - Good-bye.mp3"),
]

def split_text_into_chunks(text, max_len=1800):
    paras = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks = []
    curr = []
    curr_len = 0
    for p in paras:
        if curr_len + len(p) > max_len and curr:
            chunks.append("\n\n".join(curr))
            curr = [p]
            curr_len = len(p)
        else:
            curr.append(p)
            curr_len += len(p) + 2
    if curr:
        chunks.append("\n\n".join(curr))
    return chunks

async def synthesize_chunk(sem, text, out_path, chunk_idx):
    for attempt in range(1, 5):
        async with sem:
            try:
                comm = edge_tts.Communicate(text, VOICE)
                await comm.save(out_path)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    return
            except Exception as e:
                pass
        await asyncio.sleep(attempt * 1.5)
    raise RuntimeError(f"Failed chunk {chunk_idx}")

async def process_chapter(sem, txt_name, mp3_name):
    final_path = os.path.join(BASE_DIR, mp3_name)
    if os.path.exists(final_path) and os.path.getsize(final_path) > 100000:
        print(f"Skipping already completed {mp3_name}")
        return

    txt_path = os.path.join(TRANSCRIPTS_DIR, txt_name)
    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = split_text_into_chunks(text, max_len=1800)
    temp_dir = os.path.join(BASE_DIR, f".tmp_{txt_name.replace(' ', '_')}")
    os.makedirs(temp_dir, exist_ok=True)

    print(f"[{mp3_name}] Synthesizing {len(chunks)} chunks in parallel...")
    try:
        tasks = []
        chunk_files = []
        for i, chunk in enumerate(chunks):
            cf = os.path.join(temp_dir, f"chunk_{i:04d}.mp3")
            chunk_files.append(cf)
            tasks.append(synthesize_chunk(sem, chunk, cf, i))

        await asyncio.gather(*tasks)

        concat_list = os.path.join(temp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for cf in chunk_files:
                f.write(f"file '{cf}'\n")

        tmp_final = final_path + ".assembling.mp3"
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", tmp_final]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {res.stderr.decode()}")

        os.replace(tmp_final, final_path)
        size_mb = os.path.getsize(final_path) / (1024 * 1024)
        print(f"[{mp3_name}] COMPLETED! ({size_mb:.2f} MB)")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

async def main():
    sem = asyncio.Semaphore(5)
    for txt_file, mp3_file in CHAPTER_FILES:
        await process_chapter(sem, txt_file, mp3_file)
    print("ALL REMAINING BRYSON CHAPTERS COMPLETE!")

if __name__ == "__main__":
    asyncio.run(main())
