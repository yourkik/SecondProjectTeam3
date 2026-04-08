import json
import os
import sys
import xml.etree.ElementTree as ET

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.config import settings

# ── 경사도 분류 헬퍼 ──────────────────────────────────────────────────
SLOPE_MIDPOINTS = {
    "0-7%": 3.5, "0~7%": 3.5,
    "7-15%": 11.0, "7~15%": 11.0,
    "15-30%": 22.5, "15~30%": 22.5,
    "30-60%": 45.0, "30~60%": 45.0,
    "60%이상": 70.0, "60% 이상": 70.0,
}

def categorize_slope(avg_pct: float) -> str:
    """평균 경사 수치(%)로 등급 분류 (15% 기준)"""
    if avg_pct is None:
        return "정보 없음"
    return "평탄" if avg_pct < 15.0 else "경사"

def val_to_num(slope_val: str) -> float | None:
    for k, v in SLOPE_MIDPOINTS.items():
        if k in str(slope_val):
            return v
    return None

def parse_gpx_points(gpx_path: str) -> list[tuple[float, float]]:
    """GPX → [(lng, lat), ...] (WGS84)"""
    pts = []
    try:
        tree = ET.parse(gpx_path)
        root = tree.getroot()
        ns = {'g': 'http://www.topografix.com/GPX/1/1'}
        for tp in root.findall('.//g:trkpt', ns):
            pts.append((float(tp.get('lon')), float(tp.get('lat'))))
    except Exception as e:
        print(f"  GPX 파싱 에러 {os.path.basename(gpx_path)}: {e}")
    return pts


# ── 메인 전처리 ───────────────────────────────────────────────────────
def run_real_preprocessing():
    """
    [위경도 기반] 이름 매칭 없이 순수 공간 연산으로 경사도 추출
    - 모든 데이터를 WGS84(EPSG:4326)로 통일한 뒤 sjoin
    - Vworld SHP: CRS 없음 → EPSG:5185(Korea 2000 West Belt) 로 지정 후 WGS84 변환
    """
    try:
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import Point, LineString, MultiLineString
    except ImportError:
        print("geopandas / shapely 누락. 설치 후 재시도하세요.")
        return

    WGS84 = "EPSG:4326"
    VWORLD_CRS = 5185  # 실제 측정으로 확인된 EPSG

    # ── 1. Vworld 경사도 로드 & WGS84 변환 ────────────────────────────
    print("1. Vworld 경사도 SHP 로드 및 좌표계 변환...")
    slope_shp = os.path.join(settings.DATA_DIR, "Vworld", "slope", "ASIT_SOILSLOPE_AREA.shp")
    slope_gdf = gpd.read_file(slope_shp, encoding='cp949')
    slope_gdf.set_crs(epsg=VWORLD_CRS, inplace=True, allow_override=True)
    slope_gdf = slope_gdf.to_crs(WGS84)
    print(f"   경사도 폴리곤 {len(slope_gdf)}개, CRS → WGS84")

    # ── 2. 산책로 선형 SHP 로드 (WGS84) ──────────────────────────────
    print("2. 산책로 선형 SHP 로드...")
    trail_shp_path = os.path.join(
        settings.DATA_DIR, "PTP019401",
        "ECLGY_CLTUR_ST_2015_W_SHP", "ECLGY_CLTUR_ST_2015_W.shp"
    )
    trail_line_gdf = gpd.read_file(trail_shp_path, encoding='cp949')
    # PRJ 확인 결과 WGS84
    if trail_line_gdf.crs is None:
        trail_line_gdf.set_crs(WGS84, inplace=True)
    else:
        trail_line_gdf = trail_line_gdf.to_crs(WGS84)
    print(f"   선형 피처 {len(trail_line_gdf)}개")

    # ── 3. GPX 파일 로드 ──────────────────────────────────────────────
    print("3. GPX 파일 로드...")
    gpx_dir = os.path.join(settings.DATA_DIR, "PTP019401", "서울둘레길 코스별 GPX 파일")
    gpx_lines = []  # list of (filename, LineString)
    if os.path.exists(gpx_dir):
        for f in os.listdir(gpx_dir):
            if f.endswith(".gpx"):
                pts = parse_gpx_points(os.path.join(gpx_dir, f))
                if len(pts) >= 2:
                    gpx_lines.append((f, LineString(pts)))
    print(f"   GPX 코스 {len(gpx_lines)}개")

    # ── 4. 산책로 CSV 로드 (시작점 좌표) ─────────────────────────────
    print("4. 산책로 CSV 로드...")
    trail_df = pd.read_csv(settings.PET_TRAIL_CSV)
    # PNTM_XCRD=경도(lng), PNTM_YCRD=위도(lat) 확인됨 (126.8 range)
    trail_df_gdf = gpd.GeoDataFrame(
        trail_df,
        geometry=gpd.points_from_xy(trail_df.PNTM_XCRD, trail_df.PNTM_YCRD),
        crs=WGS84
    )

    def sample_line_slope(geom, n_samples=20) -> dict | None:
        """LineString에서 n_samples 개 위경도 점을 뽑아 경사도 폴리곤과 sjoin"""
        pts = [geom.interpolate(i / (n_samples - 1), normalized=True) for i in range(n_samples)]
        pts_gdf = gpd.GeoDataFrame(geometry=pts, crs=WGS84)
        joined = gpd.sjoin(pts_gdf, slope_gdf[['SOILSLOPE', 'geometry']], how='left', predicate='within')
        vals = joined['SOILSLOPE'].dropna().tolist()
        if not vals:
            return None
        nums = [val_to_num(v) for v in vals if val_to_num(v) is not None]
        if not nums:
            return None
        avg = round(sum(nums) / len(nums), 1)
        rep = vals[len(vals) // 2]
        return {"lvl": categorize_slope(avg), "val": rep, "avg": avg}

    # ── 5. 선형 SHP 피처별 경사도 분석 & 이름 매핑 ──────────────────
    print("5. 선형 SHP 경사도 분석...")
    shp_cache: dict[str, dict] = {}
    for idx, row in trail_line_gdf.iterrows():
        name = row.get('NAME', '').strip()
        if not name:
            continue
        result = sample_line_slope(row.geometry)
        if result:
            shp_cache[name] = result
    print(f"   SHP 완료: {len(shp_cache)}개")

    # ── 6. GPX 피처별 경사도 분석 ────────────────────────────────────
    print("6. GPX 경사도 분석...")
    gpx_cache: dict[str, dict] = {}
    for fname, line_geom in gpx_lines:
        result = sample_line_slope(line_geom)
        if result:
            gpx_cache[fname.replace('.gpx', '')] = result
    print(f"   GPX 완료: {len(gpx_cache)}개")

    # ── 7. 산책로 CSV 각 항목에 경사도 매핑 ─────────────────────────
    print("7. 산책로 CSV 항목 매핑...")
    final_cache = {}
    for _, row in trail_df.iterrows():
        name = row['TRL_NM']

        # A) SHP의 NAME에서 isin 방식으로 유사 이름 검색
        matched = None
        for shp_name, res in shp_cache.items():
            if name in shp_name or shp_name in name:
                matched = res
                break

        # B) GPX에서도 유사 이름 탐색
        if matched is None:
            for gpx_name, res in gpx_cache.items():
                kw = name.replace(" ", "")
                gk = gpx_name.replace(" ", "")
                if kw in gk or gk in kw:
                    matched = res
                    break

        # C) 아무것도 없으면 CSV 시작점(Point)으로 직접 sjoin
        if matched is None:
            pt_gdf = trail_df_gdf[trail_df_gdf['TRL_NM'] == name][['geometry']]
            joined = gpd.sjoin(pt_gdf, slope_gdf[['SOILSLOPE', 'geometry']], how='left', predicate='within')
            vals = joined['SOILSLOPE'].dropna().tolist()
            if vals:
                nums = [val_to_num(v) for v in vals if val_to_num(v) is not None]
                avg = round(sum(nums) / len(nums), 1) if nums else None
                matched = {"lvl": categorize_slope(avg), "val": vals[0], "avg": avg}

        final_cache[name] = matched if matched else {"lvl": "정보 없음", "val": "상세 경로 없음", "avg": None}

    # ── 8. 공원 처리 (위경도 기반 sjoin) ─────────────────────────────
    print("8. 공원 sjoin 처리...")
    park_df = pd.read_csv(settings.PARK_CSV_PATH, encoding='cp949')
    park_gdf = gpd.GeoDataFrame(
        park_df,
        geometry=gpd.points_from_xy(park_df['X좌표(WGS84)'], park_df['Y좌표(WGS84)']),
        crs=WGS84
    )
    park_joined = gpd.sjoin(park_gdf, slope_gdf[['SOILSLOPE', 'geometry']], how='left', predicate='within')
    for _, row in park_joined.iterrows():
        pname = row['공원명']
        sval = row.get('SOILSLOPE')
        import pandas as pd_inner
        if pd_inner.notna(sval):
            num = val_to_num(sval)
            final_cache[pname] = {"lvl": categorize_slope(num), "val": sval, "avg": num}
        else:
            final_cache[pname] = {"lvl": "정보 없음", "val": "위치 외 지역", "avg": None}

    # ── 9. 저장 ──────────────────────────────────────────────────────
    output_path = os.path.join(settings.DATA_DIR, "slope_cache.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_cache, f, ensure_ascii=False, indent=2)

    matched_count = sum(1 for v in final_cache.values() if v.get('avg') is not None)
    print(f"\n완료! 총 {len(final_cache)}개 중 {matched_count}개 경사도 매핑 성공 → {output_path}")


if __name__ == "__main__":
    run_real_preprocessing()
