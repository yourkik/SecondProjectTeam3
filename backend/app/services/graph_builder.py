"""
graph_builder.py
================
edges_clean.geojson → NetworkX MultiGraph 변환

노드 생성 전략:
  각 LineString의 시작/끝 좌표를 소수점 6자리로 라운딩하여
  (lon, lat) 튜플을 고유 노드 ID로 사용합니다.
"""

import json
import networkx as nx
from pathlib import Path


def _round_coord(coord, precision=6):
    """좌표를 지정된 소수점 자리로 라운딩하여 노드 키로 사용."""
    return (round(coord[0], precision), round(coord[1], precision))


def _parse_width(width_raw):
    """
    width 문자열을 float(m)로 변환.
    예: '3' -> 3.0, '2m' -> 2.0, None -> None
    """
    if width_raw is None:
        return None
    s = str(width_raw).strip().lower().replace('m', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def build_graph(edges_geojson_path: str, precision: int = 6) -> nx.MultiGraph:
    """
    edges_clean.geojson을 읽어 NetworkX MultiGraph를 구성합니다.

    Parameters
    ----------
    edges_geojson_path : str
        edges_clean.geojson 파일 경로
    precision : int
        좌표 라운딩 소수점 자릿수 (기본 6 → 약 0.11m 정밀도)

    Returns
    -------
    nx.MultiGraph
        노드 속성: x(lon), y(lat)
        엣지 속성: highway, surface, width, width_m, smoothness, length, name, osm_id
    """
    path = Path(edges_geojson_path)
    print(f"📂 엣지 데이터 로드 중: {path.name}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    features = data['features']
    print(f"   총 {len(features):,}개 피처 발견")

    G = nx.MultiGraph()

    edge_count = 0
    for feat in features:
        coords = feat['geometry']['coordinates']
        props = feat['properties']

        # 시작/끝 좌표 → 노드 ID
        start_coord = _round_coord(coords[0], precision)
        end_coord = _round_coord(coords[-1], precision)

        # 노드 추가 (중복 시 무시됨)
        if start_coord not in G:
            G.add_node(start_coord, x=start_coord[0], y=start_coord[1])
        if end_coord not in G:
            G.add_node(end_coord, x=end_coord[0], y=end_coord[1])

        # 엣지 속성 구성
        edge_attrs = {
            'highway': props.get('highway', 'unknown'),
            'surface': props.get('surface'),
            'width': props.get('width'),
            'width_m': _parse_width(props.get('width')),
            'smoothness': props.get('smoothness'),
            'length': props.get('length', 10.0),
            'name': props.get('name'),
            'osm_id': props.get('id'),
        }

        G.add_edge(start_coord, end_coord, **edge_attrs)
        edge_count += 1

    print(f"✅ 그래프 구성 완료: 노드 {len(G.nodes):,}개, 엣지 {edge_count:,}개")

    # 연결 컴포넌트 분석
    components = list(nx.connected_components(G))
    if len(components) == 1:
        print(f"   🟢 단일 연결 그래프 (모든 노드가 연결됨)")
    else:
        sizes = sorted([len(c) for c in components], reverse=True)
        print(f"   🟡 {len(components)}개의 연결 컴포넌트 발견")
        print(f"      최대 컴포넌트: {sizes[0]:,}개 노드")
        print(f"      상위 5개 크기: {sizes[:5]}")
        # 가장 큰 컴포넌트만 유지할지 여부는 호출자가 결정
        # 여기선 전체를 반환

    return G


def keep_largest_component(G: nx.MultiGraph) -> nx.MultiGraph:
    """가장 큰 연결 컴포넌트만 남기고 나머지를 제거합니다."""
    components = list(nx.connected_components(G))
    if len(components) <= 1:
        return G

    largest = max(components, key=len)
    nodes_to_remove = set(G.nodes()) - largest
    G.remove_nodes_from(nodes_to_remove)
    print(f"🔧 최대 컴포넌트 유지: {len(largest):,}개 노드 (제거: {len(nodes_to_remove):,}개)")
    return G


def keep_significant_components(G: nx.MultiGraph, min_nodes: int = 100) -> nx.MultiGraph:
    """
    min_nodes 이상의 노드를 가진 연결 컴포넌트만 유지합니다.
    3개 구(강동구·송파구·강남구)가 별도 컴포넌트로 구성되므로,
    작은 노이즈 컴포넌트만 제거합니다.
    """
    components = list(nx.connected_components(G))
    if len(components) <= 1:
        return G

    significant = [c for c in components if len(c) >= min_nodes]
    keep_nodes = set()
    for c in significant:
        keep_nodes |= c

    nodes_to_remove = set(G.nodes()) - keep_nodes
    G.remove_nodes_from(nodes_to_remove)

    sizes = sorted([len(c) for c in significant], reverse=True)
    print(f"🔧 유의미 컴포넌트 유지: {len(significant)}개 (min_nodes={min_nodes})")
    print(f"   유지: {len(keep_nodes):,}개 노드, 제거: {len(nodes_to_remove):,}개")
    print(f"   컴포넌트 크기: {sizes[:10]}")
    return G


if __name__ == "__main__":
    import os
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    edges_path = os.path.join(base, "data", "osm", "edges_clean.geojson")

    G = build_graph(edges_path)
    G = keep_largest_component(G)

    # 기본 통계
    print(f"\n=== 그래프 요약 ===")
    print(f"노드: {len(G.nodes):,}")
    print(f"엣지: {len(G.edges):,}")

    lengths = [d.get('length', 0) for _, _, d in G.edges(data=True)]
    print(f"총 네트워크 길이: {sum(lengths)/1000:.1f} km")
    print(f"평균 엣지 길이: {sum(lengths)/len(lengths):.1f} m")
