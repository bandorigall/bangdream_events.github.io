"""코믹월드 335(아워 노트 ZA02 부스) 굿즈 썸네일 크롭 스크립트.

원본 2장(공식 X @bangdreamon_KR 2026-08-07 공지 이미지)에서
- sale.jpg  : 현장 판매 굿즈 안내 (418x4096)  → 캐릭터 아크릴 25종 + 배경 아크릴 + 홀더파일
- event.jpg : 현장 이벤트 안내 (750x3800)   → 이벤트 증정 굿즈 3종
품목별 대표 영역을 잘라 assets/comicw335/thumb/ 에 저장한다.

캐릭터 아크릴은 10행(3-2-3-2… 반복) 격자라 좌표를 계산으로 생성한다.
"""
from PIL import Image
import os

BASE = os.path.dirname(__file__)
ROOT = os.path.join(BASE, "comicw335")
SOURCE = os.path.join(ROOT, "source")
THUMB = os.path.join(ROOT, "thumb")
os.makedirs(THUMB, exist_ok=True)

# --- 캐릭터 아크릴 스탠드 25종 (판매 순서 = 공지 이미지 배치 순서) ---
CHARACTERS = [
    "takamatsu_tomori",  "chihaya_anon",     "kaname_rana",
    "nagasaki_soyo",     "shiina_taki",
    "misumi_uika",       "wakaba_mutsumi",   "yahata_umiri",
    "yutenji_nyamu",     "togawa_sakiko",
    "nakamachi_arare",   "miyanaga_nonoka",  "minetsuki_ritsu",
    "fuji_miyako",       "sengoku_yuno",
    "shiomi_hotaru",     "izawa_natsume",    "kotohira_nagi",
    "hamasaki_mahoro",   "izumi_houka",
    "suga_raika",        "mahashi_miku",     "yakura_yomogi",
    "umezato_chieri",    "shinomiya_shizuku",
]
ROW_Y = [723 + 210 * i for i in range(10)]  # 각 행 이름표 y좌표
COL_X3 = [105, 209, 313]                    # 3열 행 중심 x
COL_X2 = [157, 261]                         # 2열 행 중심 x

char_crops = []
i = 0
for r, ly in enumerate(ROW_Y):
    for xc in (COL_X3 if r % 2 == 0 else COL_X2):
        char_crops.append(("sale.jpg", f"acryl_{CHARACTERS[i]}.jpg",
                           (xc - 62, ly - 205, xc + 62, ly - 8)))
        i += 1

# --- 그 외 품목 ---
CROPS = char_crops + [
    ("sale.jpg",  "acryl_background.jpg", (60, 2780, 360, 3140)),
    ("sale.jpg",  "holderfile.jpg",       (55, 3325, 350, 3500)),
    ("event.jpg", "prize_hologram.jpg",   (60, 1950, 690, 2270)),
    ("event.jpg", "prize_holderfile.jpg", (60, 2400, 690, 2940)),
    ("event.jpg", "prize_diary.jpg",      (60, 3080, 690, 3560)),
]

for src, out, box in CROPS:
    im = Image.open(os.path.join(SOURCE, src)).convert("RGB")
    crop = im.crop(box)
    crop.thumbnail((320, 320))  # 가볍게 축소
    crop.save(os.path.join(THUMB, out), quality=85, optimize=True)
    print(out, crop.size)

print("done:", len(CROPS))
