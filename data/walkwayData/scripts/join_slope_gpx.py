
import pandas as pd
import geopandas as gpd
import os
import re
import glob
import json
import xml.etree.ElementTree as ET
from shapely.geometry import LineString

# Paths
SLOPE_PATH = r'workplace/data/processed/slope_seoul_all.shp'
GPX_DIR = r'workplace/data/PTP019401/서울둘레길 코스별 GPX 파일'
OUTPUT_DIR = r'workplace/data'
OLD_CACHE_PATH = os.path.join(OUTPUT_DIR, 'slope_cache.json')
NEW_CACHE_PATH = os.path.join(OUTPUT_DIR, 'slope_cachev2.json')

def parse_slope_string(s):
    if not isinstance(s, str): return 0.0
    nums = re.findall(r'\d+', s)
    if len(nums) == 2:
        return (float(nums[0]) + float(nums[1])) / 2.0
    elif len(nums) == 1:
        return float(nums[0])
    if '고' in s or '湲' in s: return 80.0
    return 0.0

def get_lvl(val):
    if val >= 15.0: return '경사짐'
    if val >= 10.0: return '보통'
    if val >= 5.0: return '완만'
    return '평지'

def parse_gpx_to_gdf(file_path):
    """GPX 파일을 읽어 LineString GeoDataFrame으로 변환합니다."""
    tree = ET.parse(file_path)
    root = tree.getroot()
    
    points = []
    # GPX 네임스페이스 무시하고 trkpt 태그 검색
    for trkpt in root.iter():
        if trkpt.tag.endswith('trkpt'):
            lat = float(trkpt.attrib['lat'])
            lon = float(trkpt.attrib['lon'])
            points.append((lon, lat))
            
    if len(points) < 2:
        return None
        
    name = os.path.basename(file_path).replace('.gpx', '')
    line = LineString(points)
    
    gdf = gpd.GeoDataFrame([{'NAME': name, 'geometry': line}], crs='EPSG:4326')
    return gdf

def run_gpx_analysis():
    print('1. 경사도 데이터(전 서울) 로딩...')
    gdf_slope = gpd.read_file(SLOPE_PATH, encoding='cp949')
    gdf_slope.crs = 'EPSG:5181'
    
    print('2. GPX 파일 파싱 및 통합...')
    gpx_files = glob.glob(os.path.join(GPX_DIR, '*.gpx'))
    gpx_gdfs = []
    
    for f in gpx_files:
        gdf = parse_gpx_to_gdf(f)
        if gdf is not None:
            gpx_gdfs.append(gdf)
            
    if not gpx_gdfs:
        print('오류: 처리할 GPX 파일이 없습니다.')
        return
        
    gdf_trails = pd.concat(gpx_gdfs, ignore_index=True)
    gdf_trails = gdf_trails.to_crs('EPSG:5181')
    gdf_trails['TMP_ID'] = range(len(gdf_trails))
    
    print('3. 공간 중첩 분석 (GPX x Slope)...')
    intersection = gpd.overlay(gdf_trails, gdf_slope, how='intersection')
    
    print('4. 코스별 가중 평균 경사도 계산...')
    intersection['slope_num'] = intersection['SOILSLOPE'].apply(parse_slope_string)
    intersection['length'] = intersection.geometry.length
    intersection['weighted_prod'] = intersection['slope_num'] * intersection['length']
    
    agg = intersection.groupby('TMP_ID').agg({
        'weighted_prod': 'sum',
        'length': 'sum'
    })
    agg['avg_result'] = agg['weighted_prod'] / agg['length']
    
    final_results = gdf_trails.merge(agg[['avg_result', 'length']], left_on='TMP_ID', right_index=True, how='left')
    
    # 캐시 데이터 생성용 딕셔너리 구성
    gpx_cache = {}
    for _, row in final_results.iterrows():
        name = row['NAME']
        avg = row['avg_result']
        if pd.isna(avg) or row['length'] < 1.0:
            continue
            
        lvl = get_lvl(avg)
        gpx_cache[name] = {
            'lvl': lvl,
            'val': f'{avg:.1f}%',
            'avg': round(float(avg), 2)
        }
    
    print(f'   GPX 분석 완료: {len(gpx_cache)}개 코스')
    
    print('5. 기존 캐시와 통합하여 slope_cachev2.json 생성...')
    try:
        with open(OLD_CACHE_PATH, 'r', encoding='utf-8') as f:
            full_cache = json.load(f)
    except:
        full_cache = {}
        
    # 기존 데이터에 GPX 데이터 추가 (덮어쓰기 포함)
    full_cache.update(gpx_cache)
    
    with open(NEW_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(full_cache, f, ensure_ascii=False, indent=2)
        
    print(f'✅ 전 서울 권역 캐시 생성 완료: {NEW_CACHE_PATH}')
    print(f'   총 데이터 수: {len(full_cache)}개')

if __name__ == "__main__":
    run_gpx_analysis()
