import csv
import json
from datetime import datetime, timedelta
import urllib.parse

def build_events_data(csv_filename):
    """CSV 한 개를 읽어 events_data 리스트로 변환한다.
    해외용 CSV처럼 '네이버지도'/'다음지도' 열이 없어도 안전하게 동작한다.
    (해당 열이 없으면 map_targets에 n_link/k_link가 비어 버튼이 자동으로 안 나온다)
    """
    events_data = []

    raw_rows = []
    try:
        with open(csv_filename, newline='', encoding='utf-8-sig') as csvfile:  # -sig: BOM이 붙어도 첫 헤더('이벤트명')가 깨지지 않게
            reader = csv.DictReader(csvfile)
            for row in reader:
                raw_rows.append(row)
    except FileNotFoundError:
        print(f"[i] CSV file not found (skipped): {csv_filename}")
        return events_data

    # [정렬 로직] '시작기간' 열을 기준으로 정렬
    raw_rows.sort(key=lambda x: x.get('시작기간', '9999-12-31').strip())

    # 정렬된 데이터를 바탕으로 events_data 생성
    for idx, row in enumerate(raw_rows):
        title = row.get('이벤트명', '')
        start = row.get('시작기간', '').strip()
        end = row.get('종료기간', '').strip()
        raw_location = row.get('장소', '')
        main_link_raw = row.get('통합정보모음', '')
        note = row.get('비고', '')

        # 날짜 포맷팅
        try:
            end_date_obj = datetime.strptime(end, "%Y-%m-%d").date()
            cal_end = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            cal_end = end

        # -----------------------------------------------------------
        # [변경됨] JSON 형식의 문자열을 리스트로 변환
        # -----------------------------------------------------------
        # 변경 - JSON 파싱 실패 시 평문 문자열도 리스트로 감싸서 반환
        def safe_json_load(text):
            if not text or text.strip() == '': return []
            try:
                result = json.loads(text)
                return result if isinstance(result, list) else [result]
            except json.JSONDecodeError:
                return [text.strip()]  # ← "검색", "37.5, 127.0" 같은 평문도 처리

        # 통합정보모음: 단일 URL 또는 리스트. "라벨|URL" 형식이면 버튼 이름에 라벨 사용
        def parse_main_links(text):
            out = []
            for it in safe_json_load(text):
                if isinstance(it, str) and '|' in it:
                    lbl, _, u = it.partition('|')
                    out.append({'label': lbl.strip(), 'url': u.strip()})
                else:
                    out.append({'label': '', 'url': it})
            return out
        main_links = parse_main_links(main_link_raw)
        # 예매처: 통합정보모음과 동일 형식("라벨|URL" 또는 리스트). 별도 예매 버튼으로 노출
        ticket_links = parse_main_links(row.get('예매처', ''))

        naver_links = safe_json_load(row.get('네이버지도', '[]'))
        kakao_links = safe_json_load(row.get('다음지도', '[]'))
        coord_strs = safe_json_load(row.get('좌표', '[]'))
        
        # 장소 이름 분리
        loc_names = [x.strip() for x in raw_location.split(',')]

        # 데이터 중 가장 긴 길이를 기준으로 반복 (링크가 3개면 3번, 1개면 1번)
        max_len = max(len(naver_links), len(kakao_links), len(coord_strs), len(loc_names), 1)

        map_targets = []
        
        for i in range(max_len):
            # 1. 장소 이름 매칭
            if i < len(loc_names):
                loc_name = loc_names[i]
            else:
                # 이름이 모자르면 첫 번째 이름을 쓰거나 '장소 N'으로 표기
                loc_name = loc_names[0] if loc_names else f"장소 {i+1}"

            # 2. 링크 매칭
            raw_n = naver_links[i] if i < len(naver_links) else ''
            raw_k = kakao_links[i] if i < len(kakao_links) else ''

            encoded_loc = urllib.parse.quote(loc_name)

            n_link = f"https://map.naver.com/p/search/{encoded_loc}" if raw_n == '검색' else raw_n
            k_link = f"https://map.kakao.com/?q={encoded_loc}"       if raw_k == '검색' else raw_k

            # 3. 좌표 파싱 (문자열 "37.5, 127.0" -> float 변환)
            lat, lng = None, None
            if i < len(coord_strs):
                c_str = coord_strs[i]
                if c_str and ',' in c_str:
                    try:
                        lat_str, lng_str = c_str.split(',')
                        lat = float(lat_str)
                        lng = float(lng_str)
                    except ValueError:
                        pass

            # 유효한 정보가 하나라도 있으면 추가
            if n_link or k_link or (lat and lng):
                map_targets.append({
                    'name': loc_name,
                    'n_link': n_link,
                    'k_link': k_link,
                    'lat': lat,
                    'lng': lng
                })
        # -----------------------------------------------------------

        events_data.append({
            'id': idx,
            'title': title,
            'start': start,
            'end': end,
            'cal_end': cal_end,
            'location_text': raw_location,
            'map_targets': map_targets,
            'main_links': main_links,
            'ticket_links': ticket_links,
            'note': note,
            # 콜라보 카페 이벤트에만 굿즈/메뉴 계산기 버튼을 노출
            'has_goods': ('콜라보 카페' in title),
            # 코믹월드 335(아워 노트 ZA02 부스)에만 부스 가이드 버튼을 노출
            # (사설 부스 행은 공식 굿즈 데이터와 무관하므로 '아워 노트' 조건으로 배제)
            'has_cw': ('코믹월드 335' in title and '아워 노트' in title),
            # 카드 게임 페스티벌 2026 in KOREA — 무겐다이 뮤타입 물판/추첨 계산기
            'has_cgf': ('카드 게임 페스티벌' in title)
        })

    return events_data


def generate_final_page(korea_csv, overseas_csv, output_filename):
    # 1. 현재 시간 (생성 시점 기록용)
    now = datetime.now()
    current_time_str = now.strftime("%Y.%m.%d %H:%M:%S")

    # 한국 / 해외 두 데이터셋 빌드
    korea_events = build_events_data(korea_csv)
    overseas_events = build_events_data(overseas_csv)

    # JSON 데이터 생성
    json_korea = json.dumps(korea_events, ensure_ascii=False)
    json_overseas = json.dumps(overseas_events, ensure_ascii=False)

    # -----------------------------------------------------------
    # 콜라보 카페 굿즈/메뉴 계산기 데이터
    # cat: 분류 / thumb: 썸네일 / full: 원본(라이트박스용)
    # -----------------------------------------------------------
    T = 'assets/cafe/thumb/'
    S = 'assets/cafe/source/'
    cafe_goods = [
        {'id': 'drink_star',  'cat': '메뉴', 'name': '마이고의 별을 향한 드링크',        'price': 6900,  'thumb': T+'menu_drink_star.jpg',  'full': S+'menu.jpg'},
        {'id': 'drink_cross', 'cat': '메뉴', 'name': '마이고 아베무지카 교차하는 운명의 드링크', 'price': 6900, 'thumb': T+'menu_drink_cross.jpg', 'full': S+'menu.jpg'},
        {'id': 'drink_grail', 'cat': '메뉴', 'name': '아베무지카의 성배 드링크',          'price': 6900,  'thumb': T+'menu_drink_grail.jpg', 'full': S+'menu.jpg', 'bday': True},
        {'id': 'parfait',     'cat': '메뉴', 'name': '푸른 하늘의 나침반 파르페',         'price': 9900,  'thumb': T+'menu_parfait.jpg',     'full': S+'menu.jpg'},
        {'id': 'burger',      'cat': '메뉴', 'name': '개연의 만찬 햄버거',               'price': 13900, 'thumb': T+'menu_burger.jpg',      'full': S+'menu.jpg', 'bday': True},
        {'id': 'badge',       'cat': '굿즈', 'name': '트레이딩 캔뱃지 (10종 랜덤)',      'price': 8000,  'thumb': T+'goods_badge.jpg',      'full': S+'goods_badge_keyring.jpg'},
        {'id': 'keyring',     'cat': '굿즈', 'name': '트레이딩 CD형 키링 (10종 랜덤)',   'price': 13900, 'thumb': T+'goods_keyring.jpg',    'full': S+'goods_badge_keyring.jpg'},
        {'id': 'stand',       'cat': '굿즈', 'name': '아크릴 스탠드 (10종)',            'price': 18900, 'thumb': T+'goods_stand.jpg',      'full': S+'goods_stand_block.jpg', 'bday': '돌로리스 선택 시'},
        {'id': 'block',       'cat': '굿즈', 'name': '아크릴 블록 (2종)',              'price': 34900, 'thumb': T+'goods_block.jpg',      'full': S+'goods_stand_block.jpg', 'bday': '아베무지카 · 확인필요'},
    ]
    cafe_goods_json = json.dumps(cafe_goods, ensure_ascii=False)
    # 특전 안내 이미지 (라이트박스로 열어 확인)
    cafe_bonus = {
        'coaster': S+'bonus_coaster.jpg',          # 메뉴 구매 특전(코스터·돌로리스 생일)
        'postcard_poster': S+'bonus_postcard_poster.jpg',  # 4만/8만 엽서·포스터
    }
    cafe_bonus_json = json.dumps(cafe_bonus, ensure_ascii=False)

    # -----------------------------------------------------------
    # 코믹월드 335 일산 · 아워 노트 ZA02 부스 데이터
    # 출처: 공식 X(@bangdreamon_KR) 2026-08-07 참가 정보 공개 이미지 2장
    # CT/CS: 크롭 썸네일 / 원본(라이트박스)
    # -----------------------------------------------------------
    CT = 'assets/comicw335/thumb/'
    CS = 'assets/comicw335/source/'
    # 캐릭터 아크릴 스탠드 25종 (공지 이미지 배치 순서 = 밴드 순서)
    cw_chars = [
        ('takamatsu_tomori', '타카마츠 토모리'), ('chihaya_anon', '치하야 아논'),
        ('kaname_rana', '카나메 라나'),          ('nagasaki_soyo', '나가사키 소요'),
        ('shiina_taki', '시이나 타키'),          ('misumi_uika', '미스미 우이카'),
        ('wakaba_mutsumi', '와카바 무츠미'),     ('yahata_umiri', '야하타 우미리'),
        ('yutenji_nyamu', '유텐지 냐무'),        ('togawa_sakiko', '토가와 사키코'),
        ('nakamachi_arare', '나카마치 아라레'),  ('miyanaga_nonoka', '미야나가 노노카'),
        ('minetsuki_ritsu', '미네츠키 리츠'),    ('fuji_miyako', '후지 미야코'),
        ('sengoku_yuno', '센고쿠 유노'),         ('shiomi_hotaru', '시오미 호타루'),
        ('izawa_natsume', '이자와 나츠메'),      ('kotohira_nagi', '코토히라 나기'),
        ('hamasaki_mahoro', '하마사키 마호로'),  ('izumi_houka', '이즈미 호우카'),
        ('suga_raika', '스가 라이카'),           ('mahashi_miku', '마하시 미쿠'),
        ('yakura_yomogi', '야쿠라 요모기'),      ('umezato_chieri', '우메자토 치에리'),
        ('shinomiya_shizuku', '시노미야 시즈쿠'),
    ]
    cw_goods = [
        {'id': 'acryl_' + cid, 'cat': '캐릭터 아크릴 스탠드 (₩24,000 · 총 25종)',
         'name': kname, 'price': 24000, 'size': '본체 약 W80×H150mm / 받침대 약 W60×H45mm',
         'thumb': CT + 'acryl_' + cid + '.jpg', 'full': CS + 'sale.jpg'}
        for cid, kname in cw_chars
    ] + [
        {'id': 'acryl_bg', 'cat': '그 외 판매 굿즈', 'name': '배경 아크릴 스탠드 (1종)',
         'price': 26000, 'size': '약 W210×H150mm',
         'thumb': CT + 'acryl_background.jpg', 'full': CS + 'sale.jpg'},
        {'id': 'holderfile', 'cat': '그 외 판매 굿즈', 'name': '홀더파일 (1종)',
         'price': 6000, 'size': 'A4',
         'thumb': CT + 'holderfile.jpg', 'full': CS + 'sale.jpg'},
    ]
    # 현장 이벤트: 조건 체크 → 받을 수 있는 증정 굿즈 자동 계산
    cw_missions = [
        {'id': 'preorder', 'label': '사전예약 완료 화면 인증',
         'desc': '부스에서 사전예약 완료 화면을 보여주면 증정',
         'gives': [['hologram', 1]]},
        {'id': 'sns', 'label': '부스 사진·영상 SNS 업로드',
         'desc': '#뱅드림 #아워노트 해시태그와 함께 업로드 시 추가 증정',
         'gives': [['hologram', 1]]},
        {'id': 'live_join', 'label': '프리 라이브 참가 (공식 계정 팔로우)',
         'desc': '플랫폼 무관 공식 계정 팔로우 + 게임 내 프리 라이브 도전',
         'gives': [['hologram', 1]]},
        {'id': 'live_fc', 'label': '프리 라이브 풀 콤보(FC) 달성',
         'desc': '난이도와 관계없이 FC 달성 시 추가 증정',
         'gives': [['holderfile', 1]]},
        {'id': 'live_fc27', 'label': '난이도 27 이상 + 풀 콤보(FC)',
         'desc': '고난도 FC 달성 시 추가 증정',
         'gives': [['diary', 1]]},
    ]
    cw_prizes = {
        'hologram':   {'name': '아워 노트 보컬 홀로그램 티켓 (무작위 1종)', 'thumb': CT + 'prize_hologram.jpg'},
        'holderfile': {'name': '아워 노트 보컬 홀더파일 (무작위 1종)',      'thumb': CT + 'prize_holderfile.jpg'},
        'diary':      {'name': '아워 노트 밴드 다이어리 (무작위 1종)',      'thumb': CT + 'prize_diary.jpg'},
    }
    cw_info = {
        'booth': 'ZA02',
        'place': '일산 킨텍스 제1전시장',
        'date': '2026.08.15(토) ~ 08.16(일)',
        'limit': 5,
        'event_img': CS + 'event.jpg',
        'sale_img': CS + 'sale.jpg',
        'rules': [
            '현장 판매 구역 혼잡 방지를 위해 구매 시간을 적절히 분산해 주세요.',
            '1인 1회 대기 기준, <b>품목별 최대 5개</b>까지 구매 가능합니다.',
            '상품은 매일 준비된 수량 한정 판매이며, 당일 품절분은 다음 날 재입고될 수 있습니다.',
            '결제 후 현장에서 상품 상태 확인 필수 · <b>부스를 벗어난 이후에는 교환/환불 불가</b>입니다.',
            '이벤트 증정 굿즈도 매일 수량이 한정되어 있으며 선착순 증정입니다.',
        ],
    }
    cw_json = json.dumps({'goods': cw_goods, 'missions': cw_missions,
                          'prizes': cw_prizes, 'info': cw_info}, ensure_ascii=False)

    # -----------------------------------------------------------
    # 카드 게임 페스티벌 2026 in KOREA · 무겐다이 뮤타입 물판 데이터
    # 출처: 공식 X(@BUSHIASIA_KR) 2026-08-19 굿즈 라인업/추첨 안내 이미지 2장
    # 굿즈 3만원 구매당 퀴즈쇼&사인회 추첨권 1회(최대 5회) → 자동 계산
    # -----------------------------------------------------------
    GT = 'assets/cgf2026/thumb/'
    GS = 'assets/cgf2026/source/'
    cgf_goods = [
        {'id': 'diorama',        'name': '디오라마 아크릴 스탠드',        'price': 50000, 'size': '약 W150×H190×D70mm', 'kind': '단품',   'thumb': GT+'diorama.jpg'},
        {'id': 'pouch',          'name': '파우치',                      'price': 25000, 'size': '약 W140×H110mm',    'kind': '단품',   'thumb': GT+'pouch.jpg'},
        {'id': 'acryl_stand',    'name': '아크릴 스탠드',                'price': 20000, 'size': '본체 약 W75×H150mm / 받침대 약 W60×H60mm', 'kind': '종류별', 'thumb': GT+'acryl_stand.jpg'},
        {'id': 'acryl_keyring',  'name': 'SNS풍 아크릴 키체인',          'price': 12500, 'size': '약 W70×H100mm',     'kind': '종류별', 'thumb': GT+'acryl_keyring.jpg'},
        {'id': 'clearfile',      'name': '클리어 파일',                  'price': 6000,  'size': '약 W210×H300mm',    'kind': '단품',   'thumb': GT+'clearfile.jpg'},
        {'id': 'acryl_block',    'name': '트레이딩 아크릴 블록',          'price': 11000, 'size': '약 W70×H50×D8mm',   'kind': '랜덤',   'thumb': GT+'acryl_block.jpg'},
        {'id': 'badge_big_holo', 'name': '트레이딩 빅 홀로그래픽 캔뱃지',  'price': 8500,  'size': '직경 약 W75mm',      'kind': '랜덤',   'thumb': GT+'badge_big_holo.jpg'},
        {'id': 'badge_square',   'name': '트레이딩 사각 홀로그램 캔뱃지',  'price': 6000,  'size': '약 W70×H100mm',     'kind': '랜덤',   'thumb': GT+'badge_square.jpg'},
        {'id': 'badge_trading',  'name': '트레이딩 캔뱃지 (통상·홀로 ver.)', 'price': 6000, 'size': '공지 표기 약 W150×H190×D70mm', 'kind': '랜덤', 'thumb': GT+'badge_trading.jpg'},
        {'id': 'ticket_card',    'name': '트레이딩 티켓 스타일 카드',      'price': 6000,  'size': '약 W80×H210mm',     'kind': '랜덤',   'thumb': GT+'ticket_card.jpg'},
        {'id': 'bromide',        'name': '트레이딩 브로마이드',           'price': 4500,  'size': '약 W140×H110mm',    'kind': '랜덤',   'thumb': GT+'bromide.jpg'},
    ]
    cgf_info = {
        'place': '서울 양재 aT센터 제2전시장',
        'date': '2026.08.22(토) ~ 08.23(일)',
        'per_draw': 30000,      # 추첨권 1회 기준 금액
        'max_draw': 5,          # 1회 구매당 최대 추첨 횟수
        'draw_time': '8/23(일) 10:00 ~ 14:30 · 추첨 부스',
        'show_time': '8/23(일) 15:00 ~ 16:30 · 스테이지',
        'guests': '나카마치 아라레 · 센고쿠 유노',
        'goods_img': GS + 'goods.jpg',
        'lottery_img': GS + 'lottery.jpg',
        'rules': [
            '추첨은 <b>8/23(일)에만</b> 진행되며, 물판 코너에서 무겐다이 뮤타입 굿즈를 <b>3만원 구매할 때마다 추첨 1회</b>(1회 구매당 최대 5회)를 받습니다.',
            '추첨 부스의 추첨기를 돌려 <b>해당 색(빨강·하늘·노랑·보라)</b>이 나오면 당첨 → 퀴즈쇼 &amp; 사인회 참가.',
            '<b>구매 1건당 최대 1회만 당첨</b>되며 중복 당첨은 불가합니다. 추첨은 조기 종료될 수 있습니다.',
            '당첨자 확인을 위해 이름·연락처 등 개인정보 수집 및 확인이 진행됩니다.',
            '사인은 부시로드측이 준비한 포스트카드에만 가능하며, 퀴즈쇼 경품은 게스트 포스트카드입니다.',
            '모든 이벤트 참가에는 당일 사용 가능한 행사 티켓이 필요합니다.',
        ],
    }
    cgf_json = json.dumps({'goods': cgf_goods, 'info': cgf_info}, ensure_ascii=False)

    # 추가 CSS (일반 문자열 → 중괄호 그대로 사용)
    extra_css = """
        /* ===== 굿즈 계산기 모달 ===== */
        .gm-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.55); z-index:2000; align-items:center; justify-content:center; padding:20px; box-sizing:border-box; }
        .gm-box { background:#fff; width:min(820px,100%); max-height:90vh; max-height:calc(100dvh - 16px); border-radius:16px; overflow:hidden; display:flex; flex-direction:column; box-shadow:0 10px 40px rgba(0,0,0,0.3); }
        .gm-header { display:flex; align-items:center; justify-content:space-between; padding:16px 20px; background:linear-gradient(135deg,#ff4081,#ff80ab); color:#fff; font-weight:800; font-size:1.1rem; }
        .gm-close { background:rgba(255,255,255,0.25); border:none; color:#fff; width:44px; height:44px; border-radius:50%; font-size:1.1rem; cursor:pointer; flex-shrink:0; }
        .gm-body { display:flex; min-height:0; flex:1; }
        .gm-list { flex:1.3; overflow-y:auto; padding:14px; border-right:1px solid #eee; }
        .gm-cart { flex:1; overflow-y:auto; padding:14px; background:#fcfafc; display:flex; flex-direction:column; }
        .gm-cat { font-weight:800; color:#ff4081; margin:10px 4px 6px; font-size:0.95rem; }
        .gm-item { display:flex; align-items:center; gap:10px; padding:8px; border:1px solid #eee; border-radius:10px; margin-bottom:8px; }
        .gm-thumb { width:52px; height:52px; object-fit:cover; border-radius:8px; cursor:zoom-in; background:#f3f3f3; flex-shrink:0; }
        .gm-info { flex:1; cursor:pointer; min-width:0; }
        .gm-name { font-size:0.88rem; font-weight:600; word-break:keep-all; }
        .gm-bday-badge { display:inline-block; margin-left:5px; padding:1px 6px; border-radius:999px; background:#fff0d9; color:#c47a00; font-size:0.68rem; font-weight:700; white-space:nowrap; }
        .gm-price { font-size:0.82rem; color:#888; }
        .gm-add { border:none; background:#ff4081; color:#fff; border-radius:8px; padding:8px 12px; font-weight:700; cursor:pointer; flex-shrink:0; }
        .gm-add:hover { opacity:0.9; }
        .gm-cart h3 { margin:0 0 10px; font-size:1rem; }
        .gm-empty { color:#666; text-align:center; padding:30px 0; font-size:0.85rem; }
        .gm-cart-row { display:flex; align-items:center; gap:6px; padding:7px 0; border-bottom:1px dashed #eee; font-size:0.82rem; }
        .gm-cart-name { flex:1; word-break:keep-all; }
        .gm-qtybox { display:flex; align-items:center; gap:6px; }
        .gm-qtybox button { width:36px; height:36px; font-size:1rem; border:1px solid #ddd; background:#fff; border-radius:6px; cursor:pointer; font-weight:700; }
        .gm-cart-sub { width:74px; text-align:right; font-weight:600; }
        .gm-total { margin-top:auto; padding-top:14px; font-size:1.05rem; text-align:right; }
        .gm-total b { color:#ff4081; font-size:1.25rem; }
        .gm-bonus-title { margin-top:14px; font-weight:800; font-size:0.9rem; color:#444; }
        .gm-bonus-row { margin-top:8px; padding:9px 11px; border-radius:8px; background:#f1f1f1; color:#666; font-size:0.85rem; }
        .gm-bonus-row.on { background:#fff0f5; color:#d81b60; font-weight:700; }
        .gm-bonus-row.clickable { cursor:pointer; }
        .gm-bonus-row.clickable:hover { outline:2px solid #ff80ab; }
        .gm-bonus-row span { font-weight:400; font-size:0.75rem; color:#b08; }
        .gm-hint { margin-top:8px; font-size:0.78rem; color:#ff8a00; text-align:right; }
        .gm-note { margin-top:12px; font-size:0.72rem; color:#666; line-height:1.4; }
        .gm-lightbox { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.85); z-index:3000; align-items:center; justify-content:center; cursor:zoom-out; padding:20px; }
        .gm-lightbox img { max-width:95%; max-height:95%; border-radius:8px; }
        [data-lb] { cursor:zoom-in; }
        .cw-card, .cw-card img { cursor:pointer; }
        .gm-overlay [role=button]:focus-visible, .gm-lightbox:focus-visible { outline:3px solid #1a73e8; outline-offset:2px; }
        @media (max-width:680px) {
            .gm-overlay { padding:8px; }
            .gm-header { padding:10px 12px 10px 16px; font-size:1rem; }
            /* 모바일: 목록/장바구니 각각 스크롤하던 이중 스크롤 → 본문 하나만 스크롤 */
            .gm-body { flex-direction:column; overflow-y:auto; overscroll-behavior:contain; }
            .gm-list, .gm-cart { flex:none; overflow:visible; }
            .gm-list { border-right:none; border-bottom:1px solid #eee; }
            .gm-total { margin-top:12px; }
        }

        /* ===== 카드 게임 페스티벌 2026 · 무겐다이 뮤타입 물판 ===== */
        .cg-header { background:linear-gradient(135deg,#38b6ff,#b39bff 55%,#ff7fc4); }
        .cg-box { width:min(940px,100%); }
        .cg-meta { display:flex; flex-wrap:wrap; gap:6px; padding:11px 14px; background:#f2f9ff; border-bottom:1px solid #eee; }
        .cg-chip { background:#fff; border:1px solid #cfe7ff; color:#1b7fc4; border-radius:999px; padding:4px 10px; font-size:0.78rem; font-weight:700; }
        .cg-chip b { color:#e0348b; }
        .cg-chip.link { cursor:zoom-in; border-color:#ffc9e6; color:#d81b7a; }
        .cg-row { display:flex; align-items:center; gap:10px; border:1px solid #eee; border-radius:10px; padding:8px; margin-bottom:8px; }
        .cg-row img { width:84px; height:62px; object-fit:contain; cursor:zoom-in; flex-shrink:0; background:#fafafa; border-radius:6px; }
        .cg-row .nm { font-size:0.86rem; font-weight:700; word-break:keep-all; }
        .cg-row .sz { font-size:0.72rem; color:#666; margin-top:2px; }
        .cg-tag { display:inline-block; margin-left:5px; padding:1px 6px; border-radius:999px; font-size:0.68rem; font-weight:700; background:#eef4ff; color:#5b6bd6; }
        .cg-tag.rand { background:#fff0f7; color:#d81b7a; }
        .cg-draw { margin-top:12px; padding:12px; border-radius:12px; background:linear-gradient(135deg,#f2f9ff,#ffeef7); border:1px solid #e2eefc; text-align:center; }
        .cg-draw .big { font-size:1.6rem; font-weight:900; color:#e0348b; }
        .cg-draw .sub { font-size:0.78rem; color:#777; margin-top:4px; word-break:keep-all; }
        .cg-bar { height:8px; border-radius:999px; background:#e9e9ef; overflow:hidden; margin-top:9px; }
        .cg-bar i { display:block; height:100%; background:linear-gradient(90deg,#38b6ff,#ff7fc4); }
        .cg-rules { margin-top:12px; font-size:0.73rem; color:#666; line-height:1.55; }
        .cg-rules li { margin-bottom:3px; }
        .cg-src { margin-top:9px; font-size:0.7rem; color:#666; }

        /* ===== 코믹월드 335 부스 가이드 ===== */
        .cw-header { background:linear-gradient(135deg,#6a5cff,#c07bff 55%,#ff8ad1); }
        .cw-box { width:min(940px,100%); }
        .cw-meta { display:flex; flex-wrap:wrap; gap:6px; padding:11px 14px; background:#f6f3ff; border-bottom:1px solid #eee; }
        .cw-chip { background:#fff; border:1px solid #e3dcff; color:#5b46c9; border-radius:999px; padding:4px 10px; font-size:0.78rem; font-weight:700; }
        .cw-chip b { color:#e0348b; }
        .cw-chip.link { cursor:zoom-in; border-color:#ffc9e6; color:#d81b7a; }
        .cw-cat { font-weight:800; color:#6a5cff; margin:12px 4px 8px; font-size:0.92rem; }
        .cw-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(96px,1fr)); gap:8px; }
        .cw-card { border:1px solid #eee; border-radius:10px; padding:6px 4px 7px; text-align:center; cursor:pointer; background:#fff; transition:.15s; }
        .cw-card:hover { border-color:#c07bff; transform:translateY(-2px); }
        .cw-card.picked { border-color:#6a5cff; background:#f4f1ff; box-shadow:0 0 0 2px #ded5ff inset; }
        .cw-card img { width:100%; height:106px; object-fit:contain; }
        .cw-card .nm { font-size:0.72rem; font-weight:600; margin-top:3px; word-break:keep-all; line-height:1.25; }
        .cw-card .qty { display:inline-block; margin-top:3px; font-size:0.7rem; font-weight:800; color:#6a5cff; }
        .cw-row { display:flex; align-items:center; gap:10px; border:1px solid #eee; border-radius:10px; padding:8px; margin-bottom:8px; }
        .cw-row img { width:76px; height:56px; object-fit:contain; cursor:zoom-in; flex-shrink:0; }
        .cw-row .nm { font-size:0.86rem; font-weight:700; }
        .cw-row .sz { font-size:0.72rem; color:#666; }
        .cw-mission { display:flex; gap:9px; align-items:flex-start; padding:8px 9px; border:1px solid #eee; border-radius:10px; margin-bottom:7px; cursor:pointer; }
        .cw-mission.on { border-color:#ff8ad1; background:#fff4fa; }
        .cw-mission input { margin-top:3px; accent-color:#e0348b; }
        .cw-mission .ml { font-size:0.82rem; font-weight:700; word-break:keep-all; }
        .cw-mission .md { font-size:0.72rem; color:#666; margin-top:2px; word-break:keep-all; }
        .cw-prize { display:flex; align-items:center; gap:9px; padding:7px; border-radius:9px; background:#f7f7f7; margin-top:7px; }
        .cw-prize.on { background:#fff0f7; }
        .cw-prize img { width:56px; height:40px; object-fit:contain; cursor:zoom-in; }
        .cw-prize .pn { flex:1; font-size:0.78rem; word-break:keep-all; }
        .cw-prize .pc { font-weight:800; color:#e0348b; font-size:0.86rem; }
        .cw-warn { margin-top:8px; font-size:0.75rem; color:#e0348b; font-weight:700; text-align:right; }
        .cw-rules { margin-top:12px; font-size:0.73rem; color:#666; line-height:1.55; }
        .cw-rules li { margin-bottom:3px; }
        .cw-src { margin-top:9px; font-size:0.7rem; color:#666; }
    """

    # 모달 HTML
    modal_html = """
<div id="goods-modal" class="gm-overlay" role="dialog" aria-modal="true" aria-labelledby="goods-modal-title" onclick="if(event.target===this)closeGoodsModal()">
  <div class="gm-box">
    <div class="gm-header">
      <span id="goods-modal-title">🛒 콜라보 카페 굿즈 · 메뉴 계산기</span>
      <button type="button" class="gm-close" aria-label="닫기" onclick="closeGoodsModal()">✕</button>
    </div>
    <div class="gm-body">
      <div class="gm-list" id="gm-list"></div>
      <div class="gm-cart">
        <h3>🧾 장바구니</h3>
        <div class="gm-cart-items" id="gm-cart-items"></div>
        <div class="gm-total" id="gm-total"></div>
        <div id="gm-bonus"></div>
      </div>
    </div>
  </div>
</div>
<div id="cw-modal" class="gm-overlay" role="dialog" aria-modal="true" aria-labelledby="cw-modal-title" onclick="if(event.target===this)closeCwModal()">
  <div class="gm-box cw-box">
    <div class="gm-header cw-header">
      <span id="cw-modal-title">🎪 코믹월드 335 · 아워 노트 부스 가이드</span>
      <button type="button" class="gm-close" aria-label="닫기" onclick="closeCwModal()">✕</button>
    </div>
    <div class="cw-meta" id="cw-meta"></div>
    <div class="gm-body">
      <div class="gm-list" id="cw-list"></div>
      <div class="gm-cart">
        <h3>🧾 구매 목록</h3>
        <div class="gm-cart-items" id="cw-cart-items"></div>
        <div class="gm-total" id="cw-total"></div>
        <div id="cw-warn"></div>
        <h3 style="margin-top:16px;">🎁 현장 이벤트 (해당 항목 체크)</h3>
        <div id="cw-missions"></div>
        <div id="cw-prizes"></div>
        <ol class="cw-rules" id="cw-rules"></ol>
        <div class="cw-src">※ 이미지·정보 출처: 공식 X @bangdreamon_KR (2026-08-07 참가 정보 공개). 실제 굿즈 디자인·색상은 실물과 다를 수 있습니다.</div>
      </div>
    </div>
  </div>
</div>
<div id="cg-modal" class="gm-overlay" role="dialog" aria-modal="true" aria-labelledby="cg-modal-title" onclick="if(event.target===this)closeCgModal()">
  <div class="gm-box cg-box">
    <div class="gm-header cg-header">
      <span id="cg-modal-title">🛸 무겐다이 뮤타입 물판 · 사인회 추첨 계산기</span>
      <button type="button" class="gm-close" aria-label="닫기" onclick="closeCgModal()">✕</button>
    </div>
    <div class="cg-meta" id="cg-meta"></div>
    <div class="gm-body">
      <div class="gm-list" id="cg-list"></div>
      <div class="gm-cart">
        <h3>🧾 구매 목록</h3>
        <div class="gm-cart-items" id="cg-cart-items"></div>
        <div class="gm-total" id="cg-total"></div>
        <div id="cg-draw"></div>
        <ol class="cg-rules" id="cg-rules"></ol>
        <div class="cg-src">※ 이미지·정보 출처: 공식 X @BUSHIASIA_KR (2026-08-19 굿즈 라인업 · 추첨 이벤트 공지). 판매 수량·구매 제한은 별도 공지가 없어 반영되지 않았습니다.</div>
      </div>
    </div>
  </div>
</div>
<div id="gm-lightbox" class="gm-lightbox" role="dialog" aria-modal="true" aria-label="원본 이미지 (클릭하거나 ESC로 닫기)" tabindex="-1" onclick="closeLightbox()"><img id="gm-lightbox-img" alt="원본 이미지"></div>
"""

    # 계산기 JS (일반 문자열)
    goods_js = """
    const CAFE_GOODS = __CAFE_GOODS__;
    const CAFE_BONUS = __CAFE_BONUS__;
    let gmCart = {};

    function openGoodsModal() { buildGoodsList(); renderCart(); openOverlay('goods-modal'); }
    function closeGoodsModal() { closeOverlay('goods-modal'); }

    function buildGoodsList() {
        const wrap = document.getElementById('gm-list');
        if (wrap.dataset.built) return;
        const cats = {};
        CAFE_GOODS.forEach(g => { (cats[g.cat] = cats[g.cat] || []).push(g); });
        let html = '';
        for (const c in cats) {
            html += `<div class="gm-cat">${esc(c)}</div>`;
            cats[c].forEach(g => {
                const bdayBadge = g.bday
                    ? `<span class="gm-bday-badge" title="돌로리스 생일 특전 대상 (6/26~7/2)">🎂 생일특전${typeof g.bday==='string' ? ' ('+g.bday+')' : ''}</span>`
                    : '';
                html += `<div class="gm-item">
                    <img src="${esc(g.thumb)}" class="gm-thumb" alt="${esc(g.name)} 이미지" data-lb="${esc(g.full)}" tabindex="0" role="button">
                    <div class="gm-info" onclick="addToCart('${g.id}')">
                        <div class="gm-name">${esc(g.name)}${bdayBadge}</div>
                        <div class="gm-price">${g.price.toLocaleString()}원</div>
                    </div>
                    <button type="button" class="gm-add" onclick="addToCart('${g.id}')">담기</button>
                </div>`;
            });
        }
        wrap.innerHTML = html;
        wrap.dataset.built = '1';
    }

    function addToCart(id) { gmCart[id] = (gmCart[id] || 0) + 1; renderCart(); }
    function changeQty(id, d) { gmCart[id] = (gmCart[id] || 0) + d; if (gmCart[id] <= 0) delete gmCart[id]; renderCart(); }

    function renderCart() {
        const box = document.getElementById('gm-cart-items');
        const ids = Object.keys(gmCart);
        if (ids.length === 0) {
            box.innerHTML = '<div class="gm-empty">왼쪽에서 상품을 담아보세요</div>';
        } else {
            let h = '';
            ids.forEach(id => {
                const g = CAFE_GOODS.find(x => x.id === id);
                const q = gmCart[id];
                h += `<div class="gm-cart-row">
                    <span class="gm-cart-name">${esc(g.name)}</span>
                    <span class="gm-qtybox">
                        <button type="button" aria-label="하나 빼기" onclick="changeQty(\'${id}\',-1)">−</button><b>${q}</b><button type="button" aria-label="하나 더" onclick="changeQty(\'${id}\',1)">＋</button>
                    </span>
                    <span class="gm-cart-sub">${(g.price*q).toLocaleString()}원</span>
                </div>`;
            });
            box.innerHTML = h;
        }
        const total = ids.reduce((s, id) => s + CAFE_GOODS.find(x => x.id === id).price * gmCart[id], 0);
        document.getElementById('gm-total').innerHTML = `합계 <b>${total.toLocaleString()}원</b>`;

        // 메뉴 수량만큼 메뉴 구매 특전(코스터) 자동 증정 (메뉴 1개당 1장)
        const menuQty = ids.reduce((s, id) => s + (CAFE_GOODS.find(x => x.id === id).cat === '메뉴' ? gmCart[id] : 0), 0);
        const card = Math.floor(total / 40000);
        const poster = Math.floor(total / 80000);
        let b = '<div class="gm-bonus-title">🎁 받을 수 있는 특전</div>';
        if (menuQty > 0) {
            b += `<div class="gm-bonus-row on clickable" data-lb="${esc(CAFE_BONUS.coaster)}" tabindex="0" role="button">🥤 메뉴 구매 특전 코스터 <b>${menuQty}장</b> <span>(메뉴 1개당 1장 · 클릭하여 보기)</span></div>`;
        }

        // 돌로리스 생일 특전 (기간 한정: 2026-06-26 ~ 2026-07-02)
        // 조건: 성배 드링크 / 개연의 만찬 햄버거 구매 시 생일 엽서 증정
        const bdayStart = new Date('2026-06-26T00:00:00');
        const bdayEnd = new Date('2026-07-02T23:59:59');
        const inBday = (new Date() >= bdayStart) && (new Date() <= bdayEnd);
        const hasBday = ids.some(id => CAFE_GOODS.find(x => x.id === id).bday);
        if (hasBday) {
            const bdayTag = inBday ? '증정' : '대상 (기간 외)';
            b += `<div class="gm-bonus-row ${inBday?'on':''} clickable" data-lb="${esc(CAFE_BONUS.coaster)}" tabindex="0" role="button">🎂 돌로리스 생일 엽서 <b>${bdayTag}</b> <span>(6/26~7/2 한정 · 성배 드링크·개연의 만찬 햄버거·돌로리스 굿즈(랜덤굿즈 제외) 구매 시 1장 · 클릭하여 보기)</span></div>`;
        }
        b += `<div class="gm-bonus-row ${card>0?'on':''} clickable" data-lb="${esc(CAFE_BONUS.postcard_poster)}" tabindex="0" role="button">🎴 홀로그램 엽서 <b>${card}장</b> <span>(4만원당 1장 · 클릭하여 보기)</span></div>`;
        b += `<div class="gm-bonus-row ${poster>0?'on':''} clickable" data-lb="${esc(CAFE_BONUS.postcard_poster)}" tabindex="0" role="button">🖼️ A3 펄 포스터 <b>${poster}장</b> <span>(8만원당 1장 · 클릭하여 보기)</span></div>`;
        if (total > 0 && total % 40000 !== 0) {
            b += `<div class="gm-hint">${(40000-(total%40000)).toLocaleString()}원 더 담으면 엽서 1장 추가</div>`;
        }
        b += `<div class="gm-note">※ 코스터는 1~2주차 MyGO!!!!! / 3~4주차 Ave Mujica 전 6종 중 랜덤. 엽서·포스터는 굿즈+메뉴 합산 결제금액 기준 랜덤 증정. 돌로리스 생일 엽서(6/26~7/2)는 성배 드링크·햄버거 외 돌로리스 굿즈(랜덤굿즈 제외) 구매 시에도 증정.</div>`;
        document.getElementById('gm-bonus').innerHTML = b;
    }

    // ---- 모달 공통: 열기/닫기, 포커스, 배경 스크롤 잠금, ESC ----
    let lastFocus = null, lbFocus = null;
    const OVERLAYS = ['goods-modal', 'cw-modal', 'cg-modal'];
    function syncBodyLock() {
        const anyOpen = OVERLAYS.concat(['gm-lightbox']).some(id => document.getElementById(id).style.display === 'flex');
        document.body.classList.toggle('modal-open', anyOpen);
    }
    function openOverlay(id) {
        lastFocus = document.activeElement;
        const el = document.getElementById(id);
        el.style.display = 'flex';
        syncBodyLock();
        const c = el.querySelector('.gm-close');
        if (c) c.focus();
    }
    function closeOverlay(id) {
        document.getElementById(id).style.display = 'none';
        syncBodyLock();
        if (lastFocus && lastFocus.focus) lastFocus.focus();
    }
    function showLightbox(src) {
        lbFocus = document.activeElement;
        document.getElementById('gm-lightbox-img').src = src;
        const lb = document.getElementById('gm-lightbox');
        lb.style.display = 'flex';
        syncBodyLock();
        lb.focus();
    }
    function closeLightbox() {
        document.getElementById('gm-lightbox').style.display = 'none';
        syncBodyLock();
        if (lbFocus && lbFocus.focus) lbFocus.focus();
    }
    // data-lb="이미지경로" 요소 클릭 → 라이트박스 (onclick 문자열에 URL 직접 삽입 안 함)
    document.addEventListener('click', function (e) {
        const t = e.target.closest('[data-lb]');
        if (!t) return;
        e.stopPropagation();
        showLightbox(t.dataset.lb);
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Tab') {
            const lbOpen = document.getElementById('gm-lightbox').style.display === 'flex';
            const oid = lbOpen ? null : OVERLAYS.find(id => document.getElementById(id).style.display === 'flex');
            if (lbOpen) { e.preventDefault(); return; }  // 라이트박스는 포커스 고정
            if (oid) {
                const box = document.getElementById(oid);
                const f = [...box.querySelectorAll('button, a[href], input, [tabindex]:not([tabindex="-1"])')]
                    .filter(el => el.offsetParent !== null);
                if (!f.length) return;
                const first = f[0], last = f[f.length - 1];
                if (e.shiftKey && (document.activeElement === first || !box.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
                else if (!e.shiftKey && (document.activeElement === last || !box.contains(document.activeElement))) { e.preventDefault(); first.focus(); }
            }
            return;
        }
        if (e.key === 'Escape') {
            // 라이트박스가 위에 떠 있으면 그것부터 닫는다
            if (document.getElementById('gm-lightbox').style.display === 'flex') { closeLightbox(); return; }
            const open = OVERLAYS.find(id => document.getElementById(id).style.display === 'flex');
            if (open) closeOverlay(open);
            return;
        }
        // div/span/img 에 role=button 을 붙인 요소는 Enter/Space 로도 동작
        if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('[role=button]:not(button):not(a)')) {
            if (e.target.classList.contains('event-card')) return;  // 카드는 자체 핸들러
            e.preventDefault();
            e.target.click();
        }
    });
    """
    # ---- 코믹월드 335 부스 가이드 JS ----
    goods_js += """
    const CW = __CW_DATA__;
    let cwCart = {}, cwMission = {};

    function openCwModal() { buildCwModal(); renderCw(); openOverlay('cw-modal'); }
    function closeCwModal() { closeOverlay('cw-modal'); }

    function buildCwModal() {
        const meta = document.getElementById('cw-meta');
        if (meta.dataset.built) return;
        const i = CW.info;
        meta.innerHTML = `<span class="cw-chip">📍 ${esc(i.place)} <b>${esc(i.booth)}</b></span>
            <span class="cw-chip">📅 ${esc(i.date)}</span>
            <span class="cw-chip">🛍️ 품목별 최대 ${i.limit}개</span>
            <span class="cw-chip link" data-lb="${esc(i.event_img)}" tabindex="0" role="button">🖼️ 이벤트 공지 원본</span>
            <span class="cw-chip link" data-lb="${esc(i.sale_img)}" tabindex="0" role="button">🖼️ 판매 공지 원본</span>`;

        const cats = {};
        CW.goods.forEach(g => { (cats[g.cat] = cats[g.cat] || []).push(g); });
        let html = '';
        for (const c in cats) {
            const isChar = c.indexOf('캐릭터') === 0;
            html += `<div class="cw-cat">${esc(c)}</div>`;
            if (isChar) {
                html += '<div class="cw-grid">';
                cats[c].forEach(g => {
                    html += `<div class="cw-card" id="cwc-${g.id}" tabindex="0" role="button" aria-label="${esc(g.name)} 담기" onclick="cwAdd('${g.id}')" title="클릭: 담기">
                        <img src="${esc(g.thumb)}" alt="${esc(g.name)}">
                        <div class="nm">${esc(g.name)}</div>
                        <div class="qty" id="cwq-${g.id}"></div>
                    </div>`;
                });
                html += '</div>';
            } else {
                cats[c].forEach(g => {
                    html += `<div class="cw-row">
                        <img src="${esc(g.thumb)}" data-lb="${esc(g.full)}" tabindex="0" role="button" alt="${esc(g.name)}">
                        <div style="flex:1;cursor:pointer;" onclick="cwAdd('${g.id}')">
                            <div class="nm">${esc(g.name)}</div>
                            <div class="sz">${esc(g.size)} · ${g.price.toLocaleString()}원</div>
                        </div>
                        <button type="button" class="gm-add" style="background:#6a5cff;" onclick="cwAdd('${g.id}')">담기</button>
                    </div>`;
                });
            }
        }
        document.getElementById('cw-list').innerHTML = html;

        document.getElementById('cw-missions').innerHTML = CW.missions.map(m =>
            `<label class="cw-mission" id="cwm-${m.id}">
                <input type="checkbox" onchange="cwToggle('${m.id}', this.checked)">
                <span><span class="ml">${esc(m.label)}</span><span class="md">${esc(m.desc)}</span></span>
            </label>`).join('');

        document.getElementById('cw-rules').innerHTML =
            CW.info.rules.map(r => `<li>${r}</li>`).join('');
        meta.dataset.built = '1';
    }

    function cwAdd(id) {
        const lim = CW.info.limit;
        cwCart[id] = Math.min((cwCart[id] || 0) + 1, lim);
        renderCw();
    }
    function cwQty(id, d) { cwCart[id] = (cwCart[id] || 0) + d; if (cwCart[id] <= 0) delete cwCart[id]; renderCw(); }
    function cwToggle(id, on) { cwMission[id] = on; document.getElementById('cwm-'+id).classList.toggle('on', on); renderCw(); }

    function renderCw() {
        const ids = Object.keys(cwCart);
        const find = id => CW.goods.find(g => g.id === id);

        // 카드 선택 상태 갱신
        CW.goods.forEach(g => {
            const card = document.getElementById('cwc-' + g.id);
            if (!card) return;
            const q = cwCart[g.id] || 0;
            card.classList.toggle('picked', q > 0);
            document.getElementById('cwq-' + g.id).textContent = q ? '× ' + q : '';
        });

        const box = document.getElementById('cw-cart-items');
        if (ids.length === 0) {
            box.innerHTML = '<div class="gm-empty">왼쪽에서 굿즈를 담아보세요<br>(캐릭터 카드는 클릭하면 담깁니다)</div>';
        } else {
            box.innerHTML = ids.map(id => {
                const g = find(id), q = cwCart[id];
                return `<div class="gm-cart-row">
                    <span class="gm-cart-name">${esc(g.name)}</span>
                    <span class="gm-qtybox">
                        <button type="button" aria-label="하나 빼기" onclick="cwQty(\'${id}\',-1)">−</button><b>${q}</b><button type="button" aria-label="하나 더" onclick="cwQty(\'${id}\',1)">＋</button>
                    </span>
                    <span class="gm-cart-sub">${(g.price*q).toLocaleString()}원</span>
                </div>`;
            }).join('');
        }
        const total = ids.reduce((s, id) => s + find(id).price * cwCart[id], 0);
        const count = ids.reduce((s, id) => s + cwCart[id], 0);
        document.getElementById('cw-total').innerHTML =
            `${count}점 · 합계 <b>${total.toLocaleString()}원</b>`;
        const maxed = ids.filter(id => cwCart[id] >= CW.info.limit).length;
        document.getElementById('cw-warn').innerHTML = maxed
            ? `<div class="cw-warn">⚠️ ${maxed}개 품목이 1회 대기 한도(품목별 ${CW.info.limit}개)에 도달했습니다 — 더 사려면 재줄서기 필요</div>` : '';

        // 현장 이벤트 → 받을 수 있는 증정 굿즈 집계
        const got = {};
        CW.missions.forEach(m => {
            if (!cwMission[m.id]) return;
            m.gives.forEach(([p, n]) => { got[p] = (got[p] || 0) + n; });
        });
        document.getElementById('cw-prizes').innerHTML = Object.keys(CW.prizes).map(k => {
            const p = CW.prizes[k], n = got[k] || 0;
            return `<div class="cw-prize ${n?'on':''}">
                <img src="${esc(p.thumb)}" data-lb="${esc(CW.info.event_img)}" tabindex="0" role="button" alt="${esc(p.name)}">
                <span class="pn">${esc(p.name)}</span><span class="pc">${n}개</span>
            </div>`;
        }).join('');
    }
    """

    # ---- 카드 게임 페스티벌 2026 · 무겐다이 뮤타입 물판 JS ----
    goods_js += """
    const CG = __CG_DATA__;
    let cgCart = {};

    function openCgModal() { buildCgModal(); renderCg(); openOverlay('cg-modal'); }
    function closeCgModal() { closeOverlay('cg-modal'); }

    function buildCgModal() {
        const meta = document.getElementById('cg-meta');
        if (meta.dataset.built) return;
        const i = CG.info;
        meta.innerHTML = `<span class="cg-chip">📍 ${esc(i.place)}</span>
            <span class="cg-chip">🎲 추첨 <b>${esc(i.draw_time)}</b></span>
            <span class="cg-chip">🎤 퀴즈쇼&amp;사인회 ${esc(i.show_time)}</span>
            <span class="cg-chip">👤 ${esc(i.guests)}</span>
            <span class="cg-chip link" data-lb="${esc(i.goods_img)}" tabindex="0" role="button">🖼️ 굿즈 공지 원본</span>
            <span class="cg-chip link" data-lb="${esc(i.lottery_img)}" tabindex="0" role="button">🖼️ 추첨 공지 원본</span>`;

        document.getElementById('cg-list').innerHTML = CG.goods.map(g => {
            const tag = g.kind === '랜덤' ? '<span class="cg-tag rand">랜덤</span>'
                      : (g.kind === '종류별' ? '<span class="cg-tag">종류별</span>' : '');
            return `<div class="cg-row">
                <img src="${esc(g.thumb)}" data-lb="${esc(CG.info.goods_img)}" tabindex="0" role="button" alt="${esc(g.name)}">
                <div style="flex:1;cursor:pointer;" onclick="cgAdd('${g.id}')">
                    <div class="nm">${esc(g.name)}${tag}</div>
                    <div class="sz">${esc(g.size)} · ${g.price.toLocaleString()}원</div>
                </div>
                <button type="button" class="gm-add" style="background:#38b6ff;" onclick="cgAdd('${g.id}')">담기</button>
            </div>`;
        }).join('');

        document.getElementById('cg-rules').innerHTML =
            CG.info.rules.map(r => `<li>${r}</li>`).join('');
        meta.dataset.built = '1';
    }

    function cgAdd(id) { cgCart[id] = (cgCart[id] || 0) + 1; renderCg(); }
    function cgQty(id, d) { cgCart[id] = (cgCart[id] || 0) + d; if (cgCart[id] <= 0) delete cgCart[id]; renderCg(); }

    function renderCg() {
        const ids = Object.keys(cgCart);
        const find = id => CG.goods.find(g => g.id === id);
        const box = document.getElementById('cg-cart-items');
        if (ids.length === 0) {
            box.innerHTML = '<div class="gm-empty">왼쪽에서 굿즈를 담아보세요<br>3만원마다 사인회 추첨권 1회!</div>';
        } else {
            box.innerHTML = ids.map(id => {
                const g = find(id), q = cgCart[id];
                return `<div class="gm-cart-row">
                    <span class="gm-cart-name">${esc(g.name)}</span>
                    <span class="gm-qtybox">
                        <button type="button" aria-label="하나 빼기" onclick="cgQty(\'${id}\',-1)">−</button><b>${q}</b><button type="button" aria-label="하나 더" onclick="cgQty(\'${id}\',1)">＋</button>
                    </span>
                    <span class="gm-cart-sub">${(g.price*q).toLocaleString()}원</span>
                </div>`;
            }).join('');
        }
        const total = ids.reduce((s, id) => s + find(id).price * cgCart[id], 0);
        const count = ids.reduce((s, id) => s + cgCart[id], 0);
        document.getElementById('cg-total').innerHTML =
            `${count}점 · 합계 <b>${total.toLocaleString()}원</b>`;

        const per = CG.info.per_draw, max = CG.info.max_draw;
        const raw = Math.floor(total / per);
        const draws = Math.min(raw, max);
        const rest = total % per;
        let sub;
        if (raw >= max) {
            sub = `1회 구매 기준 최대 ${max}회에 도달했습니다. 더 받으려면 <b>결제를 나눠서</b> 진행해야 합니다.`;
        } else if (total === 0) {
            sub = `${per.toLocaleString()}원 구매마다 추첨 1회 (1회 구매당 최대 ${max}회)`;
        } else {
            sub = `다음 추첨권까지 <b>${(per - rest).toLocaleString()}원</b> 남았습니다.`;
        }
        const pct = raw >= max ? 100 : Math.round(rest / per * 100);
        document.getElementById('cg-draw').innerHTML = `<div class="cg-draw">
            🎲 예상 추첨 횟수 <span class="big">${draws}회</span>
            <div class="cg-bar"><i style="width:${pct}%"></i></div>
            <div class="sub">${sub}</div>
        </div>`;
    }
    """
    goods_js = goods_js.replace('__CW_DATA__', cw_json)
    goods_js = goods_js.replace('__CG_DATA__', cgf_json)
    goods_js = goods_js.replace('__CAFE_GOODS__', cafe_goods_json)
    goods_js = goods_js.replace('__CAFE_BONUS__', cafe_bonus_json)

    # HTML 생성 (HTML/CSS/JS 부분은 기존과 동일하므로 그대로 유지)
    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light">
    <title>BanG Dream! 한국 오프라인 이벤트 목록</title>

    <script defer src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js'></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script defer src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <style>
        :root {{
            --bg: #f4f6f8;
            --accent: #ff4081;
            --dark: #333;
            --gray: #b0b0b0;
            color-scheme: light;
        }}
        body {{
            margin: 0; padding: 0;
            font-family: 'Pretendard', -apple-system, sans-serif;
            background: var(--bg);
            height: 100vh;
            display: flex;
            overflow: hidden;
            color: var(--dark);
        }}
        body.modal-open {{ overflow: hidden !important; }}
        body.modal-open #site-nav {{ display: none; }}
        .btn-super-main {{ word-break: keep-all; }}
        :focus-visible {{ outline: 3px solid #1a73e8; outline-offset: 2px; }}

        .left-panel {{
            width: 50%;
            padding: 25px;
            background: #fff;
            border-right: 1px solid #e0e0e0;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            z-index: 10;
            min-width: 0;
        }}

        h1.page-title {{
            font-size: 1.8rem;
            margin: 0 0 18px 0;
            color: var(--accent);
            font-weight: 800;
            text-align: center;
            flex-shrink: 0;
            word-break: keep-all;
        }}

        .tab-bar {{
            display: flex;
            gap: 8px;
            margin-bottom: 18px;
            flex-shrink: 0;
        }}
        .tab-btn {{
            flex: 1;
            padding: 12px 10px;
            border: 2px solid #eee;
            background: #fafafa;
            color: #666;
            font-size: 1rem;
            font-weight: 700;
            border-radius: 10px;
            cursor: pointer;
            transition: 0.2s;
        }}
        .tab-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
        .tab-btn.active {{
            background: var(--accent);
            border-color: var(--accent);
            color: #fff;
            box-shadow: 0 4px 10px rgba(233, 30, 99, 0.2);
        }}

        .card-list-container {{
            flex: 1;
            overflow-y: auto;
            padding-right: 5px;
        }}

        #card-list {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }}

        .footer-credits {{
            text-align: center;
            font-size: 0.8rem;
            color: #666;
            padding-top: 20px;
            margin-top: auto;
            font-weight: 500;
            line-height: 1.4;
            font-family: 'Courier New', monospace;
        }}

        .event-card {{
            background: #ffffff;
            border: 1px solid #eee;
            border-radius: 12px;
            padding: 15px;
            cursor: pointer;
            transition: all 0.2s ease;
            position: relative;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-width: 0;
        }}
        .event-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.08);
            border-color: var(--accent);
        }}
        .event-card:focus-visible {{ outline: 3px solid #1a73e8; outline-offset: 2px; }}
        .event-card.active {{
            border: 2px solid var(--accent);
            background: #fff0f5;
        }}

        .card-badge {{
            align-self: flex-start; display: inline-block; margin-bottom: 7px;
            padding: 2px 9px; border-radius: 999px; font-size: 0.75rem; font-weight: 800;
            background: #eef1f5; color: #4a5568;
        }}
        .card-badge.live {{ background: #e6f9ee; color: #12803f; }}
        .card-badge.soon {{ background: #fff0f5; color: #c2185b; }}
        .card-title {{ font-size: 1.1rem; font-weight: 700; margin-bottom: 8px; word-break: keep-all; overflow-wrap: anywhere; }}
        .card-date {{ font-size: 0.85rem; color: #666; margin-bottom: 5px; }}
        .card-loc {{ font-size: 0.85rem; color: #555; font-weight: 500; overflow-wrap: anywhere; }}

        .right-panel {{
            width: 50%;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }}

        .top-calendar {{
            height: 38%;
            padding: 20px;
            background: #fff;
            border-bottom: 1px solid #ddd;
            overflow: hidden;
            box-sizing: border-box;
            min-height: 300px;
        }}
        .fc .fc-toolbar-title {{ white-space: nowrap; }}
        /* 칸이 낮아도 이벤트 막대가 들어가도록 날짜 숫자를 작게 */
        .fc .fc-daygrid-day-number {{ padding: 1px 4px; font-size: 0.78rem; }}
        .fc .fc-daygrid-day-top {{ line-height: 1.2; }}
        .fc .fc-daygrid-event {{ font-size: 0.72rem; }}
        .fc .fc-daygrid-day-events {{ margin-bottom: 1px; }}

        .bottom-container {{
            height: 62%;
            display: grid;
            grid-template-columns: 1fr 1fr;
            background: #fff;
            min-height: 0;
        }}

        .info-area {{
            min-width: 0;
            padding: 25px;
            box-sizing: border-box;
            border-right: 1px solid #eee;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            background: #fcfcfc;
        }}

        .map-area {{
            position: relative;
            min-width: 0;
            min-height: 0;
        }}
        #map {{ width: 100%; height: 100%; z-index: 1; }}

        .panel-header {{ font-size: 1.4rem; font-weight: 800; margin-bottom: 8px; color: var(--accent); line-height: 1.2; word-break: keep-all; overflow-wrap: anywhere; flex: 0 0 auto; }}
        .panel-meta {{ font-size: 0.88rem; color: #555; margin-bottom: 14px; line-height: 1.5; flex: 0 0 auto; overflow-wrap: anywhere; }}
        .empty-msg {{ color: #666; text-align: center; margin-top: 50px; line-height: 1.6; }}

        .btn-group {{ display: flex; flex-direction: column; gap: 8px; margin: 6px 0 4px; flex: 0 0 auto; }}
        .btn {{
            padding: 10px 14px; border-radius: 8px; text-decoration: none;
            font-size: 0.9rem; font-weight: 600; color: white; border: none; cursor: pointer;
            display: flex; align-items: center; justify-content: space-between; transition: 0.2s;
        }}
        .btn:hover {{ opacity: 0.9; transform: translateX(3px); }}
        .btn-naver {{ background-color: #03C75A; }}
        .btn-zoom {{ background-color: #fff; color: #c2185b; border: 1.5px solid #ffc1d9; font-family: inherit; text-align: left; }}
        .btn-kakao {{ background-color: #FEE500; color: #191919; }}

        .note-text {{ font-size: 0.9rem; background: #fff3cd; color: #856404; padding: 12px; border-radius: 8px; margin-bottom: 15px; overflow-wrap: anywhere; }}

        /* 비고를 【머리말】 단위로 쪼개 카드로 표시 (양일 행사 토/일 구분용) */
        /* .info-area 가 flex column 이라 flex:none 이 없으면 카드가 찌부러진다 */
        .note-text, .note-sec {{ flex: 0 0 auto; }}
        .note-sec {{ margin-bottom: 10px; border-radius: 10px; overflow: hidden; border: 1px solid #ffe08a; background: #fffdf5; }}
        .note-sec > h4 {{
            margin: 0; padding: 7px 12px; font-size: 0.86rem; font-weight: 700;
            background: #ffe9a8; color: #7a5b00; letter-spacing: -0.2px;
        }}
        .note-sec > ul {{ margin: 0; padding: 9px 12px 10px 28px; }}
        .note-sec > ul > li {{ font-size: 0.84rem; line-height: 1.5; color: #5c4a1a; margin-bottom: 4px; overflow-wrap: anywhere; }}
        .note-sec > ul > li:last-child {{ margin-bottom: 0; }}
        .note-sec > ul > li.is-caveat {{ list-style: none; margin-left: -16px; color: #7a6a3e; font-size: 0.78rem; }}
        .note-sec .note-time {{ font-weight: 700; color: #d1477a; }}
        .note-sec.is-sat {{ border-color: #b9d8ff; background: #f7fbff; }}
        .note-sec.is-sat > h4 {{ background: #d6e9ff; color: #14508f; }}
        .note-sec.is-sat > ul > li {{ color: #2b4a6b; }}
        .note-sec.is-sun {{ border-color: #ffc2d8; background: #fff8fb; }}
        .note-sec.is-sun > h4 {{ background: #ffd6e6; color: #a12057; }}
        .note-sec.is-sun > ul > li {{ color: #6b2b46; }}
        .note-sec.is-shop {{ border-color: #cfe8d5; background: #f7fcf8; }}
        .note-sec.is-shop > h4 {{ background: #d9f0e0; color: #1d6b3a; }}
        .note-sec.is-shop > ul > li {{ color: #2c5c3d; }}

        .link-block {{ flex: 0 0 auto; margin-bottom: 14px; display: flex; flex-direction: column; gap: 8px; }}
        .goods-block {{ flex: 0 0 auto; margin-bottom: 14px; }}
        .btn-super-main {{
            display: block; width: 100%; box-sizing: border-box; text-align: center;
            background: linear-gradient(135deg, #ff4081, #ff80ab); color: white;
            font-size: 1.1rem; font-weight: bold; padding: 15px;
            border-radius: 12px; margin-top: 0; border: none; cursor: pointer; font-family: inherit;
            text-decoration: none; box-shadow: 0 4px 10px rgba(233, 30, 99, 0.2);
            transition: 0.2s;
            flex: 0 0 auto;
        }}
        .btn-super-main.btn-mini {{
            font-size: 0.85rem; font-weight: 600; padding: 9px 12px; border-radius: 9px;
            text-align: left; box-shadow: none;
            background: #fff; color: #d81b60; border: 1.5px solid #ffc1d9;
        }}
        .btn-super-main.btn-mini:hover {{ background: #fff2f7; }}
        .img-chip-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
        .img-chip-head {{ font-size: 0.75rem; font-weight: 700; color: #8a5a6e; margin-right: 2px; }}
        .img-chip {{
            font-size: 0.75rem; font-weight: 600; padding: 4px 9px; border-radius: 999px;
            text-decoration: none; color: #8a5a6e; background: #fff;
            border: 1px solid #f0cfdd; line-height: 1.5;
        }}
        .img-chip:hover {{ background: #fff2f7; color: #d81b60; }}
        .btn-super-main:hover {{ transform: translateY(-2px); box-shadow: 0 6px 15px rgba(233, 30, 99, 0.3); }}
        .btn-ticket {{ background: linear-gradient(135deg, #00cd3c, #21d35d); box-shadow: 0 4px 10px rgba(0, 205, 60, 0.25); }}
        .btn-ticket:hover {{ box-shadow: 0 6px 15px rgba(0, 205, 60, 0.35); }}

        @media (max-width: 900px) {{
            body {{ display: block; height: auto; overflow-x: hidden; overflow-y: auto; }}
            .left-panel, .right-panel {{ width: 100%; height: auto; }}
            /* nav.js 우측 고정 메뉴 버튼(약 30px)과 카드가 겹치지 않게 오른쪽 여백 확보 */
            .left-panel {{ height: auto; padding: 18px 44px 18px 16px; border-right: none; border-bottom: 5px solid #eee; }}
            h1.page-title {{ font-size: 1.4rem; margin-bottom: 14px; }}
            .card-list-container {{ flex: none; max-height: 60vh; overscroll-behavior: contain; }}
            #card-list {{ grid-template-columns: 1fr; gap: 12px; }}
            .footer-credits {{ padding-top: 14px; }}
            .top-calendar {{ height: auto !important; min-height: 0; overflow: visible !important; padding: 14px 12px; }}
            .top-calendar .fc-scroller, .top-calendar .fc-view-harness {{ height: auto !important; overflow: visible !important; }}
            .fc .fc-toolbar-title {{ font-size: 1.1rem; }}
            .fc .fc-button {{ min-height: 40px; min-width: 40px; }}
            .bottom-container {{ display: flex; flex-direction: column; height: auto; }}
            .info-area {{ width: 100%; min-width: 0; height: auto; padding: 18px 16px 18px 16px; border-right: none; border-bottom: 1px solid #ddd; overflow: visible; }}
            .map-area {{ flex: none; height: 400px; margin-bottom: 72px; }}
            .img-chip {{ padding: 8px 12px; }}
        }}
        {extra_css}
    </style>
</head>
<body>

<div class="left-panel">
    <h1 class="page-title" id="page-title">BanG Dream!<br>한국 오프라인 이벤트 목록</h1>
    <div class="tab-bar" role="tablist">
        <button class="tab-btn active" data-tab="korea" role="tab" aria-selected="true" onclick="switchTab('korea')">🇰🇷 국내</button>
        <button class="tab-btn" data-tab="overseas" role="tab" aria-selected="false" onclick="switchTab('overseas')">🌏 해외</button>
    </div>
    <div class="card-list-container" id="card-list-container">
        <div id="card-list"></div>
    </div>
    <div class="footer-credits">
        데이터 업데이트: {current_time_str}<br>
        (접속일 기준 지난 행사는 숨김 처리됨)<br>
        made by Bangbung Kim
    </div>
</div>

<div class="right-panel">
    <div class="top-calendar">
        <div id='calendar'></div>
    </div>
    <div class="bottom-container">
        <div class="info-area" id="info-panel" aria-live="polite">
            <div class="empty-msg">
                왼쪽 목록이나 달력에서 이벤트를 고르면<br>여기에 상세 정보가 나옵니다.
            </div>
        </div>
        <div class="map-area">
            <div id="map"></div>
        </div>
    </div>
</div>

<script>
    const DATASETS = {{ korea: {json_korea}, overseas: {json_overseas} }};
    const TAB_META = {{
        korea:    {{ title: 'BanG Dream!<br>한국 오프라인 이벤트 목록',   center: [37.5665, 126.9780], zoom: 11 }},
        overseas: {{ title: 'BanG Dream!<br>해외 오프라인 이벤트 목록',   center: [35.6812, 139.7671], zoom: 4 }}
    }};
    const EMPTY_INFO = '<div class="empty-msg">왼쪽 목록이나 달력에서 이벤트를 고르면<br>여기에 상세 정보가 나옵니다.</div>';
    const CAL_BG = '#e4e4e4', CAL_TEXT = '#444', CAL_SEL = '#ff4081';

    let currentTab = 'korea';
    let rawEvents = DATASETS[currentTab];
    let events = [];
    let map = null;
    let calendar = null;
    let markers = [];
    let currentEvt = null;

    const mq = window.matchMedia('(max-width: 900px)');
    const isMobile = () => mq.matches;

    // innerHTML 에 넣는 모든 데이터는 이걸 거친다
    function esc(v) {{
        return String(v == null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }}
    // href 는 http(s) 만 허용
    function safeUrl(u) {{
        const s = String(u || '').trim();
        return /^https?:\/\//i.test(s) ? esc(s) : '#';
    }}
    const EXT = 'target="_blank" rel="noopener noreferrer"';

    function calToolbar() {{
        return isMobile()
            ? {{ left: 'prev', center: 'title', right: 'next' }}
            : {{ left: 'prev,next today', center: 'title', right: '' }};
    }}

    document.addEventListener('DOMContentLoaded', function() {{
        filterEventsByCurrentDate();
        // 카드 목록을 먼저 그린다 (지도/캘린더 CDN 이 실패해도 목록은 보이게)
        renderCards();

        const meta = TAB_META[currentTab];
        try {{
            map = L.map('map').setView(meta.center, meta.zoom);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                attribution: '© OpenStreetMap'
            }}).addTo(map);
        }} catch (e) {{ console.warn('지도 초기화 실패', e); map = null; }}

        try {{
            const calendarEl = document.getElementById('calendar');
            calendar = new FullCalendar.Calendar(calendarEl, {{
                initialView: 'dayGridMonth',
                height: isMobile() ? 'auto' : '100%',
                headerToolbar: calToolbar(),
                buttonText: {{ today: '오늘' }},
                fixedWeekCount: false,
                stickyHeaderDates: false,
                dayMaxEvents: true,
                eventBackgroundColor: CAL_BG,
                eventBorderColor: CAL_BG,
                eventTextColor: CAL_TEXT,
                events: getAllCalendarEvents(),
                eventClick: function(info) {{
                    selectEvent(parseInt(info.event.id), 'calendar');
                }}
            }});
            calendar.render();
        }} catch (e) {{ console.warn('캘린더 초기화 실패', e); calendar = null; }}

        const onMq = () => {{
            if (calendar) {{
                calendar.setOption('height', isMobile() ? 'auto' : '100%');
                calendar.setOption('headerToolbar', calToolbar());
            }}
            if (map) setTimeout(() => map.invalidateSize(), 100);
        }};
        if (mq.addEventListener) mq.addEventListener('change', onMq); else mq.addListener(onMq);
        const fixMap = () => {{ if (map) setTimeout(() => map.invalidateSize(), 200); }};
        window.addEventListener('resize', fixMap);
        window.addEventListener('orientationchange', fixMap);
        window.addEventListener('load', fixMap);
        fixMap();

        // 상세 패널의 지도 버튼: 인덱스로 좌표를 찾는다 (onclick 문자열 삽입 금지)
        document.getElementById('info-panel').addEventListener('click', function(e) {{
            const a = e.target.closest('[data-tidx]');
            if (!a || !currentEvt) return;
            const t = currentEvt.map_targets[+a.dataset.tidx];
            if (t && t.lat && t.lng) zoomToLocation(t.lat, t.lng);
        }});
    }});

    function switchTab(tab) {{
        if (tab === currentTab) return;
        currentTab = tab;
        rawEvents = DATASETS[tab];
        currentEvt = null;

        // 탭 버튼 / 제목 갱신
        document.querySelectorAll('.tab-btn').forEach(b => {{
            const on = b.dataset.tab === tab;
            b.classList.toggle('active', on);
            b.setAttribute('aria-selected', on ? 'true' : 'false');
        }});
        document.getElementById('page-title').innerHTML = TAB_META[tab].title;

        // 데이터 다시 필터링
        filterEventsByCurrentDate();
        renderCards();

        document.getElementById('info-panel').innerHTML = EMPTY_INFO;

        // 마커 초기화 + 지도 기본 위치로
        if (map) {{
            markers.forEach(m => map.removeLayer(m));
            markers = [];
            resetMapView();
            setTimeout(() => map.invalidateSize(), 200);
        }}

        // 캘린더 이벤트 교체
        if (calendar) {{
            calendar.getEvents().forEach(e => e.remove());
            getAllCalendarEvents().forEach(e => calendar.addEvent(e));
        }}
    }}

    function resetMapView() {{
        if (!map) return;
        const meta = TAB_META[currentTab];
        map.setView(meta.center, meta.zoom);
    }}

    function parseDay(s) {{
        const d = new Date(String(s || '') + 'T00:00:00');
        return isNaN(d) ? null : d;
    }}

    function filterEventsByCurrentDate() {{
        const now = new Date();
        now.setHours(0, 0, 0, 0);

        events = rawEvents.filter(evt => {{
            const endDate = parseDay(evt.end) || new Date(evt.end);
            return endDate >= now;
        }});

        console.log(`총 ${{rawEvents.length}}개 중 ${{events.length}}개의 유효 이벤트 로드됨.`);
    }}

    function getAllCalendarEvents() {{
        return events.map(e => ({{
            id: e.id,
            title: e.title,
            start: e.start,
            end: e.cal_end
        }}));
    }}

    // D-n / 진행중 배지
    function dayBadge(evt) {{
        const today = new Date(); today.setHours(0, 0, 0, 0);
        const s = parseDay(evt.start), e = parseDay(evt.end) || s;
        if (!s) return '';
        if (s <= today && today <= e) return '<span class="card-badge live">진행중</span>';
        const n = Math.round((s - today) / 86400000);
        if (n > 0) return `<span class="card-badge${{n <= 7 ? ' soon' : ''}}">D-${{n}}</span>`;
        return '';
    }}

    function renderCards() {{
        const container = document.getElementById('card-list');
        container.innerHTML = '';

        if (events.length === 0) {{
            container.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:24px 12px; color:#666; line-height:1.6;">현재 예정된 이벤트가 없습니다.<br>새 행사가 등록되면 이곳에 표시됩니다.</div>';
            return;
        }}

        events.forEach(evt => {{
            const card = document.createElement('div');
            card.className = 'event-card';
            card.dataset.id = evt.id;
            card.tabIndex = 0;
            card.setAttribute('role', 'button');
            card.setAttribute('aria-label', `${{evt.title}} 상세 보기`);
            card.onclick = () => selectEvent(evt.id, 'card');
            card.onkeydown = (e) => {{
                if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); selectEvent(evt.id, 'card'); }}
            }};
            card.innerHTML = `
                ${{dayBadge(evt)}}
                <div class="card-title">${{esc(evt.title)}}</div>
                <div class="card-date">🗓️ ${{esc(evt.start)}} ~ ${{esc(evt.end)}}</div>
                <div class="card-loc">📍 ${{esc(evt.location_text)}}</div>
            `;
            container.appendChild(card);
        }});
    }}

    // 비고가 "【머리말】 …" 형태면 머리말 단위 카드 + 항목 리스트로 쪼갠다.
    // (양일 개최 행사의 토/일 구분용. 해당 포맷이 아니면 기존 한 덩어리 표시 유지)
    function formatNote(note) {{
        const chunks = note.split('◆◆').map(s => s.trim()).filter(Boolean);
        const secs = [];
        chunks.forEach(chunk => {{
            const m = chunk.match(/^【(.+?)】\s*([\s\S]*)$/);
            if (!m) return;
            secs.push({{ head: m[1].trim(), body: m[2].trim() }});
        }});
        if (!secs.length) return `<div class="note-text">📢 ${{esc(note)}}</div>`;

        return secs.map(sec => {{
            let cls = '';
            if (/\(토\)|토요일/.test(sec.head)) cls = ' is-sat';
            else if (/\(일\)|일요일/.test(sec.head)) cls = ' is-sun';
            else if (sec.head.includes('판매')) cls = ' is-shop';

            const items = sec.body
                .split(/\s\/\s/)
                .map(s => s.trim().replace(/^[·\s]+|[·\s]+$/g, ''))
                .filter(Boolean)
                .map(s => {{
                    const caveat = s.startsWith('※') ? 'is-caveat' : '';
                    // 맨 앞의 시각 표기(12:30~, 10:00, ★15:00~ 등)를 강조
                    const html = esc(s).replace(
                        /^(★?\s*\d{{1,2}}:\d{{2}}\s*~?)/,
                        '<span class="note-time">$1</span>'
                    );
                    return `<li class="${{caveat}}">${{html}}</li>`;
                }})
                .join('');
            return `<div class="note-sec${{cls}}"><h4>${{esc(sec.head)}}</h4><ul>${{items}}</ul></div>`;
        }}).join('');
    }}

    // 카드 목록 안에서 해당 카드가 보이도록
    function revealCard(card) {{
        if (!card) return;
        if (!isMobile()) {{ card.scrollIntoView({{ block: 'nearest' }}); return; }}
        // 모바일: 페이지 전체가 튀지 않도록 목록 컨테이너만 스크롤
        const box = document.getElementById('card-list-container');
        const top = card.offsetTop - box.offsetTop;
        if (top < box.scrollTop) box.scrollTop = top;
        else if (top + card.offsetHeight > box.scrollTop + box.clientHeight)
            box.scrollTop = top + card.offsetHeight - box.clientHeight;
    }}

    function selectEvent(id, from) {{
        const evt = events.find(e => e.id === id);
        if (!evt) return;
        currentEvt = evt;

        document.querySelectorAll('.event-card').forEach(c => c.classList.remove('active'));
        const card = document.querySelector(`.event-card[data-id="${{id}}"]`);
        if (card) {{
            card.classList.add('active');
            if (from !== 'card') revealCard(card);
        }}

        if (calendar) {{
            calendar.getEvents().forEach(calEvt => {{
                const sel = parseInt(calEvt.id) === id;
                calEvt.setProp('backgroundColor', sel ? CAL_SEL : CAL_BG);
                calEvt.setProp('borderColor', sel ? CAL_SEL : CAL_BG);
                calEvt.setProp('textColor', sel ? '#fff' : CAL_TEXT);
            }});
            if (from !== 'calendar') calendar.gotoDate(evt.start);
        }}

        if (map) {{
            markers.forEach(m => map.removeLayer(m));
            markers = [];
            let bounds = L.latLngBounds();
            let hasCoords = false;

            evt.map_targets.forEach(target => {{
                if (target.lat && target.lng) {{
                    const marker = L.marker([target.lat, target.lng]).addTo(map);
                    marker.bindPopup(`<b>${{esc(target.name)}}</b>`);
                    marker.on('click', () => revealCard(document.querySelector(`.event-card[data-id="${{id}}"]`)));
                    markers.push(marker);
                    bounds.extend([target.lat, target.lng]);
                    hasCoords = true;
                }}
            }});

            setTimeout(() => {{
                map.invalidateSize();
                if (hasCoords) {{
                    map.fitBounds(bounds, {{ padding: [50, 50], maxZoom: 14 }});
                }} else {{
                    resetMapView();
                }}
            }}, 200);
        }}

        const panel = document.getElementById('info-panel');

        // 지도 버튼 (맨 아래)
        let btnsHtml = '';
        evt.map_targets.forEach((target, ti) => {{
            if (target.lat && target.lng) {{
                btnsHtml += `<button type="button" class="btn btn-zoom" data-tidx="${{ti}}"><span>📍 ${{esc(target.name)}} 지도에서 보기</span></button>`;
            }}
            if (target.n_link) {{
                btnsHtml += `<a href="${{safeUrl(target.n_link)}}" ${{EXT}} class="btn btn-naver"><span>N 네이버지도 (${{esc(target.name)}})</span> <span aria-hidden="true">➚</span></a>`;
            }}
            if (target.k_link) {{
                btnsHtml += `<a href="${{safeUrl(target.k_link)}}" ${{EXT}} class="btn btn-kakao"><span>K 카카오맵 (${{esc(target.name)}})</span> <span aria-hidden="true">➚</span></a>`;
            }}
        }});
        if (btnsHtml) btnsHtml = `<div class="btn-group">${{btnsHtml}}</div>`;

        let noteHtml = evt.note ? formatNote(evt.note) : '';
        let goodsBtnHtml = evt.has_goods
            ? `<button type="button" onclick="openGoodsModal()" class="btn-super-main" style="background:linear-gradient(135deg,#7b4fff,#a17bff);">🛒 굿즈 · 메뉴 계산기 열기</button>`
            : '';
        if (evt.has_cgf) {{
            goodsBtnHtml = `<button type="button" onclick="openCgModal()" class="btn-super-main" style="background:linear-gradient(135deg,#38b6ff,#b39bff 55%,#ff7fc4);">🛸 무겐다이 뮤타입 물판 · 사인회 추첨 계산기</button>`;
        }}
        if (evt.has_cw) {{
            goodsBtnHtml = `<button type="button" onclick="openCwModal()" class="btn-super-main" style="background:linear-gradient(135deg,#6a5cff,#c07bff 55%,#ff8ad1);">🎪 부스 굿즈 · 현장 이벤트 가이드 (ZA02)</button>`;
        }}
        if (goodsBtnHtml) goodsBtnHtml = `<div class="goods-block">${{goodsBtnHtml}}</div>`;

        // "공지 이미지 N" 류는 본 버튼이 아니라 곁다리이므로 따로 모아 작은 칩으로 한 줄에 깐다
        const isImgLink = m => /^공지 이미지/.test(m.label || '');
        const normalLinks = (evt.main_links || []).filter(m => !isImgLink(m));
        const imgLinks = (evt.main_links || []).filter(isImgLink);
        // 링크가 많은 행사는 버튼을 작게(btn-mini) — 안 그러면 버튼 벽이 된다
        const manyLinks = normalLinks.length > 3;
        let ticketHtml = (evt.ticket_links || []).map(m => {{
            const label = m.label ? `🎟️ ${{esc(m.label)}} 예매하러 가기` : '🎟️ 예매하러 가기';
            return `<a href="${{safeUrl(m.url)}}" ${{EXT}} class="btn btn-super-main btn-ticket">${{label}}</a>`;
        }}).join('');
        let mainLinkHtml = normalLinks.map(m => {{
            const label = m.label ? `👉 ${{esc(m.label)}}` : '👉 통합 정보 확인하기';
            const mini = manyLinks ? ' btn-mini' : '';
            return `<a href="${{safeUrl(m.url)}}" ${{EXT}} class="btn btn-super-main${{mini}}">${{label}}</a>`;
        }}).join('');
        if (imgLinks.length) {{
            mainLinkHtml += `<div class="img-chip-row">`
                + `<span class="img-chip-head">🖼 공식 공지 원본 이미지</span>`
                + imgLinks.map((m, i) => {{
                    const n = (m.label.match(/\d+/) || [i + 1])[0];
                    return `<a href="${{safeUrl(m.url)}}" ${{EXT}} class="img-chip" title="${{esc(m.label)}} 원본 열기 (X 로그인 불필요)">${{esc(n)}}번째</a>`;
                }}).join('') + `</div>`;
        }}
        const linkBlock = (ticketHtml || mainLinkHtml) ? `<div class="link-block">${{ticketHtml}}${{mainLinkHtml}}</div>` : '';

        const dateTxt = evt.start === evt.end ? evt.start : `${{evt.start}} ~ ${{evt.end}}`;
        panel.innerHTML = `
            <div class="panel-header">${{esc(evt.title)}}</div>
            <div class="panel-meta">🗓️ ${{esc(dateTxt)}}<br>📍 ${{esc(evt.location_text)}}</div>
            ${{linkBlock}}
            ${{goodsBtnHtml}}
            ${{noteHtml}}
            ${{btnsHtml}}
        `;
        panel.scrollTop = 0;

        if (from === 'card' && isMobile()) {{
            panel.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
    }}

    function zoomToLocation(lat, lng) {{
        if (!map) return;
        map.flyTo([lat, lng], 17, {{ animate: true, duration: 1.5 }});
    }}
    {goods_js}
</script>
{modal_html}
<script src="nav.js"></script>
</body>
</html>
"""

    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"'{output_filename}' build complete. (data updated: {current_time_str})")

if __name__ == "__main__":
    # 해외(베타)는 별도 폴더의 스크래퍼가 생성한 CSV를 읽는다. 없으면 자동으로 빈 탭.
    generate_final_page('events.csv', '해외오프이벤/events_overseas.csv', 'index.html')