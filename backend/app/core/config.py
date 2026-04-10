import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Settings:
    """
    애플리케이션 전역 설정 및 데이터 경로를 일괄 관리하는 클래스입니다.
    """
    # app/core 폴더의 절대 경로
    CORE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # backend 최상위 디렉토리 (app/core의 상위 2단계)
    BACKEND_DIR = os.path.dirname(os.path.dirname(CORE_DIR))
    
    # 공통 데이터 디렉토리 (backend 바깥쪽의 data 폴더)
    DATA_DIR = os.path.abspath(os.path.join(BACKEND_DIR, "../data/walkwayData"))
    
    # 개별 데이터셋 절대 경로
    PET_TRAIL_CSV = os.path.join(DATA_DIR, "TB_PTP_TRAIL_M_Pet.csv")
    SHP_DATA_PATH = os.path.join(DATA_DIR, "PTP019401", "ECLGY_CLTUR_ST_2015_W_SHP", "ECLGY_CLTUR_ST_2015_W.shp")
    GPX_DATA_DIR = os.path.join(DATA_DIR, "PTP019401", "서울둘레길 코스별 GPX 파일")
    PARK_CSV_PATH = os.path.join(DATA_DIR, "서울시 주요 공원현황.csv")
    
    # 서울 실시간 도시 데이터 API KEY (TOPIS 공용)
    SEOUL_CITY_API_KEY = os.getenv("SEOUL_CITY_API_KEY")
    
    # 공공데이터포털 행정안전부 재난문자 API KEY
    DISASTER_API_KEY = os.getenv("DISASTER_API_KEY")
    
    # SmallScale(주변 루프 경로) 데이터 경로
    OSM_EDGES_PATH = os.path.join(DATA_DIR, "osm", "edges_clean.geojson")
    OSM_LEISURE_PATH = os.path.join(DATA_DIR, "osm", "leisure_clean.geojson")
    OSM_STAIRS_PATH = os.path.join(DATA_DIR, "osm", "stairs.geojson")
    WEIGHTS_YAML_PATH = os.path.join(BACKEND_DIR, "config", "weights.yaml")

settings = Settings()
