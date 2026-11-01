# 生产镜像：前端用 Node 构建，后端用 Python 运行
#
# 阶段 1  node:22-alpine  构建 Vue 看板，产物落到 static/live
# 阶段 2  python:3.13-slim  安装依赖，用 uvicorn 起 ASGI（HTTP 与 WebSocket 共用一个入口）

# ---------------------------------------------------------------------------
# 前端构建
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY frontend/ ./
# vite 的 outDir 指向仓库的 static/live，这里再收一份到 /out 方便拷贝
RUN npm run build && mkdir -p /out && cp -r /static/live /out/live

# ---------------------------------------------------------------------------
# 后端运行
# ---------------------------------------------------------------------------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=frontend /out/live /app/static/live

RUN python manage.py collectstatic --noinput \
    && mkdir -p /app/data \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV DJANGO_DEBUG=0 \
    DJANGO_ALLOWED_HOSTS=* \
    DJANGO_DB_PATH=/app/data/db.sqlite3 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz/').status==200 else 1)"

CMD ["uvicorn", "ll_project.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "3", "--timeout-keep-alive", "75"]
