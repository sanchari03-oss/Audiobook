#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"

echo "=========================================================="
echo "⚡ [LANE 3 - BRIAN (AMERICAN DYNAMIC)] Starting Misery at $(date)"
echo "=========================================================="

python3 -u "$MAKER" \
  "/home/ssk/Desktop/Misery on Bookdio.org.pdf" \
  -o "$WEBSITE_DIR/Misery" \
  --title "Misery" \
  --author "Stephen King" \
  --voice 2 \
  --rate "+8%" \
  --max-chunk-chars 3800

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [LANE 3] Misery COMPLETE & catalog updated at $(date)!"

# Auto-spin The Silent Patient if not already running
/home/ssk/Desktop/audiobook-website/runners/run_silent_patient.sh

