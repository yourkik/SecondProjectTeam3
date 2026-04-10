# 🐾 반려동물 산책 시스템 통합 백엔드 가이드

본 서비스는 기존의 **LargeScale(공원·산책로 추천)** 기능과 새롭게 추가된 **SmallScale(집 주변 루프 경로 생성)** 기능을 통합한 FastAPI 백엔드입니다.

---

## 1. 사전 준비 (Environment Setup)

프로젝트 구동을 위해 Python 3.9 이상의 환경을 권장합니다.

```bash
# 1. 가상환경 생성 및 활성화
python -m venv venv

# Windows (Command Prompt)
venv\Scripts\activate.bat
# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Mac/Linux
source venv/bin/activate

# 2. 필수 패키지 설치
# (기존 대비 networkx, pyyaml 등이 추가되었습니다)
pip install -r requirements.txt
```

---

## 2. 서버 실행 및 접속 (Execution)

모든 데이터 파일이 `backend/../data` 경로에 있는지 확인한 후 실행합니다.

```bash
# /backend 폴더 내에서 실행!
uvicorn app.main:app --reload
```

*   **웹 인터페이스 접속**: [http://localhost:8000/map](http://localhost:8000/map)
*   **API 자동 문서(Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 3. 기능 안내 (Key Features)

상단 탭을 통해 두 가지 모드를 전환하며 사용할 수 있습니다.

### 🌲 LargeScale (산책로·공원 추천)
*   **용도**: 유명한 큰 공원이나 검증된 산책 코스를 방문하고 싶을 때 사용합니다.
*   **특징**: 기상청 날씨, 서울시 실시간 혼잡도, 경사도 분석 데이터가 결합된 추천 결과를 제공합니다.

### 🐾 SmallScale (주변 루프 경로 생성) - **NEW**
*   **용도**: 집 바로 앞에서 출발하여 지정한 시간만큼 돌고 다시 돌아오는 경로가 필요할 때 사용합니다.
*   **특징**: OSM 도로 데이터를 분석하여 **차도 기피, 계단 회피, 공원 선호** 가중치가 적용된 최적의 순환 코스를 생성합니다.
*   **⚠️ 주의**: 서버 시작 후 **최초 경로 생성 시 약 20~30초**가 소요됩니다 (도로 네트워크 그래프를 빌드하고 메모리에 대기시키는 과정입니다). 한 번 로드된 이후부터는 즉시 생성됩니다.

---

## 4. 경로 가중치 커스텀 (Customization)

산책 경로의 성향을 바꾸고 싶다면 `backend/config/weights.yaml` 파일을 수정하세요. 코드 수정 없이 즉시 반영됩니다.

*   `highway_weights`: 차도(primary, secondary) 기피 강도 조절
*   `leisure_bonus`: 공원이나 반려견 놀이터 근처 경로를 얼마나 우대할지 결정
*   `loop`: 원형 정규성(shape_regularity) 또는 산책 속도 설정

---

## 5. 트러블슈팅

*   **주소 검색이 정확하지 않아요**: OSM(Nominatim) 검색 엔진 특성상 상세 지번(444-20 등)은 인식이 어려울 수 있습니다. **"서울 강동구 성내동"**과 같이 행정구역 이름을 포함하면 더 높은 정확도로 검색됩니다.
*   **경로가 겹쳐서 보여요**: 지도 왼쪽 하단의 **'경로 토글 버튼'**을 사용하여 특정 경로만 골라서 확인하거나 전체를 비교할 수 있습니다.
