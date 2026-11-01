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
    """OpenAPI 文档：从视图集与序列化器自动生成。"""

    permission_classes = []
    authentication_classes = []
    # 文档是公开的，不参与限流
    throttle_classes = []

    def get(self, request):
        from .api_schema import build_openapi

        return Response(build_openapi())
