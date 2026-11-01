"""待办清单。"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from ..models import Entry, snapshot_entry
from .. import events
from ..services import cache as cache_service
from ..services import todos as todos_service

logger = logging.getLogger(__name__)

@login_required
def todos(request):
    """待办清单：把散落在各篇笔记里的 `- [ ]` 汇总到一页。

    只做「读」，勾选由 toggle_todo 回写笔记正文完成。
    """
    status = request.GET.get("status", "open")
    if status not in {"open", "done", "all"}:
        status = "open"

    rows = todos_service.scan(request.user)
    if status == "open":
        visible = [row for row in rows if not row["done"]]
    elif status == "done":
        visible = [row for row in rows if row["done"]]
    else:
        visible = rows

    return render(
        request,
        "learning_logs/todos.html",
        {
            "status": status,
            "groups": todos_service.group_by_topic(visible),
            "summary": todos_service.summarize(rows),
            "shown": len(visible),
        },
    )


@login_required
@require_POST
def toggle_todo(request, entry_id):
    """勾选 / 取消勾选一条待办，改动会写回笔记并留一份历史版本。"""
    entry = get_object_or_404(Entry, id=entry_id, topic__owner=request.user)
    raw = (request.POST.get("index") or "").strip()
    if not raw.isdigit():
        return JsonResponse({"ok": False, "error": "待办序号不合法。"}, status=400)

    result = todos_service.toggle(entry, int(raw))
    if result is None:
        return JsonResponse({"ok": False, "error": "没找到这条待办。"}, status=404)

    snapshot_entry(entry, request.user)
    entry.save()
    events.publish(
        "todo_toggled",
        request.user,
        f"{'完成' if result['done'] else '恢复'}了一条待办：{result['text']}",
        topic=entry.topic,
        payload={"entry_id": entry.id, "done": result["done"]},
    )
    cache_service.invalidate(request.user.id)

    wants_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
    if not wants_json:
        messages.success(request, "已更新待办状态。")
        return redirect("learning_logs:todos")

    remaining = todos_service.summarize(todos_service.scan(request.user))
    return JsonResponse({"ok": True, "done": result["done"], "open": remaining["open"]})
