"""
loop_route_service.py
=====================
SmallScale 루프 경로 생성 서비스.

서버 첫 요청 시 그래프를 빌드하고 메모리에 캐싱합니다.
이후 요청은 캐싱된 그래프를 사용하므로 빠르게 응답합니다.
"""

import os
import math
import yaml
import importlib
from typing import Optional
import networkx as nx

from app.core.config import settings
from app.services.small_scale.graph_db_loader import build_graph_from_db
from app.services.small_scale.weight_calculator import apply_weights_to_graph
from app.services.small_scale.loop_router import generate_loop_routes
from app.models.small_scale.route import LoopRouteInfo, DogProfile, WalkCondition, WeatherContext, RejectedRouteInfo
from app.services.small_scale.scenario1_feature_provider import collect_route_profile
from app.services.small_scale.scenario1_filter_engine import evaluate_route_rules, build_filter_info
from app.services.small_scale.route_explainer import build_route_explanations

# === 전역 캐싱 (서버 수명 동안 1회만 로드) ===
_G_weighted = None
_config = None
_PSYCOPG = None


def _haversine_m(lon1, lat1, lon2, lat2):
    """두 WGS84 좌표 사이의 거리(m)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))



def _ensure_graph_loaded():
    """그래프가 메모리에 없으면 빌드합니다 (1회만 실행)."""
    global _G_weighted, _config

    if _G_weighted is not None:
        return

    print("🔄 SmallScale 그래프 빌드 시작... (DB 기반)")

    # config 로드
    config_path = os.path.join(settings.BACKEND_DIR, "config", "weights.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        _config = yaml.safe_load(f)
    print(f"   ⚙️ 설정 로드: {config_path}")

    # DB에서 그래프 빌드
    # 테이블명은 실제 환경에 맞게 조정 필요
    G = build_graph_from_db(edge_table="walk_features")

    # 가중치 적용
    _G_weighted = apply_weights_to_graph(G, _config)
    print("✅ SmallScale 그래프 빌드 완료 (DB 기반, 메모리 캐싱됨)")


def _find_nearest_node(G, lat, lon):
    """주어진 좌표에서 가장 가까운 그래프 노드를 반환."""
    best_node = None
    best_dist = float('inf')
    for node in G.nodes():
        nx_val = G.nodes[node]['x']
        ny_val = G.nodes[node]['y']
        dist = _haversine_m(lon, lat, nx_val, ny_val)
        if dist < best_dist:
            best_dist = dist
            best_node = node
    return best_node


def _build_emergency_fallback_route(G, start_node, target_minutes: int, walking_speed: float = 1.0):
    """후보가 전혀 없을 때 최소 1개 경로를 보장하기 위한 비상 왕복 경로를 만든다."""
    target_distance = max(300.0, float(target_minutes) * 60.0 * float(walking_speed))
    half_target = max(120.0, target_distance / 2.0)

    try:
        dist_map = nx.single_source_dijkstra_path_length(G, start_node, cutoff=half_target, weight="length")
    except Exception:
        dist_map = {}

    candidates = [(node, dist) for node, dist in dist_map.items() if node != start_node]

    # 목표 거리의 절반에 가장 가까운 노드를 우선 선택
    if candidates:
        best_node, best_dist = min(candidates, key=lambda x: abs(x[1] - half_target))
        try:
            path = nx.shortest_path(G, source=start_node, target=best_node, weight="length")
            if len(path) >= 2:
                route_nodes = path + list(reversed(path[:-1]))
                total_distance = float(best_dist) * 2.0
                return {
                    "path_nodes": route_nodes,
                    "estimated_minutes": round(total_distance / max(float(walking_speed), 0.1) / 60.0, 1),
                    "total_distance_m": round(total_distance, 1),
                    "waypoint_count": 1,
                }
        except Exception:
            pass

    # dijkstra 실패 시 인접 노드 왕복이라도 생성
    try:
        neighbors = list(G.neighbors(start_node))
    except Exception:
        neighbors = []

    if neighbors:
        n = neighbors[0]
        edge_data = G.get_edge_data(start_node, n)
        one_way = 20.0
        if edge_data:
            key = list(edge_data.keys())[0]
            one_way = float(edge_data[key].get("length", one_way))
        total_distance = one_way * 2.0
        return {
            "path_nodes": [start_node, n, start_node],
            "estimated_minutes": round(total_distance / max(float(walking_speed), 0.1) / 60.0, 1),
            "total_distance_m": round(total_distance, 1),
            "waypoint_count": 1,
        }

    return None


def _should_avoid_stairs(dog_profile: Optional[DogProfile], walk_condition: Optional[WalkCondition]) -> bool:
    if dog_profile is not None and (
        dog_profile.size == "소형"
        or dog_profile.joint_sensitive
        or dog_profile.age_group == "노령견"
        or dog_profile.is_long_back
    ):
        return True

    if walk_condition is not None and walk_condition.slope_preference == "평지 위주":
        return True

    return False


def _build_routing_graph(G, avoid_stairs: bool = False):
    if not avoid_stairs:
        return G

    routing_graph = G.copy()
    removed_edges = 0

    for u, v, key, data in list(routing_graph.edges(keys=True, data=True)):
        if data.get("near_stairs", False):
            routing_graph.remove_edge(u, v, key=key)
            removed_edges += 1

    print(f"   🧹 계단 회피용 엣지 제거: {removed_edges:,}개")
    return routing_graph


def _get_default_dog_profile() -> DogProfile:
    """사용자가 입력하지 않은 경우 사용할 기본 강아지 프로필."""
    return DogProfile(
        size="중형",
        age_group="성견",
        energy="보통",
        is_long_back=False,
        is_brachycephalic=False,
        noise_sensitive=False,
        heat_sensitive=False,
        joint_sensitive=False,
    )


def _get_default_walk_condition() -> WalkCondition:
    """사용자가 입력하지 않은 경우 사용할 기본 산책 조건."""
    return WalkCondition(
        crowd_preference="상관없음",
        slope_preference="상관없음",
        time_min=30,
    )


def _load_psycopg():
    global _PSYCOPG
    if _PSYCOPG is not None:
        return _PSYCOPG
    try:
        _PSYCOPG = importlib.import_module("psycopg")
    except Exception:
        _PSYCOPG = None
    return _PSYCOPG


def _resolve_weather_context_from_db(user_lat: float, user_lng: float, fallback: Optional[WeatherContext] = None) -> WeatherContext:
    """요청 weather_context와 무관하게 PostgreSQL에서 기온/혼잡도를 우선 조회한다."""
    fallback = fallback or WeatherContext()
    database_url = os.getenv("DATABASE_URL")
    psycopg = _load_psycopg()

    if not database_url or psycopg is None:
        return fallback

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'walk_features'
                    """
                )
                cols = {str(r[0]).lower() for r in cur.fetchall()}

                temp_candidates = [
                    "temperature_c", "temp_c", "temperature", "air_temp", "air_temperature"
                ]
                temp_col = next((c for c in temp_candidates if c in cols), None)
                has_congest_col = "area_congest_lvl" in cols

                select_parts = []
                if temp_col:
                    select_parts.append(f"AVG({temp_col})::float AS avg_temp")
                if has_congest_col:
                    select_parts.append("MODE() WITHIN GROUP (ORDER BY area_congest_lvl) AS area_congest_lvl")

                if not select_parts:
                    return fallback

                query = (
                    "SELECT " + ", ".join(select_parts) + " "
                    "FROM public.walk_features "
                    "WHERE geom IS NOT NULL "
                    "AND ST_DWithin(geom::geography, ST_SetSRID(ST_Point(%s, %s), 4326)::geography, %s)"
                )

                # 1차 반경 600m, 없으면 2차 1500m
                cur.execute(query, (user_lng, user_lat, 600))
                row = cur.fetchone()
                if row is None or all(v is None for v in row):
                    cur.execute(query, (user_lng, user_lat, 1500))
                    row = cur.fetchone()

                if row is None:
                    return fallback

                idx = 0
                avg_temp = None
                db_congest = None

                if temp_col:
                    avg_temp = row[idx]
                    idx += 1
                if has_congest_col:
                    db_congest = row[idx] if idx < len(row) else None

                return WeatherContext(
                    temperature_c=float(avg_temp) if avg_temp is not None else fallback.temperature_c,
                    area_congest_lvl=str(db_congest).strip() if db_congest is not None and str(db_congest).strip() else fallback.area_congest_lvl,
                )
    except Exception:
        return fallback


def _build_filter_info(
    dog_profile: Optional[DogProfile],
    walk_condition: Optional[WalkCondition],
    weather_context: Optional[WeatherContext] = None,
    total_routes: int = 0,
    accepted_routes: int = 0,
    rejected_by_route=None,
    db_used_any: bool = False,
    db_reason_samples=None,
    hazard_used_any: bool = False,
    hazard_reason_samples=None,
):
    return build_filter_info(
        dog=dog_profile,
        walk=walk_condition,
        weather=weather_context,
        total_routes=total_routes,
        accepted_routes=accepted_routes,
        rejected_by_route=rejected_by_route or {},
        db_used_any=db_used_any,
        db_reason_samples=db_reason_samples or [],
        hazard_used_any=hazard_used_any,
        hazard_reason_samples=hazard_reason_samples or [],
    )


def _build_xai_context(
    dog_profile: Optional[DogProfile],
    walk_condition: Optional[WalkCondition],
    weather_context: Optional[WeatherContext],
    target_minutes: int,
):
    conditions = []
    activated_rules = []

    def _build_persona_intro() -> str:
        parts = []
        if dog_profile:
            if dog_profile.joint_sensitive or dog_profile.age_group == "노령견" or dog_profile.size == "소형" or dog_profile.is_long_back:
                parts.append("슬개골이 약한 우리 아이를 위해")
            if dog_profile.is_brachycephalic or dog_profile.heat_sensitive:
                parts.append("더위에 민감한 우리 아이를 위해")
            if dog_profile.noise_sensitive:
                parts.append("소음에 예민한 우리 아이를 위해")
        if not parts:
            parts.append("우리 아이를 위해")
        return " 그리고 ".join(parts)

    rule_catalog = [
        "R1 취약견(소형/관절약함/노령견/장허리종): filter_attributes의 급경사/계단 구간 배제",
        "R2 고온(여름철 화상 주의): final_safety_grade='주의 (여름철 화상 주의)' 배제",
        "R3 단두종/더위민감: heat_risk >= 60(또는 운영값 70) 배제",
        "R4 소음 민감: highway 차량 많은 구간 + sdot_avg_noise >= 50 회피",
        "R5 혼잡도 민감: AREA_CONGEST_LVL이 '약간 붐빔' 이상 회피",
    ]

    if dog_profile:
        if dog_profile.size:
            conditions.append(f"견종 크기={dog_profile.size}")
        if dog_profile.age_group:
            conditions.append(f"나이대={dog_profile.age_group}")
        if dog_profile.noise_sensitive:
            conditions.append("소음 민감")
        if dog_profile.heat_sensitive:
            conditions.append("더위 민감")
        if dog_profile.joint_sensitive:
            conditions.append("관절 민감")
        if dog_profile.is_brachycephalic:
            conditions.append("단두종")
        if dog_profile.is_long_back:
            conditions.append("장허리종")

        if dog_profile.size == "소형" or dog_profile.joint_sensitive or dog_profile.age_group == "노령견" or dog_profile.is_long_back:
            activated_rules.append("R1")
        if dog_profile.is_brachycephalic or dog_profile.heat_sensitive:
            activated_rules.append("R3")
        if dog_profile.noise_sensitive:
            activated_rules.append("R4")

    if walk_condition:
        if walk_condition.crowd_preference:
            conditions.append(f"혼잡 선호={walk_condition.crowd_preference}")
        if walk_condition.slope_preference:
            conditions.append(f"경사 선호={walk_condition.slope_preference}")

        if walk_condition.crowd_preference == "조용한 곳":
            activated_rules.append("R5")

    if weather_context and weather_context.temperature_c is not None:
        conditions.append(f"기온={weather_context.temperature_c}C")
        if weather_context.temperature_c >= float(os.getenv("SCENARIO1_HOT_TEMP_C", "27")):
            activated_rules.append("R2")

    return {
        "persona_intro": _build_persona_intro(),
        "target_minutes": str(target_minutes),
        "user_conditions": ", ".join(conditions) if conditions else "없음",
        "rule_catalog": " | ".join(rule_catalog),
        "activated_rules": ", ".join(sorted(set(activated_rules))) if activated_rules else "없음",
        "area_congest_lvl": weather_context.area_congest_lvl if weather_context and weather_context.area_congest_lvl else "미지정",
    }


def generate_routes(
    user_lat,
    user_lng,
    target_minutes=30,
    num_routes=3,
    dog_profile: Optional[DogProfile] = None,
    walk_condition: Optional[WalkCondition] = None,
    weather_context: Optional[WeatherContext] = None,
    use_ai_explanation: bool = False,
):
    """
    API에서 호출되는 메인 함수.
    
    사용자가 입력하지 않은 경우 기본값을 사용하여 항상 맞춤형 필터를 적용합니다.

    Returns
    -------
    tuple: (list[LoopRouteInfo], start_node_tuple, filter_info, no_match_found, no_match_message)
    """
    _ensure_graph_loaded()
    
    # 사용자 입력 없을 때 기본값 적용
    if dog_profile is None:
        dog_profile = _get_default_dog_profile()
    if walk_condition is None:
        walk_condition = _get_default_walk_condition()

    # weather_context는 요청값보다 DB 조회값을 우선 사용
    weather_context = _resolve_weather_context_from_db(user_lat, user_lng, fallback=weather_context)

    start_node = _find_nearest_node(_G_weighted, user_lat, user_lng)

    avoid_stairs = _should_avoid_stairs(dog_profile, walk_condition)
    routing_graph = _build_routing_graph(_G_weighted, avoid_stairs=avoid_stairs)

    raw_routes = generate_loop_routes(
        routing_graph, start_node,
        target_minutes=target_minutes,
        num_routes=num_routes,
        config=_config,
    )

    used_relaxed_fallback = False
    used_emergency_fallback = False
    if not raw_routes:
        # 후보가 0개일 때는 필터 이전 단계부터 완화해서 기본 경로를 한 번 더 시도한다.
        relaxed_config = dict(_config or {})
        relaxed_loop = dict(relaxed_config.get("loop", {}))
        relaxed_loop["num_candidates"] = max(int(relaxed_loop.get("num_candidates", 80)), 160)
        relaxed_loop["time_tolerance_minutes"] = max(int(relaxed_loop.get("time_tolerance_minutes", 0) or 0), 12)
        relaxed_loop["overlap_threshold"] = max(float(relaxed_loop.get("overlap_threshold", 0.55)), 0.85)
        relaxed_config["loop"] = relaxed_loop

        # 계단 회피 그래프로 후보가 0개였을 수 있으므로, 기본 가중치 그래프에서도 재시도.
        raw_routes = generate_loop_routes(
            _G_weighted, start_node,
            target_minutes=target_minutes,
            num_routes=num_routes,
            config=relaxed_config,
        )
        if raw_routes:
            used_relaxed_fallback = True
            routing_graph = _G_weighted

    if not raw_routes:
        walking_speed = float((_config or {}).get("loop", {}).get("walking_speed_mps", 1.0))
        emergency_route = _build_emergency_fallback_route(
            _G_weighted,
            start_node,
            target_minutes=target_minutes,
            walking_speed=walking_speed,
        )
        if emergency_route:
            raw_routes = [emergency_route]
            routing_graph = _G_weighted
            used_relaxed_fallback = True
            used_emergency_fallback = True

    result = []
    rejected_routes = []
    route_profiles = []
    rejected_by_route = {}
    db_used_any = False
    db_reason_samples = []
    hazard_used_any = False
    hazard_reason_samples = []
    user_coord = [user_lat, user_lng]

    for idx, r in enumerate(raw_routes):
        route_profile = collect_route_profile(r['path_nodes'], routing_graph)
        if route_profile.get("has_hazard"):
            hazard_used_any = True
            hazard_reason = route_profile.get("nearest_hazard_type")
            hazard_distance = route_profile.get("nearest_hazard_distance_m")
            if hazard_reason and hazard_distance is not None:
                hazard_reason_samples.append(f"{hazard_reason} ({hazard_distance:.0f}m)")
            elif hazard_reason:
                hazard_reason_samples.append(str(hazard_reason))
            else:
                hazard_reason_samples.append("돌발상황 인근")
        passed, reject_reasons, route_warnings = evaluate_route_rules(
            profile=route_profile,
            dog=dog_profile,
            walk=walk_condition,
            weather=weather_context,
        )

        if route_profile.get("db_used"):
            db_used_any = True
        elif route_profile.get("db_reason"):
            db_reason_samples.append(route_profile.get("db_reason"))

        # 노드 좌표를 [lat, lng] 형식 polyline으로 변환
        path_coords = [
            [_G_weighted.nodes[n]['y'], _G_weighted.nodes[n]['x']]
            for n in r['path_nodes']
        ]
        
        # 실제 네트워크 경로만 반환 (사용자 좌표와의 직선 연결 방지)
        full_polyline = path_coords

        if not passed:
            rejected_by_route[idx + 1] = reject_reasons
            # 거부된 경로도 시각화를 위해 수집
            rejected_routes.append(RejectedRouteInfo(
                route_id=idx + 1,
                estimated_minutes=r['estimated_minutes'],
                total_distance_m=r['total_distance_m'],
                waypoint_count=r['waypoint_count'],
                polyline=full_polyline,
                reject_reasons=reject_reasons,
                has_steep=bool(route_profile.get("has_steep")),
                has_stairs=bool(route_profile.get("has_stairs")),
                has_hot_surface_grade=bool(route_profile.get("has_hot_surface_grade")),
                max_heat_risk=route_profile.get("max_heat_risk"),
                vehicle_ratio=float(route_profile.get("vehicle_ratio") or 0.0),
                highways=list(route_profile.get("highways") or []),
                has_hazard=bool(route_profile.get("has_hazard")),
                hazard_count=int(route_profile.get("hazard_count") or 0),
                nearest_hazard_distance_m=route_profile.get("nearest_hazard_distance_m"),
                nearest_hazard_type=route_profile.get("nearest_hazard_type"),
            ))
            continue

        result.append(LoopRouteInfo(
            route_id=idx + 1,
            estimated_minutes=r['estimated_minutes'],
            total_distance_m=r['total_distance_m'],
            waypoint_count=r['waypoint_count'],
            polyline=full_polyline,
            route_warnings=route_warnings,
            has_stairs=bool(route_profile.get("has_stairs")),
        ))
        route_profiles.append(route_profile)

    # 조건에 맞는 경로가 없을 때 상황 표시
    no_match_found = False
    no_match_message = None

    if not raw_routes:
        no_match_found = True
        applied_rules_text = "; ".join(_build_filter_info(
            dog_profile=dog_profile,
            walk_condition=walk_condition,
            weather_context=weather_context,
            total_routes=0,
            accepted_routes=0,
            rejected_by_route={},
            db_used_any=db_used_any,
            db_reason_samples=db_reason_samples,
            hazard_used_any=hazard_used_any,
            hazard_reason_samples=hazard_reason_samples,
        ).get("applied_rules", [])) or "설정된 필터"
        no_match_message = (
            f"경로 후보를 생성하지 못했습니다. {applied_rules_text}가 너무 엄격하거나 시작점 주변 연결이 부족할 수 있습니다."
        )
    
    # 최소 결과 보장을 위해 전부 탈락 시 원본 상위 num_routes를 fallback 반환
    if not result and raw_routes:
        no_match_found = True
        for idx, r in enumerate(raw_routes[:num_routes]):
            path_coords = [
                [routing_graph.nodes[n]['y'], routing_graph.nodes[n]['x']]
                for n in r['path_nodes']
            ]
            full_polyline = path_coords
            fallback_profile = collect_route_profile(r['path_nodes'], routing_graph)
            result.append(LoopRouteInfo(
                route_id=idx + 1,
                estimated_minutes=r['estimated_minutes'],
                total_distance_m=r['total_distance_m'],
                waypoint_count=r['waypoint_count'],
                polyline=full_polyline,
                route_warnings=["⚠️ 조건을 만족하는 경로가 없습니다. 기본 경로로 대체되었습니다."],
                has_stairs=bool(fallback_profile.get("has_stairs")),
            ))

    filter_info = _build_filter_info(
        dog_profile=dog_profile,
        walk_condition=walk_condition,
        weather_context=weather_context,
        total_routes=len(raw_routes),
        accepted_routes=0 if no_match_found else len(result),
        rejected_by_route=rejected_by_route,
        db_used_any=db_used_any,
        db_reason_samples=db_reason_samples,
        hazard_used_any=hazard_used_any,
        hazard_reason_samples=hazard_reason_samples,
    )

    if no_match_found:
        filter_info["no_match_found"] = True
        applied_rules_text = "; ".join(filter_info.get("applied_rules", [])) or "설정된 필터"
        no_match_message = f"조건에 맞는 경로가 없습니다 ({applied_rules_text}). 아래는 필터 미적용 기본 경로입니다."
    elif used_relaxed_fallback:
        filter_info["used_relaxed_fallback"] = True
        if used_emergency_fallback:
            filter_info["fallback_note"] = "주변에 조건에 맞는 경로가 없어 비상 왕복 경로를 생성했습니다."
        else:
            filter_info["fallback_note"] = "주변에 조건에 맞는 경로가 없어 완화된 조건으로 경로를 생성했습니다."

    # 경로 설명은 항상 AI(실패 시 내부 fallback)로 생성
    if result:
        xai_context = _build_xai_context(
            dog_profile=dog_profile,
            walk_condition=walk_condition,
            weather_context=weather_context,
            target_minutes=target_minutes,
        )
        explanations = build_route_explanations(
            result,
            filter_info.get("summary", ""),
            xai_context=xai_context,
            route_profiles=route_profiles,
        )
        for i, route in enumerate(result):
            exp = explanations[i] if i < len(explanations) else None
            # dict 형태면 description 값만 추출
            if isinstance(exp, dict) and "description" in exp:
                route.route_explanation = exp["description"]
            else:
                route.route_explanation = exp

    # 기본 경로 대체 시에는 설명에 반드시 대체 사유를 명시한다.
    if result and (no_match_found or used_relaxed_fallback):
        fallback_note = filter_info.get("fallback_note")
        fallback_reason = no_match_message or fallback_note or "조건 미충족으로 기본 경로를 제공합니다."
        for route in result:
            base_explanation = (route.route_explanation or "").strip()
            prefix = f"[기본 경로 안내] {fallback_reason}"
            if base_explanation:
                if prefix not in base_explanation:
                    route.route_explanation = f"{prefix} {base_explanation}"
            else:
                route.route_explanation = prefix

    return result, rejected_routes, start_node, filter_info, no_match_found, no_match_message
