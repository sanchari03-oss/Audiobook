#!/usr/bin/env python3
"""
Incoming Audiobooks Watcher Daemon (DDIA Ch 10 - Stream / Batch Ingestion)
Monitors /home/ssk/Desktop/Incoming_Audiobooks/ for newly dropped PDF/EPUB books.
Automatically triggers audiobook_maker.py, runs generate_books.py to update manifests,
and archives the source documents into processed/.
"""

import os
import sys
import time
import shutil
import signal
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
AUDIOBOOK_MAKER = BASE_DIR / "audiobook_maker.py"
GENERATE_BOOKS = BASE_DIR / "generate_books.py"

DEFAULT_WATCH_DIR = Path("/home/ssk/Desktop/Incoming_Audiobooks")
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".txt"}

running = True

def signal_handler(sig, frame):
    global running
    print("\n🛑 Shutting down Incoming Audiobooks Watcher Daemon...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def ensure_directories(watch_dir: Path):
    """Ensure watch, processed, and failed directories exist."""
    watch_dir.mkdir(parents=True, exist_ok=True)
    processed_dir = watch_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir = watch_dir / "failed"
    failed_dir.mkdir(parents=True, exist_ok=True)
    return processed_dir, failed_dir

def is_file_copy_complete(file_path: Path, wait_seconds: float = 1.5) -> bool:
    """Verify that a file has finished being written by checking size stability."""
    try:
        initial_size = file_path.stat().st_size
        if initial_size == 0:
            return False
        time.sleep(wait_seconds)
        final_size = file_path.stat().st_size
        return initial_size == final_size
    except Exception:
        return False

def process_file(file_path: Path, processed_dir: Path, failed_dir: Path, args):
    """Process a single incoming book through the automated pipeline."""
    print("\n" + "="*70)
    print(f"📥 New Book Detected: {file_path.name}")
    print(f"📏 Size: {file_path.stat().st_size / (1024*1024):.2f} MB")
    print("="*70)

    # 1. Wait for write to complete
    if not is_file_copy_complete(file_path):
        print(f"⏳ File is still being written or is empty: {file_path.name}. Waiting...")
        return False

    book_title = file_path.stem.replace('_', ' ').replace('-', ' ').strip()
    clean_folder_name = f"{book_title}"
    output_dir = BASE_DIR / clean_folder_name

    cmd = [
        sys.executable,
        str(AUDIOBOOK_MAKER),
        str(file_path),
        "-o", str(output_dir)
    ]

    if getattr(args, 'voice', None):
        cmd.extend(["-v", str(args.voice)])
    if getattr(args, 'engine', None):
        cmd.extend(["--engine", str(args.engine)])
    if getattr(args, 'rate', None):
        cmd.extend(["--rate", str(args.rate)])

    print(f"🚀 Launching synthesis pipeline:\n   {' '.join(cmd)}\n")

    start_time = time.time()
    try:
        ret = subprocess.run(cmd, check=True)
        elapsed = time.time() - start_time
        print(f"\n✅ Audiobook generation completed in {elapsed:.1f}s!")

        # 2. Run generate_books.py to update partitioned manifests and books.json
        print("📑 Regenerating library catalog and manifests...")
        subprocess.run([sys.executable, str(GENERATE_BOOKS)], check=True)

        # 3. Archive processed source document
        dest_path = processed_dir / file_path.name
        if dest_path.exists():
            dest_path = processed_dir / f"{file_path.stem}_{int(time.time())}{file_path.suffix}"
        shutil.move(str(file_path), str(dest_path))
        print(f"📦 Archived source book to: {dest_path}")
        print("🎉 Book is now available on your Audiobook website!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error processing book {file_path.name} (exit code {e.returncode})")
        dest_fail = failed_dir / file_path.name
        if dest_fail.exists():
            dest_fail = failed_dir / f"{file_path.stem}_{int(time.time())}{file_path.suffix}"
        try:
            shutil.move(str(file_path), str(dest_fail))
            print(f"⚠️ Moved failed book to: {dest_fail}")
        except Exception:
            pass
        return False

def scan_once(watch_dir: Path, processed_dir: Path, failed_dir: Path, args) -> int:
    """Scan watch folder once for pending books."""
    count = 0
    for item in sorted(watch_dir.iterdir()):
        if not item.is_file():
            continue
        if item.name.startswith('.') or item.name.endswith('.crdownload') or item.name.endswith('.tmp'):
            continue
        if item.suffix.lower() in SUPPORTED_EXTENSIONS:
            count += 1
            process_file(item, processed_dir, failed_dir, args)
    return count

def run_watcher(args):
    watch_dir = Path(args.watch_dir).expanduser().resolve()
    processed_dir, failed_dir = ensure_directories(watch_dir)

    print("\n" + "="*70)
    print("🎧 INCOMING AUDIOBOOKS WATCHER DAEMON (DDIA Ch 10)")
    print(f"📁 Monitoring:   {watch_dir}")
    print(f"📦 Processed:    {processed_dir}")
    print(f"⚠️ Failures:     {failed_dir}")
    print(f"⚙️ Target Site:  {BASE_DIR}")
    print(f"⏱️ Poll Interval: {args.poll_interval}s")
    print("="*70)
    print("Drop any PDF or EPUB book into the monitoring directory to synthesize.\n")

    if args.once:
        print("🔍 Running single-pass sweep (--once)...")
        n = scan_once(watch_dir, processed_dir, failed_dir, args)
        print(f"Sweep complete. Processed {n} file(s).")
        return

    while running:
        try:
            scan_once(watch_dir, processed_dir, failed_dir, args)
        except Exception as e:
            print(f"⚠️ Watcher exception: {e}")

        # Sleep in small slices to remain responsive to SIGINT
        for _ in range(int(args.poll_interval * 10)):
            if not running:
                break
            time.sleep(0.1)

    print("👋 Watcher daemon stopped.")

def main():
    parser = argparse.ArgumentParser(
        description="Monitor an incoming folder for PDF/EPUB books and synthesize them automatically."
    )
    parser.add_argument(
        "-w", "--watch-dir",
        default=str(DEFAULT_WATCH_DIR),
        help=f"Directory to monitor for incoming books (default: {DEFAULT_WATCH_DIR})"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=3.0,
        help="Polling interval in seconds (default: 3.0)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Perform a single scan of the watch directory and exit"
    )
    parser.add_argument(
        "-v", "--voice",
        help="Voice override for synthesis (e.g. '1', 'andrew', 'brian')"
    )
    parser.add_argument(
        "--engine",
        choices=["edge", "kokoro"],
        help="TTS engine: 'edge' (cloud neural) or 'kokoro' (local onnx)"
    )
    parser.add_argument(
        "--rate",
        help="Speech rate override (e.g. '+8%%')"
    )

    args = parser.parse_args()
    run_watcher(args)

if __name__ == "__main__":
    main()
