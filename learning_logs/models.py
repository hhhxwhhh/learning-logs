"""学习日志核心模型。

约定：
- 所有业务对象都通过 owner/user 归属到用户，视图层必须按用户过滤；
- 时间相关的计算统一放在模型方法里，模板只负责展示。
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class Topic(models.Model):
    """用户学习的主题"""

    text = models.CharField("主题", max_length=200)
    date_added = models.DateTimeField("创建时间", auto_now_add=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name="所有者",
        related_name="topics",
    )
    total_items = models.IntegerField("条目总数", default=0)
    completed_items = models.IntegerField("已完成条目数", default=0)

    class Meta:
        verbose_name = "主题"
        verbose_name_plural = "主题"
        ordering = ["-date_added"]

    def update_progress(self):
        """从条目重新计算进度，只写回两个统计字段，避免整行覆盖。"""
        entries = self.entry_set.all()
        self.total_items = entries.count()
        self.completed_items = entries.filter(completed=True).count()
        self.save(update_fields=["total_items", "completed_items"])

    def progress_percentage(self):
        if not self.total_items:
            return 0
        return round(self.completed_items / self.total_items * 100)

    def last_activity(self):
        latest = self.entry_set.order_by("-date_added").first()
        return latest.date_added if latest else self.date_added

    def __str__(self):
        return self.text


class Entry(models.Model):
    """某个主题下的一条学习记录"""

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, verbose_name="主题")
    text = models.TextField("内容")
    date_added = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField("已完成", default=False)

    class Meta:
        verbose_name_plural = "entries"
        ordering = ["-date_added"]

    def __str__(self):
        return self.text[:50] + ("..." if len(self.text) > 50 else "")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.topic.update_progress()


class Comment(models.Model):
    """条目下的讨论"""

    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField("评论内容")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "评论"
        verbose_name_plural = "评论"

    def __str__(self):
        return f"Comment by {self.user.username} on {self.entry}"


class LearningGoal(models.Model):
    """学习目标"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="learning_goals")
    title = models.CharField("目标", max_length=200)
    description = models.TextField("说明", blank=True)
    target_date = models.DateField("截止日期")
    completed = models.BooleanField("已完成", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["target_date"]
        verbose_name = "学习目标"
        verbose_name_plural = "学习目标"

    def days_remaining(self):
        if self.completed:
            return 0
        return (self.target_date - timezone.localdate()).days

    def is_overdue(self):
        return not self.completed and self.days_remaining() < 0

    def __str__(self):
        return self.title


class StudySession(models.Model):
    """一次学习计时记录"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="study_sessions")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="study_sessions")
    start_time = models.DateTimeField("开始时间")
    end_time = models.DateTimeField("结束时间", null=True, blank=True)
    duration = models.DurationField("时长", null=True, blank=True)

    class Meta:
        ordering = ["-start_time"]
        verbose_name = "学习会话"
        verbose_name_plural = "学习会话"

    def save(self, *args, **kwargs):
        if self.start_time and self.end_time:
            self.duration = self.end_time - self.start_time
        super().save(*args, **kwargs)

    def stop(self):
        """结束会话并落库。"""
        if not self.end_time:
            self.end_time = timezone.now()
            self.save()
        return self

    def duration_minutes(self):
        if not self.duration:
            return 0
        return int(self.duration.total_seconds() // 60)

    def __str__(self):
        return f"{self.user} · {self.topic} · {self.start_time:%Y-%m-%d %H:%M}"


class LearningPath(models.Model):
    """由多个主题组成的学习路径"""

    title = models.CharField("标题", max_length=200)
    description = models.TextField("描述", blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    estimated_hours = models.PositiveIntegerField("预计学时", default=0)
    is_completed = models.BooleanField("已完成", default=False)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "学习路径"
        verbose_name_plural = "学习路径"

    def __str__(self):
        return self.title

    def get_progress(self):
        steps = self.pathstep_set.all()
        if not steps:
            return 0
        return round(steps.filter(is_completed=True).count() / steps.count() * 100)


class PathStep(models.Model):
    """学习路径中的一个步骤"""

    path = models.ForeignKey(LearningPath, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    description = models.TextField("说明", blank=True)
    is_completed = models.BooleanField("已完成", default=False)
    estimated_hours = models.PositiveIntegerField("预计学时", default=1)

    class Meta:
        ordering = ["order"]
        verbose_name = "路径步骤"
        verbose_name_plural = "路径步骤"

    def __str__(self):
        return f"{self.path.title} - Step {self.order}: {self.topic.text}"


class StepResource(models.Model):
    """学习步骤关联的资源"""

    TYPE_CHOICES = (
        ("book", "书籍"),
        ("video", "视频"),
        ("article", "文章"),
        ("exercise", "练习"),
        ("other", "其他"),
    )

    step = models.ForeignKey(PathStep, on_delete=models.CASCADE, related_name="resources")
    title = models.CharField("标题", max_length=200)
    url = models.URLField("链接", blank=True)
    resource_type = models.CharField("类型", max_length=20, choices=TYPE_CHOICES, default="other")
    is_completed = models.BooleanField("已完成", default=False)
    notes = models.TextField("备注", blank=True)

    class Meta:
        verbose_name = "学习资源"
        verbose_name_plural = "学习资源"

    def __str__(self):
        return self.title


class AIInteraction(models.Model):
    """历史 AI 交互记录（旧版数据结构，后续版本迁移到会话模型）。"""

    INTERACTION_TYPES = [
        ("question", "提问"),
        ("summary", "摘要"),
        ("quiz", "测验"),
        ("recommendation", "建议"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, null=True, blank=True)
    question = models.TextField("问题")
    response = models.TextField("回答")
    interaction_type = models.CharField("类型", max_length=20, choices=INTERACTION_TYPES)
    model_used = models.CharField("模型", max_length=50, default="llama3")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AI 交互"
        verbose_name_plural = "AI 交互"

    def __str__(self):
        return f"{self.interaction_type}: {self.question[:50]}"


def default_review_date():
    return timezone.localdate() + timedelta(days=1)
