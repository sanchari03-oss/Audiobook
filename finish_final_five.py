#!/usr/bin/env python3
import asyncio
import os
import shutil
import subprocess
import edge_tts

BASE_DIR = "/home/ssk/Desktop/audiobook-website/A Short History of Nearly Everything"
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "transcripts")
WEBSITE_DIR = "/home/ssk/Desktop/audiobook-website"

TASKS = [
    {
        "voice": "en-US-BrianMultilingualNeural",
        "txt": "20 - Small World.txt",
        "mp3": "20 - Chapter 20 - Small World.mp3",
    },
    {
        "voice": "en-US-ChristopherNeural",
        "txt": "21 - Life Goes On.txt",
        "mp3": "21 - Chapter 21 - Life Goes On.mp3",
    },
    {
        "voice": "en-US-GuyNeural",
        "txt": "22 - Good-bye to All That.txt",
        "mp3": "22 - Chapter 22 - Good-bye to All That.mp3",
    },
    {
        "voice": "en-GB-RyanNeural",
        "txt": "25 - Darwin's Singular Notion.txt",
        "mp3": "25 - Chapter 25 - Darwin's Singular Notion.mp3",
    },
    {
        "voice": "en-US-AndrewMultilingualNeural",
        "txt": "28 - The Mysterious Biped.txt",
        "mp3": "28 - Chapter 28 - The Mysterious Biped.mp3",
    }
]

def split_text(text, max_len=1500):
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

async def synthesize_chunk(voice, text, out_path, chunk_idx):
    for attempt in range(1, 6):
        try:
            comm = edge_tts.Communicate(text, voice)
            await comm.save(out_path)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
                return
        except Exception:
            pass
        await asyncio.sleep(attempt * 0.8)
    raise RuntimeError(f"Failed chunk {chunk_idx}")

async def process_task(task):
    voice = task["voice"]
    txt_name = task["txt"]
    mp3_name = task["mp3"]
    final_path = os.path.join(BASE_DIR, mp3_name)

    if os.path.exists(final_path) and os.path.getsize(final_path) > 100000:
        print(f"Skipping already complete: {mp3_name}")
        return

    txt_path = os.path.join(TRANSCRIPTS_DIR, txt_name)
    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = split_text(text, max_len=1500)
    clean_dir_name = txt_name.replace("'", "").replace(" ", "_")
    temp_dir = os.path.join(BASE_DIR, f".tmp_{clean_dir_name}")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    print(f"[{voice}] Synthesizing {mp3_name} ({len(chunks)} chunks)...")
    try:
        sem = asyncio.Semaphore(3)
        async def sem_run(i, c, cp):
            async with sem:
                await synthesize_chunk(voice, c, cp, i)

        subtasks = []
        chunk_files = []
        for i, chunk in enumerate(chunks):
            cf = os.path.join(temp_dir, f"chunk_{i:04d}.mp3")
            chunk_files.append(cf)
            subtasks.append(sem_run(i, chunk, cf))

        await asyncio.gather(*subtasks)

        # Write concat list with properly escaped single quotes
        concat_list = os.path.join(temp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for cf in chunk_files:
                escaped_cf = cf.replace("'", "'\\''")
                f.write(f"file '{escaped_cf}'\n")

        tmp_out = final_path + ".tmp.mp3"
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", tmp_out]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {res.stderr.decode()}")

        os.replace(tmp_out, final_path)
        mb = os.path.getsize(final_path) / (1024 * 1024)
        print(f"*** COMPLETED {mp3_name} ({mb:.2f} MB) ***")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

async def main():
    print("RUNNING FINAL 5 CHAPTERS SIMULTANEOUSLY ACROSS 5 DEDICATED VOICES...")
    await asyncio.gather(*[process_task(t) for t in TASKS])
    print("ALL 31 CHAPTERS ARE 100% DONE! Finalizing manifests and pushing to GitHub...")

    # 1. Update manifest.json & books.json
    subprocess.run(["python3", os.path.join(WEBSITE_DIR, "generate_books.py")], check=True)

    # 2. Git commit & push
    subprocess.run(["git", "-C", WEBSITE_DIR, "add", "."], check=True)
    subprocess.run(["git", "-C", WEBSITE_DIR, "commit", "-m", "Add The Pearl and A Short History of Nearly Everything complete audiobooks & player fixes"], check=False)
    subprocess.run(["git", "-C", WEBSITE_DIR, "push", "origin", "main"], check=True)
    print("SUCCESS: GIT PUSH TO ORIGIN MAIN COMPLETE!")

if __name__ == "__main__":
    asyncio.run(main())
