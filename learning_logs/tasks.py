"""后台任务。

有 Celery broker 时任务交给 worker 异步跑，没有时在请求线程里同步跑
（settings 里的 CELERY_TASK_ALWAYS_EAGER 会自动切换）。
两种模式下对外接口一致，调用方不用关心。
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)


def dispatch(task, *args, **kwargs):
    """投递任务；投递失败时退回同步执行，保证业务不中断。"""
    try:
        return task.delay(*args, **kwargs)
    except Exception:
        logger.warning("任务投递失败，改为同步执行：%s", getattr(task, "name", task), exc_info=True)
        return task(*args, **kwargs)


@shared_task(name="learning_logs.tasks.refresh_notifications")
def refresh_notifications(user_id: int | None = None) -> int:
    """生成站内提醒，返回新提醒条数。"""
    from .services import notifications as notifications_service

    users = get_user_model().objects.all()
    if user_id is not None:
        users = users.filter(id=user_id)

    created = 0
    for user in users:
        try:
            created += notifications_service.generate(user)
        except Exception:
            logger.warning("生成提醒失败：user=%s", user_id, exc_info=True)
    return created


@shared_task(name="learning_logs.tasks.refresh_insights")
def refresh_insights(user_id: int | None = None) -> int:
    """预热洞察与图谱缓存，读页面时就不用现算。"""
    from .services import graph as graph_service
    from .services import insights as insights_service

    users = get_user_model().objects.all()
    if user_id is not None:
        users = users.filter(id=user_id)

    count = 0
    for user in users:
        try:
            insights_service.build(user)
            graph_service.build(user)
            count += 1
        except Exception:
            logger.warning("预热缓存失败：user=%s", user_id, exc_info=True)
    return count


@shared_task(name="learning_logs.tasks.generate_weekly_report")
def generate_weekly_report(user_id: int, model: str | None = None) -> int:
    """生成学习周报。周报要跑模型，放在 worker 里不占着请求。"""
    from .services import report as report_service

    user = get_user_model().objects.filter(id=user_id).first()
    if user is None:
        return 0
    try:
        report_service.generate(user, timezone.localdate() - timedelta(days=7), model=model)
    except Exception:
        logger.warning("周报生成失败：user=%s", user_id, exc_info=True)
        return 0
    return 1


@shared_task(name="learning_logs.tasks.prune_event_log")
def prune_event_log() -> int:
    """清理过期的事件日志。"""
    from django.conf import settings

    from .models import EventLog

    days = getattr(settings, "EVENT_LOG_RETENTION_DAYS", 30)
    deadline = timezone.now() - timedelta(days=days)
    deleted, _ = EventLog.objects.filter(created_at__lt=deadline).delete()
    return deleted
