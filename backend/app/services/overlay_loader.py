"""
overlay_loader.py
=================
계단(stairs.geojson)과 공원/놀이터(leisure_clean.geojson) 데이터를
NetworkX 그래프 엣지에 공간 태깅합니다.

좌표계: WGS84 (EPSG:4326)
거리 근사: Haversine 공식 사용 (geopandas 없이 순수 Python 구현)
"""

import json
import math
from pathlib import Path


def _haversine_m(lon1, lat1, lon2, lat2):
    """두 WGS84 좌표 사이의 거리를 미터 단위로 반환 (Haversine)."""
    R = 6_371_000  # 지구 반경(m)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _edge_midpoint(G, u, v):
    """엣지의 양 끝 노드 좌표의 중점 (lon, lat) 반환."""
    x1, y1 = G.nodes[u]['x'], G.nodes[u]['y']
    x2, y2 = G.nodes[v]['x'], G.nodes[v]['y']
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _load_stairs_points(stairs_path):
    """
    stairs.geojson(LineString)의 각 라인 중점을 계단 위치로 반환합니다.
    Returns: list of (lon, lat)
    """
    with open(stairs_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    points = []
    for feat in data['features']:
        coords = feat['geometry']['coordinates']
        if len(coords) >= 2:
            # 라인의 중점 사용
            mid_idx = len(coords) // 2
            points.append(tuple(coords[mid_idx][:2]))
        elif len(coords) == 1:
            points.append(tuple(coords[0][:2]))

    print(f"   🪜 계단 위치 {len(points):,}개 로드")
    return points


def _load_leisure_points(leisure_path):
    """
    leisure_clean.geojson(Point)을 로드합니다.
    Returns: list of (lon, lat, leisure_type)
    """
    with open(leisure_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    points = []
    for feat in data['features']:
        coords = feat['geometry']['coordinates']
        leisure_type = feat['properties'].get('leisure', 'park')
        points.append((coords[0], coords[1], leisure_type))

    # 타입별 카운트
    from collections import Counter
    type_counts = Counter(p[2] for p in points)
    print(f"   🌳 레저 포인트 {len(points):,}개 로드: {dict(type_counts)}")
    return points


def apply_stairs_overlay(G, stairs_path, buffer_m=15, multiplier=4.0):
    """
    계단 위치로부터 buffer_m 이내의 엣지에 'near_stairs' = True 속성을 추가합니다.
    
    최적화: 위도 1도 ≈ 111km이므로, 사전 필터링으로 먼 계단은 건너뜁니다.
    """
    stairs_points = _load_stairs_points(stairs_path)
    if not stairs_points:
        return G

    # 위/경도 기준 박스 필터링 threshold (buffer_m의 2배를 도 단위로 변환)
    lat_threshold = (buffer_m * 2) / 111_000
    lon_threshold = lat_threshold / math.cos(math.radians(37.5))  # 서울 위도 기준 보정

    tagged_count = 0

    for u, v, key, data in G.edges(keys=True, data=True):
        mid_lon, mid_lat = _edge_midpoint(G, u, v)

        for slon, slat in stairs_points:
            # 빠른 박스 필터
            if abs(mid_lat - slat) > lat_threshold or abs(mid_lon - slon) > lon_threshold:
                continue

            dist = _haversine_m(mid_lon, mid_lat, slon, slat)
            if dist <= buffer_m:
                data['near_stairs'] = True
                tagged_count += 1
                break  # 하나라도 가까우면 태깅하고 다음 엣지로

    print(f"   📌 계단 인접 엣지 태깅: {tagged_count:,}개 (buffer={buffer_m}m)")
    return G


def apply_leisure_overlay(G, leisure_path, config_leisure):
    """
    공원/놀이터 주변 엣지에 'near_leisure' 속성을 추가합니다.
    config_leisure: weights.yaml의 leisure_bonus 섹션 딕셔너리
    """
    leisure_points = _load_leisure_points(leisure_path)
    if not leisure_points:
        return G

    park_radius = config_leisure.get('park_radius_m', 200)
    dog_park_radius = config_leisure.get('dog_park_radius_m', 300)

    # 타입별 반경 매핑
    radius_map = {
        'park': park_radius,
        'dog_park': dog_park_radius,
    }

    max_radius = max(radius_map.values())
    lat_threshold = (max_radius * 2) / 111_000
    lon_threshold = lat_threshold / math.cos(math.radians(37.5))

    tagged_count = 0
    dog_park_count = 0

    for u, v, key, data in G.edges(keys=True, data=True):
        mid_lon, mid_lat = _edge_midpoint(G, u, v)

        best_type = None
        best_dist = float('inf')

        for llon, llat, ltype in leisure_points:
            # 빠른 박스 필터
            if abs(mid_lat - llat) > lat_threshold or abs(mid_lon - llon) > lon_threshold:
                continue

            radius = radius_map.get(ltype, park_radius)
            dist = _haversine_m(mid_lon, mid_lat, llon, llat)

            if dist <= radius and dist < best_dist:
                best_dist = dist
                best_type = ltype

        if best_type:
            data['near_leisure'] = best_type
            tagged_count += 1
            if best_type == 'dog_park':
                dog_park_count += 1

    print(f"   📌 공원 인접 엣지 태깅: {tagged_count:,}개 (dog_park: {dog_park_count})")
    return G


def apply_all_overlays(G, stairs_path, leisure_path, config):
    """계단 + 공원 오버레이를 모두 적용합니다."""
    print("🗂️ 오버레이 데이터 적용 중...")

    stairs_cfg = config.get('stairs_penalty', {})
    G = apply_stairs_overlay(
        G, stairs_path,
        buffer_m=stairs_cfg.get('buffer_m', 15),
        multiplier=stairs_cfg.get('multiplier', 4.0)
    )

    leisure_cfg = config.get('leisure_bonus', {})
    G = apply_leisure_overlay(G, leisure_path, leisure_cfg)

    print("✅ 오버레이 적용 완료\n")
    return G
