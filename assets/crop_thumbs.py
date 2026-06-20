"""콜라보 카페 상품 대표 썸네일 크롭 스크립트.
원본 5장(1080x1350)에서 상품별 대표 영역을 잘라 assets/cafe/thumb/ 에 저장한다.
좌표는 (left, top, right, bottom) 픽셀.
"""
from PIL import Image
import os

BASE = os.path.dirname(__file__)
CAFE = os.path.join(BASE, "cafe")
SOURCE = os.path.join(CAFE, "source")
THUMB = os.path.join(CAFE, "thumb")
os.makedirs(THUMB, exist_ok=True)

# (소스파일, 출력이름(={분류}_{상품}.jpg), (l,t,r,b))
CROPS = [
    ("menu.jpg",                "menu_drink_star.jpg",  (120, 205, 330, 505)),
    ("menu.jpg",                "menu_drink_cross.jpg", (350, 205, 550, 505)),
    ("menu.jpg",                "menu_drink_grail.jpg", (560, 205, 745, 505)),
    ("menu.jpg",                "menu_parfait.jpg",     (240, 700, 560, 1130)),
    ("menu.jpg",                "menu_burger.jpg",      (560, 730, 900, 1130)),
    ("goods_badge_keyring.jpg", "goods_badge.jpg",      (90, 150, 300, 365)),
    ("goods_badge_keyring.jpg", "goods_keyring.jpg",    (90, 705, 300, 920)),
    ("goods_stand_block.jpg",   "goods_stand.jpg",      (105, 150, 320, 480)),
    ("goods_stand_block.jpg",   "goods_block.jpg",      (120, 950, 470, 1185)),
]

for src, out, box in CROPS:
    im = Image.open(os.path.join(SOURCE, src)).convert("RGB")
    crop = im.crop(box)
    crop.thumbnail((300, 300))  # 가볍게 축소
    crop.save(os.path.join(THUMB, out), quality=82, optimize=True)
    print(out, crop.size)

print("done")
