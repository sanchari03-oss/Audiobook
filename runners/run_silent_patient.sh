#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"
PDF="/home/ssk/Desktop/The Silent Patient on Bookdio.org.pdf"
OUT="$WEBSITE_DIR/The Silent Patient"
LOCK_FILE="/tmp/silent_patient.lock"

# Mutex lock: Ensure only 1 runner spins The Silent Patient
if [ -f "$LOCK_FILE" ]; then
  echo "ℹ️ The Silent Patient is already running or completed by another lane."
  exit 0
fi
touch "$LOCK_FILE"

echo "=========================================================="
echo "🎭 [LANE NEXT - THE SILENT PATIENT] Starting at $(date)"
echo "Narrator: Ryan (Classic British - fitting London psychotherapist Theo Faber)"
echo "=========================================================="

python3 -u "$MAKER" "$PDF" -o "$OUT" \
  --title "The Silent Patient" \
  --author "Alex Michaelides" \
  --voice 3 \
  --rate "+8%" \
  --max-chunk-chars 3800

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [THE SILENT PATIENT] COMPLETE & catalog updated at $(date)!"
