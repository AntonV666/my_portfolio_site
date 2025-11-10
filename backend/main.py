# main.py

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import URL
import os
import sqlite3
import threading
from datetime import datetime

DB_PATH = "analytics.sqlite3"
ADMIN_KEY = os.getenv("ADMIN_KEY", "changeme")  # задай в .env/окружении

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="backend/templates")

# --- SQLite (потокобезопасный доступ через лок) ---
_db_lock = threading.Lock()

def init_db():
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            ip TEXT,
            ua TEXT,
            path TEXT,
            referer TEXT
        )
        """)
        conn.commit()
        conn.close()

def log_visit(ip: str, ua: str, path: str, referer: str):
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO visits (ts, ip, ua, path, referer) VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(timespec="seconds"), ip, ua, path, referer)
        )
        conn.commit()
        conn.close()

def get_total_views() -> int:
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("SELECT COUNT(*) FROM visits")
        (cnt,) = cur.fetchone()
        conn.close()
    return cnt

@app.on_event("startup")
def _on_startup():
    init_db()

# --- Middleware: логируем все HTML-запросы, кроме статики и /admin/stats ---
class VisitLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        url: URL = request.url
        path = request.url.path

        skip = (
            path.startswith("/static")
            or path.startswith("/favicon")
            or path.startswith("/admin/stats")  # чтобы не крутить счётчик при просмотре статистики
        )

        response = await call_next(request)

        content_type = response.headers.get("content-type", "")
        is_html = "text/html" in content_type or path in ("/", "/index", "/index.html")

        if not skip and is_html:
            ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "")
            ua = request.headers.get("user-agent", "")
            referer = request.headers.get("referer", "")
            # логируем «как есть»
            try:
                log_visit(ip, ua, path, referer)
            except Exception:
                pass  # не ломаем рендер из-за логгера
        return response

app.add_middleware(VisitLoggerMiddleware)

# --- Маршруты ---

def require_admin(key: str | None):
    if key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    total = get_total_views()
    # покажем счётчик на главной
    return templates.TemplateResponse("index.html", {"request": request, "total_views": total})

@app.get("/admin/stats", response_class=HTMLResponse)
async def admin_stats(request: Request, key: str | None = None, _ok: bool = Depends(require_admin)):
    # последние 200 визитов
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.execute("""
            SELECT ts, ip, ua, path, COALESCE(referer,'')
            FROM visits
            ORDER BY id DESC
            LIMIT 200
        """)
        rows = cur.fetchall()
        conn.close()

    # простая HTML-таблица
    html = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Статистика</title>",
        "<style>body{font-family:Arial,sans-serif;margin:20px} table{border-collapse:collapse;width:100%} th,td{border:1px solid #ddd;padding:8px} th{background:#f3f6fa;text-align:left}</style>",
        "</head><body>",
        "<h2>Последние визиты (200)</h2>",
        "<table><tr><th>Время (UTC)</th><th>IP</th><th>User-Agent</th><th>Путь</th><th>Referer</th></tr>"
    ]
    for ts, ip, ua, path, ref in rows:
        html.append(f"<tr><td>{ts}</td><td>{ip}</td><td>{ua}</td><td>{path}</td><td>{ref}</td></tr>")
    html.append("</table></body></html>")
    return HTMLResponse("".join(html))

# Опционально: «сухая» метрика для Prometheus/healthcheck
@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return f"portfolio_total_views {get_total_views()}\n"


# from fastapi import FastAPI, Request
# from fastapi.responses import HTMLResponse
# from fastapi.staticfiles import StaticFiles
# from fastapi.templating import Jinja2Templates

# app = FastAPI()
# app.mount("/static", StaticFiles(directory="static"), name="static")
# # templates = Jinja2Templates(directory="templates")
# templates = Jinja2Templates(directory="backend/templates")

# @app.get("/", response_class=HTMLResponse)
# async def read_root(request: Request):
#     return templates.TemplateResponse("index.html", {"request": request})
