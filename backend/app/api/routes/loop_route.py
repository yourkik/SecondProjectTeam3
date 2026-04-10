from fastapi import APIRouter
from app.models.route import LoopRouteRequest, LoopRouteResponse
from app.services.loop_route_service import generate_routes

router = APIRouter()


@router.post("/generate", response_model=LoopRouteResponse,
             summary="집 주변 소규모 루프 산책 경로 생성")
def create_loop_routes(request: LoopRouteRequest):
    """
    사용자의 위/경도와 목표 시간을 받아
    주변 도로 네트워크(OSM)에서 순환 산책 경로를 생성합니다.

    - 차도, 좁은 길, 계단을 자동으로 기피
    - 공원·놀이터 근처 경로를 우선 선택
    - 가중치 설정은 config/weights.yaml에서 조정 가능
    """
    routes, start_node = generate_routes(
        user_lat=request.user_lat,
        user_lng=request.user_lng,
        target_minutes=request.target_minutes,
        num_routes=request.num_routes,
    )
    return LoopRouteResponse(
        routes=routes,
        requested_lat=request.user_lat,
        requested_lng=request.user_lng,
        start_lat=start_node[1],
        start_lng=start_node[0],
        count=len(routes),
    )
