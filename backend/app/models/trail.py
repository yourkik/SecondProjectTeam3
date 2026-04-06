from pydantic import BaseModel, Field
from typing import List, Optional

# 사용자 요청(Request) 모델: 위도(Y), 경도(X)
class TrailRecommendationRequest(BaseModel):
    user_lat: float = Field(..., description="사용자 현재 위도 (Y)", example=37.550)
    user_lng: float = Field(..., description="사용자 현재 경도 (X)", example=127.150)
    max_distance_km: float = Field(5.0, description="검색 최대 거리(km)", example=5.0)
    limit: int = Field(5, description="추천받을 산책로 최대 개수")

# 산책로 정보(Response) 세부 모델
class TrailInfo(BaseModel):
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

# 추천 결과(Response) 통합 모델
class TrailRecommendationResponse(BaseModel):
    items: List[TrailInfo]
    count: int
