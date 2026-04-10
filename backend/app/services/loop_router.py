"""
loop_router.py
==============
시작점에서 출발하여 다시 돌아오는 순환(Loop) 산책 경로를 생성합니다.

핵심 개선:
  - 시작점이 속한 연결 컴포넌트 내에서만 경유지를 선정 (컴포넌트 간 경로 실패 방지)
  - 경유지(waypoint)를 목표 반경 내에서 각도 균등 분포로 선정하여 자연스러운 루프 형태 유지
  - max_waypoints 제한으로 과도하게 복잡한 경로 방지
  - shape_regularity 파라미터로 루프의 원형 정도를 조절
  - config(YAML)에서 모든 파라미터를 읽어옴
"""

import networkx as nx
import random
import math


def _haversine_m(lon1, lat1, lon2, lat2):
    """두 WGS84 좌표 사이의 거리(m)."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _get_reachable_nodes(G, start_node):
    """시작 노드에서 도달 가능한 (같은 컴포넌트) 노드 집합을 반환."""
    for comp in nx.connected_components(G):
        if start_node in comp:
            return comp
    return {start_node}


def _select_waypoints(G, start_node, target_radius_m, num_waypoints,
                      shape_regularity=0.7, reachable_nodes=None):
    """
    시작점 주변에서 경유지를 선정합니다.
    reachable_nodes가 제공되면 해당 집합 내에서만 후보를 선택합니다.
    """
    sx, sy = G.nodes[start_node]['x'], G.nodes[start_node]['y']

    # 같은 컴포넌트 내의 노드만 사용
    if reachable_nodes is not None:
        pool = list(reachable_nodes - {start_node})
    else:
        pool = [n for n in G.nodes() if n != start_node]

    if num_waypoints <= 0 or not pool:
        return []

    if shape_regularity < 0.3:
        # 낮은 정규성: 반경 내 무작위 선정
        candidates = []
        for n in pool:
            nx_val, ny_val = G.nodes[n]['x'], G.nodes[n]['y']
            dist = _haversine_m(sx, sy, nx_val, ny_val)
            if dist <= target_radius_m * 1.5:
                candidates.append(n)

        if len(candidates) < num_waypoints:
            return candidates if candidates else []

        selected = random.sample(candidates, num_waypoints)
        selected.sort(key=lambda n: math.atan2(
            G.nodes[n]['y'] - sy, G.nodes[n]['x'] - sx
        ))
        return selected

    # 높은 정규성: 목표 각도에 가장 가까운 노드를 선정
    start_angle = random.uniform(0, 2 * math.pi)
    target_angles = [
        start_angle + (2 * math.pi * i / num_waypoints)
        for i in range(num_waypoints)
    ]

    # 반경 범위 내 후보 노드 & 각도/거리 사전 계산
    candidates = []
    for n in pool:
        nx_val, ny_val = G.nodes[n]['x'], G.nodes[n]['y']
        dist = _haversine_m(sx, sy, nx_val, ny_val)
        # 반경의 10%~200% 범위 내 후보 (소규모 컴포넌트 대응 위해 범위 확대)
        if target_radius_m * 0.1 <= dist <= target_radius_m * 2.0:
            angle = math.atan2(ny_val - sy, nx_val - sx)
            candidates.append((n, dist, angle))

    # 후보가 부족하면 거리 제한 없이 전체 pool에서 선정
    if len(candidates) < num_waypoints:
        candidates = []
        for n in pool:
            nx_val, ny_val = G.nodes[n]['x'], G.nodes[n]['y']
            dist = _haversine_m(sx, sy, nx_val, ny_val)
            angle = math.atan2(ny_val - sy, nx_val - sx)
            candidates.append((n, dist, angle))

    if not candidates:
        return []

    # 각 목표 각도에 대해 가장 가까운 후보 선정
    selected = []
    used = set()
    ideal_dist = target_radius_m * 0.6

    for target_angle in target_angles:
        best_node = None
        best_score = float('inf')

        for n, dist, angle in candidates:
            if n in used:
                continue

            angle_diff = abs(math.atan2(
                math.sin(angle - target_angle),
                math.cos(angle - target_angle)
            ))

            dist_diff = abs(dist - ideal_dist) / max(target_radius_m, 1)

            score = angle_diff * shape_regularity + dist_diff * (1 - shape_regularity)

            if score < best_score:
                best_score = score
                best_node = n

        if best_node:
            selected.append(best_node)
            used.add(best_node)

    return selected


def generate_loop_routes(G, start_node, target_minutes=30, num_routes=3, config=None):
    """
    시작 노드에서 출발하여 목표 산책 시간에 맞는 루프형 산책 코스를 생성합니다.
    """
    if config is None:
        config = {}

    loop_cfg = config.get('loop', {})
    max_wp = loop_cfg.get('max_waypoints', 4)
    min_wp = loop_cfg.get('min_waypoints', 2)
    shape_reg = loop_cfg.get('shape_regularity', 0.7)
    revisit_penalty = loop_cfg.get('revisit_penalty', 999999)
    num_candidates = loop_cfg.get('num_candidates', 150)
    walking_speed = loop_cfg.get('walking_speed_mps', 1.0)

    # 시작점이 속한 컴포넌트만 사용 (다른 컴포넌트 노드로의 경로 실패 방지)
    reachable = _get_reachable_nodes(G, start_node)

    print(f"🚶 [{start_node[0]:.5f}, {start_node[1]:.5f}]에서 {target_minutes}분 루프 코스 탐색...")
    print(f"   설정: waypoints={min_wp}~{max_wp}, regularity={shape_reg}, speed={walking_speed} m/s")
    print(f"   시작점 컴포넌트: {len(reachable)}개 노드")

    # 목표 거리 계산
    target_distance = target_minutes * 60 * walking_speed
    min_dist = (target_minutes - 5) * 60 * walking_speed
    max_dist = (target_minutes + 5) * 60 * walking_speed

    # 경유지 배치 반경
    target_radius = target_distance / (2 * math.pi) * 1.5

    # 컴포넌트가 너무 작으면 최소 경유지를 1로 줄임
    effective_min_wp = min(min_wp, max(1, len(reachable) // 20))
    effective_max_wp = min(max_wp, max(1, len(reachable) // 10))

    routes = []

    for attempt in range(num_candidates):
        if len(routes) >= num_routes:
            break

        num_wp = random.randint(effective_min_wp, max(effective_min_wp, effective_max_wp))

        waypoints = _select_waypoints(
            G, start_node, target_radius, num_wp, shape_reg,
            reachable_nodes=reachable
        )

        if num_wp > 0 and len(waypoints) == 0:
            continue

        # 왕복 방지를 위해 임시 그래프 복사
        temp_G = G.copy()

        loop_path = []
        total_real_dist = 0.0
        valid_loop = True
        current = start_node

        # 시작 → 경유지들 → 시작 (복귀)
        for wp in waypoints + [start_node]:
            try:
                segment = nx.shortest_path(temp_G, source=current, target=wp, weight='weight')

                for i in range(len(segment) - 1):
                    u, v = segment[i], segment[i + 1]
                    edge_data = temp_G.get_edge_data(u, v)
                    if edge_data:
                        key = list(edge_data.keys())[0]
                        total_real_dist += edge_data[key].get('length', 10.0)

                        temp_G[u][v][key]['weight'] += revisit_penalty
                        if temp_G.has_edge(v, u):
                            for rev_k in temp_G[v][u]:
                                temp_G[v][u][rev_k]['weight'] += revisit_penalty

                if loop_path:
                    loop_path.extend(segment[1:])
                else:
                    loop_path.extend(segment)

                current = wp

                if total_real_dist > max_dist * 1.3:
                    valid_loop = False
                    break

            except nx.NetworkXNoPath:
                valid_loop = False
                break

        if not valid_loop:
            continue

        # 거리 조건 필터링 (소규모 컴포넌트에서는 조건 완화)
        dist_low = min_dist * 0.6 if len(reachable) < 500 else min_dist * 0.8
        dist_high = max_dist * 1.5 if len(reachable) < 500 else max_dist * 1.3

        if dist_low <= total_real_dist <= dist_high:
            est_minutes = round(total_real_dist / walking_speed / 60, 1)

            routes.append({
                "path_nodes": loop_path,
                "estimated_minutes": est_minutes,
                "total_distance_m": round(total_real_dist, 1),
                "waypoint_count": len(waypoints),
            })

    print(f"✅ {len(routes)}개 루프 코스 생성 완료 (시도: {min(attempt + 1, num_candidates)}회)\n")
    return routes
