"""Celery 应用入口。

任务定义在 ``learning_logs.tasks``，由 Django 的 INSTALLED_APPS 自动发现。
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ll_project.settings")

app = Celery("zhiji")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
