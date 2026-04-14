import pandas as pd
import math
import os
import glob
import xml.etree.ElementTree as ET
import shapefile
from app.models.large_scale.trail import TrailInfo
from app.core.config import settings
from app.core.db import fetch_all
from app.services.large_scale.weather_congestion import fetch_city_data
from app.services.large_scale.slope_service import inject_slope_info
from app.services.large_scale.soil_service import inject_soil_info
from app.services.large_scale.safety_service import inject_safety_tips

# 산책로 CSV는 DB에 없으므로 파일 유지
ABS_DATA_PATH = settings.PET_TRAIL_CSV

# SHP 폴리라인 캐싱 (파일 유지 - 지도 경로선 렌더링용)
shp_cache = {}
try:
    print("Loading SHP data...")
    sf = shapefile.Reader(settings.SHP_DATA_PATH, encoding='euc-kr')
    field_names = [f[0] for f in sf.fields[1:]]
    if 'NAME' in field_names:
        name_idx = field_names.index('NAME')
        for shprec in sf.iterShapeRecords():
            rec = shprec.record
            points = shprec.shape.points
            if len(points) > 0 and len(rec) > name_idx:
                raw_name = rec[name_idx]
                if raw_name:
                    cleaned_name = str(raw_name).strip()
                    lat_lng_points = [[p[1], p[0]] for p in points]
                    shp_cache[cleaned_name] = lat_lng_points
        print(f"SHP data loaded successfully (Cached {len(shp_cache)} tracks).")
    else:
        print("SHP 데이터에 'NAME' 필드가 없습니다.")
except Exception as e:
    print(f"Warning: SHP 데이터를 불러올 수 없습니다. ({e})")

# GPX 폴리라인 캐싱 (파일 유지)
try:
    print("Loading GPX data...")
    gpx_files = glob.glob(os.path.join(settings.GPX_DATA_DIR, "*.gpx"))
    for file_path in gpx_files:
        filename = os.path.basename(file_path).replace(".gpx", "").strip()
        tree = ET.parse(file_path)
        root = tree.getroot()
        points = []
        for elem in root.iter():
            if elem.tag.endswith("trkpt"):
                lat = float(elem.attrib.get('lat', 0))
                lon = float(elem.attrib.get('lon', 0))
                if lat != 0 and lon != 0:
                    points.append([lat, lon])
        if points:
            shp_cache[filename] = points
    print(f"GPX data loaded successfully (Added {len(gpx_files)} tracks).")
except Exception as e:
    print(f"Warning: GPX 데이터를 불러올 수 없습니다. ({e})")


# ── PostgreSQL에서 시설 데이터 로드 (앱 시작 시 1회 캐싱) ──────────────
def _load_facilities_from_db():
    """공원/놀이터/병원/카페 데이터를 DB에서 로드"""

    # park 테이블: geometry는 텍스트라 위도/경도 직접 없음 → 파싱 생략, name만 활용
    parks = fetch_all("SELECT id, name, leisure FROM park WHERE name IS NOT NULL")

    playgrounds = fetch_all("""
        SELECT id, park_name, closed_day, operator, phone, area_sqm,
               night_light, location, usage_fee, operating_hours,
               special_notes, flooring, large_dog_allowed,
               latitude, longitude
        FROM dog_playground
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    hospitals = fetch_all("""
        SELECT id, facility_name, business_status, road_address,
               phone, facility_type, latitude, longitude
        FROM animal_hospital
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    cafes = fetch_all("""
        SELECT id, facility_name, district_name, address, phone,
               operating_hours, closed_day, parking_available,
               pet_size_limit, pet_restrictions, latitude, longitude
        FROM pet_cafe
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    print(f"[DB] 공원 {len(parks)}건, 놀이터 {len(playgrounds)}건, 병원 {len(hospitals)}건, 카페 {len(cafes)}건 로드 완료")
    return parks, playgrounds, hospitals, cafes


# 앱 시작 시 1회 로드
try:
    _db_parks, _db_playgrounds, _db_hospitals, _db_cafes = _load_facilities_from_db()
except Exception as e:
    print(f"[DB] 시설 데이터 로드 실패, 빈 리스트로 폴백: {e}")
    _db_parks, _db_playgrounds, _db_hospitals, _db_cafes = [], [], [], []


def haversine(lat1, lon1, lat2, lon2):
    """두 위경도 좌표점 사이의 직선 거리를 km 단위로 반환"""
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_recommended_trails(user_lat: float, user_lng: float, max_distance_km: float = 20.0,
                           limit: int = 5, view_type: str = "all", use_realtime_api: bool = False):
    """
    사용자 위치(user_lat, user_lng)를 기준으로
    가장 가까운 산책로 및 공원을 최대 limit개까지 추천합니다.
    view_type: "all"(전체), "trail"(산책로만), "park"(공원만), "facility"(시설)
    use_realtime_api: True일 경우 핫스팟 실시간 혼잡도/날씨 데이터 적재
    """
    try:
        df = pd.read_csv(ABS_DATA_PATH)
    except Exception as e:
        print(f"Error loading CSV data: {e}")
        return [], None

    filtered_df = df[df['Pet_AP'] == 1].copy()
    recommendations = []

    # 3-1. 산책로 탐색 (CSV 기반 유지)
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
                    type="trail", trail_id=t_id, trail_name=t_nm,
                    is_pet_allowed=int(row['Pet_AP']),
                    length_km=float(row.get('km', 0)),
                    time_minute=int(row.get('minute', 0)),
                    start_lat=start_lat, start_lng=start_lng,
                    end_lat=float(row.get('TRMNA_YCRD', 0)),
                    end_lng=float(row.get('TRMNA_XCRD', 0)),
                    distance_from_user=round(dist, 2),
                    polyline=matched_polyline
                )
                recommendations.append(trail)

    # 3-2. 공원 탐색 → PostgreSQL park 테이블 사용
    # park 테이블에는 위도/경도가 geometry(text)로 저장되어 있어
    # 기존 CSV 방식을 병행 유지 (geometry 파싱이 복잡한 경우 대비)
    if view_type in ["trail+park", "park"]:
        try:
            park_df = pd.read_csv(settings.PARK_CSV_PATH, encoding="euc-kr")
            for _, row in park_df.iterrows():
                lat = float(row.get('Y좌표(WGS84)', 0))
                lng = float(row.get('X좌표(WGS84)', 0))
                if pd.isna(lat) or pd.isna(lng) or lat == 0 or lng == 0:
                    continue
                dist = haversine(user_lat, user_lng, lat, lng)
                if dist <= max_distance_km:
                    trail = TrailInfo(
                        type="park", trail_id=f"P_{row.get('연번', 0)}",
                        trail_name=str(row.get('공원명', '알수없음')),
                        is_pet_allowed=1, length_km=0.0, time_minute=0,
                        start_lat=lat, start_lng=lng, end_lat=0.0, end_lng=0.0,
                        distance_from_user=round(dist, 2), polyline=None
                    )
                    recommendations.append(trail)
        except Exception as e:
            print(f"Error: 공원 데이터를 불러올 수 없습니다. ({e})")

    # 3-3. 반려견 시설 → PostgreSQL 테이블 사용
    if view_type in ["facility", "all"]:

        # 반려견 놀이터 (dog_playground)
        for row in _db_playgrounds:
            lat = float(row.get('latitude') or 0)
            lng = float(row.get('longitude') or 0)
            if lat == 0 or lng == 0:
                continue
            dist = haversine(user_lat, user_lng, lat, lng)
            if dist <= max_distance_km:
                trail = TrailInfo(
                    type="playground",
                    trail_id=f"PG_{row['id']}",
                    trail_name=str(row.get('park_name', '알수없음')),
                    is_pet_allowed=1, length_km=0.0, time_minute=0,
                    start_lat=lat, start_lng=lng, end_lat=0.0, end_lng=0.0,
                    distance_from_user=round(dist, 2), polyline=None,
                    pg_holidays=str(row['closed_day']) if row.get('closed_day') else None,
                    pg_agency=str(row['operator']) if row.get('operator') else None,
                    pg_phone=str(row['phone']) if row.get('phone') else None,
                    pg_size=str(row['area_sqm']) if row.get('area_sqm') else None,
                    pg_night_light=str(row['night_light']) if row.get('night_light') else None,
                    pg_location=str(row['location']) if row.get('location') else None,
                    pg_fee=str(row['usage_fee']) if row.get('usage_fee') else None,
                    pg_hours=str(row['operating_hours']) if row.get('operating_hours') else None,
                    pg_notes=str(row['special_notes']) if row.get('special_notes') else None,
                    pg_floor=str(row['flooring']) if row.get('flooring') else None,
                    pg_large_dog=str(row['large_dog_allowed']) if row.get('large_dog_allowed') else None,
                )
                recommendations.append(trail)

        # 동물병원 (animal_hospital)
        for row in _db_hospitals:
            lat = float(row.get('latitude') or 0)
            lng = float(row.get('longitude') or 0)
            if lat == 0 or lng == 0:
                continue
            dist = haversine(user_lat, user_lng, lat, lng)
            if dist <= max_distance_km:
                trail = TrailInfo(
                    type="hospital",
                    trail_id=f"HP_{row['id']}",
                    trail_name=str(row.get('facility_name', '알수없음')),
                    is_pet_allowed=1, length_km=0.0, time_minute=0,
                    start_lat=lat, start_lng=lng, end_lat=0.0, end_lng=0.0,
                    distance_from_user=round(dist, 2), polyline=None,
                    pg_location=str(row['road_address']) if row.get('road_address') else None,
                    pg_phone=str(row['phone']) if row.get('phone') else None,
                    pg_notes=str(row['business_status']) if row.get('business_status') else None,
                )
                recommendations.append(trail)

        # 애견카페 (pet_cafe)
        for row in _db_cafes:
            lat = float(row.get('latitude') or 0)
            lng = float(row.get('longitude') or 0)
            if lat == 0 or lng == 0:
                continue
            dist = haversine(user_lat, user_lng, lat, lng)
            if dist <= max_distance_km:
                notes_arr = []
                if row.get('pet_restrictions'):
                    notes_arr.append(f"제한: {row['pet_restrictions']}")
                if row.get('parking_available'):
                    notes_arr.append(f"주차: {row['parking_available']}")
                trail = TrailInfo(
                    type="cafe",
                    trail_id=f"CF_{row['id']}",
                    trail_name=str(row.get('facility_name', '알수없음')),
                    is_pet_allowed=1, length_km=0.0, time_minute=0,
                    start_lat=lat, start_lng=lng, end_lat=0.0, end_lng=0.0,
                    distance_from_user=round(dist, 2), polyline=None,
                    pg_location=str(row['address']) if row.get('address') else None,
                    pg_phone=str(row['phone']) if row.get('phone') else None,
                    pg_hours=str(row['operating_hours']) if row.get('operating_hours') else None,
                    pg_holidays=str(row['closed_day']) if row.get('closed_day') else None,
                    pg_large_dog=str(row['pet_size_limit']) if row.get('pet_size_limit') else None,
                    pg_notes=" / ".join(notes_arr) if notes_arr else None,
                )
                recommendations.append(trail)

    # 4. 거리순 정렬 및 슬라이싱
    recommendations.sort(key=lambda x: x.distance_from_user)
    final_limit_items = recommendations[:limit]

    # 5. 혼잡도/날씨 (서울 실시간 도시데이터 연동)
    weather_info = None
    if use_realtime_api:
        for item in final_limit_items:
            city_data = fetch_city_data(item.trail_name)
            if city_data:
                ppltn_list = city_data.get('LIVE_PPLTN_STTS', [])
                if ppltn_list:
                    item.congestion_lvl = ppltn_list[0].get('AREA_CONGEST_LVL')
                    item.congestion_msg = ppltn_list[0].get('AREA_CONGEST_MSG')
                if not weather_info:
                    # 1) 날씨 정보 (기온, 메시지)
                    weather_list = city_data.get('WEATHER_STTS', [])
                    weather = weather_list[0] if weather_list else {}
                    
                    # 2) 미세먼지 정보 (수치, 메시지)
                    air_list = city_data.get('AIR_QUALITY_STTS', [])
                    air = air_list[0] if air_list else {}

                    temp = weather.get('TEMP')
                    pm10 = air.get('PM10')
                    w_msg = weather.get('WEATHER_MSG', '')
                    a_msg = air.get('AIR_MSG', '')
                    
                    # 메시지 통합
                    full_msg = f"{w_msg} {a_msg}".strip()
                    
                    # 기온이 높을 경우 경고 문구 추가
                    if temp:
                        try:
                            if float(temp) >= 25:
                                full_msg = f"🔥 [고온 주의] 기온이 {temp}℃로 높습니다. 수분 섭취에 유의하세요! {full_msg}"
                        except ValueError:
                            pass

                    if not weather_info:
                        weather_info = {
                            'temp': temp,
                            'pm10': pm10,
                            'msg': full_msg
                        }
        if not weather_info:
            default_data = fetch_city_data("강동구청")
            if default_data:
                # 1) 날씨 정보
                weather_list = default_data.get('WEATHER_STTS', [])
                weather = weather_list[0] if weather_list else {}
                
                # 2) 미세먼지 정보
                air_list = default_data.get('AIR_QUALITY_STTS', [])
                air = air_list[0] if air_list else {}

                temp = weather.get('TEMP')
                pm10 = air.get('PM10')
                w_msg = weather.get('WEATHER_MSG', '')
                a_msg = air.get('AIR_MSG', '')
                
                full_msg = f"{w_msg} {a_msg}".strip()
                
                if temp:
                    try:
                        if float(temp) >= 25:
                            full_msg = f"🔥 [고온 주의] 기온이 {temp}℃로 높습니다. 수분 섭취에 유의하세요! {full_msg}"
                    except ValueError:
                        pass

                weather_info = {
                    'temp': temp,
                    'pm10': pm10,
                    'msg': full_msg
                }

    # 6. 경사도 정보 주입
    inject_slope_info(final_limit_items)

    # 7. 바닥 재질 정보 주입
    inject_soil_info(final_limit_items)

    # 8. 개인화 안전 가이드 주입 (신규)
    weather_temp = weather_info.get('temp') if weather_info else None
    inject_safety_tips(final_limit_items, weather_temp)

    return final_limit_items, weather_info
