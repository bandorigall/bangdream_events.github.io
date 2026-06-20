import csv
import json
from datetime import datetime, timedelta
import urllib.parse

def generate_final_page(csv_filename, output_filename):
    events_data = []
    
    # 1. 현재 시간 (생성 시점 기록용)
    now = datetime.now()
    current_time_str = now.strftime("%Y.%m.%d %H:%M:%S")

    raw_rows = []
    try:
        with open(csv_filename, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                raw_rows.append(row)
        
        # [정렬 로직] '시작기간' 열을 기준으로 정렬
        raw_rows.sort(key=lambda x: x.get('시작기간', '9999-12-31').strip())

    except FileNotFoundError:
        print("ERROR: CSV file not found.")
        return

    # 정렬된 데이터를 바탕으로 events_data 생성
    for idx, row in enumerate(raw_rows):
        title = row.get('이벤트명', '')
        start = row.get('시작기간', '').strip()
        end = row.get('종료기간', '').strip()
        raw_location = row.get('장소', '')
        main_link = row.get('통합정보모음', '')
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
            'main_link': main_link,
            'note': note,
            # 콜라보 카페 이벤트에만 굿즈/메뉴 계산기 버튼을 노출
            'has_goods': ('콜라보 카페' in title)
        })

    # JSON 데이터 생성
    json_data = json.dumps(events_data, ensure_ascii=False)

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

    # 추가 CSS (일반 문자열 → 중괄호 그대로 사용)
    extra_css = """
        /* ===== 굿즈 계산기 모달 ===== */
        .gm-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.55); z-index:2000; align-items:center; justify-content:center; padding:20px; box-sizing:border-box; }
        .gm-box { background:#fff; width:min(820px,100%); max-height:90vh; border-radius:16px; overflow:hidden; display:flex; flex-direction:column; box-shadow:0 10px 40px rgba(0,0,0,0.3); }
        .gm-header { display:flex; align-items:center; justify-content:space-between; padding:16px 20px; background:linear-gradient(135deg,#ff4081,#ff80ab); color:#fff; font-weight:800; font-size:1.1rem; }
        .gm-close { background:rgba(255,255,255,0.25); border:none; color:#fff; width:30px; height:30px; border-radius:50%; font-size:1rem; cursor:pointer; }
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
        .gm-empty { color:#aaa; text-align:center; padding:30px 0; font-size:0.85rem; }
        .gm-cart-row { display:flex; align-items:center; gap:6px; padding:7px 0; border-bottom:1px dashed #eee; font-size:0.82rem; }
        .gm-cart-name { flex:1; word-break:keep-all; }
        .gm-qtybox { display:flex; align-items:center; gap:6px; }
        .gm-qtybox button { width:22px; height:22px; border:1px solid #ddd; background:#fff; border-radius:6px; cursor:pointer; font-weight:700; }
        .gm-cart-sub { width:74px; text-align:right; font-weight:600; }
        .gm-total { margin-top:auto; padding-top:14px; font-size:1.05rem; text-align:right; }
        .gm-total b { color:#ff4081; font-size:1.25rem; }
        .gm-bonus-title { margin-top:14px; font-weight:800; font-size:0.9rem; color:#444; }
        .gm-bonus-row { margin-top:8px; padding:9px 11px; border-radius:8px; background:#f1f1f1; color:#999; font-size:0.85rem; }
        .gm-bonus-row.on { background:#fff0f5; color:#d81b60; font-weight:700; }
        .gm-bonus-row.clickable { cursor:pointer; }
        .gm-bonus-row.clickable:hover { outline:2px solid #ff80ab; }
        .gm-bonus-row span { font-weight:400; font-size:0.75rem; color:#b08; }
        .gm-hint { margin-top:8px; font-size:0.78rem; color:#ff8a00; text-align:right; }
        .gm-note { margin-top:12px; font-size:0.72rem; color:#999; line-height:1.4; }
        .gm-lightbox { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.85); z-index:3000; align-items:center; justify-content:center; cursor:zoom-out; padding:20px; }
        .gm-lightbox img { max-width:95%; max-height:95%; border-radius:8px; }
        @media (max-width:680px) { .gm-body { flex-direction:column; } .gm-list { border-right:none; border-bottom:1px solid #eee; } }
    """

    # 모달 HTML
    modal_html = """
<div id="goods-modal" class="gm-overlay" onclick="if(event.target===this)closeGoodsModal()">
  <div class="gm-box">
    <div class="gm-header">
      <span>🛒 콜라보 카페 굿즈 · 메뉴 계산기</span>
      <button class="gm-close" onclick="closeGoodsModal()">✕</button>
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
<div id="gm-lightbox" class="gm-lightbox" onclick="this.style.display='none'"><img id="gm-lightbox-img" alt=""></div>
"""

    # 계산기 JS (일반 문자열)
    goods_js = """
    const CAFE_GOODS = __CAFE_GOODS__;
    const CAFE_BONUS = __CAFE_BONUS__;
    let gmCart = {};

    function openGoodsModal() { buildGoodsList(); renderCart(); document.getElementById('goods-modal').style.display='flex'; }
    function closeGoodsModal() { document.getElementById('goods-modal').style.display='none'; }

    function buildGoodsList() {
        const wrap = document.getElementById('gm-list');
        if (wrap.dataset.built) return;
        const cats = {};
        CAFE_GOODS.forEach(g => { (cats[g.cat] = cats[g.cat] || []).push(g); });
        let html = '';
        for (const c in cats) {
            html += `<div class="gm-cat">${c}</div>`;
            cats[c].forEach(g => {
                const bdayBadge = g.bday
                    ? `<span class="gm-bday-badge" title="돌로리스 생일 특전 대상 (6/26~7/2)">🎂 생일특전${typeof g.bday==='string' ? ' ('+g.bday+')' : ''}</span>`
                    : '';
                html += `<div class="gm-item">
                    <img src="${g.thumb}" class="gm-thumb" onclick="showLightbox('${g.full}')">
                    <div class="gm-info" onclick="addToCart('${g.id}')">
                        <div class="gm-name">${g.name}${bdayBadge}</div>
                        <div class="gm-price">${g.price.toLocaleString()}원</div>
                    </div>
                    <button class="gm-add" onclick="addToCart('${g.id}')">담기</button>
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
                    <span class="gm-cart-name">${g.name}</span>
                    <span class="gm-qtybox">
                        <button onclick="changeQty('${id}',-1)">−</button><b>${q}</b><button onclick="changeQty('${id}',1)">＋</button>
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
            b += `<div class="gm-bonus-row on clickable" onclick="showLightbox('${CAFE_BONUS.coaster}')">🥤 메뉴 구매 특전 코스터 <b>${menuQty}장</b> <span>(메뉴 1개당 1장 · 클릭하여 보기)</span></div>`;
        }

        // 돌로리스 생일 특전 (기간 한정: 2026-06-26 ~ 2026-07-02)
        // 조건: 성배 드링크 / 개연의 만찬 햄버거 구매 시 생일 엽서 증정
        const bdayStart = new Date('2026-06-26T00:00:00');
        const bdayEnd = new Date('2026-07-02T23:59:59');
        const inBday = (new Date() >= bdayStart) && (new Date() <= bdayEnd);
        const hasBday = ids.some(id => CAFE_GOODS.find(x => x.id === id).bday);
        if (hasBday) {
            const bdayTag = inBday ? '증정' : '대상 (기간 외)';
            b += `<div class="gm-bonus-row ${inBday?'on':''} clickable" onclick="showLightbox('${CAFE_BONUS.coaster}')">🎂 돌로리스 생일 엽서 <b>${bdayTag}</b> <span>(6/26~7/2 한정 · 성배 드링크·개연의 만찬 햄버거·돌로리스 굿즈(랜덤굿즈 제외) 구매 시 1장 · 클릭하여 보기)</span></div>`;
        }
        b += `<div class="gm-bonus-row ${card>0?'on':''} clickable" onclick="showLightbox('${CAFE_BONUS.postcard_poster}')">🎴 홀로그램 엽서 <b>${card}장</b> <span>(4만원당 1장 · 클릭하여 보기)</span></div>`;
        b += `<div class="gm-bonus-row ${poster>0?'on':''} clickable" onclick="showLightbox('${CAFE_BONUS.postcard_poster}')">🖼️ A3 펄 포스터 <b>${poster}장</b> <span>(8만원당 1장 · 클릭하여 보기)</span></div>`;
        if (total > 0 && total % 40000 !== 0) {
            b += `<div class="gm-hint">${(40000-(total%40000)).toLocaleString()}원 더 담으면 엽서 1장 추가</div>`;
        }
        b += `<div class="gm-note">※ 코스터는 1~2주차 MyGO!!!!! / 3~4주차 Ave Mujica 전 6종 중 랜덤. 엽서·포스터는 굿즈+메뉴 합산 결제금액 기준 랜덤 증정. 돌로리스 생일 엽서(6/26~7/2)는 성배 드링크·햄버거 외 돌로리스 굿즈(랜덤굿즈 제외) 구매 시에도 증정.</div>`;
        document.getElementById('gm-bonus').innerHTML = b;
    }

    function showLightbox(src) {
        document.getElementById('gm-lightbox-img').src = src;
        document.getElementById('gm-lightbox').style.display = 'flex';
    }
    """
    goods_js = goods_js.replace('__CAFE_GOODS__', cafe_goods_json)
    goods_js = goods_js.replace('__CAFE_BONUS__', cafe_bonus_json)

    # HTML 생성 (HTML/CSS/JS 부분은 기존과 동일하므로 그대로 유지)
    html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BanG Dream! 한국 오프라인 이벤트 목록</title>
    
    <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js'></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <style>
        :root {{ 
            --bg: #f4f6f8; 
            --accent: #ff4081; 
            --dark: #333; 
            --gray: #b0b0b0;
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
        
        .left-panel {{ 
            width: 50%; 
            padding: 25px; 
            background: #fff; 
            border-right: 1px solid #e0e0e0; 
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            z-index: 10;
        }}
        
        h1.page-title {{ 
            font-size: 1.8rem; 
            margin: 0 0 25px 0; 
            color: var(--accent); 
            font-weight: 800; 
            text-align: center; 
            flex-shrink: 0; 
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
            color: #999;
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
        }}
        .event-card:hover {{ 
            transform: translateY(-3px); 
            box-shadow: 0 5px 15px rgba(0,0,0,0.08); 
            border-color: var(--accent); 
        }}
        .event-card.active {{ 
            border: 2px solid var(--accent); 
            background: #fff0f5; 
        }}
        
        .card-title {{ font-size: 1.1rem; font-weight: 700; margin-bottom: 8px; word-break: keep-all; }}
        .card-date {{ font-size: 0.85rem; color: #666; margin-bottom: 5px; }}
        .card-loc {{ font-size: 0.85rem; color: #555; font-weight: 500; }}

        .right-panel {{ 
            width: 50%; 
            display: flex; 
            flex-direction: column; 
        }}
        
        .top-calendar {{ 
            height: 45%; 
            padding: 20px; 
            background: #fff; 
            border-bottom: 1px solid #ddd; 
            overflow: hidden;
        }}
        
        .bottom-container {{ 
            height: 55%; 
            display: flex; 
            background: #fff; 
        }}

        .info-area {{
            width: 340px; 
            min-width: 300px; 
            padding: 25px;
            border-right: 1px solid #eee; 
            overflow-y: auto;
            display: flex; 
            flex-direction: column; 
            background: #fcfcfc;
        }}
        
        .map-area {{ 
            flex: 1; 
            position: relative; 
        }}
        #map {{ width: 100%; height: 100%; z-index: 1; }}

        .panel-header {{ font-size: 1.4rem; font-weight: 800; margin-bottom: 15px; color: var(--accent); line-height: 1.2; }}
        .empty-msg {{ color: #999; text-align: center; margin-top: 50px; }}
        
        .btn-group {{ display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }}
        .btn {{ 
            padding: 10px 14px; border-radius: 8px; text-decoration: none; 
            font-size: 0.9rem; font-weight: 600; color: white; border: none; cursor: pointer;
            display: flex; align-items: center; justify-content: space-between; transition: 0.2s;
        }}
        .btn:hover {{ opacity: 0.9; transform: translateX(3px); }}
        .btn-naver {{ background-color: #03C75A; }}
        .btn-kakao {{ background-color: #FEE500; color: #191919; }}
        
        .note-text {{ font-size: 0.9rem; background: #fff3cd; color: #856404; padding: 12px; border-radius: 8px; margin-bottom: 15px; }}
        
        .btn-super-main {{
            display: block; width: 100%; box-sizing: border-box; text-align: center; 
            background: linear-gradient(135deg, #ff4081, #ff80ab); color: white;
            font-size: 1.1rem; font-weight: bold; padding: 15px; 
            border-radius: 12px; margin-top: auto; 
            text-decoration: none; box-shadow: 0 4px 10px rgba(233, 30, 99, 0.2);
            transition: 0.2s;
        }}
        .btn-super-main:hover {{ transform: translateY(-2px); box-shadow: 0 6px 15px rgba(233, 30, 99, 0.3); }}

        @media (max-width: 900px) {{
            body {{ flex-direction: column; overflow: auto; }}
            .left-panel, .right-panel {{ width: 100%; height: auto; }}
            .left-panel {{ height: 500px; border-bottom: 5px solid #eee; }}
            #card-list {{ grid-template-columns: 1fr; }} 
            .bottom-container {{ flex-direction: column; height: auto; }}
            .info-area {{ width: 100%; height: auto; border-right: none; border-bottom: 1px solid #ddd; }}
            .map-area {{ height: 400px; }}
        }}
        {extra_css}
    </style>
</head>
<body>

<div class="left-panel">
    <h1 class="page-title">BanG Dream!<br>한국 오프라인 이벤트 목록</h1>
    <div class="card-list-container">
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
        <div class="info-area" id="info-panel">
            <div class="empty-msg">
                이벤트를 선택하면<br>여기에 상세 정보가 나옵니다!
            </div>
        </div>
        <div class="map-area">
            <div id="map"></div>
        </div>
    </div>
</div>

<script>
    const rawEvents = {json_data};
    let events = [];
    let map = null;
    let calendar = null;
    let markers = [];

    document.addEventListener('DOMContentLoaded', function() {{
        filterEventsByCurrentDate();

        map = L.map('map').setView([37.5665, 126.9780], 11);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap'
        }}).addTo(map);

        const calendarEl = document.getElementById('calendar');
        calendar = new FullCalendar.Calendar(calendarEl, {{
            initialView: 'dayGridMonth',
            height: '100%',
            headerToolbar: {{ left: 'prev,next today', center: 'title', right: '' }},
            events: getAllCalendarEvents(),
            eventClick: function(info) {{
                selectEvent(parseInt(info.event.id));
            }}
        }});
        calendar.render();
        renderCards();
    }});

    function filterEventsByCurrentDate() {{
        const now = new Date();
        now.setHours(0, 0, 0, 0);

        events = rawEvents.filter(evt => {{
            const endDate = new Date(evt.end);
            return endDate >= now;
        }});
        
        console.log(`총 ${{rawEvents.length}}개 중 ${{events.length}}개의 유효 이벤트 로드됨.`);
    }}

    function getAllCalendarEvents() {{
        return events.map(e => ({{
            id: e.id, 
            title: e.title, 
            start: e.start, 
            end: e.cal_end, 
            color: '#d1d1d1'
        }}));
    }}

    function renderCards() {{
        const container = document.getElementById('card-list');
        container.innerHTML = ''; 
        
        if (events.length === 0) {{
            container.innerHTML = '<div style="text-align:center; padding:20px; color:#999;">진행 중인 이벤트가 없습니다.</div>';
            return;
        }}

        events.forEach(evt => {{
            const card = document.createElement('div');
            card.className = 'event-card';
            card.dataset.id = evt.id;
            card.onclick = () => selectEvent(evt.id);
            card.innerHTML = `
                <div class="card-title">${{evt.title}}</div>
                <div class="card-date">🗓️ ${{evt.start}} ~ ${{evt.end}}</div>
                <div class="card-loc">📍 ${{evt.location_text}}</div>
            `;
            container.appendChild(card);
        }});
    }}

    function selectEvent(id) {{
        const evt = events.find(e => e.id === id);
        if (!evt) return;

        document.querySelectorAll('.event-card').forEach(c => c.classList.remove('active'));
        document.querySelector(`.event-card[data-id="${{id}}"]`)?.classList.add('active');

        const allCalEvents = calendar.getEvents();
        allCalEvents.forEach(calEvt => {{
            if (parseInt(calEvt.id) === id) {{
                calEvt.setProp('color', '#ff4081');
            }} else {{
                calEvt.setProp('color', '#d1d1d1');
            }}
        }});
        calendar.gotoDate(evt.start);

        markers.forEach(m => map.removeLayer(m));
        markers = [];
        let bounds = L.latLngBounds();
        let hasCoords = false;

        evt.map_targets.forEach(target => {{
            if (target.lat && target.lng) {{
                const marker = L.marker([target.lat, target.lng]).addTo(map);
                marker.bindPopup(`<b>${{target.name}}</b>`);
                markers.push(marker);
                bounds.extend([target.lat, target.lng]);
                hasCoords = true;
            }}
        }});

        setTimeout(() => {{
            map.invalidateSize();
            if (hasCoords) {{
                map.fitBounds(bounds, {{ padding: [50, 50], maxZoom: 14 }});
            }}
        }}, 100);

        const panel = document.getElementById('info-panel');
        let btnsHtml = '<div class="btn-group">';
        
        evt.map_targets.forEach(target => {{
            const zoomAttr = (target.lat && target.lng) 
                ? `onclick="zoomToLocation(${{target.lat}}, ${{target.lng}})"` 
                : '';
            
            if (target.n_link) {{
                btnsHtml += `<a href="${{target.n_link}}" target="_blank" class="btn btn-naver" ${{zoomAttr}}><span>N 네이버지도 (${{target.name}})</span> <span>➚</span></a>`;
            }}
            
            if (target.k_link) {{
                btnsHtml += `<a href="${{target.k_link}}" target="_blank" class="btn btn-kakao" ${{zoomAttr}}><span>K 카카오맵 (${{target.name}})</span> <span>➚</span></a>`;
            }}
        }});
        btnsHtml += '</div>';

        let noteHtml = evt.note ? `<div class="note-text">📢 ${{evt.note}}</div>` : '';
        let goodsBtnHtml = evt.has_goods
            ? `<button onclick="openGoodsModal()" class="btn-super-main" style="background:linear-gradient(135deg,#7b4fff,#a17bff); margin-top:auto;">🛒 굿즈 · 메뉴 계산기 열기</button>`
            : '';
        let mainLinkHtml = evt.main_link
            ? `<a href="${{evt.main_link}}" target="_blank" class="btn btn-super-main" style="${{evt.has_goods ? 'margin-top:10px;' : ''}}">👉 통합 정보 확인하기</a>`
            : '';

        panel.innerHTML = `
            <div class="panel-header">${{evt.title}}</div>
            ${{noteHtml}}
            ${{btnsHtml}}
            ${{goodsBtnHtml}}
            ${{mainLinkHtml}}
        `;
    }}

    function zoomToLocation(lat, lng) {{
        map.flyTo([lat, lng], 17, {{ animate: true, duration: 1.5 }});
    }}
    {goods_js}
</script>
{modal_html}
</body>
</html>
"""

    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"'{output_filename}' build complete. (data updated: {current_time_str})")

if __name__ == "__main__":
    generate_final_page('events.csv', 'index.html')