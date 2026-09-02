#!/bin/bash
# After editing events.csv, run this single script to: rebuild index.html -> commit -> pull -> push
# Usage: ./update_and_push.sh "commit message"   (auto-generated if omitted)

set +H  # disable history expansion ('!' in strings stays literal)

# 0. Move to the script's own directory (so it works from anywhere)
cd "$(dirname "$0")" || exit 1

# 0-b. [BETA] Scrape overseas events (bang-dream.com) -> 해외오프이벤/events_overseas.csv
#      Failure here is non-fatal: the previous cached CSV is kept and the build goes on.
echo "[+] Scraping overseas events (beta)..."
python "해외오프이벤/scraper.py"
if [ $? -ne 0 ]; then
    echo "[i] Overseas scrape failed or skipped. Using cached events_overseas.csv."
fi

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

# 2-a. 훅 실행 가능 여부 판정 + 신원 가드
#      이 리포는 구글드라이브(rclone) 마운트 위에 있을 수 있고, 그 경우 .git/hooks 에
#      실행 권한이 붙지 않아 git 이 "cannot exec ... 허가 거부" 로 죽는다.
#      → 훅을 못 쓰는 컴에서는 --no-verify 로 우회하되, 훅이 하던 신원 검사를 여기서 직접 한다.
#      (컴퓨터마다 다른 설정을 .git/config 에 넣으면 드라이브로 공유되어 다른 컴이 깨지므로
#       core.hooksPath 같은 건 쓰지 않는다.)
FORBIDDEN='tksqhddnfl5\|snu\.ac\.kr'
IDENT="$(git var GIT_AUTHOR_IDENT 2>/dev/null) $(git var GIT_COMMITTER_IDENT 2>/dev/null)"
if echo "$IDENT" | grep -qi "$FORBIDDEN"; then
    echo ""
    echo '###################################################'
    echo " [ERROR] 금지된 신원 감지: $IDENT"
    echo " 이 리포는 bandorigall 로만 커밋할 수 있습니다."
    echo "   git config user.name  bandorigall"
    echo "   git config user.email bandorigall@gmail.com"
    echo '###################################################'
    exit 1
fi

NOVERIFY=""
if [ -x .git/hooks/pre-commit ] || [ -x .git/hooks/pre-push ]; then
    echo "[i] Hooks are executable. Using them."
else
    echo "[i] Hooks are not executable (drive mount). Skipping hooks; identity checked above."
    NOVERIFY="--no-verify"
fi

# 3. Commit (message from arg, or default)
COMMIT_MSG=${1:-"Auto update - $(date '+%Y-%m-%d %H:%M:%S')"}

# Skip commit if there is nothing staged
if git diff --cached --quiet; then
    echo "[i] No changes to commit. Skipping commit."
else
    echo "[+] Committing with message: $COMMIT_MSG"
    git commit $NOVERIFY -m "$COMMIT_MSG"
fi

# 4. Pull (merge remote changes)
#    --no-edit: 머지 커밋 메시지 에디터(vim)가 떠서 멈추는 것 방지
#    --no-rebase: pull 전략을 명시(divergent branches 에러 방지)
echo "[+] Pulling from remote..."
git pull --no-rebase --no-edit
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
git push $NOVERIFY
if [ $? -ne 0 ]; then
    echo ""
    echo ' [ERROR] Push failed (check permissions or remote settings).'
    exit 1
fi

echo ""
echo '[OK] Rebuilt index.html + committed + pushed successfully.'

# push_all.sh 등에서 SKIP_DEPLOY_WAIT=1 로 부르면 배포 대기/브라우저 열기 없이 즉시 종료
[ -n "$SKIP_DEPLOY_WAIT" ] && exit 0

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
