"""学习日志核心模型。

约定：
- 所有业务对象都通过 owner/user 归属到用户，视图层必须按用户过滤；
- 时间相关的计算统一放在模型方法里，模板只负责展示。
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
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
    share_token = models.CharField("分享令牌", max_length=40, blank=True, default="", db_index=True)
    shared_at = models.DateTimeField("开启分享时间", null=True, blank=True)

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


class ChatSession(models.Model):
    """一次围绕某个主题的多轮 AI 对话。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_sessions"
    )
    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, null=True, blank=True, related_name="chat_sessions"
    )
    title = models.CharField("会话标题", max_length=120, default="新的对话")
    model_name = models.CharField("模型", max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "AI 会话"
        verbose_name_plural = "AI 会话"

    def __str__(self):
        return self.title

    def touch(self):
        self.save(update_fields=["updated_at"])

    def last_message(self):
        return self.messages.last()


class ChatMessage(models.Model):
    """会话中的一条消息。"""

    ROLE_CHOICES = [("user", "用户"), ("assistant", "助手"), ("system", "系统")]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField("角色", max_length=12, choices=ROLE_CHOICES)
    content = models.TextField("内容")
    model_name = models.CharField("模型", max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "AI 消息"
        verbose_name_plural = "AI 消息"

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


class WeeklyReport(models.Model):
    """一周学习总结，可由 AI 生成并保存。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_reports"
    )
    week_start = models.DateField("周一日期")
    summary = models.TextField("总结", blank=True)
    stats = models.JSONField("统计数据", default=dict, blank=True)
    model_name = models.CharField("生成模型", max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "week_start")]
        ordering = ["-week_start"]
        verbose_name = "学习周报"
        verbose_name_plural = "学习周报"

    def __str__(self):
        return f"{self.user} · {self.week_start:%Y-%m-%d} 周报"


def default_review_date():
    """新卡默认当天可复习，先学一遍再进入间隔队列。"""
    return timezone.localdate()


class Flashcard(models.Model):
    """间隔重复闪卡：用 SM-2 算法安排复习时间。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="flashcards"
    )
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="flashcards")
    front = models.CharField("正面/问题", max_length=300)
    back = models.TextField("背面/答案")
    source_entry = models.ForeignKey(
        Entry, on_delete=models.SET_NULL, null=True, blank=True, related_name="flashcards"
    )

    ease_factor = models.FloatField("难度系数", default=2.5)
    interval_days = models.PositiveIntegerField("间隔天数", default=0)
    repetitions = models.PositiveIntegerField("连续答对次数", default=0)
    lapses = models.PositiveIntegerField("遗忘次数", default=0)
    due_date = models.DateField("下次复习", default=default_review_date)
    last_reviewed_at = models.DateTimeField("上次复习", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "id"]
        verbose_name = "闪卡"
        verbose_name_plural = "闪卡"

    def __str__(self):
        return self.front

    def review(self, quality: int):
        """按 SM-2 更新记忆参数。quality: 0-5，<3 视为遗忘。"""
        quality = max(0, min(5, int(quality)))

        if quality < 3:
            self.repetitions = 0
            self.interval_days = 1
            self.lapses += 1
        else:
            if self.repetitions == 0:
                self.interval_days = 1
            elif self.repetitions == 1:
                self.interval_days = 6
            else:
                self.interval_days = max(1, round(self.interval_days * self.ease_factor))
            self.repetitions += 1

        self.ease_factor = max(
            1.3, self.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        )
        self.due_date = timezone.localdate() + timedelta(days=self.interval_days)
        self.last_reviewed_at = timezone.now()
        self.save()
        return self.due_date

    def is_due(self):
        return self.due_date <= timezone.localdate()


class Tag(models.Model):
    """用户自定义标签，可同时挂在主题与笔记上。"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField("标签", max_length=32)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "标签"
        verbose_name_plural = "标签"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="uniq_tag_name_per_user")
        ]

    def __str__(self):
        return self.name

    def usage_count(self):
        return self.items.count()

    @property
    def hue(self):
        """由标签名派生的稳定色相，保证同名标签颜色始终一致。"""
        return sum(ord(char) * (index + 3) for index, char in enumerate(self.name)) % 360


class TaggedItem(models.Model):
    """标签与被标记对象（主题或笔记）之间的关联。"""

    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="items")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "标签关联"
        verbose_name_plural = "标签关联"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.tag} → {self.content_type}#{self.object_id}"
