"""学习周报。"""

from __future__ import annotations

import logging

from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from ..ai.providers import AIError
from ..models import WeeklyReport
from ..services import report as report_service
from ..services import stats
from ..utils.markdown import render_markdown

logger = logging.getLogger(__name__)

@login_required
def weekly_report(request):
    """学习周报：本周数据 + AI 复盘。"""
    week_param = request.GET.get("week")
    start = report_service.week_start_of(stats.parse_date(week_param))
    data = report_service.collect(request.user, start)
    saved = WeeklyReport.objects.filter(user=request.user, week_start=start).first()

    today = timezone.localdate()
    next_week = start + timedelta(days=7)
    context = {
        "data": data,
        "saved": saved,
        "summary_html": render_markdown(saved.summary) if saved else "",
        "suggestions": report_service.suggestions(data),
        "week_start": start,
        "week_end": start + timedelta(days=6),
        "prev_week": start - timedelta(days=7),
        "next_week": next_week,
        "can_go_next": next_week <= report_service.week_start_of(today),
        "is_current": start == report_service.week_start_of(today),
        "models": getattr(settings, "AI_AVAILABLE_MODELS", []),
    }
    return render(request, "learning_logs/weekly.html", context)


@login_required
@require_POST
def weekly_report_generate(request):
    start = report_service.week_start_of(stats.parse_date(request.POST.get("week")))
    try:
        report_service.generate(request.user, start, model=request.POST.get("model"))
    except AIError as exc:
        messages.error(request, str(exc))
    except Exception:  # noqa: BLE001 - 模型服务异常不应让整页 500
        logger.exception("生成周报失败")
        messages.error(request, "生成失败，请检查 AI 配置或稍后重试。")
    else:
        messages.success(request, "周报已生成，可以随时重新生成覆盖。")
    return redirect(f"/weekly/?week={start:%Y-%m-%d}")
