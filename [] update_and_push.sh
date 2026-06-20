#!/bin/bash
# events.csv 수정 후 이 스크립트 하나로: index.html 재생성 → 커밋 → pull → push
# 사용법: ./update_and_push.sh "커밋 메시지"   (메시지 생략 시 자동 생성)

# 0. 스크립트 위치로 이동 (어디서 실행하든 동작하도록)
cd "$(dirname "$0")" || exit 1

# 1. index.html 재생성 (make_page.py 실행)
echo "[+] Building index.html (python -m make_page)..."
python -m make_page
if [ $? -ne 0 ]; then
    echo ""
    echo " [!!!] 에러: index.html 생성 실패! make_page.py 를 확인하세요."
    exit 1
fi

# 2. 변경사항 추가
echo "[+] Adding changes..."
git add .

# 3. 커밋 (메시지는 인자로 받거나 기본값 사용)
COMMIT_MSG=${1:-"Auto update - $(date '+%Y-%m-%d %H:%M:%S')"}

# 변경사항이 없으면 커밋 단계 건너뛰기
if git diff --cached --quiet; then
    echo "[i] 변경사항이 없어 커밋을 건너뜁니다."
else
    echo "[+] Committing with message: $COMMIT_MSG"
    git commit -m "$COMMIT_MSG"
fi

# 4. Pull (원격 변경사항 병합)
echo "[+] Pulling from remote..."
git pull
if [ $? -ne 0 ]; then
    echo ""
    echo "###################################################"
    echo " [!!!] 에러 발생: 머지 충돌(Conflict)이 감지되었습니다."
    echo " 직접 충돌을 해결한 뒤 다시 실행해주세요."
    echo "###################################################"
    exit 1
fi

# 5. Push
echo "[+] Pushing to remote..."
git push
if [ $? -ne 0 ]; then
    echo ""
    echo " [!!!] 에러 발생: Push 실패! (권한 문제 또는 원격 설정 확인)"
    exit 1
fi

echo ""
echo "[OK] index.html 재생성 + 커밋 + 푸시 완료!"
