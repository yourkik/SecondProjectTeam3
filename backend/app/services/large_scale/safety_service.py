"""
safety_service.py (Simplified)
============================
환경 데이터(경사, 바닥재질, 날씨)에 근거한 공통 안전 가이드를 생성합니다.
견종별 복잡한 분류는 제거되었습니다.
"""

from typing import List, Optional
from app.models.large_scale.trail import TrailInfo

# 바닥 재질 분류
HARD_SOILS = ["인공지", "암석지"]

def get_safety_tips(item: TrailInfo, weather_temp: Optional[float] = None) -> List[str]:
    """
    아이템의 환경 정보에 근거한 범용 안전 팁 리스트를 반환합니다.
    """
    tips = []
    
    # 1. 경사도 관련 팁
    if item.slope_lvl == "경사":
        tips.append("⚠️ 경사가 가파른 구간이 포함되어 있습니다. 관절이 약한 경우 주의가 필요합니다.")
    elif item.slope_lvl == "완만":
        tips.append("⚠️ 완만한 경사가 있는 코스입니다.")
    elif item.slope_lvl == "평지":
        tips.append("✨ 경사가 없는 평탄한 길로, 누구나 부담 없이 산책하기 좋은 코스입니다.")

    # 2. 바닥 재질 관련 팁
    is_hard_ground = any(soil in (item.soil_type or "") for soil in HARD_SOILS)
    if is_hard_ground:
        tips.append(f"⚠️ 바닥({item.soil_type})이 딱딱하여 관절에 무리가 갈 수 있으니 서행해 주세요.")
    elif any(soft in (item.soil_type or "") for soft in ["흙", "사질", "모래", "사양질"]):
        tips.append("✨ 쿠션감이 있는 부드러운 바닥이 포함되어 있어 반려동물 관절 보호에 유리합니다.")

    return tips

def inject_safety_tips(items: List[TrailInfo], weather_temp: Optional[str] = None):
    """
    추천 리스트 전체에 안전 가이드를 주입합니다.
    """
    temp_float = None
    if weather_temp:
        try:
            temp_float = float(weather_temp)
        except ValueError:
            pass

    for item in items:
        item.safety_tips = get_safety_tips(item, temp_float)
