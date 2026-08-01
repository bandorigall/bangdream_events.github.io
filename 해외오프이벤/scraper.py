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
import html as html_mod
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
SUMMARIES_PATH = os.path.join(HERE, "summaries.json")     # URL→한국어요약 캐시
GEMINI_KEY_PATH = os.path.join(HERE, "gemini_apikey.txt")  # 무료 Gemini API 키(커밋 금지)
GEMINI_MODEL = "gemini-2.5-flash"   # 이 키에서 무료 쿼터가 열려 있는 모델

UA = "Mozilla/5.0 (bandori-overseas-scraper; +https://bang-dream.com)"

# events/ 목록을 몇 페이지까지 훑을지. 조기중단 없이 끝까지 쭉 스캔한다.
# (과거 행사는 어차피 종료일 기준으로 걸러지므로 페이지를 넉넉히 봐도 결과엔 미래분만 남음)
EVENT_PAGE_CAP = 10
# None 이면 조기중단 안 함. 숫자면 과거 행사 누적이 그만큼일 때 페이징 중단.
EVENT_STOP_AFTER_PAST = None

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
    # HTML 엔티티 복원(&#039; &amp; 등). &nbsp; 는 일반 공백으로.
    text = html_mod.unescape(text).replace("\xa0", " ")
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


def parse_jp_date_groups(text):
    """일본어 날짜 문자열을 '연속일 묶음' 단위로 나눈다.
    '・'로 나열된 날짜 중 달력상 연속된 날은 한 그룹(기간형),
    사이가 벌어진 날은 별도 그룹(투어형)으로 분리한다.
    반환: [(start_iso, end_iso, first_day_index), ...]  (없으면 [])
    """
    from datetime import date as _date, timedelta
    if not text:
        return []
    t = re.sub(r"[（(][^）)]*[）)]", "", text)          # (土)/(月・祝) 등 요일 괄호 제거
    matches = re.findall(r"(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日", t)
    y = m = None
    days = []
    for (yy, mm, dd) in matches:
        if yy:
            y = int(yy)
        if mm:
            m = int(mm)
        if y and m:
            try:
                days.append(_date(y, m, int(dd)))
            except ValueError:
                pass
    if not days:
        return []
    groups = [[0]]                                     # 각 그룹에 담긴 '날짜 인덱스'
    for i in range(1, len(days)):
        if days[i] - days[i - 1] == timedelta(days=1):
            groups[-1].append(i)
        else:
            groups.append([i])
    out = []
    for g in groups:
        out.append((days[g[0]].isoformat(), days[g[-1]].isoformat(), g[0]))
    return out


def split_venues(place):
    """장소 문자열을 개별 장소 리스트로. (、 · ／ / 로 구분)"""
    if not place:
        return []
    return [v.strip() for v in re.split(r"[、・／/]", place) if v.strip()]


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
    """events/ 목록 페이지 → [dict].
    투어처럼 날짜가 여러 번(・로 나열, 사이가 벌어짐)이면 개최일 그룹마다 별도 행으로 분리하고,
    장소도 날짜별로 나열되어 있으면 그룹에 맞춰 매칭한다.
    """
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

        datetxt = date_p.group(1) if date_p else ""
        place = strip_tags(place_p.group(1)) if place_p else ""
        url = hrefs.group(1).strip()
        title_txt = strip_tags(title.group(1))
        cat_txt = strip_tags(cat.group(1)) if cat else ""

        groups = parse_jp_date_groups(datetxt)
        if not groups:
            continue

        venues = split_venues(place)
        # 날짜 총 개수 (장소를 날짜별로 매칭할지 판단용)
        n_days = sum(1 for _ in re.finditer(
            r"\d{1,2}日", re.sub(r"[（(][^）)]*[）)]", "", datetxt)))

        # 날짜그룹마다 별도 행으로 분리. 제목 접미사는 여기서 붙이지 않는다.
        # (과거 필터·중복 제거 후 '같은 제목이 2건 이상 남을 때'만 뒤에서 장소를 붙임)
        for gi, (s, e, day_idx) in enumerate(groups):
            # 장소 매칭: 그룹 수와 장소 수가 같으면 그룹별, 날짜 수와 같으면 날짜별, 아니면 통째로
            if venues and len(venues) == len(groups):
                gplace = venues[gi]
            elif venues and len(venues) == n_days and day_idx < len(venues):
                gplace = venues[day_idx]
            else:
                gplace = place
            out.append({
                "title": title_txt,
                "start": s,
                "end": e or s,
                "place": gplace,
                "url": url,
                "category": cat_txt,
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

        # (선택) 과거 행사가 충분히 나오면 조기중단. EVENT_STOP_AFTER_PAST=None이면 끝까지.
        if EVENT_STOP_AFTER_PAST is not None and past_seen >= EVENT_STOP_AFTER_PAST:
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
        # 상세페이지에서 '실제 개최 기간'을 뽑아낸 것만 채택한다.
        # 못 뽑으면 기간을 지어내지 않고 그냥 건너뛴다 (게시일/임의 기간 사용 금지).
        try:
            ds, de = extract_period_from_detail(fetch(n["url"]))
        except Exception as ex:                       # noqa: BLE001
            print(f"    [news detail] {n['url']} 실패: {ex}")
            ds = de = None
        if not ds:
            print(f"    [news skip] 기간 파악 불가 → 제외: {n['title'][:40]}")
            time.sleep(0.3)
            continue
        out.append({
            "title": n["title"], "start": ds, "end": de or ds,
            "place": "", "url": n["url"], "category": n.get("category", ""),
            "note": "",
        })
        time.sleep(0.3)
    return out


# ----------------------------------------------------------------------------
# Gemini 요약 (무료 API, '단 한 번'의 배치 호출로 새 이벤트만 요약)
# ----------------------------------------------------------------------------
def load_gemini_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(GEMINI_KEY_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def load_summaries():
    if os.path.exists(SUMMARIES_PATH):
        try:
            with open(SUMMARIES_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_summaries(cache):
    try:
        with open(SUMMARIES_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError as ex:                              # noqa: BLE001
        print(f"[i] summaries.json 저장 실패(무시): {ex}")


def base_url(url):
    """분리된 투어 행의 #앵커를 떼어 상세페이지 URL로 통일."""
    return (url or "").split("#", 1)[0]


def _detail_excerpt(url, limit=700):
    """상세페이지 본문에서 요약 재료가 될 앞부분 텍스트만 뽑는다. 실패 시 ''."""
    try:
        text = strip_tags(fetch(url))
    except Exception:                                 # noqa: BLE001
        return ""
    # 공통 헤더/사이트명 잡음 제거 후 앞부분만
    text = text.replace("BanG Dream!（バンドリ！）公式サイト", "").strip()
    return text[:limit]


def gemini_summarize_batch(items, key):
    """items: [(idx, title, place, date, excerpt)] → {idx: '한국어 한 줄 요약'}.
    딱 1회의 API 호출. 어떤 예외든 던지지 않고 빈 dict/부분 dict를 반환한다.
    """
    if not items or not key:
        return {}

    lines = []
    for idx, title, place, datestr, excerpt in items:
        lines.append(
            f"[{idx}] 제목: {title}\n"
            f"    기간: {datestr} / 장소: {place or '미상'}\n"
            f"    본문발췌: {excerpt or '(없음)'}"
        )
    joined = "\n\n".join(lines)

    prompt = (
        "너는 일본 '뱅드림!(BanG Dream!)' 오프라인 이벤트 정보를 한국 팬에게 안내하는 편집자다.\n"
        "아래 각 이벤트를 한국어 한 문장(35자 이내)으로 요약하라.\n"
        "규칙:\n"
        "- 홍보성 수식어·감탄사 빼고 '무엇을 하는 행사인지' 핵심만 (라이브/콜라보 카페/전시/물판 등).\n"
        "- 밴드명·아티스트명은 그대로, 장소/날짜는 이미 아니까 요약에 억지로 넣지 말 것.\n"
        "- 본문발췌가 비었거나 불명확하면 제목만으로 추정해 요약.\n"
        "- 반드시 JSON 배열로만 답한다. 형식: [{\"i\": 번호, \"summary\": \"요약\"}]\n\n"
        f"{joined}"
    )

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    endpoint = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{GEMINI_MODEL}:generateContent?key={key}")
    try:
        req = Request(endpoint, data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
    except Exception as ex:                            # noqa: BLE001
        print(f"[i] Gemini 요약 실패(무시하고 진행): {ex}")
        return {}

    out = {}
    if isinstance(parsed, list):
        for obj in parsed:
            try:
                out[int(obj["i"])] = str(obj["summary"]).strip()
            except (KeyError, ValueError, TypeError):
                continue
    return out


def attach_summaries(dedup):
    """dedup 이벤트들의 note(비고)에 한국어 요약을 채운다.
    캐시에 없는 URL만 모아 '한 번의' Gemini 호출로 처리한다. 실패해도 조용히 넘어간다.
    """
    key = load_gemini_key()
    cache = load_summaries()

    # 캐시에 없는(=새) 이벤트만 요약 대상.
    #   키는 '제목' — 같은 URL을 공유하는 별개 공연(13th DAY1/2/3)도 각자 요약되게 한다.
    todo, seen_titles = [], set()
    for e in dedup:
        t = e.get("title", "")
        if not t or t in cache or t in seen_titles:
            continue
        seen_titles.add(t)
        todo.append(e)

    if todo and key:
        print(f"[+] Gemini 요약 대상 {len(todo)}건 → 상세페이지 수집 후 1회 호출")
        items = []
        for i, e in enumerate(todo):
            excerpt = _detail_excerpt(base_url(e["url"]))
            items.append((i, e.get("title", ""), e.get("place", ""),
                          f"{e.get('start','')}~{e.get('end','')}", excerpt))
            time.sleep(0.3)                            # 상세페이지에 대한 예의
        result = gemini_summarize_batch(items, key)
        for i, e in enumerate(todo):
            s = result.get(i, "").strip()
            if s:
                cache[e["title"]] = s
        if result:
            save_summaries(cache)
    elif todo and not key:
        print("[i] Gemini 키 없음 → 요약 생략 (gemini_apikey.txt 확인)")

    # 캐시된 요약을 note에 병합 (기존 note가 있으면 ' · '로 이어 붙임)
    for e in dedup:
        s = cache.get(e.get("title", ""), "")
        if s:
            e["note"] = f"{e['note']} · {s}" if e.get("note") else s


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


def _venue_short(place):
    """접미사용으로 장소명을 짧게. 괄호 보충설명·부가 장소 제거 후 앞부분만."""
    p = re.split(r"[、・／,]", place)[0]              # 첫 장소만
    p = re.sub(r"[（(][^）)]*[）)]", "", p).strip()    # (보충설명) 제거
    return p[:16]


def apply_tour_suffix(dedup):
    """같은 제목이 2건 이상(=지역/날짜를 옮겨 다니는 투어)일 때만
    각 행 제목 뒤에 '(장소)'를 붙여 구분한다. 장소가 없으면 '(M/D)'.
    한 건만 남는 제목(양일 라이브 등)은 그대로 둔다.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for e in dedup:
        groups[e["title"]].append(e)
    for title, evs in groups.items():
        if len(evs) <= 1:
            continue
        for e in evs:
            place = _venue_short(e.get("place", ""))
            if place:
                suffix = place
            else:
                mm, dd = e["start"].split("-")[1:]
                suffix = f"{int(mm)}/{int(dd)}"
            e["title"] = f"{title} ({suffix})"


def main():
    print("=== BanG Dream! 해외 이벤트 수집 시작 ===")
    scraped = collect_events() + collect_news()

    # 유효한 시작일이 있고, 아직 안 끝난 것만 (지난 행사는 프런트에서도 숨김)
    from datetime import date
    today = date.today().isoformat()
    scraped = [e for e in scraped
               if e.get("start") and (e.get("end") or e["start"]) >= today]
    # 중복 제거: (제목, 시작일) 기준.
    #   같은 URL이라도 제목이 다르면(13th LIVE DAY1/2/3처럼 출연진이 다른 공연) 살린다.
    seen, dedup = set(), []
    for e in scraped:
        k = (e["title"], e.get("start"))
        if k in seen:
            continue
        seen.add(k)
        dedup.append(e)

    if not dedup:
        print("[!] 수집 결과 없음(네트워크 문제 가능). 기존 CSV 유지.")
        return 0

    # 투어 접미사: 같은 제목이 2건 이상 남았을 때만 뒤에 '(장소)'를 붙여 구분한다.
    #   (한 건만 남으면 양일 라이브 등이므로 접미사 없음)
    apply_tour_suffix(dedup)

    # 지오코딩
    venues = load_venues()
    for e in dedup:
        e["coord"] = geocode(e.get("place", ""), venues) if e.get("place") else ""
    save_venues(venues)

    # Gemini로 설명(비고) 자동 요약 — 새 이벤트가 있을 때만 단 1회 호출
    try:
        attach_summaries(dedup)
    except Exception as ex:                            # noqa: BLE001
        print(f"[i] 요약 단계 예외(무시): {ex}")

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
