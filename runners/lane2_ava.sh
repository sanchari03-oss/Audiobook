#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"

echo "=========================================================="
echo "🌸 [LANE 2 - AVA] Continuing A Thousand Splendid Suns at $(date)"
echo "=========================================================="

python3 -u "$MAKER" \
  "/home/ssk/Desktop/a_thousand_splendid_sun.pdf" \
  -o "$WEBSITE_DIR/A Thousand Splendid Suns" \
  --title "A Thousand Splendid Suns" \
  --author "Khaled Hosseini" \
  --voice ava \
  --rate "+8%" \
  --max-chunk-chars 3800

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [LANE 2] A Thousand Splendid Suns COMPLETE & catalog updated at $(date)!"

# Auto-spin The Silent Patient if not already running
/home/ssk/Desktop/audiobook-website/runners/run_silent_patient.sh

