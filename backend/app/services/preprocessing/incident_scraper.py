import urllib.request
import xml.etree.ElementTree as ET  # JSON 대신 XML을 파싱하기 위한 내장 모듈
import json
import os
import sys
from pathlib import Path
from pyproj import Proj, transform

# 현재 파일 위치에서 3단계 부모 폴더(backend)를 찾아 PATH에 추가
project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.config import settings

def safe_float(val, default=0.0):
    """빈 문자열이나 None을 안전하게 float로 변환합니다."""
    try:
        if val is None or str(val).strip() == "":
            return default
        return float(val)
    except ValueError:
        return default

def update_incidents():
    """
    서울시 돌발정보(TOPIS) API를 XML로 호출하여 파싱한 뒤, JSON 파일로 캐싱하는 스크립트
    """
    output_path = os.path.join(settings.DATA_DIR, "seoul_incidents.json")
    os.makedirs(settings.DATA_DIR, exist_ok=True)

    try:
        api_key = settings.SEOUL_CITY_API_KEY.strip()
        
        # 💡 핵심 변경: URL 중간의 json을 xml로 변경!
        url = f"http://openapi.seoul.go.kr:8088/{api_key}/xml/AccInfo/1/100"
        
        req = urllib.request.Request(url)
        res = urllib.request.urlopen(req, timeout=5)
        raw_data = res.read().decode('utf-8')
        
        # 💡 핵심 변경: 응답받은 XML 데이터를 파싱
        root = ET.fromstring(raw_data)
        
        # API 내부 에러(ERROR-XXX) 체크 로직
        code_elem = root.find('.//CODE')
        if code_elem is not None and code_elem.text.startswith('ERROR'):
            msg_elem = root.find('.//MESSAGE')
            error_msg = msg_elem.text if msg_elem is not None else "Unknown Error"
            raise Exception(f"서울시 API 에러: {code_elem.text} - {error_msg}")

        incidents = []
        
        # <row> 태그(개별 돌발정보)들을 모두 찾아서 순회
        for row in root.findall('.//row'):
            # 태그 안의 텍스트를 안전하게 가져오는 내부 헬퍼 함수
            def get_text(tag_name):
                elem = row.find(tag_name)
                return elem.text if elem is not None else ""

            raw_x = safe_float(get_text('grs80tm_x'))
            raw_y = safe_float(get_text('grs80tm_y'))
            
            lat, lng = 0.0, 0.0
            
            if raw_y > 1000:
                 # GRS80 TM 중부원점 (서울시 표준)
                 proj_tm = Proj(init='epsg:5181') 
                 # WGS84 (일반적인 위경도)
                 proj_wgs84 = Proj(init='epsg:4326') 

                 # 변환 실행! (주의: transform은 x, y 순서로 넣습니다)
                 # 최신 pyproj에서는 transform 대신 Transformer 클래스를 권장하기도 하지만, 
                 # 간단한 스크립트에서는 여전히 잘 작동합니다.
                 lng, lat = transform(proj_tm, proj_wgs84, raw_x, raw_y)

            incidents.append({
                "acc_id": get_text('acc_id'),
                "acc_type": get_text('acc_type'),
                "acc_info": get_text('acc_info'),
                "lat": lat,
                "lng": lng
            })
        
        # 파싱된 정상 데이터를 JSON 파일로 예쁘게 저장
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(incidents, f, ensure_ascii=False, indent=2)
            
        print(f"Success! Cached {len(incidents)} incidents to {output_path}")
        return incidents
        
    except Exception as e:
        print(f"Error fetching TOPIS Incident data: {e}. 목업 데이터로 대체합니다.")
        
        mock_incidents = [
            {"acc_id": "MOCK-1", "acc_type": "공사", "acc_info": "강동구청 앞 송수관 교체 공사", "lat": 37.5284, "lng": 127.1245},
            {"acc_id": "MOCK-2", "acc_type": "행사", "acc_info": "올림픽공원 평화의광장 걷기 대회 (일부 통제)", "lat": 37.5204, "lng": 127.1158},
            {"acc_id": "MOCK-3", "acc_type": "사고", "acc_info": "천호역 사거리 추돌 사고로 혼잡", "lat": 37.5385, "lng": 127.1235}
        ]
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(mock_incidents, f, ensure_ascii=False, indent=2)
            
        return mock_incidents

if __name__ == "__main__":
    update_incidents()