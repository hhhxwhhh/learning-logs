from django.contrib import admin

from .models import (
    ChatMessage,
    ChatSession,
    Comment,
    Entry,
    LearningGoal,
    LearningPath,
    PathStep,
    StepResource,
    StudySession,
    Topic,
)


class EntryInline(admin.TabularInline):
    model = Entry
    extra = 0
    fields = ("text", "completed", "date_added")
    readonly_fields = ("date_added",)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("text", "owner", "total_items", "completed_items", "date_added")
    list_filter = ("owner",)
    search_fields = ("text",)
    inlines = [EntryInline]


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "topic", "completed", "date_added")
    list_filter = ("completed",)
    search_fields = ("text",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("user", "entry", "created_at")


@admin.register(LearningGoal)
class LearningGoalAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "target_date", "completed")
    list_filter = ("completed",)


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ("user", "topic", "start_time", "duration")
    list_filter = ("user",)


class PathStepInline(admin.TabularInline):
    model = PathStep
    extra = 0


@admin.register(LearningPath)
class LearningPathAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "estimated_hours", "is_completed", "updated_at")
    inlines = [PathStepInline]


@admin.register(StepResource)
class StepResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "step", "resource_type", "is_completed")


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    fields = ("role", "content", "model_name", "created_at")
    readonly_fields = ("created_at",)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "topic", "model_name", "updated_at")
    list_filter = ("model_name",)
    search_fields = ("title",)
    inlines = [ChatMessageInline]
