#!/bin/bash
# After editing events.csv, run this single script to: rebuild index.html -> commit -> pull -> push
# Usage: ./update_and_push.sh "commit message"   (auto-generated if omitted)

# 0. Move to the script's own directory (so it works from anywhere)
cd "$(dirname "$0")" || exit 1

# 1. Rebuild index.html (run make_page.py)
echo "[+] Building index.html (python -m make_page)..."
python -m make_page
if [ $? -ne 0 ]; then
    echo ""
    echo " [!!!] ERROR: Failed to build index.html. Check make_page.py."
    exit 1
fi

# 2. Stage changes
echo "[+] Adding changes..."
git add .

# 3. Commit (message from arg, or default)
COMMIT_MSG=${1:-"Auto update - $(date '+%Y-%m-%d %H:%M:%S')"}

# Skip commit if there is nothing staged
if git diff --cached --quiet; then
    echo "[i] No changes to commit. Skipping commit."
else
    echo "[+] Committing with message: $COMMIT_MSG"
    git commit -m "$COMMIT_MSG"
fi

# 4. Pull (merge remote changes)
echo "[+] Pulling from remote..."
git pull
if [ $? -ne 0 ]; then
    echo ""
    echo "###################################################"
    echo " [!!!] ERROR: Merge conflict detected."
    echo " Resolve the conflict manually, then run again."
    echo "###################################################"
    exit 1
fi

# 5. Push
echo "[+] Pushing to remote..."
git push
if [ $? -ne 0 ]; then
    echo ""
    echo " [!!!] ERROR: Push failed (check permissions or remote settings)."
    exit 1
fi

echo ""
echo "[OK] Rebuilt index.html + committed + pushed successfully!"

# 6. Open the deployed GitHub Pages site in the default browser
URL="https://bandorigall.github.io/bangdream_events.github.io/"
echo "[+] Opening $URL ..."
cmd.exe /c start "" "$URL" 2>/dev/null \
    || start "" "$URL" 2>/dev/null \
    || xdg-open "$URL" 2>/dev/null \
    || open "$URL" 2>/dev/null \
    || echo "[i] Could not auto-open browser. Open manually: $URL"
