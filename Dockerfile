# 生产镜像：python:3.13-slim + Gunicorn + WhiteNoise
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pillow 运行期依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# 构建静态资源并用非 root 用户运行
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

CMD ["gunicorn", "ll_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
