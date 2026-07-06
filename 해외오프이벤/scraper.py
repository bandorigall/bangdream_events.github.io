# -*- coding: utf-8 -*-
"""
BanG Dream! 해외(일본) 오프라인 이벤트 자동 수집기  [BETA]

수집원:
  1) https://bang-dream.com/events/   → ライブ・イベント 카드 전부 (개최일/장소가 구조화되어 있음)
  2) https://bang-dream.com/news/      → 콜라보/카페/캠페인/전시 등 오프라인성 공지만 키워드로 선별

장소명(일본어)은 OpenStreetMap Nominatim으로 지오코딩하여 venues.json에 캐시한다.
결과는 events_overseas.csv (한국 페이지 make_page.py가 읽는 포맷과 동일)로 저장.
manual_overseas.csv 가 있으면 병합하며, 같은 URL이면 수동 데이터가 우선한다.

stdlib만 사용. 네트워크 실패 시 기존 CSV를 덮어쓰지 않고 그대로 둔다.
"""

import re
import os
import csv
import json
import time
import sys
from urllib.request import Request, urlopen
from urllib.parse import quote

BASE = "https://bang-dream.com"
HERE = os.path.dirname(os.path.abspath(__file__))
VENUES_PATH = os.path.join(HERE, "venues.json")
OUT_CSV = os.path.join(HERE, "events_overseas.csv")
MANUAL_CSV = os.path.join(HERE, "manual_overseas.csv")

UA = "Mozilla/5.0 (bandori-overseas-scraper; +https://bang-dream.com)"

# events/ 목록은 미래→과거 순으로 정렬되어 있다.
# 과거 행사(종료일 < 오늘)가 누적 이만큼 나오면 더 볼 필요 없으므로 페이징 중단.
EVENT_STOP_AFTER_PAST = 3
# 만일을 위한 안전 상한 (무한 페이징 방지)
EVENT_PAGE_CAP = 16

# news/ 에서 '오프라인/콜라보성'으로 볼 키워드 (하나라도 포함되면 후보)
NEWS_INCLUDE = ["コラボ", "カフェ", "cafe", "キャンペーン", "フェア", "ポップアップ",
                "POP UP", "POPUP", "ストア", "原画展", "展示", "オンリー", "R Baker",
                "催事", "出展", "ブース"]
# 아래 키워드가 있으면 오프라인 이벤트가 아님(세트리스트/배포/방송/음원 등) → 제외
NEWS_EXCLUDE = ["セットリスト", "プレイリスト", "配信", "放送", "Blu-ray", "リリース",
                "ラジオ", "デジタル", "同時購入", "見放題", "第", "放送のお知らせ"]

CSV_HEADER = ["이벤트명", "시작기간", "종료기간", "장소", "좌표", "통합정보모음", "비고", "예매처"]


# ----------------------------------------------------------------------------
# 네트워크
# ----------------------------------------------------------------------------
def fetch(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def strip_tags(html):
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------------------
# 날짜 파싱 (일본어)
# ----------------------------------------------------------------------------
def parse_jp_date(text):
    """'2026年10月24日(土)・25日(日)' 같은 문자열 → (start, end) ISO. 실패 시 (None, None)."""
    if not text:
        return (None, None)
    t = re.sub(r"[（(][^）)]*[）)]", "", text)          # (土) 등 요일 괄호 제거
    matches = re.findall(r"(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日", t)
    y = m = None
    dates = []
    for (yy, mm, dd) in matches:
        if yy:
            y = int(yy)
        if mm:
            m = int(mm)
        if y and m:
            try:
                dates.append((y, m, int(dd)))
            except ValueError:
                pass
    if not dates:
        return (None, None)
    fmt = lambda d: f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d}"
    return (fmt(dates[0]), fmt(dates[-1]))


def parse_dot_date(text):
    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", text or "")
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def extract_period_from_detail(html):
    """뉴스 상세 본문에서 개최 기간을 최대한 뽑아본다. (start, end) 또는 (None, None)."""
    text = strip_tags(html)
    # '開催期間'/'期間' 근처를 우선 탐색
    for kw in ("開催期間", "期間", "開催日", "会期"):
        idx = text.find(kw)
        if idx != -1:
            s, e = parse_jp_date(text[idx:idx + 120])
            if s:
                return (s, e)
    # 없으면 본문 전체에서 첫 날짜 범위
    return parse_jp_date(text[:2000])


# ----------------------------------------------------------------------------
# 지오코딩 (Nominatim, 캐시)
# ----------------------------------------------------------------------------
def load_venues():
    if os.path.exists(VENUES_PATH):
        try:
            with open(VENUES_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_venues(venues):
    with open(VENUES_PATH, "w", encoding="utf-8") as f:
        json.dump(venues, f, ensure_ascii=False, indent=2)


def geocode(name, venues):
    """장소명 → 'lat, lng' 문자열. 캐시 우선. 실패 시 '' 반환."""
    name = (name or "").strip()
    if not name:
        return ""
    if name in venues:
        v = venues[name]
        return v if v else ""      # 캐시된 null은 '못 찾음'으로 스킵

    # 여러 장소가 、·／, 로 묶인 경우 첫 장소만 떼서도 시도
    first = re.split(r"[、,・／/]", name)[0].strip()
    queries = [name, f"{name} 日本"]
    if first and first != name:
        queries += [first, f"{first} 日本"]

    coord = ""
    for q in queries:
        try:
            url = ("https://nominatim.openstreetmap.org/search?format=json&limit=1&q="
                   + quote(q))
            data = json.loads(fetch(url))
            if data:
                coord = f"{float(data[0]['lat']):.6f}, {float(data[0]['lon']):.6f}"
                break
        except Exception as ex:                       # noqa: BLE001
            print(f"    [geocode] '{q}' 실패: {ex}")
        time.sleep(1.1)                               # Nominatim 예의상 1req/s
    venues[name] = coord                              # 못 찾으면 '' 저장(다음 실행 시 재시도 안 함)
    print(f"    [geocode] {name} -> {coord or '(없음)'}")
    return coord


# ----------------------------------------------------------------------------
# 파서
# ----------------------------------------------------------------------------
def parse_events_page(html):
    """events/ 목록 페이지 → [dict] (title, start, end, place, url, category)."""
    out = []
    for block in re.findall(r'<article class="p-live-event-list__item">(.*?)</article>',
                            html, re.S):
        hrefs = re.search(r'href="([^"]+)"', block)
        title = re.search(r'item-title">(.*?)</div>', block, re.S)
        cat = re.search(r'item-category"><span>(.*?)</span>', block, re.S)
        date_p = re.search(r'item-date">.*?</h2>\s*<p>(.*?)</p>', block, re.S)
        place_p = re.search(r'item-place">.*?</h2>\s*<p>(.*?)</p>', block, re.S)
        if not (hrefs and title):
            continue
        s, e = parse_jp_date(date_p.group(1) if date_p else "")
        out.append({
            "title": strip_tags(title.group(1)),
            "start": s,
            "end": e or s,
            "place": strip_tags(place_p.group(1)) if place_p else "",
            "url": hrefs.group(1).strip(),
            "category": strip_tags(cat.group(1)) if cat else "",
            "note": "",
        })
    return out


def parse_news_page(html):
    """news/ 목록 페이지 → [dict] (title, date, url, category). 필터 전 raw."""
    out = []
    for block in re.findall(r'<article class="p-news-list__item">(.*?)</article>',
                            html, re.S):
        hrefs = re.search(r'href="([^"]+)"', block)
        title = re.search(r'item-title">(.*?)</h3>', block, re.S)
        cat = re.search(r'item-category"><span>(.*?)</span>', block, re.S)
        date_d = re.search(r'item-date">(.*?)</div>', block, re.S)
        if not (hrefs and title):
            continue
        out.append({
            "title": strip_tags(title.group(1)),
            "pub": parse_dot_date(date_d.group(1) if date_d else ""),
            "url": hrefs.group(1).strip(),
            "category": strip_tags(cat.group(1)) if cat else "",
        })
    return out


def news_is_offline(item):
    title = item["title"]
    if any(k in title for k in NEWS_EXCLUDE):
        return False
    if any(k.lower() in title.lower() for k in NEWS_INCLUDE):
        return True
    # 카테고리가 라이브·이벤트면서 제외어가 없으면 후보로
    return "ライブ・イベント" in item.get("category", "")


# ----------------------------------------------------------------------------
# 수집
# ----------------------------------------------------------------------------
def collect_events():
    from datetime import date
    today = date.today().isoformat()

    events = []
    past_seen = 0
    for page in range(1, EVENT_PAGE_CAP + 1):
        url = f"{BASE}/events/" if page == 1 else f"{BASE}/events/page/{page}/"
        try:
            html = fetch(url)
        except Exception as ex:                       # noqa: BLE001
            print(f"[i] events page {page} 실패: {ex}")
            break
        rows = parse_events_page(html)
        if not rows:
            break
        events.extend(rows)

        # 이 페이지에서 '이미 끝난 행사'(종료일 < 오늘) 개수 누적
        page_past = sum(1 for e in rows
                        if (e.get("end") or e.get("start") or "9999") < today)
        past_seen += page_past
        print(f"[+] events page {page}: {len(rows)}건 (지난 행사 누적 {past_seen})")

        # 과거 행사가 충분히 나오면 뒤쪽은 전부 과거이므로 중단
        if past_seen >= EVENT_STOP_AFTER_PAST:
            print(f"[i] 지난 행사 {past_seen}건 도달 → events 페이징 중단")
            break
    return events


def collect_news():
    try:
        html = fetch(f"{BASE}/news/")
    except Exception as ex:                           # noqa: BLE001
        print(f"[i] news 페이지 실패: {ex}")
        return []
    candidates = [n for n in parse_news_page(html) if news_is_offline(n)]
    print(f"[+] news 오프라인 후보: {len(candidates)}건")

    out = []
    for n in candidates:
        s = e = n["pub"]
        note = ""
        try:
            detail = fetch(n["url"])
            ds, de = extract_period_from_detail(detail)
            if ds:
                s, e = ds, de
            else:
                note = "기간 미확정(게시일 기준)"
        except Exception as ex:                       # noqa: BLE001
            print(f"    [news detail] {n['url']} 실패: {ex}")
            note = "기간 미확정(게시일 기준)"
        # 기간을 못 잡았으면 게시일 + 90일을 임시 종료로 (목록에서 바로 사라지지 않게)
        if s and e == s and note:
            from datetime import date, timedelta
            try:
                y, m, d = map(int, s.split("-"))
                e = (date(y, m, d) + timedelta(days=90)).isoformat()
            except ValueError:
                pass
        out.append({
            "title": n["title"], "start": s, "end": e,
            "place": "", "url": n["url"], "category": n.get("category", ""),
            "note": note,
        })
        time.sleep(0.4)
    return out


# ----------------------------------------------------------------------------
# 병합 / 저장
# ----------------------------------------------------------------------------
def read_manual():
    if not os.path.exists(MANUAL_CSV):
        return []
    rows = []
    with open(MANUAL_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def to_csv_row(ev):
    return {
        "이벤트명": ev["title"],
        "시작기간": ev.get("start") or "",
        "종료기간": ev.get("end") or ev.get("start") or "",
        "장소": ev.get("place", ""),
        "좌표": ev.get("coord", ""),
        "통합정보모음": ev.get("url", ""),
        "비고": ev.get("note", ""),
        "예매처": ev.get("ticket", ""),
    }


def main():
    print("=== BanG Dream! 해외 이벤트 수집 시작 ===")
    scraped = collect_events() + collect_news()

    # 유효한 시작일이 있고, 아직 안 끝난 것만 (지난 행사는 프런트에서도 숨김)
    from datetime import date
    today = date.today().isoformat()
    scraped = [e for e in scraped
               if e.get("start") and (e.get("end") or e["start"]) >= today]
    # URL 기준 중복 제거 (먼저 온 events/ 우선)
    seen, dedup = set(), []
    for e in scraped:
        if e["url"] in seen:
            continue
        seen.add(e["url"])
        dedup.append(e)

    if not dedup:
        print("[!] 수집 결과 없음(네트워크 문제 가능). 기존 CSV 유지.")
        return 0

    # 지오코딩
    venues = load_venues()
    for e in dedup:
        e["coord"] = geocode(e.get("place", ""), venues) if e.get("place") else ""
    save_venues(venues)

    # 수동 데이터 병합 (같은 URL이면 수동 우선, URL 없으면 그냥 추가)
    manual = read_manual()
    manual_urls = {r.get("통합정보모음", "").strip() for r in manual if r.get("통합정보모음")}
    rows = [to_csv_row(e) for e in dedup if e["url"] not in manual_urls]
    rows += [{h: r.get(h, "") for h in CSV_HEADER} for r in manual]

    # 시작일 정렬
    rows.sort(key=lambda r: r.get("시작기간") or "9999-12-31")

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)

    coord_cnt = sum(1 for r in rows if r["좌표"])
    print(f"=== 완료: {len(rows)}건 저장 (좌표 {coord_cnt}건) → {OUT_CSV} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
