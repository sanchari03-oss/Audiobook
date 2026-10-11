#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"

echo "=========================================================="
echo "⚡ [LANE 2 - CLOUD TTS RYAN] Starting Digital Fortress (Part 2: Ch 85-128) at $(date)"
echo "=========================================================="

python3 -u "$MAKER" \
  "/home/ssk/Desktop/digital_fortress.pdf" \
  -o "$WEBSITE_DIR/Digital Fortress" \
  --voice 3 \
  --rate "+8%" \
  --max-chunk-chars 3800 \
  --start-chapter 85 \
  --end-chapter 128

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [LANE 2] Digital Fortress (Part 2: Ch 85-128) COMPLETE at $(date)!"
