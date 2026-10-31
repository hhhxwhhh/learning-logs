from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("statistics/", views.study_statistics, name="statistics"),
    path("progress/", views.progress_report, name="progress"),
    path("topic/<int:topic_id>/", views.topic_analysis, name="topic_analysis"),
    path("preferences/", views.update_preferences, name="update_preferences"),
]
