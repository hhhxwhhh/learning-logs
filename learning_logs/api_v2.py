"""DRF 版开放接口（/api/v2/）。

v1 保持原有响应结构，已有脚本不用改；v2 用 Django REST Framework 重写，
提供分页、搜索、排序与统一的错误结构。
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import filters, mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_serializers import (
    CardSerializer,
    EntryCreateSerializer,
    EntrySerializer,
    EventSerializer,
    SessionSerializer,
    TopicSerializer,
)
from .models import Entry, EventLog, Flashcard, StudySession, Topic
from .services import stats


class OwnedViewSet(viewsets.ReadOnlyModelViewSet):
    """只读集合，所有查询都按当前令牌的用户过滤。"""

    permission_classes = [IsAuthenticated]


class TopicViewSet(OwnedViewSet):
    serializer_class = TopicSerializer
    search_fields = ["text"]
    ordering_fields = ["date_added", "text"]
    ordering = ["-date_added"]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]

    def get_queryset(self):
        return (
            Topic.objects.filter(owner=self.request.user)
            .prefetch_related("entry_set")
            .order_by("-date_added")
        )


class EntryViewSet(mixins.CreateModelMixin, OwnedViewSet):
    serializer_class = EntrySerializer
    search_fields = ["text", "topic__text"]
    ordering_fields = ["date_added"]
    ordering = ["-date_added"]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]

    def get_queryset(self):
        queryset = Entry.objects.filter(topic__owner=self.request.user).select_related("topic")
        topic_id = self.request.query_params.get("topic")
        if str(topic_id or "").isdigit():
            queryset = queryset.filter(topic_id=int(topic_id))
        query = (self.request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(text__icontains=query)
        return queryset.order_by("-date_added")

    def get_serializer_class(self):
        if self.action == "create":
            return EntryCreateSerializer
        return EntrySerializer

    def create(self, request, *args, **kwargs):
        serializer = EntryCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        entry = serializer.save()
        return Response(EntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class CardViewSet(OwnedViewSet):
    serializer_class = CardSerializer
    filter_backends = [filters.OrderingFilter]

    def get_queryset(self):
        queryset = Flashcard.objects.filter(user=self.request.user).select_related("topic")
        if self.request.query_params.get("due") in {"1", "true"}:
            queryset = queryset.filter(due_date__lte=timezone.localdate())
        return queryset.order_by("due_date")


class SessionViewSet(OwnedViewSet):
    serializer_class = SessionSerializer

    def get_queryset(self):
        return (
            StudySession.objects.filter(user=self.request.user, duration__isnull=False)
            .select_related("topic")
            .order_by("-start_time")
        )


class EventViewSet(OwnedViewSet):
    """事件流：外部系统可以拉取自己产生的学习事件。"""

    serializer_class = EventSerializer
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    filter_backends = [filters.OrderingFilter]

    def get_queryset(self):
        return EventLog.objects.filter(user=self.request.user).select_related("topic")


class StatsView(APIView):
    """统计概览。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        ranking = [
            {
                "topic": row["topic"].text,
                "entry_count": row["entry_count"],
                "progress": row["progress"],
            }
            for row in stats.topic_ranking(user)
        ]
        return Response(
            {
                "overview": stats.overview(user),
                "streak": stats.current_streak(user),
                "week_minutes": stats.range_minutes(user, 7),
                "topic_ranking": ranking,
            }
        )


class SchemaView(APIView):
    """OpenAPI 文档。"""

    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return Response(
            {
                "openapi": "3.0.3",
                "info": {
                    "title": "知迹开放 API",
                    "version": "2.0.0",
                    "description": "个人学习数据接口，需要 Bearer 令牌。",
                },
                "servers": [{"url": "/api/v2"}],
                "components": {
                    "securitySchemes": {
                        "bearer": {"type": "http", "scheme": "bearer"}
                    }
                },
                "security": [{"bearer": []}],
                "paths": {
                    "/topics/": {
                        "get": {
                            "summary": "主题列表",
                            "parameters": [
                                {"name": "search", "in": "query", "schema": {"type": "string"}},
                                {"name": "ordering", "in": "query", "schema": {"type": "string"}},
                                {"name": "page", "in": "query", "schema": {"type": "integer"}},
                            ],
                            "responses": {"200": {"description": "分页后的主题列表"}},
                        }
                    },
                    "/entries/": {
                        "get": {
                            "summary": "笔记列表",
                            "parameters": [
                                {"name": "topic", "in": "query", "schema": {"type": "integer"}},
                                {"name": "q", "in": "query", "schema": {"type": "string"}},
                            ],
                            "responses": {"200": {"description": "分页后的笔记列表"}},
                        },
                        "post": {
                            "summary": "新建笔记",
                            "responses": {"201": {"description": "已创建"}},
                        },
                    },
                    "/cards/": {
                        "get": {
                            "summary": "闪卡列表",
                            "parameters": [
                                {"name": "due", "in": "query", "schema": {"type": "string"}}
                            ],
                            "responses": {"200": {"description": "闪卡列表"}},
                        }
                    },
                    "/sessions/": {
                        "get": {
                            "summary": "学习会话列表",
                            "responses": {"200": {"description": "会话列表"}},
                        }
                    },
                    "/events/": {
                        "get": {
                            "summary": "学习事件流",
                            "responses": {"200": {"description": "事件列表"}},
                        }
                    },
                    "/stats/": {
                        "get": {
                            "summary": "统计概览",
                            "responses": {"200": {"description": "统计概览"}},
                        }
                    },
                },
            }
        )
