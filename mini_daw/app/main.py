"""
main.py

FastAPI 서버 엔트리포인트.
- 템플릿(index.html) 렌더링
- static 파일 서빙(app.js/app.css)
- API 라우터 등록
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes_project import router as project_router
from app.api.routes_chat import router as chat_router


app = FastAPI(title="Mini DAW (FastAPI)")


# 템플릿/정적 파일 연결
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# API 라우터
app.include_router(project_router)
app.include_router(chat_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """
    메인 UI 화면.

    주의:
    - UI 파일은 사용자가 제공한 ui.html을 index.html로 저장해두면 됩니다. :contentReference[oaicite:1]{index=1}
    """
    return templates.TemplateResponse("index.html", {"request": request})
