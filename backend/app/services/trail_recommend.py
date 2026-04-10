import pandas as pd
import math
import os
import glob
import xml.etree.ElementTree as ET
import shapefile
from app.models.trail import TrailInfo
from app.core.config import settings
from app.services.weather_congestion import fetch_city_data
from app.services.slope_service import inject_slope_info

# 앱 전역 설정에서 데이터 경로 가져오기
ABS_DATA_PATH = settings.PET_TRAIL_CSV

# SHP 폴리라인 데이터를 메모리에 캐싱하여 렌더링 성능 최적화
shp_cache = {}
try:
    print("Loading SHP data...")
    sf = shapefile.Reader(settings.SHP_DATA_PATH, encoding='euc-kr')
    
    # NAME 필드 인덱스를 추출 (sf.fields의 0번은 DeletionFlag이므로 1번부터 시작)
    field_names = [f[0] for f in sf.fields[1:]]
    if 'NAME' in field_names:
        name_idx = field_names.index('NAME')
        
        # Shape과 Record를 동시에 순회
        for shprec in sf.iterShapeRecords():
            rec = shprec.record
            points = shprec.shape.points
            
            if len(points) > 0 and len(rec) > name_idx:
                raw_name = rec[name_idx]
                if raw_name:
                    cleaned_name = str(raw_name).strip()
                    # pyshp의 좌표계는 (경도 x, 위도 y) 이므로 Leaflet 맵용인 [위도 y, 경도 x] 로 스왑
                    lat_lng_points = [[p[1], p[0]] for p in points]
                    shp_cache[cleaned_name] = lat_lng_points
        print(f"SHP data loaded successfully (Cached {len(shp_cache)} tracks).")
    else:
        print("SHP 데이터에 'NAME' 필드가 없습니다.")
except Exception as e:
    print(f"Warning: SHP 데이터를 불러올 수 없습니다. ({e})")

# GPX 폴리라인 데이터 추가 캐싱
try:
    print("Loading GPX data...")
    gpx_files = glob.glob(os.path.join(settings.GPX_DATA_DIR, "*.gpx"))
    for file_path in gpx_files:
        # 파일명에서 .gpx 확장자를 제거한 문자열(예: '1코스-수락산 코스')을 키값으로 사용
        filename = os.path.basename(file_path).replace(".gpx", "").strip()
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        points = []
        for elem in root.iter():
            # 태그 끝이 trkpt(Track Point)인 엘리먼트 추출 (네임스페이스 무시)
            if elem.tag.endswith("trkpt"):
                lat = float(elem.attrib.get('lat', 0))
                lon = float(elem.attrib.get('lon', 0))
                if lat != 0 and lon != 0:
                    points.append([lat, lon])
        if points:
            # SHP와 동일하게 맵핑하여 병합 (이름으로 매칭되므로 구조 변경 없음)
            shp_cache[filename] = points
    print(f"GPX data loaded successfully (Added {len(gpx_files)} tracks).")
except Exception as e:
    print(f"Warning: GPX 데이터를 불러올 수 없습니다. ({e})")

def haversine(lat1, lon1, lat2, lon2):
    """
    두 위경도 좌표점 사이의 직선 거리를 km 단위로 반환
    """
    R = 6371.0 # 지구 반지름 (km)
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def get_recommended_trails(user_lat: float, user_lng: float, max_distance_km: float = 20.0, limit: int = 5, view_type: str = "all", use_realtime_api: bool = False):
    """
    사용자 위치(user_lat, user_lng)를 기준으로
    가장 가까운 산책로 및 공원을 최대 limit개까지 추천합니다.
    view_type: "all"(전체), "trail"(산책로만), "park"(공원만)
    use_realtime_api: True일 경우 핫스팟 실시간 혼잡도/날씨 데이터 적재
    """
    try:
        # 데이터 로드
        df = pd.read_csv(ABS_DATA_PATH)
    except Exception as e:
        print(f"Error loading CSV data: {e}")
        return []

    # 1. 필터링: 반려견 출입 가능 (Pet_AP == 1) 항목 전체 대상
    filtered_df = df[df['Pet_AP'] == 1].copy()

    recommendations = []
    
    # 3-1. 산책로 탐색 (CSV 데이터 기반)
    if view_type in ["trail+park", "trail"]:
        for _, row in filtered_df.iterrows():
            start_lat = float(row.get('PNTM_YCRD', 0))
            start_lng = float(row.get('PNTM_XCRD', 0))
            
            if start_lat == 0 or start_lng == 0:
                continue
                
            dist = haversine(user_lat, user_lng, start_lat, start_lng)
            
            if dist <= max_distance_km:
                t_id = str(row['TRL_ID'])
                t_nm = str(row['TRL_NM']).strip()
                
                matched_polyline = None
                if t_nm in shp_cache:
                    matched_polyline = shp_cache[t_nm]
                else:
                    for shp_name, pts in shp_cache.items():
                        if t_nm in shp_name or shp_name in t_nm:
                            matched_polyline = pts
                            break

                trail = TrailInfo(
                    type="trail",
                    trail_id=t_id,
                    trail_name=t_nm,
                    is_pet_allowed=int(row['Pet_AP']),
                    length_km=float(row.get('km', 0)),
                    time_minute=int(row.get('minute', 0)),
                    start_lat=start_lat,
                    start_lng=start_lng,
                    end_lat=float(row.get('TRMNA_YCRD', 0)),
                    end_lng=float(row.get('TRMNA_XCRD', 0)),
                    distance_from_user=round(dist, 2),
                    polyline=matched_polyline
                )
                recommendations.append(trail)

    # 3-2. 공원 탐색 및 리스트업
    if view_type in ["trail+park", "park"]:
        try:
            park_df = pd.read_csv(settings.PARK_CSV_PATH, encoding="euc-kr")
            filtered_park_df = park_df.copy()
            
            for _, row in filtered_park_df.iterrows():
                lat = float(row.get('Y좌표(WGS84)', 0))
                lng = float(row.get('X좌표(WGS84)', 0))
                
                if pd.isna(lat) or pd.isna(lng) or lat == 0 or lng == 0:
                    continue
                    
                dist = haversine(user_lat, user_lng, lat, lng)
                
                if dist <= max_distance_km:
                    trail = TrailInfo(
                        type="park",
                        trail_id=f"P_{row.get('연번', 0)}",
                        trail_name=str(row.get('공원명', '알수없음')),
                        is_pet_allowed=1,
                        length_km=0.0,
                        time_minute=0,
                        start_lat=lat,
                        start_lng=lng,
                        end_lat=0.0,
                        end_lng=0.0,
                        distance_from_user=round(dist, 2),
                        polyline=None
                    )
                    recommendations.append(trail)
        except Exception as e:
            print(f"Error: 공원 데이터를 불러올 수 없습니다. ({e})")

    # 3-3. 반려견 시설 (놀이터, 병원, 카페) 탐색 및 리스트업
    if view_type == "facility":
        try:
            pg_df = pd.read_csv(settings.PLAYGROUND_CSV_PATH, encoding="utf-8")
            for idx, row in pg_df.iterrows():
                lat = float(row.get('위도', 0))
                lng = float(row.get('경도', 0))
                if pd.isna(lat) or pd.isna(lng) or lat == 0 or lng == 0: continue
                dist = haversine(user_lat, user_lng, lat, lng)
                
                if dist <= max_distance_km:
                    trail = TrailInfo(
                        type="playground", trail_id=f"PG_{idx}", trail_name=str(row.get('공원명', '알수없음')),
                        is_pet_allowed=1, length_km=0.0, time_minute=0, start_lat=lat, start_lng=lng, end_lat=0.0, end_lng=0.0, distance_from_user=round(dist, 2), polyline=None,
                        pg_holidays=str(row.get('휴무일', '')) if pd.notna(row.get('휴무일')) else None,
                        pg_agency=str(row.get('운영기관', '')) if pd.notna(row.get('운영기관')) else None,
                        pg_phone=str(row.get('전화번호', '')) if pd.notna(row.get('전화번호')) else None,
                        pg_size=str(row.get('규모(㎡)', '')) if pd.notna(row.get('규모(㎡)')) else None,
                        pg_night_light=str(row.get('야간조명', '')) if pd.notna(row.get('야간조명')) else None,
                        pg_location=str(row.get('위치', '')) if pd.notna(row.get('위치')) else None,
                        pg_fee=str(row.get('이용요금', '')) if pd.notna(row.get('이용요금')) else None,
                        pg_hours=str(row.get('운영시간', '')) if pd.notna(row.get('운영시간')) else None,
                        pg_notes=str(row.get('특이사항', '')) if pd.notna(row.get('특이사항')) else None,
                        pg_floor=str(row.get('바닥재', '')) if pd.notna(row.get('바닥재')) else None,
                        pg_large_dog=str(row.get('대형견_출입가능', '')) if pd.notna(row.get('대형견_출입가능')) else None,
                    )
                    recommendations.append(trail)
        except Exception as e:
            print(f"Error: 놀이터 데이터를 불러올 수 없습니다. ({e})")

    if view_type in ["all", "facility"]:
        # 동물병원
        try:
            hp_df = pd.read_csv(settings.HOSPITAL_CSV_PATH, encoding="utf-8")
            for idx, row in hp_df.iterrows():
                lat = float(row.get('위도', 0))
                lng = float(row.get('경도', 0))
                if pd.isna(lat) or pd.isna(lng) or lat == 0 or lng == 0: continue
                dist = haversine(user_lat, user_lng, lat, lng)
                
                if dist <= max_distance_km:
                    trail = TrailInfo(
                        type="hospital", trail_id=f"HP_{idx}", trail_name=str(row.get('업소명', '알수없음')),
                        is_pet_allowed=1, length_km=0.0, time_minute=0, start_lat=lat, start_lng=lng, end_lat=0.0, end_lng=0.0, distance_from_user=round(dist, 2), polyline=None,
                        pg_location=str(row.get('도로명주소', '')) if pd.notna(row.get('도로명주소')) else str(row.get('지번주소', '')),
                        pg_phone=str(row.get('전화번호', '')) if pd.notna(row.get('전화번호')) else None,
                        pg_notes=str(row.get('영업상태', '')) if pd.notna(row.get('영업상태')) else None
                    )
                    recommendations.append(trail)
        except Exception as e:
            print(f"Error: 동물병원 데이터를 불러올 수 없습니다. ({e})")

        # 애견동반 카페
        try:
            cf_df = pd.read_csv(settings.CAFE_CSV_PATH, encoding="utf-8")
            for idx, row in cf_df.iterrows():
                lat = float(row.get('위도', 0))
                lng = float(row.get('경도', 0))
                if pd.isna(lat) or pd.isna(lng) or lat == 0 or lng == 0: continue
                dist = haversine(user_lat, user_lng, lat, lng)
                
                if dist <= max_distance_km:
                    notes_arr = []
                    if pd.notna(row.get('반려견 제한사항')): notes_arr.append(f"제한: {row.get('반려견 제한사항')}")
                    if pd.notna(row.get('주차(가능) 여부')): notes_arr.append(f"주차: {row.get('주차(가능) 여부')}")
                    
                    trail = TrailInfo(
                        type="cafe", trail_id=f"CF_{idx}", trail_name=str(row.get('시설명', '알수없음')),
                        is_pet_allowed=1, length_km=0.0, time_minute=0, start_lat=lat, start_lng=lng, end_lat=0.0, end_lng=0.0, distance_from_user=round(dist, 2), polyline=None,
                        pg_location=str(row.get('도로명주소', '')) if pd.notna(row.get('도로명주소')) else None,
                        pg_phone=str(row.get('전화번호', '')) if pd.notna(row.get('전화번호')) else None,
                        pg_hours=str(row.get('운영시간', '')) if pd.notna(row.get('운영시간')) else None,
                        pg_holidays=str(row.get('휴무일', '')) if pd.notna(row.get('휴무일')) else None,
                        pg_large_dog=str(row.get('동반 가능 크기', '')) if pd.notna(row.get('동반 가능 크기')) else None,
                        pg_notes=" / ".join(notes_arr) if notes_arr else None
                    )
                    recommendations.append(trail)
        except Exception as e:
            print(f"Error: 애견카페 데이터를 불러올 수 없습니다. ({e})")

    # 4. 사용자와 가까운 순서대로 정렬 및 슬라이싱
    recommendations.sort(key=lambda x: x.distance_from_user)
    final_limit_items = recommendations[:limit]
    
    # 5. 혼잡도와 날씨 정보 채우기 (서울 실시간 도시데이터 연동)
    weather_info = None
    
    if use_realtime_api:
        for item in final_limit_items:
            city_data = fetch_city_data(item.trail_name)
            if city_data:
                # 핫스팟 일치 시 혼잡도 저장
                ppltn_list = city_data.get('LIVE_PPLTN_STTS', [])
                if ppltn_list:
                    item.congestion_lvl = ppltn_list[0].get('AREA_CONGEST_LVL')
                    item.congestion_msg = ppltn_list[0].get('AREA_CONGEST_MSG')
                
                # 날씨 정보 캡처 (모든 장소의 날씨가 비슷하므로 가장 처음 한 곳만 추출하여 공유)
                if not weather_info:
                    weather_list = city_data.get('WEATHER_STTS', [])
                    if weather_list:
                        weather = weather_list[0]
                        weather_info = {
                            'temp': weather.get('TEMP'),
                            'pm10': weather.get('PM10'),
                            'msg': weather.get('WEATHER_MSG')
                        }
        
        # 추천지가 핫스팟이 아니어서 날씨를 못 얻은 경우 강동구의 주요 지점 "강동구청"으로 디폴트 날씨 로드 
        if not weather_info:
            default_data = fetch_city_data("강동구청")
            if default_data:
                weather_list = default_data.get('WEATHER_STTS', [])
                if weather_list:
                    weather = weather_list[0]
                    weather_info = {
                        'temp': weather.get('TEMP'),
                        'pm10': weather.get('PM10'),
                        'msg': weather.get('WEATHER_MSG')
                    }
    
    # 6. 경사도 정보 주입 (모듈화된 함수 호출 - 성능 이슈 시 이 라인만 제거 가능)
    inject_slope_info(final_limit_items)
    
    return final_limit_items, weather_info

