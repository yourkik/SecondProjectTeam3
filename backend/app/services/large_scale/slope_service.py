"""
slope_service.py
================
경사도 정보를 PostgreSQL walk_features 테이블에서 조회합니다.
기존 JSON 캐시 파일(slope_cachev2.json) 방식을 DB 방식으로 대체합니다.

walk_features 주요 컬럼:
  - avg_slope  (float8) : 평균 경사도 수치 (%)
  - slope_type (text)   : 경사도 등급 텍스트 (예: 평지, 완만, 경사)
  - road_descri (text)  : 도로/산책로 이름
"""

from typing import List
from app.models.large_scale.trail import TrailInfo
from app.core.db import fetch_all

# 서버 수명 동안 1회만 로드하는 인메모리 캐시
_slope_cache: dict | None = None


def _load_slope_cache_from_db() -> dict:
    """
    walk_features 테이블에서 경사도 정보를 전부 로드하여
    {trail_name: {lvl, val, avg}} 형태의 딕셔너리로 반환합니다.
    기존 JSON 캐시와 동일한 구조를 유지합니다.
    """
    rows = fetch_all("""
        SELECT
            trail_name,
            avg_slope,
            slope_type
        FROM trail_features
        WHERE trail_name IS NOT NULL
          AND avg_slope  IS NOT NULL
    """)

    cache = {}
    for row in rows:
        name = str(row["trail_name"]).strip()
        raw_avg = row["avg_slope"]
        
        # 사용자의 요청에 따라 0.0%는 데이터가 없는 것으로 간주함
        if raw_avg == 0.0:
            lvl = "정보 없음"
            val = "-"
            avg = None
        else:
            lvl = _categorize_slope(raw_avg)
            val = f"{raw_avg:.1f}%"
            avg = round(float(raw_avg), 2)

        cache[name] = {
            "lvl": lvl,
            "val": val,
            "avg": avg,
        }

    print(f"[slope_service] DB에서 경사도 {len(cache)}건 로드 완료")
    return cache


def _categorize_slope(avg_pct: float) -> str:
    """평균 경사 수치(%)로 등급 분류 (DB slope_type이 없을 때 폴백)"""
    if avg_pct is None or avg_pct == 0.0:
        return "정보 없음"
    if avg_pct < 3.0:
        return "평지"
    elif avg_pct < 8.0:
        return "완만"
    else:
        return "경사"


def load_slope_cache() -> dict:
    """인메모리 캐시 반환 (최초 1회만 DB 조회)"""
    global _slope_cache
    if _slope_cache is None:
        try:
            _slope_cache = _load_slope_cache_from_db()
        except Exception as e:
            print(f"[slope_service] DB 로드 실패, 빈 캐시로 폴백: {e}")
            _slope_cache = {}
    return _slope_cache


def inject_slope_info(items: List[TrailInfo]):
    """
    추천된 산책로/공원 리스트를 받아 경사도 정보를 주입합니다.
    """
    cache = load_slope_cache()
    if not cache:
        return

    for item in items:
        # 1. 완전 일치
        slope_data = cache.get(item.trail_name)

        # 2. 부분 일치
        if not slope_data:
            for cache_name, data in cache.items():
                if item.trail_name in cache_name or cache_name in item.trail_name:
                    slope_data = data
                    break

        if slope_data:
            item.slope_lvl = slope_data.get("lvl")
            item.slope_val = slope_data.get("val")
            item.slope_avg = slope_data.get("avg")
        else:
            item.slope_lvl = "정보 없음"
            item.slope_val = "-"
            item.slope_avg = None
