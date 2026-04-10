from pydantic import BaseModel, Field
from typing import List, Optional

# 사용자 요청(Request) 모델: 위도(Y), 경도(X)
class TrailRecommendationRequest(BaseModel):
    user_lat: float = Field(..., description="사용자 현재 위도 (Y)", example=37.550)
    user_lng: float = Field(..., description="사용자 현재 경도 (X)", example=127.150)
    max_distance_km: float = Field(20.0, description="최대 탐색 반경(km)")
    limit: int = Field(5, gt=0, le=50, description="반환할 추천 산책로의 최대 개수")
    view_type: str = Field("trail+park", description="보여줄 타입 ('trail+park', 'park', 'trail', 'facility')")
    use_realtime_api: bool = Field(False, description="실시간 도시 데이터 API 호출 여부")

# 산책로 정보(Response) 세부 모델
class TrailInfo(BaseModel):
    type: str = Field("trail", description="데이터 종류 ('trail', 'park', 'playground', 'cafe', 'hospital')")
    trail_id: str
    trail_name: str
    is_pet_allowed: int
    length_km: float
    time_minute: int
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    distance_from_user: float = Field(..., description="사용자로부터 떨어진 거리 (직선거리 km)")
    polyline: Optional[List[List[float]]] = Field(None, description="SHP와 매칭된 실제 선형 좌표 리스트 [[lat, lng], ...]")
    congestion_lvl: Optional[str] = Field(None, description="혼잡도 (여유, 보통, 약간 붐빔, 붐빔)")
    congestion_msg: Optional[str] = Field(None, description="혼잡도 메시지")
    slope_lvl: Optional[str] = Field(None, description="경사 등급 (평탄, 경사)")
    slope_val: Optional[str] = Field(None, description="경사 수치 (0-7%, 7-15% 등)")
    slope_avg: Optional[float] = Field(None, description="평균 경사도 수치 (%)")
    
    # 반려견 놀이터 전용 추가 정보 (Optional)
    pg_holidays: Optional[str] = Field(None, description="휴무일")
    pg_agency: Optional[str] = Field(None, description="운영기관")
    pg_phone: Optional[str] = Field(None, description="전화번호")
    pg_size: Optional[str] = Field(None, description="규모(㎡)")
    pg_night_light: Optional[str] = Field(None, description="야간조명")
    pg_location: Optional[str] = Field(None, description="위치(주소)")
    pg_fee: Optional[str] = Field(None, description="이용요금")
    pg_hours: Optional[str] = Field(None, description="운영시간")
    pg_notes: Optional[str] = Field(None, description="특이사항")
    pg_floor: Optional[str] = Field(None, description="바닥재")
    pg_large_dog: Optional[str] = Field(None, description="대형견 출입가능 여부")

# 추천 결과(Response) 통합 모델
class TrailRecommendationResponse(BaseModel):
    items: List[TrailInfo]
    weather_temp: Optional[str] = Field(None, description="현재 대표 기온")
    weather_pm10: Optional[str] = Field(None, description="현재 대표 미세먼지 수치")
    weather_msg: Optional[str] = Field(None, description="현재 대표 날씨 상세")
    count: int

# 돌발/통제 정보 모델
class IncidentInfo(BaseModel):
    acc_id: str
    acc_type: str
    acc_info: str
    lat: float
    lng: float

# 긴급 재난 문자 모델
class DisasterMessage(BaseModel):
    sn: str = Field(..., description="일련번호")
    crt_dt: str = Field(..., description="생성일시")
    msg_cn: str = Field(..., description="메시지내용")
    rcptn_rgn_nm: str = Field(..., description="수신지역명")
    emrg_step_nm: str = Field(..., description="긴급단계명")
    dst_se_nm: str = Field(..., description="재해구분명")

# 맵상 위험 정보 응답 모델
class HazardResponse(BaseModel):
    incidents: List[IncidentInfo] = []
    disasters: List[DisasterMessage] = []
