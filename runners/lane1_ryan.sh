#!/usr/bin/env bash
set -e

WEBSITE_DIR="/home/ssk/Desktop/audiobook-website"
MAKER="/home/ssk/audiobook_maker.py"

echo "=========================================================="
echo "🇬🇧 [LANE 1 - RYAN (BRITISH)] Starting Pipeline at $(date)"
echo "=========================================================="

# 1. The Invisible Man (Smallest ~49k words)
echo ""
echo ">>> [1/2] Starting: The Invisible Man (H. G. Wells)"
echo "=========================================================="
python3 -u "$MAKER" \
  "/home/ssk/Desktop/h-g-wells_invisible-man.pdf" \
  -o "$WEBSITE_DIR/The Invisible Man" \
  --title "The Invisible Man" \
  --author "H. G. Wells" \
  --voice 3 \
  --rate "+8%" \
  --max-chunk-chars 3800

python3 "$WEBSITE_DIR/generate_books.py"
echo "🎉 [LANE 1 - RYAN] The Invisible Man COMPLETE & catalog updated at $(date)!"
