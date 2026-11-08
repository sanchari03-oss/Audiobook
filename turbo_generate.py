#!/usr/bin/env python3
import asyncio
import os
import shutil
import subprocess
import json
import edge_tts

BASE_DIR = "/home/ssk/Desktop/audiobook-website/A Short History of Nearly Everything"
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "transcripts")
WEBSITE_DIR = "/home/ssk/Desktop/audiobook-website"

# 4 distinct high-performance neural voices (avoids IP connection throttling)
WORKERS = [
    {
        "id": "worker_1",
        "voice": "en-US-BrianMultilingualNeural",
        "chapters": [
            ("20 - Small World.txt", "20 - Chapter 20 - Small World.mp3"),
            ("21 - Life Goes On.txt", "21 - Chapter 21 - Life Goes On.mp3"),
            ("22 - Good-bye to All That.txt", "22 - Chapter 22 - Good-bye to All That.mp3"),
        ]
    },
    {
        "id": "worker_2",
        "voice": "en-US-ChristopherNeural",
        "chapters": [
            ("23 - The Richness of Being.txt", "23 - Chapter 23 - The Richness of Being.mp3"),
            ("24 - Cells.txt", "24 - Chapter 24 - Cells.mp3"),
            ("25 - Darwin's Singular Notion.txt", "25 - Chapter 25 - Darwin's Singular Notion.mp3"),
        ]
    },
    {
        "id": "worker_3",
        "voice": "en-GB-RyanNeural",
        "chapters": [
            ("26 - The Stuff of Life.txt", "26 - Chapter 26 - The Stuff of Life.mp3"),
            ("27 - Ice Time.txt", "27 - Chapter 27 - Ice Time.mp3"),
            ("28 - The Mysterious Biped.txt", "28 - Chapter 28 - The Mysterious Biped.mp3"),
        ]
    },
    {
        "id": "worker_4",
        "voice": "en-US-GuyNeural",
        "chapters": [
            ("29 - The Restless Ape.txt", "29 - Chapter 29 - The Restless Ape.mp3"),
            ("30 - Good-bye.txt", "30 - Chapter 30 - Good-bye.mp3"),
        ]
    }
]

def split_text_into_chunks(text, max_len=1600):
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
    raise RuntimeError(f"Failed chunk {chunk_idx} on voice {voice}")

async def synthesize_chapter(voice, txt_name, mp3_name):
    final_path = os.path.join(BASE_DIR, mp3_name)
    if os.path.exists(final_path) and os.path.getsize(final_path) > 100000:
        print(f"[{voice}] Skipping existing: {mp3_name}")
        return

    txt_path = os.path.join(TRANSCRIPTS_DIR, txt_name)
    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = split_text_into_chunks(text, max_len=1600)
    temp_dir = os.path.join(BASE_DIR, f".tmp_{mp3_name.replace(' ', '_')}")
    os.makedirs(temp_dir, exist_ok=True)

    print(f"[{voice}] -> Starting {mp3_name} ({len(chunks)} chunks)...")
    try:
        # Run 3 concurrent chunks per voice worker
        sem = asyncio.Semaphore(3)
        async def sem_task(i, c, cp):
            async with sem:
                await synthesize_chunk(voice, c, cp, i)

        tasks = []
        chunk_files = []
        for i, chunk in enumerate(chunks):
            cf = os.path.join(temp_dir, f"chunk_{i:04d}.mp3")
            chunk_files.append(cf)
            tasks.append(sem_task(i, chunk, cf))

        await asyncio.gather(*tasks)

        concat_list = os.path.join(temp_dir, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for cf in chunk_files:
                f.write(f"file '{cf}'\n")

        tmp_out = final_path + ".tmp.mp3"
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", tmp_out]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed for {mp3_name}: {res.stderr.decode()}")

        os.replace(tmp_out, final_path)
        mb = os.path.getsize(final_path) / (1024 * 1024)
        print(f"[{voice}] *** FINISHED {mp3_name} ({mb:.2f} MB) ***")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

async def run_worker(worker):
    v = worker["voice"]
    for txt_file, mp3_file in worker["chapters"]:
        await synthesize_chapter(v, txt_file, mp3_file)

async def main():
    print("LAUNCHING 4 CONCURRENT VOICE WORKERS...")
    await asyncio.gather(*[run_worker(w) for w in WORKERS])
    print("ALL REMAINING CHAPTERS COMPLETE! Finalizing manifests and pushing...")

    # 1. Update manifest.json & books.json
    subprocess.run(["python3", os.path.join(WEBSITE_DIR, "generate_books.py")], check=True)

    # 2. Git commit & push
    subprocess.run(["git", "-C", WEBSITE_DIR, "add", "."], check=True)
    subprocess.run(["git", "-C", WEBSITE_DIR, "commit", "-m", "Add The Pearl and A Short History of Nearly Everything complete audiobooks"], check=False)
    subprocess.run(["git", "-C", WEBSITE_DIR, "push", "origin", "main"], check=True)
    print("GIT PUSH COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
