
import pandas as pd
import geopandas as gpd
import os
import re

# Paths - Using the new file provided by the user
SLOPE_PATH = r'workplace/data/Vworld/slope/gangnam_songpa_gangdong_soilslope.shp'
TRAIL_PATH = r'workplace/data/PTP019401/ECLGY_CLTUR_ST_2015_W_SHP/ECLGY_CLTUR_ST_2015_W.shp'
OUTPUT_DIR = r'workplace/data/processed'
OUTPUT_SHP = os.path.join(OUTPUT_DIR, 'trail_with_slope_final.shp')
OUTPUT_CSV = os.path.join(OUTPUT_DIR, 'trail_slope_summary_final.csv')

def parse_slope_string(s):
    """
    경사도 등급 문자열에서 중간 수치값을 추출합니다.
    """
    if not isinstance(s, str): return 0.0
    nums = re.findall(r'\d+', s)
    if len(nums) == 2:
        return (float(nums[0]) + float(nums[1])) / 2.0
    elif len(nums) == 1:
        return float(nums[0])
    if '고' in s or '湲' in s:
        return 80.0
    return 0.0

def run_integration():
    print('1. 데이터 로딩 및 좌표계 설정...')
    # cp949 인코딩으로 한글 속성 유지
    gdf_slope = gpd.read_file(SLOPE_PATH, encoding='cp949')
    gdf_trail = gpd.read_file(TRAIL_PATH, encoding='cp949')
    
    # EPSG:5181 좌표계 적용
    slope_crs = 'EPSG:5181'
    gdf_slope.crs = slope_crs
    gdf_trail = gdf_trail.to_crs(slope_crs)
    
    # 병합용 임시 ID 생성
    gdf_trail['TMP_ID'] = range(len(gdf_trail))
    
    # 산책로 데이터가 LineString이므로 면적이 아닌 길이(Length)를 가중치로 사용해야 함
    print('   데이터 타입 확인:', gdf_trail.geom_type.unique())
    is_line = 'LineString' in gdf_trail.geom_type.unique() or 'MultiLineString' in gdf_trail.geom_type.unique()

    print('2. 공간 중첩 분석 (Overlay Intersection)...')
    # overlay는 LineString과 Polygon 사이의 교차도 지원합니다.
    intersection = gpd.overlay(gdf_trail, gdf_slope, how='intersection')
    
    print(f'   추출된 조각 개수: {len(intersection)}')
    if len(intersection) == 0:
        print('오류: 공간적 중첩 영역을 찾을 수 없습니다.')
        return

    print('3. 가중 평균 경사도 계산 중 (Line length weighting)...')
    # 문자열 등급을 수치로 변환
    intersection['slope_num'] = intersection['SOILSLOPE'].apply(parse_slope_string)
    
    # 가중치 계산: 선형 데이터이므로 면적이 아닌 길이(.length) 사용
    intersection['weight'] = intersection.geometry.length if is_line else intersection.geometry.area
    intersection['weighted_prod'] = intersection['slope_num'] * intersection['weight']
    
    # 산책로 ID별로 그룹화하여 합계 계산
    agg = intersection.groupby('TMP_ID').agg({
        'weighted_prod': 'sum',
        'weight': 'sum'
    }).reset_index()
    
    # 최종 가중 평균
    agg['avg_result'] = agg['weighted_prod'] / agg['weight']
    
    # 원본 데이터와 결합
    final = gdf_trail.merge(agg[['TMP_ID', 'avg_result', 'weight']], on='TMP_ID', how='left')
    
    print('4. 결과 포맷팅...')
    def format_slope(row):
        val = row.get('avg_result')
        w = row.get('weight', 0)
        # 가중치(길이/면적)가 너무 작거나 없으면 정보 없음 처리
        if pd.isna(val) or w < 0.1:
            return '정보 없음'
        return "{:.1f}%".format(val)
    
    final['AVG_SLOPE'] = final.apply(format_slope, axis=1)
    
    # 임시 컬럼 제거
    cols_to_drop = ['TMP_ID', 'avg_result', 'weight', 'weighted_prod', 'slope_num']
    for col in cols_to_drop:
        if col in final.columns:
            final = final.drop(columns=col)
    
    print(f'5. 파일 저장 중...')
    final.drop(columns='geometry').to_csv(OUTPUT_CSV, encoding='cp949', index=False)
    final.to_file(OUTPUT_SHP, encoding='cp949')
    
    print('\n✅ 분석 성공!')
    valid_results = final[final['AVG_SLOPE'] != '정보 없음']
    print(f'   성공한 산책로 개수: {len(valid_results)} / {len(final)}')
    if len(valid_results) > 0:
        print('\n[결과 샘플]')
        print(valid_results[['NAME', 'AVG_SLOPE']].head(10))

if __name__ == "__main__":
    run_integration()
