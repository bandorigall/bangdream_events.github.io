# -*- coding: utf-8 -*-
"""카드 게임 페스티벌 2026 in KOREA · 무겐다이 뮤타입 굿즈 썸네일 크롭.

원본(공식 X @BUSHIASIA_KR 2026-08-19 공지 이미지 2장):
  cgf2026/source/goods.jpg   : GOODS LINEUP (2005x2836) — 4-4-3 격자 11품목
  cgf2026/source/lottery.jpg : 퀴즈쇼&사인회 추첨 안내 (2006x2836)
격자 카드에서 상품 이미지 영역만 잘라 cgf2026/thumb/ 에 저장한다.
"""
from PIL import Image
import os

BASE = os.path.dirname(__file__)
SRC = os.path.join(BASE, "cgf2026", "source", "goods.jpg")
THUMB = os.path.join(BASE, "cgf2026", "thumb")
os.makedirs(THUMB, exist_ok=True)

COLS = [(64, 515), (550, 991), (1027, 1466), (1493, 1941)]
ROWS = [(975, 1290), (1640, 1875), (2320, 2565)]
IDS = [
    "diorama", "pouch", "acryl_stand", "acryl_keyring",
    "clearfile", "acryl_block", "badge_big_holo", "badge_square",
    "badge_trading", "ticket_card", "bromide",
]

im = Image.open(SRC)
i = 0
for r, (y0, y1) in enumerate(ROWS):
    for c, (x0, x1) in enumerate(COLS):
        if i >= len(IDS):
            break
        im.crop((x0, y0, x1, y1)).save(
            os.path.join(THUMB, IDS[i] + ".jpg"), quality=88)
        i += 1
print("crop done:", i)
