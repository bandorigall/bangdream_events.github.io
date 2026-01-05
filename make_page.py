import csv
import json
from datetime import datetime, timedelta

def generate_final_page(csv_filename, output_filename):
    events_data = []
    # 오늘 날짜 확인 (시간 제외, 날짜만 비교)
    today = datetime.now().date()

    try:
        with open(csv_filename, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for idx, row in enumerate(reader):
                # 1. 기본 데이터 파싱
                title = row.get('이벤트명', '')
                start = row.get('시작기간', '').strip()
                end = row.get('종료기간', '').strip()
                raw_location = row.get('장소', '')
                main_link = row.get('통합정보모음', '')
                note = row.get('비고', '')

                # 2. 날짜 필터링 및 포맷팅
                try:
                    # 문자열을 날짜 객체로 변환
                    end_date_obj = datetime.strptime(end, "%Y-%m-%d").date()
                    
                    # [핵심] 종료일이 오늘보다 이전(과거)이면 데이터에서 제외
                    if end_date_obj < today:
                        continue
                        
                    # FullCalendar용 종료일 계산 (표시일 + 1일)
                    cal_end = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")
                except ValueError:
                    # 날짜 형식이 올바르지 않으면 해당 데이터는 스킵하거나 원본 유지
                    cal_end = end

                # 3. 장소 이름 분리
                loc_names = [x.strip() for x in raw_location.split(',')]

                # 4. 좌표 데이터 처리
                coords = []
                for i in range(1, 4):
                    c_str = row.get(f'좌표{i}', '').strip()
                    if c_str and ',' in c_str:
                        try:
                            lat, lng = map(float, c_str.split(','))
                            coords.append({'lat': lat, 'lng': lng})
                        except:
                            coords.append(None)
                    else:
                        coords.append(None)

                # 5. 지도 타겟 매핑
                map_targets = []
                for i in range(3):
                    loc_name = loc_names[i] if i < len(loc_names) else (loc_names[0] if loc_names else f"장소{i+1}")
                    n_link = row.get(f'네이버지도{"" if i==0 else i+1}', '').strip()
                    k_link = row.get(f'다음지도{"" if i==0 else i+1}', '').strip()
                    coord = coords[i] if i < len(coords) else None

                    if n_link or k_link or coord:
                        map_targets.append({
                            'name': loc_name,
                            'n_link': n_link,
                            'k_link': k_link,
                            'lat': coord['lat'] if coord else None,
                            'lng': coord['lng'] if coord else None
                        })

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

    except FileNotFoundError:
        print("오류: CSV 파일을 찾을 수 없습니다.")
        return

    # Python 데이터를 JSON 문자열로 변환
    json_data = json.dumps(events_data, ensure_ascii=False)

    # HTML 생성 (f-string 사용 시 중괄호 {{ }} 이중 처리 주의)
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
            font-size: 0.85rem;
            color: #999;
            padding-top: 20px;
            margin-top: auto;
            font-weight: 500;
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
    const events = {json_data};
    let map = null;
    let calendar = null;
    let markers = [];

    document.addEventListener('DOMContentLoaded', function() {{
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
        
        // [중요] f-string 내부에서 JS if문 사용 시 중괄호 2개 필수
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
    print(f"'{output_filename}' 생성 완료. 종료된 이벤트가 제외되었습니다.")

if __name__ == "__main__":
    generate_final_page('events.csv', 'index.html')