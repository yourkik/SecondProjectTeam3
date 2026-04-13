FROM python:3.10-slim

WORKDIR /app

# 시스템 한글 폰트 및 빌드 의존성(GDAL 등 공간 라이브러리 지원) 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 패키지 매니저 업데이트 및 파이썬 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools \
    && pip install --no-cache-dir -r requirements.txt

# 코드 및 데이터 폴더 일괄 복사 (초대용량 원본 파일은 .dockerignore에서 제외됨)
COPY backend/ ./backend/
COPY data/ ./data/

# 앱 구동 포트
EXPOSE 8000

# 작업 디렉토리를 backend로 변경하여 uvicorn 실행 (app.main 위치)
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
