import json
import math
import os
import re

from fastapi import APIRouter, Query
from app.models.large_scale.trail import TrailRecommendationRequest, TrailRecommendationResponse, HazardResponse
from app.models.large_scale.weather import WeatherRequest, WeatherResponse
from app.services.large_scale.trail_recommend import get_recommended_trails

router = APIRouter()

@router.post("/recommend", response_model=TrailRecommendationResponse, summary="사용자 위치 기반 산책로 추천")
def recommend_trails(request: TrailRecommendationRequest):
    """
    사용자의 현재 위도(Y)와 경도(X)를 받아서
    반려견 출입이 가능한 강동구 산책로 목록을 가장 가까운 순서대로 반환합니다.
    (추후 경사도, 혼잡도 필터링 변수가 추가될 부분입니다)
    """
    trails, weather_info = get_recommended_trails(
        user_lat=request.user_lat, 
        user_lng=request.user_lng, 
        max_distance_km=request.max_distance_km,
        limit=request.limit,
        view_type=request.view_type,
        use_realtime_api=request.use_realtime_api
    )
    
    return TrailRecommendationResponse(
        items=trails,
        weather_temp=weather_info.get("temp") if weather_info else None,
        weather_pm10=weather_info.get("pm10") if weather_info else None,
        weather_pm25=weather_info.get("pm25") if weather_info else None,
        weather_pm25_index=weather_info.get("pm25_index") if weather_info else None,
        weather_uv_index=weather_info.get("uv_index") if weather_info else None,
        weather_precipitation=weather_info.get("precipitation") if weather_info else None,
        weather_msg=weather_info.get("msg") if weather_info else None,
        count=len(trails)
    )

@router.post("/weather", response_model=WeatherResponse, summary="특정 지역(핫스팟)의 실시간 날씨만 분리 조회")
def get_weather(request: WeatherRequest):
    """
    클라이언트에서 요청한 특정 지역(area_name)의 
    날씨 정보만 따로 추출하여 반환하는 독립된 엔드포인트입니다.
    """
    from app.services.large_scale.weather_congestion import fetch_city_data
    
    weather_info = {}
    city_data = fetch_city_data(request.area_name)
    if city_data:
        weather_list = city_data.get('WEATHER_STTS', [])
        if weather_list:
            weather = weather_list[0]
            weather_info = {
                'temp': weather.get('TEMP'),
                'sensible_temp': weather.get('SENSIBLE_TEMP'),
                'max_temp': weather.get('MAX_TEMP'),
                'min_temp': weather.get('MIN_TEMP'),
                'humidity': weather.get('HUMIDITY'),
                'wind_dirct': weather.get('WIND_DIRCT'),
                'wind_spd': weather.get('WIND_SPD'),
                'precipitation': weather.get('PRECIPITATION'),
                'precpt_type': weather.get('PRECPT_TYPE'),
                'pcp_msg': weather.get('PCP_MSG'),
                'sunrise': weather.get('SUNRISE'),
                'sunset': weather.get('SUNSET'),
                'uv_index_lvl': weather.get('UV_INDEX_LVL'),
                'uv_index': weather.get('UV_INDEX'),
                'uv_msg': weather.get('UV_MSG'),
                'pm25_index': weather.get('PM25_INDEX'),
                'pm25': str(weather.get('PM25')) if weather.get('PM25') is not None else None,
                'pm10_index': weather.get('PM10_INDEX'),
                'pm10': str(weather.get('PM10')) if weather.get('PM10') is not None else None,
                'air_idx': weather.get('AIR_IDX'),
                'air_idx_mvl': str(weather.get('AIR_IDX_MVL')) if weather.get('AIR_IDX_MVL') is not None else None,
                'air_idx_main': weather.get('AIR_IDX_MAIN'),
                'air_msg': weather.get('AIR_MSG'),
                'weather_time': weather.get('WEATHER_TIME'),
                'msg': weather.get('WEATHER_MSG')
            }
            
    return WeatherResponse(**weather_info)

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return radius_km * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _extract_region_tokens(location_hint: str | None):
    if not location_hint:
        return []
    matches = re.findall(r"[가-힣]+(?:특별시|광역시|자치시|자치도|도|시|군|구|동)", location_hint)
    tokens = []
    for token in matches:
        token = token.strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


@router.get("/hazards", response_model=HazardResponse)
def get_hazards(
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
    radius_km: float = Query(default=5.0, gt=0, le=30),
    location_hint: str | None = Query(default=None),
):
    """
    지도에 렌더링할 100건의 캐싱된 돌발정보(TOPIS)와
    실시간 재난문자(행정안전부)를 하이브리드로 병합하여 반환합니다.
    """
    from app.services.large_scale.weather_congestion import fetch_disaster_messages
    from app.core.config import settings
    
    incidents = []
    try:
        json_path = os.path.join(settings.DATA_DIR, "seoul_incidents.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                incidents = json.load(f)
    except Exception as e:
        print(f"Error reading incidents cache: {e}")

    if lat is not None and lng is not None:
        filtered_incidents = []
        for incident in incidents:
            try:
                incident_lat = float(incident.get("lat"))
                incident_lng = float(incident.get("lng"))
            except (TypeError, ValueError):
                continue
            if _haversine_km(lat, lng, incident_lat, incident_lng) <= radius_km:
                filtered_incidents.append(incident)
        incidents = filtered_incidents

    disasters = fetch_disaster_messages()
    region_tokens = _extract_region_tokens(location_hint)
    if region_tokens:
        disasters = [
            msg for msg in disasters
            if any(token in str(msg.get("rcptn_rgn_nm", "")) for token in region_tokens)
        ]

    return HazardResponse(
        incidents=incidents,
        disasters=disasters
    )
