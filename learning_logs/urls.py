"""learning_logs 路由。"""

from django.urls import path

from . import views
from .ai import views as ai_views

app_name = "learning_logs"

urlpatterns = [
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
