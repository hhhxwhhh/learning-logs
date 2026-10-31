from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
    verbose_name = "学习分析"

    def ready(self):
        # 注册信号处理器：学习会话/条目写入后自动汇总指标
        from . import signals  # noqa: F401
