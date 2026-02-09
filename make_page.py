import csv
import json
from datetime import datetime, timedelta

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
        
        # [정렬 로직] '종료기간' 열을 기준으로 정렬
        raw_rows.sort(key=lambda x: x.get('종료기간', '9999-12-31').strip())

    except FileNotFoundError:
        print("오류: CSV 파일을 찾을 수 없습니다.")
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
        def safe_json_load(text):
            if not text or text.strip() == '': return []
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return []

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
            n_link = naver_links[i] if i < len(naver_links) else ''
            k_link = kakao_links[i] if i < len(kakao_links) else ''

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
            'note': note
        })

    # JSON 데이터 생성
    json_data = json.dumps(events_data, ensure_ascii=False)

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
        let mainLinkHtml = evt.main_link ? `<a href="${{evt.main_link}}" target="_blank" class="btn btn-super-main">👉 통합 정보 확인하기</a>` : '';

        panel.innerHTML = `
            <div class="panel-header">${{evt.title}}</div>
            ${{noteHtml}}
            ${{btnsHtml}}
            ${{mainLinkHtml}}
        `;
    }}

    function zoomToLocation(lat, lng) {{
        map.flyTo([lat, lng], 17, {{ animate: true, duration: 1.5 }});
    }}
</script>
</body>
</html>
"""

    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"'{output_filename}' 생성 완료. (데이터 업데이트 시간: {current_time_str})")

if __name__ == "__main__":
    generate_final_page('events.csv', 'index.html')