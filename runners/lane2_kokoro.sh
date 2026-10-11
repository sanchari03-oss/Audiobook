#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"

echo "=========================================================="
echo "🧠 [LANE 2 - KOKORO ADAM DENOISED] Starting Pipeline at $(date)"
echo "=========================================================="

# 1. The Appeal (Kokoro Adam Denoised)
echo ""
echo ">>> [1/3] Starting: The Appeal (Kokoro Adam Denoised)"
echo "=========================================================="
python3 -u "$MAKER" \
  "/home/ssk/Desktop/ebooks.rahnuma.org_Grisham_John-The_Appeal-Grisham_John.pdf" \
  -o "$WEBSITE_DIR/THE APPEAL" \
  --engine kokoro \
  --voice adam

python3 "$WEBSITE_DIR/generate_books.py"
echo "✅ The Appeal completed & catalog updated!"

# 2. The 48 Laws of Power (Kokoro Adam Denoised)
echo ""
echo ">>> [2/3] Starting: The 48 Laws of Power (Kokoro Adam Denoised)"
echo "=========================================================="
python3 -u "$MAKER" \
  "/home/ssk/Documents/Obsidian/Literature Notes 📝/Books 📚️/48 laws of power/the+48+laws+of+power.pdf" \
  -o "$WEBSITE_DIR/The 48 Laws of Power" \
  --engine kokoro \
  --voice adam

python3 "$WEBSITE_DIR/generate_books.py"
echo "✅ The 48 Laws of Power completed & catalog updated!"

# 3. Digital Fortress (Dan Brown - Kokoro Adam Denoised)
echo ""
echo ">>> [3/3] Starting: Digital Fortress (Kokoro Adam Denoised)"
echo "=========================================================="
python3 -u "$MAKER" \
  "/home/ssk/Desktop/digital_fortress.pdf" \
  -o "$WEBSITE_DIR/Digital Fortress" \
  --engine kokoro \
  --voice adam

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [LANE 2] ALL 3 BOOKS COMPLETE at $(date)!"
