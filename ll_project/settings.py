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
    "ll_project.middleware.RequestLogMiddleware",
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
                "learning_logs.context_processors.notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "ll_project.wsgi.application"
ASGI_APPLICATION = "ll_project.asgi.application"

# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------
# 数据库后端：默认 SQLite；设置 DJANGO_DB_ENGINE=postgres 即切到 PostgreSQL。
# 两种后端的差异都收在配置里，业务代码不感知。
_DB_ENGINE = os.getenv("DJANGO_DB_ENGINE", "sqlite").strip().lower()

if _DB_ENGINE in ("postgres", "postgresql", "psql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "zhiji"),
            "USER": os.getenv("POSTGRES_USER", "zhiji"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("POSTGRES_CONN_MAX_AGE", "60")),
            "OPTIONS": {"connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5"))},
        }
    }
else:
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
_LOG_FORMAT = os.getenv("DJANGO_LOG_FORMAT", "text")
if _LOG_FORMAT == "json":
    _request_formatter = {
        "format": "%(message)s",
        "style": "{",
    }
else:
    _request_formatter = {
        "format": "[{asctime}] {levelname} {name}: {message}",
        "style": "{",
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
        "request": _request_formatter,
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
        "request_console": {"class": "logging.StreamHandler", "formatter": "request"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "learning_logs": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "zhiji.request": {
            "handlers": ["request_console"],
            "level": os.getenv("DJANGO_REQUEST_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# AI 配置：默认走本地 Ollama 的 OpenAI 兼容接口，也可切到任意兼容服务
# ---------------------------------------------------------------------------AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")  # ollama / openai / mock
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

# ---------------------------------------------------------------------------
# Redis：缓存、任务队列与实时通道共用一个实例
#
# REDIS_URL 留空表示不依赖 Redis：缓存退回进程内缓存，异步任务同步执行，
# WebSocket 退回单进程通道层。这样在没有基础设施的机器上也能跑起来。
# ---------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                # Redis 不可用时静默跳过缓存，不让业务请求整体失败
                "IGNORE_EXCEPTIONS": True,
            },
            "KEY_PREFIX": os.getenv("CACHE_KEY_PREFIX", "zhiji"),
            "TIMEOUT": int(os.getenv("CACHE_TTL", "300")),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "zhiji-locmem",
            "TIMEOUT": int(os.getenv("CACHE_TTL", "300")),
        }
    }

# ---------------------------------------------------------------------------
# Celery：把周报、提醒、索引这类耗时活儿挪出请求线程
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", not CELERY_BROKER_URL)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "refresh-notifications": {
        "task": "learning_logs.tasks.refresh_notifications",
        "schedule": 1800.0,
    },
    "refresh-insights": {
        "task": "learning_logs.tasks.refresh_insights",
        "schedule": 3600.0,
    },
}

# ---------------------------------------------------------------------------
# Kafka：学习事件总线。没有 broker 时事件落到 Redis Stream 或本地库
# ---------------------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVERS = env_list("KAFKA_BOOTSTRAP_SERVERS")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "zhiji.learning.events")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "zhiji-consumer")
KAFKA_ENABLED = env_bool("KAFKA_ENABLED", bool(KAFKA_BOOTSTRAP_SERVERS))
KAFKA_CLIENT_ID = os.getenv("KAFKA_CLIENT_ID", "zhiji-web")
KAFKA_PRODUCER_TIMEOUT = float(os.getenv("KAFKA_PRODUCER_TIMEOUT", "3"))

# 事件总线落库保留天数与单用户活动流长度
EVENT_LOG_RETENTION_DAYS = int(os.getenv("EVENT_LOG_RETENTION_DAYS", "30"))
ACTIVITY_FEED_SIZE = int(os.getenv("ACTIVITY_FEED_SIZE", "60"))

# ---------------------------------------------------------------------------
# Channels：WebSocket 实时推送
# ---------------------------------------------------------------------------
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "learning_logs.api_auth.ApiTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PAGINATION_CLASS": "learning_logs.api_pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "learning_logs.api_errors.api_exception_handler",
}

