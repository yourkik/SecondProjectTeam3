# 반려견 산책로 연동 백엔드 API 명세서

협업하는 프론트엔드/클라이언트 개발자가 참고하실 수 있도록, 새롭게 구성된 `POST` 형태의 주요 API 두 가지에 대해 정리된 문서입니다.

---

## 1. 실시간 날씨 데이터 단독 조회 API

특정 지역(서울 핫스팟/구)에 대한 현재 날씨, 강수량, 미세먼지 수치 등을 단독으로 분리하여 응답받을 수 있는 초경량 API 호출 규격입니다. 화면 우측 하단의 날씨 위젯 등에 유용하게 쓸 수 있습니다.

- **Endpoint**: `POST /api/trails/weather`
- **Content-Type**: `application/json`

### Request (요청 예시)
```json
{
  "area_name": "강동구청" 
}
```
*`area_name`: 서울시 도시데이터 API 기준에 포함된 핫스팟 혹은 "강동구청" 등 대표 관공서 명칭.*

### Response (응답 예시)
```json
{
  "temp": "15.2",
  "sensible_temp": "14.8",
  "max_temp": "18.0",
  "min_temp": "12.0",
  "humidity": "45",
  "wind_dirct": "서북서",
  "wind_spd": "2.4",
  "precipitation": "0.0",
  "precpt_type": "없음",
  "pcp_msg": "강수없음",
  "sunrise": "06:12",
  "sunset": "18:55",
  "uv_index_lvl": "보통",
  "uv_index": "4.5",
  "uv_msg": "보통",
  "pm25_index": "좋음",
  "pm25": "12",
  "pm10_index": "보통",
  "pm10": "38",
  "air_idx": "좋음",
  "air_idx_mvl": "42",
  "air_idx_main": "초미세먼지",
  "air_msg": "공기가 상쾌해요",
  "weather_time": "2026-04-10 12:00",
  "msg": "구름 조금"
}
```

---

## 2. 사용자 위치 기반 장소 추천 API

지도 상에서 탐색된 사용자 좌표 기준으로, 지정한 검색 반경 내에서 가까운 거리의 산책로/공원/애견시설 등을 계산하여 반환합니다.

- **Endpoint**: `POST /api/trails/recommend`
- **Content-Type**: `application/json`

### Request (요청 파라미터)
```json
{
  "user_lat": 37.550,
  "user_lng": 127.150,
  "max_distance_km": 10.0,
  "limit": 15,
  "view_type": "facility",
  "use_realtime_api": false
}
```
- `max_distance_km`: 탐색할 최대 반경(km) (예: 10.0~20.0)
- `limit`: 반환할 최소 결과 개수
- `view_type`: `"trail+park"`(산책로+공원), `"trail"`(산책로만), `"park"`(공원만), `"facility"`(애견시설-병원/놀이터/카페) 중 택 1.
- `use_realtime_api`: 결과 리스트 안에 있는 명칭들 기준으로 혼잡도를 실시간으로 불러와 `TrailInfo` 객체에 붙일 지 여부 (`true` 시 외부 요청 대기 시간 증가).

### Response (응답 예시)
```json
{
  "items": [
    {
      "type": "hospital",
      "trail_id": "HP_45",
      "trail_name": "강동 해랑동물병원",
      "is_pet_allowed": 1,
      "length_km": 0.0,
      "time_minute": 0,
      "start_lat": 37.545,
      "start_lng": 127.145,
      "distance_from_user": 0.52,
      "pg_location": "서울특별시 강동구 성내로 45",
      "pg_phone": "02-1234-5678",
      "pg_notes": "정상영업"
      // 그 외 pg_hours(운영시간), pg_fee(요금), pg_large_dog(대형견출입) 등 선택 필드는 null 표기
    },
    {
      "type": "trail",
      "trail_id": "TRL_12",
      "trail_name": "성내 유수지 산책길",
      "distance_from_user": 1.25
      // ... 산책로 전용 필드 생략 ...
    }
  ],
  "count": 2
}
```
*응답 내의 레거시 구조(예: weather_temp)는 Optional 필드로 반환되나, 가급적 **날씨 단독 조회 API**(위 1번 문서)를 통해 활용하는 것을 권장합니다.*
