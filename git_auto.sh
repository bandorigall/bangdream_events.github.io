#!/bin/bash

# 1. 변경사항 추가
echo "[+] Adding changes..."
git add .

# 2. 커밋 (메시지는 실행 시 인자로 받거나 기본값 사용)
# 사용법: ./git-auto.sh "메시지내용"
COMMIT_MSG=${1:-"Auto commit - $(date '+%Y-%m-%d %H:%M:%S')"}
echo "[+] Committing with message: $COMMIT_MSG"
git commit -m "$COMMIT_MSG"

# 3. Pull (원격 저장소 변경사항 가져오기)
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

# 4. Push
echo "[+] Pushing to remote..."
git push
if [ $? -ne 0 ]; then
    echo ""
    echo " [!!!] 에러 발생: Push 실패! (권한 문제 또는 원격 설정 확인)"
    exit 1
fi

echo ""
echo "[OK] 모든 작업이 성공적으로 완료되었습니다!"