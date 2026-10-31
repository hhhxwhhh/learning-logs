"""开放 API 的认证与数据序列化。

认证方式：Authorization: Bearer <token> 或 ?token=<token>。
令牌只对本人数据生效，任何越权对象一律返回 404。
"""

from __future__ import annotations

from django.utils import timezone

from learning_logs.models import ApiToken, Entry, Flashcard, StudySession, Topic
from learning_logs.services import tags as tags_service


class ApiError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.message = message
        self.status = status


def token_from_request(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return (request.GET.get("token") or "").strip()


def authenticate(request) -> ApiToken:
    """解析并校验令牌，失败时抛 ApiError。"""
    raw = token_from_request(request)
    if not raw:
        raise ApiError("缺少 API 令牌，请在请求头传入 Authorization: Bearer <token>。", 401)

    record = ApiToken.objects.filter(token=raw, revoked=False).select_related("user").first()
    if record is None:
        raise ApiError("令牌无效或已被吊销。", 401)

    ApiToken.objects.filter(id=record.id).update(last_used_at=timezone.now())
    return record


def serialize_topic(topic: Topic) -> dict:
    return {
        "id": topic.id,
        "text": topic.text,
        "entries": topic.total_items,
        "completed": topic.completed_items,
        "progress": topic.progress_percentage(),
        "tags": [tag.name for tag in tags_service.tags_of(topic)],
        "created_at": topic.date_added.isoformat(),
    }


def serialize_entry(entry: Entry) -> dict:
    return {
        "id": entry.id,
        "topic_id": entry.topic_id,
        "topic": entry.topic.text,
        "text": entry.text,
        "completed": entry.completed,
        "created_at": entry.date_added.isoformat(),
    }


def serialize_card(card: Flashcard) -> dict:
    return {
        "id": card.id,
        "topic": card.topic.text,
        "front": card.front,
        "back": card.back,
        "due_date": card.due_date.isoformat(),
        "repetitions": card.repetitions,
        "interval_days": card.interval_days,
    }


def serialize_session(session: StudySession) -> dict:
    return {
        "id": session.id,
        "topic": session.topic.text,
        "start_time": session.start_time.isoformat(),
        "minutes": session.duration_minutes(),
    }
