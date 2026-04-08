# ☁️ Azure 배포 및 지속적 업데이트(CI/CD) 통합 가이드

이 문서는 현재 개발된 **FastAPI 기반 반려동물 산책로 추천 시스템**을 Azure 클라우드에 안정적으로 탑재하고, 향후 기능이 추가될 때마다 자동으로 반영되는 무중단 배포 환경을 구축하는 방법을 설명합니다.

---

## 1. 아키텍처 구상: Web App for Containers

우리 프로젝트는 대용량 공간 데이터 파일(`data/` 폴더)에 의존하므로, 라이브러리와 데이터 환경을 통째로 패키징하는 **Docker 컨테이너 방식**을 권장합니다.

*   **Azure App Service:** 웹 서버 호스팅 (FastAPI 구동)
*   **Azure Container Registry (ACR):** 빌드된 Docker 이미지를 저장하는 클라우드 저장소
*   **GitHub Actions:** 코드 변경 시 자동으로 빌드-푸시-배포를 수행하는 자동화 파이프라인

---

## 2. 배포 준비: Dockerfile 작성

프로젝트 최상위 디렉토리에 다음 `Dockerfile`을 생성합니다. (backend와 data 폴더를 위계에 맞게 포함해야 합니다.)

```dockerfile
# 1. 베이스 이미지 선택
FROM python:3.10-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 데이터 및 소스코드 복사
COPY data/ /app/data/
COPY backend/ /app/backend/

# 4. 종속성 설치
WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements.txt

# 5. 환경 변수 기본값 설정 (Azure Portal에서 덮어쓰기 가능)
ENV PORT=8000

# 6. 서버 실행 (uvicorn)
CMD ["sh", "-content", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
```

---

## 3. Azure 리소스 생성 (CLI 기준)

1.  **리소스 그룹 생성:**
    `az group create --name pet-walk-rg --location koreacentral`
2.  **컨테이너 레지스트리 생성:**
    `az acr create --resource-group pet-walk-rg --name petwalkacr --sku Basic`
3.  **App Service 플랜 생성:**
    `az appservice plan create --name pet-walk-plan --resource-group pet-walk-rg --is-linux --sku B1`
4.  **Web App 생성:**
    `az webapp create --resource-group pet-walk-rg --plan pet-walk-plan --name pet-walk-app --deployment-container-image-name petwalkacr.azurecr.io/backend:latest`

---

## 4. 🔄 기능 추가 시 업데이트 프로세스 (CI/CD)

기능이 추가되었을 때 수동으로 배포하지 않고 **GitHub Actions**를 통해 자동화합니다.

### GitHub 워크플로우 설정 (`.github/workflows/deploy.yml`)
```yaml
name: Continuous Deployment to Azure

on:
  push:
    branches: [ "main" ] # main 브랜치에 코드가 푸시되면 실행

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      # 1. Docker 이미지 빌드 및 ACR 푸시
      - name: Build and push image to ACR
        run: |
          docker login ${{ secrets.ACR_LOGIN_SERVER }} -u ${{ secrets.ACR_USERNAME }} -p ${{ secrets.ACR_PASSWORD }}
          docker build -t ${{ secrets.ACR_LOGIN_SERVER }}/backend:${{ github.sha }} -f ./Dockerfile .
          docker push ${{ secrets.ACR_LOGIN_SERVER }}/backend:${{ github.sha }}

      # 2. Azure Web App 설정 업데이트 (새 이미지로 교체)
      - name: Deploy to Azure Web App
        uses: azure/webapps-deploy@v2
        with:
          app-name: 'pet-walk-app'
          publish-profile: ${{ secrets.AZURE_WEBAPP_PUBLISH_PROFILE }}
          images: '${{ secrets.ACR_LOGIN_SERVER }}/backend:${{ github.sha }}'
```

> [!TIP]
> **기능 추가 시 시나리오:**
> 1. 개발자가 로컬에서 새로운 추천 알고리즘을 코딩하고 테스트합니다.
> 2. `git commit` 후 GitHub의 `main` 브랜치로 `push` 합니다.
> 3. GitHub Actions가 자동으로 Docker 이미지를 다시 굽고 Azure 서버에 "새 버전이 나왔으니 교체해!"라고 명령합니다.
> 4. 약 2~3분 뒤 모바일/웹 사용자는 자동으로 업데이트된 기능을 만나보게 됩니다.

---

## 5. 🔐 환경 변수 보안 관리

`.env` 파일은 절대 클라우드(Git)에 올리지 않습니다. 대신 Azure Portal에서 관리합니다.

1.  **Azure Portal** 접속 -> **pet-walk-app** 선택
2.  **Configuration (구성)** 섹션으로 이동
3.  **New application setting** 클릭
4.  `SEOUL_CITY_API_KEY`, `DISASTER_API_KEY` 등을 직접 입력하고 저장합니다.
    *   *서버는 코드 수정 없이 이 설정값을 우선적으로 읽어옵니다.*

---

## 6. 🚧 주의사항 및 레이아웃 유지

*   **데이터 용량:** `data/` 폴더가 기하급수적으로 커질 경우(예: 500MB 초과) Docker 빌드 시간이 길어집니다. 이 경우 **Azure Files** 스토리지를 별도로 생성하여 컨테이너에 마운트하는 방식을 권장합니다.
*   **포트 바인딩:** Azure App Service는 기본적으로 컨테이너의 80번 또는 8080번 포트를 기다립니다. `WEBSITES_PORT` 설정을 8000으로 맞추거나 Dockerfile에서 포트를 조정해야 합니다.
