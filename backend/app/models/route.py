from pydantic import BaseModel, Field
from typing import List, Optional


class LoopRouteRequest(BaseModel):
    """소규모 루프 경로 추천 요청"""
    user_lat: float = Field(..., description="출발점 위도", example=37.514)
    user_lng: float = Field(..., description="출발점 경도", example=127.105)
    target_minutes: int = Field(30, ge=5, le=120, description="목표 산책 시간(분)")
    num_routes: int = Field(3, ge=1, le=5, description="생성할 경로 수")


class LoopRouteInfo(BaseModel):
    """개별 루프 경로 정보"""
    route_id: int
    estimated_minutes: float
    total_distance_m: float
    waypoint_count: int
    polyline: List[List[float]] = Field(..., description="경로 좌표 [[lat, lng], ...]")


class LoopRouteResponse(BaseModel):
    """소규모 루프 경로 추천 응답"""
    routes: List[LoopRouteInfo]
    requested_lat: float = Field(..., description="사용자가 요청한 실제 위도")
    requested_lng: float = Field(..., description="사용자가 요청한 실제 경도")
    start_lat: float = Field(..., description="그래프에서 스내핑된 위도")
    start_lng: float = Field(..., description="그래프에서 스내핑된 경도")
    count: int
