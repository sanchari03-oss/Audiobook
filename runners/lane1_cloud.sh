#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"

echo "=========================================================="
echo "🚀 [LANE 1 - CLOUD TTS] Starting Digital Fortress at $(date)"
echo "=========================================================="

python3 -u "$MAKER" \
  "/home/ssk/Desktop/digital_fortress.pdf" \
  -o "$WEBSITE_DIR/Digital Fortress" \
  --voice 3 \
  --rate "+8%" \
  --max-chunk-chars 3800

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [LANE 1] Digital Fortress COMPLETE at $(date)!"

