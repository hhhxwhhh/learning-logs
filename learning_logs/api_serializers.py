"""DRF 序列化器。

v1 接口的字段名保持不变，v2 在此基础上复用同一套模型方法，
避免两套接口的输出对不上。
"""

from __future__ import annotations

from rest_framework import serializers

from .models import Entry, EventLog, Flashcard, StudySession, Topic
from .services import tags as tags_service


class TopicSerializer(serializers.ModelSerializer):
    entries = serializers.IntegerField(source="total_items", read_only=True)
    completed = serializers.IntegerField(source="completed_items", read_only=True)
    progress = serializers.FloatField(source="progress_percentage", read_only=True)
    tags = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source="date_added", read_only=True)

    class Meta:
        model = Topic
        fields = ("id", "text", "entries", "completed", "progress", "tags", "created_at")

    def get_tags(self, obj) -> list[str]:
        return [tag.name for tag in tags_service.tags_of(obj)]


class EntrySerializer(serializers.ModelSerializer):
    topic = serializers.CharField(source="topic.text", read_only=True)
    topic_id = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(source="date_added", read_only=True)

    class Meta:
        model = Entry
        fields = ("id", "topic_id", "topic", "text", "completed", "created_at")


class EntryCreateSerializer(serializers.Serializer):
    """新建笔记：给 topic id 或 topic_name 都行。"""

    text = serializers.CharField(allow_blank=False, trim_whitespace=True)
    topic = serializers.IntegerField(required=False)
    topic_name = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        topic = None

        topic_id = attrs.get("topic")
        if topic_id:
            topic = Topic.objects.filter(id=topic_id, owner=user).first()
            if topic is None:
                raise serializers.ValidationError({"topic": "主题不存在或不属于当前账号。"})

        if topic is None and attrs.get("topic_name"):
            topic, _ = Topic.objects.get_or_create(
                text=attrs["topic_name"][:200], owner=user
            )

        if topic is None:
            raise serializers.ValidationError("需要 topic 或 topic_name 指定归属主题。")

        attrs["topic"] = topic
        return attrs

    def create(self, validated_data):
        from . import events
        from .services import cache as cache_service

        topic = validated_data.pop("topic")
        text = validated_data.pop("text")
        entry = Entry.objects.create(topic=topic, text=text)
        events.publish(
            "entry_created",
            self.context["request"].user,
            f"在「{topic.text}」写了一条笔记",
            topic=topic,
            payload={"entry_id": entry.id},
        )
        cache_service.invalidate(self.context["request"].user.id)
        return entry


class CardSerializer(serializers.ModelSerializer):
    topic = serializers.CharField(source="topic.text", read_only=True)

    class Meta:
        model = Flashcard
        fields = (
            "id",
            "topic",
            "front",
            "back",
            "due_date",
            "repetitions",
            "interval_days",
        )


class SessionSerializer(serializers.ModelSerializer):
    topic = serializers.CharField(source="topic.text", read_only=True)
    minutes = serializers.SerializerMethodField()

    class Meta:
        model = StudySession
        fields = ("id", "topic", "start_time", "minutes")

    def get_minutes(self, obj) -> int:
        return obj.duration_minutes()


class EventSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)
    topic = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = EventLog
        fields = ("event_id", "kind", "label", "summary", "topic", "payload", "created_at")

    def get_topic(self, obj) -> str:
        return obj.topic.text if obj.topic else ""
