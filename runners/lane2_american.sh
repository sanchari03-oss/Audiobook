#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"

echo "=========================================================="
echo "🇺🇸 [LANE 2 - ANDREW (AMERICAN)] Starting Pipeline at $(date)"
echo "=========================================================="

# 1. A Thousand Splendid Suns (~106k words)
echo ""
echo ">>> [1/2] Starting: A Thousand Splendid Suns (Khaled Hosseini)"
echo "=========================================================="
python3 -u "$MAKER" \
  "/home/ssk/Desktop/a_thousand_splendid_sun.pdf" \
  -o "$WEBSITE_DIR/A Thousand Splendid Suns" \
  --title "A Thousand Splendid Suns" \
  --author "Khaled Hosseini" \
  --voice 1 \
  --rate "+8%" \
  --max-chunk-chars 3800

python3 "$WEBSITE_DIR/generate_books.py"
echo "✅ A Thousand Splendid Suns complete & catalog updated!"

# 2. Sapiens A Brief History of Humankind (~141k words)
echo ""
echo ">>> [2/2] Starting: Sapiens: A Brief History of Humankind (Yuval Noah Harari)"
echo "=========================================================="
python3 -u "$MAKER" \
  "/home/ssk/Desktop/Sapiens A Brief History of Humankind.pdf" \
  -o "$WEBSITE_DIR/Sapiens A Brief History of Humankind" \
  --title "Sapiens: A Brief History of Humankind" \
  --author "Yuval Noah Harari" \
  --voice 1 \
  --rate "+8%" \
  --max-chunk-chars 3800

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [LANE 2 - AMERICAN] ALL BOOKS COMPLETE at $(date)!"
