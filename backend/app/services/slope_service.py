import json
import os
from typing import List
from app.models.trail import TrailInfo
from app.core.config import settings

# 전역 변수로 경사도 캐시 적재 (Lazy Loading)
_slope_cache = None

def load_slope_cache():
    """
    data/slope_cache.json 파일을 메모리에 로드합니다.
    (800MB SHP 파일을 전처리하여 만든 가벼운 매핑 파일)
    """
    global _slope_cache
    if _slope_cache is not None:
        return _slope_cache
    
    cache_path = os.path.join(settings.DATA_DIR, "slope_cachev2.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                _slope_cache = json.load(f)
                return _slope_cache
        except Exception as e:
            print(f"Error loading slope cache: {e}")
    
    _slope_cache = {}
    return _slope_cache

def inject_slope_info(items: List[TrailInfo]):
    """
    추천된 산책로/공원 리스트를 받아 경사도 정보를 주입합니다.
    성능이나 호환성 문제 발생 시 이 함수를 호출하지 않거나 내용을 비우는 것으로 쉽게 제어 가능합니다.
    """
    cache = load_slope_cache()
    if not cache:
        return # 캐시가 없으면 아무 작업도 하지 않음 (Graceful Fallback)

    for item in items:
        # 1. 완전 일치 검색
        slope_data = cache.get(item.trail_name)
        
        # 2. 부분 일치 검색 (완전 일치 항목이 없을 경우)
        if not slope_data:
            for cache_name, data in cache.items():
                # 산책로 이름이 캐시 이름에 포함되거나, 캐시 이름이 산책로 이름에 포함되는 경우
                if item.trail_name in cache_name or cache_name in item.trail_name:
                    slope_data = data
                    break
        
        if slope_data:
            # slope_data 예: {"lvl": "평탄", "val": "7-15%", "avg": 9.5}
            item.slope_lvl = slope_data.get("lvl")
            item.slope_val = slope_data.get("val")
            item.slope_avg = slope_data.get("avg")
        else:
            # 정보가 없는 경우 기본값 처리
            item.slope_lvl = "정보 없음"
            item.slope_val = "-"
            item.slope_avg = None
