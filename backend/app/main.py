from fastapi import FastAPI
from fastapi.responses import FileResponse
import os
from app.api.routes import recommend
from app.api.routes import loop_route

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Pet Walkway Recommendation API",
    description="반려견 산책로 추천 API — LargeScale(공원·산책로) + SmallScale(주변 루프 경로)",
    version="2.0.0"
)

# CORS (Cross-Origin Resource Sharing) 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 모든 도메인(앱, 외부 웹뷰 등)에서의 접근 허용
    allow_credentials=True,
    allow_methods=["*"], # GET, POST 등 모든 메소드 허용
    allow_headers=["*"], # 모든 헤더 허용
)

# LargeScale: 기존 산책로·공원 추천
app.include_router(recommend.router, prefix="/api/trails", tags=["LargeScale - 산책로·공원"])

# SmallScale: 신규 주변 루프 경로 추천
app.include_router(loop_route.router, prefix="/api/routes", tags=["SmallScale - 주변 루프 경로"])

@app.get("/")
def read_root():
    return {"message": "Pet Walkway Recommendation API is running!"}

@app.get("/map", summary="프론트엔드 맵 페이지")
def serve_map():
    html_path = os.path.join(os.path.dirname(__file__), "../index.html")
    return FileResponse(html_path)
