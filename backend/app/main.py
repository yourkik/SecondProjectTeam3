from fastapi import FastAPI
from fastapi.responses import FileResponse
import os
from app.api.routes import recommend
from app.api.routes import loop_route

app = FastAPI(
    title="Pet Walkway Recommendation API",
    description="반려견 산책로 추천 API — LargeScale(공원·산책로) + SmallScale(주변 루프 경로)",
    version="2.0.0"
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
