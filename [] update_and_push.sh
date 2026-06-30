#!/bin/bash
# After editing events.csv, run this single script to: rebuild index.html -> commit -> pull -> push
# Usage: ./update_and_push.sh "commit message"   (auto-generated if omitted)

set +H  # disable history expansion ('!' in strings stays literal)

# 0. Move to the script's own directory (so it works from anywhere)
cd "$(dirname "$0")" || exit 1

# 1. Rebuild index.html (run make_page.py)
echo "[+] Building index.html (python -m make_page)..."
python -m make_page
if [ $? -ne 0 ]; then
    echo ""
    echo ' [ERROR] Failed to build index.html. Check make_page.py.'
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
    echo '###################################################'
    echo ' [ERROR] Merge conflict detected.'
    echo ' Resolve the conflict manually, then run again.'
    echo '###################################################'
    exit 1
fi

# 5. Push
echo "[+] Pushing to remote..."
git push
if [ $? -ne 0 ]; then
    echo ""
    echo ' [ERROR] Push failed (check permissions or remote settings).'
    exit 1
fi

echo ""
echo '[OK] Rebuilt index.html + committed + pushed successfully.'

# 6. Wait for the GitHub Pages deploy of THIS commit to finish, then open browser
URL="https://bandorigall.github.io/bangdream_events.github.io/"
REPO="bandorigall/bangdream_events.github.io"
PUSHED_SHA="$(git rev-parse HEAD)"

if command -v gh >/dev/null 2>&1; then
    echo "[+] Waiting for GitHub Pages to deploy commit ${PUSHED_SHA:0:7} ..."
    MAX_WAIT=300   # seconds
    INTERVAL=5
    WAITED=0
    DEPLOYED=0
    # Use the deployments API (github-pages env). The legacy pages/builds endpoint
    # lags behind / doesn't reflect new deploys, so we track the deployment status here.
    while [ "$WAITED" -lt "$MAX_WAIT" ]; do
        DEPLOY_ID="$(gh api "repos/$REPO/deployments?sha=$PUSHED_SHA&environment=github-pages&per_page=1" \
                        --jq '.[0].id' 2>/dev/null)"
        if [ -n "$DEPLOY_ID" ] && [ "$DEPLOY_ID" != "null" ]; then
            STATE="$(gh api "repos/$REPO/deployments/$DEPLOY_ID/statuses?per_page=1" \
                        --jq '.[0].state' 2>/dev/null)"
            case "$STATE" in
                success)
                    echo "[OK] Pages deploy completed for ${PUSHED_SHA:0:7}."
                    DEPLOYED=1
                    break
                    ;;
                error|failure)
                    echo "[ERROR] Pages deploy $STATE for ${PUSHED_SHA:0:7}. Opening site anyway."
                    break
                    ;;
            esac
        else
            STATE="pending"
        fi
        printf '    ... state=%s (%ss elapsed)\r' "${STATE:-pending}" "$WAITED"
        sleep "$INTERVAL"
        WAITED=$((WAITED + INTERVAL))
    done
    echo ""
    if [ "$DEPLOYED" -ne 1 ] && [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "[i] Timed out waiting for deploy (${MAX_WAIT}s). Opening site anyway."
    fi
else
    echo "[i] 'gh' not found; cannot track deploy status. Opening site directly."
fi

echo "[+] Opening $URL ..."
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)   # Windows (Git Bash / MSYS / Cygwin)
        powershell.exe -NoProfile -Command "Start-Process '$URL'" \
            || echo "[i] Could not auto-open browser. Open manually: $URL"
        ;;
    Linux*)                 # Linux
        xdg-open "$URL" >/dev/null 2>&1 \
            || echo "[i] Could not auto-open browser. Open manually: $URL"
        ;;
    Darwin*)                # macOS
        open "$URL" \
            || echo "[i] Could not auto-open browser. Open manually: $URL"
        ;;
    *)
        echo "[i] Unknown OS. Open manually: $URL"
        ;;
esac

# 7. Close this terminal window after finishing.
#    NOTE: this closes the Git Bash/terminal window that launched the script.
#    Skipped when the script is "sourced" (interactive) so it won't kill your session by accident.
case "$-" in
    *i*) : ;;  # sourced / interactive -> do not close
    *)
        echo "[+] Done. Closing window..."
        ( sleep 1; kill -9 "$PPID" ) >/dev/null 2>&1 &
        ;;
esac
exit 0
