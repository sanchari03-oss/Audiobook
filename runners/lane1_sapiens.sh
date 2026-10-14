#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"
PDF="/home/ssk/Desktop/Sapiens A Brief History of Humankind.pdf"
OUT="$WEBSITE_DIR/Sapiens A Brief History of Humankind"

echo "=========================================================="
echo "🌍 [LANE 1 - SAPIENS MULTI-VOICE] Starting Pipeline at $(date)"
echo "=========================================================="

# 1. Libby (Chapters 1 - 10)
echo ""
echo ">>> [1/3] Sapiens: Part 1 (Ch 1-10) with Libby (British Female)"
echo "=========================================================="
python3 -u "$MAKER" "$PDF" -o "$OUT" \
  --title "Sapiens: A Brief History of Humankind" \
  --author "Yuval Noah Harari" \
  --voice libby \
  --rate "+8%" \
  --max-chunk-chars 3800 \
  --start-chapter 1 --end-chapter 10

python3 "$WEBSITE_DIR/generate_books.py"
echo "✅ Sapiens (Part 1 - Libby) complete & catalog updated!"

# 2. Sonia (Chapters 11 - 15)
echo ""
echo ">>> [2/3] Sapiens: Part 2 (Ch 11-15) with Sonia (British Female)"
echo "=========================================================="
python3 -u "$MAKER" "$PDF" -o "$OUT" \
  --title "Sapiens: A Brief History of Humankind" \
  --author "Yuval Noah Harari" \
  --voice sonia \
  --rate "+8%" \
  --max-chunk-chars 3800 \
  --start-chapter 11 --end-chapter 15

python3 "$WEBSITE_DIR/generate_books.py"
echo "✅ Sapiens (Part 2 - Sonia) complete & catalog updated!"

# 3. Thomas (Chapters 16 - 27)
echo ""
echo ">>> [3/3] Sapiens: Part 3 (Ch 16-27) with Thomas (British Male)"
echo "=========================================================="
python3 -u "$MAKER" "$PDF" -o "$OUT" \
  --title "Sapiens: A Brief History of Humankind" \
  --author "Yuval Noah Harari" \
  --voice thomas \
  --rate "+8%" \
  --max-chunk-chars 3800 \
  --start-chapter 16 --end-chapter 27

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [LANE 1 - SAPIENS] ALL 27 CHAPTERS COMPLETE at $(date)!"

# Auto-spin The Silent Patient if not already running
/home/ssk/Desktop/audiobook-website/runners/run_silent_patient.sh

