#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="$WEBSITE_DIR/audiobook_maker.py"

echo "=========================================================="
echo "⏳ [THE TIME MACHINE - CHRISTOPHER] Starting Generation at $(date)"
echo "=========================================================="

python3 -u "$MAKER" \
  "/home/ssk/Desktop/timemach.pdf" \
  -o "$WEBSITE_DIR/The Time Machine" \
  --title "The Time Machine" \
  --author "H. G. Wells" \
  --voice christopher \
  --rate "+8%" \
  --max-chunk-chars 3800

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [THE TIME MACHINE] COMPLETE & catalog books.json updated at $(date)!"
