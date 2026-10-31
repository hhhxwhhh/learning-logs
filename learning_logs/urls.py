"""learning_logs 路由。"""

from django.urls import path

from . import api_views, views
from .ai import views as ai_views

app_name = "learning_logs"

urlpatterns = [
    # 开放 API
    path("api/v1/me/", api_views.me, name="api_me"),
    path("api/v1/topics/", api_views.topics, name="api_topics"),
    path("api/v1/entries/", api_views.entries, name="api_entries"),
    path("api/v1/entries/create/", api_views.quick_entry, name="api_quick_entry"),
    path("api/v1/cards/due/", api_views.due_cards, name="api_due_cards"),
    path("api/v1/sessions/", api_views.sessions, name="api_sessions"),
    path("api/v1/stats/", api_views.stats_view, name="api_stats"),
    # API 文档与令牌
    path("settings/api/", views.api_tokens, name="api_tokens"),
    path("api/docs/", views.api_docs, name="api_docs"),
    # 提醒中心
    path("notifications/", views.notifications_view, name="notifications"),
    path(
        "notifications/<int:notification_id>/read/",
        views.mark_notification_read,
        name="notification_read",
    ),
    path("notifications/read-all/", views.mark_all_read, name="notifications_read_all"),
    # 主页
    path("", views.index, name="index"),
    # 主题
    path("topics/", views.topics, name="topics"),
    path("topic/<int:topic_id>", views.topic, name="topic"),
    path("new_topic/", views.new_topic, name="new_topic"),
    path("delete_topic/<int:topic_id>/", views.delete_topic, name="delete_topic"),
    # 条目
    path("new_entry/<int:topic_id>", views.new_entry, name="new_entry"),
    path("edit_entry/<int:entry_id>", views.edit_entry, name="edit_entry"),
    path("delete_entry/<int:entry_id>", views.delete_entry, name="delete_entry"),
    path("entry/<int:entry_id>/comments/", views.entry_comments, name="entry_comments"),
    # 搜索
    path("search/", views.search, name="search"),
    path("api/search/", views.api_search, name="api_search"),
    # 仪表盘与目标
    path("dashboard/", views.dashboard, name="dashboard"),
    path("goals/", views.goals, name="goals"),
    path("goals/<int:goal_id>/toggle/", views.toggle_goal, name="toggle_goal"),
    # 学习计时
    path("topics/<int:topic_id>/start_session/", views.start_session, name="start_session"),
    path("end_session/", views.end_session, name="end_session"),
    # 学习路径
    path("learning-paths/", views.learning_paths, name="learning_paths"),
    path("learning-paths/new/", views.new_learning_path, name="new_learning_path"),
    path("learning-paths/<int:path_id>/", views.learning_path_detail, name="learning_path_detail"),
    path("learning-paths/<int:path_id>/delete/", views.delete_learning_path, name="delete_learning_path"),
    path("steps/<int:step_id>/", views.step_detail, name="step_detail"),
    path("steps/<int:step_id>/toggle-completion/", views.toggle_step_completion, name="toggle_step_completion"),
    path("resources/<int:resource_id>/toggle-completion/", views.toggle_resource_completion, name="toggle_resource_completion"),
    # 只读分享
    path("topic/<int:topic_id>/share/", views.toggle_share, name="toggle_share"),
    path("s/<str:token>/", views.shared_topic, name="shared_topic"),
    # 学习成就
    path("achievements/", views.achievements, name="achievements"),
    # 学习周报
    path("weekly/", views.weekly_report, name="weekly_report"),
    path("weekly/generate/", views.weekly_report_generate, name="weekly_generate"),
    # 数据导出与导入
    path("data/", views.data_tools, name="data_tools"),
    path("data/export/notes/", views.export_notes, name="export_notes"),
    path("data/export/topic/<int:topic_id>/", views.export_topic, name="export_topic"),
    path("data/export/cards/", views.export_cards, name="export_cards"),
    path("data/export/backup/", views.export_backup, name="export_backup"),
    path("data/import/", views.import_notes, name="import_notes"),
    # 导入中心与闪卡统计
    path("import/", views.import_center, name="import_center"),
    path("import/cards/", views.import_cards_view, name="import_cards"),
    path("flashcards/stats/", views.card_stats, name="card_stats"),
    # 学习花园
    path("garden/", views.garden, name="garden"),
    # 标签体系
    path("tags/", views.tags, name="tags"),
    path("tags/<int:tag_id>/", views.tag_detail, name="tag_detail"),
    path("topics/<int:topic_id>/suggest-tags/", views.suggest_tags, name="suggest_tags"),
    # 知识图谱
    path("graph/", views.graph, name="graph"),
    # 功能地图
    path("features/", views.features, name="features"),
    # 今日速览与专注计时
    path("today/", views.today, name="today"),
    path("focus/", views.focus, name="focus"),
    path("focus/log/", views.focus_log, name="focus_log"),
    # 闪卡复习
    path("flashcards/", views.flashcards, name="flashcards"),
    path("flashcards/review/", views.review, name="review"),
    path("flashcards/<int:card_id>/answer/", views.review_answer, name="review_answer"),
    path("flashcards/<int:card_id>/delete/", views.delete_flashcard, name="delete_flashcard"),
    path("flashcards/generate/<int:topic_id>/", views.generate_cards, name="generate_cards"),
    # AI 助教
    path("topics/<int:topic_id>/ai-assistant/", ai_views.assistant, name="ai_assistant"),
    path("topics/<int:topic_id>/ai-assistant/new/", ai_views.new_session, name="ai_new_session"),
    path("ai/sessions/<int:session_id>/stream/", ai_views.stream, name="ai_stream"),
    path("ai/sessions/<int:session_id>/delete/", ai_views.delete_session, name="ai_delete_session"),
    path("ai/paths/generate/", ai_views.generate_path, name="ai_generate_path"),
]
