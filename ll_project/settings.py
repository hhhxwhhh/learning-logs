"""
Django settings for 知迹 Learning Log.

配置全部来自环境变量（.env 或容器环境），仓库里不再写死密钥。
开发环境默认可用；生产环境通过 DJANGO_DEBUG=0 切换。
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """把常见的真值写法统一解析成布尔值。"""
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """逗号分隔的环境变量转成列表。"""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------------------
# 基础安全配置
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-1e2f3a4b5c6d7e8f9g0h-change-me-in-production",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
if DEBUG:
    # 本地调试 / 测试客户端常用主机名
    ALLOWED_HOSTS += ["testserver", "0.0.0.0"]

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# ---------------------------------------------------------------------------
# 应用
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # 本项目
    "learning_logs",
    "accounts",
    "analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# 生产环境优先用 WhiteNoise 直接托管静态文件（未安装时自动跳过，不影响开发）
if importlib.util.find_spec("whitenoise") and not DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "ll_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ll_project.wsgi.application"
ASGI_APPLICATION = "ll_project.asgi.application"

# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("DJANGO_DB_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}

# ---------------------------------------------------------------------------
# 密码校验
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.CustomUser"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# ---------------------------------------------------------------------------
# 国际化
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# 静态文件与媒体文件
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if importlib.util.find_spec("whitenoise") and not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024

# ---------------------------------------------------------------------------
# 登录相关
# ---------------------------------------------------------------------------
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "learning_logs:dashboard"
LOGOUT_REDIRECT_URL = "learning_logs:index"

# ---------------------------------------------------------------------------
# 安全加固（仅生产环境生效）
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # 前端 fetch 需要读取 csrftoken
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "learning_logs": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# AI 配置：默认走本地 Ollama 的 OpenAI 兼容接口，也可切到任意兼容服务
# ---------------------------------------------------------------------------
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")  # ollama / openai / mock
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://localhost:11434/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "ollama")
AI_MODEL = os.getenv("AI_MODEL", "qwen2.5:7b")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "120"))
AI_MAX_CONTEXT_MESSAGES = int(os.getenv("AI_MAX_CONTEXT_MESSAGES", "16"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "1800"))
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.6"))

# 前端下拉框可选模型，格式：模型ID|显示名，多个用逗号分隔
# 例如 AI_MODELS="deepseek-chat|DeepSeek V3,gpt-4o-mini|GPT-4o mini"
AI_AVAILABLE_MODELS = [
    {
        "id": item.split("|", 1)[0].strip(),
        "name": (item.split("|", 1)[1] if "|" in item else item).strip(),
    }
    for item in env_list(
        "AI_MODELS",
        "qwen2.5:7b|通义千问 2.5 · 本地,deepseek-r1:8b|DeepSeek R1 · 本地,"
        "llama3.1:8b|Llama 3.1 · 本地",
    )
]
