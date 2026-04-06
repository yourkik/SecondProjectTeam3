import os

class Settings:
    """
    애플리케이션 전역 설정 및 데이터 경로를 일괄 관리하는 클래스입니다.
    """
    # app/core 폴더의 절대 경로
    CORE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # backend 최상위 디렉토리 (app/core의 상위 2단계)
    BACKEND_DIR = os.path.dirname(os.path.dirname(CORE_DIR))
    
    # 공통 데이터 디렉토리 (backend 바깥쪽의 data 폴더)
    DATA_DIR = os.path.abspath(os.path.join(BACKEND_DIR, "../data"))
    
    # 개별 데이터셋 절대 경로
    PET_TRAIL_CSV = os.path.join(DATA_DIR, "walkwayData/TB_PTP_TRAIL_M_Pet.csv")
    SHP_DATA_PATH = os.path.join(DATA_DIR, "walkwayData/PTP019401", "ECLGY_CLTUR_ST_2015_W_SHP", "ECLGY_CLTUR_ST_2015_W.shp")
    GPX_DATA_DIR = os.path.join(DATA_DIR, "walkwayData/PTP019401", "서울둘레길 코스별 GPX 파일")
    
    # (추후 이곳에 날씨 DB 경로, 혼잡도 API Key 등을 추가하시면 됩니다)

settings = Settings()
