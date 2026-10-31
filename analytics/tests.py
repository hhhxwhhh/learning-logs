"""学习分析模块测试。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from learning_logs.models import Entry, StudySession, Topic

from .models import AnalyticsPreferences

User = get_user_model()


class AnalyticsViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pass-12345")
        self.bob = User.objects.create_user("bob", password="pass-12345")
        self.topic = Topic.objects.create(text="Django ORM", owner=self.alice)
        Entry.objects.create(topic=self.topic, text="QuerySet 是惰性的")
        session = StudySession.objects.create(
            user=self.alice,
            topic=self.topic,
            start_time=timezone.now() - timedelta(minutes=50),
            end_time=timezone.now(),
        )
        session.save()
        self.client.force_login(self.alice)

    def test_dashboard(self):
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["overview"]["topic_count"], 1)
        self.assertTrue(response.context["insights"])

    def test_statistics_and_progress(self):
        self.assertEqual(self.client.get(reverse("analytics:statistics")).status_code, 200)
        self.assertEqual(self.client.get(reverse("analytics:progress")).status_code, 200)

    def test_topic_analysis_is_owner_only(self):
        url = reverse("analytics:topic_analysis", args=[self.topic.id])
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_preferences_requires_post(self):
        url = reverse("analytics:update_preferences")
        self.assertEqual(self.client.get(url).status_code, 405)

        response = self.client.post(
            url,
            {"show_study_time": "on", "show_topic_progress": "on", "chart_color_theme": "warm"},
        )
        self.assertEqual(response.status_code, 302)
        preferences = AnalyticsPreferences.objects.get(user=self.alice)
        self.assertTrue(preferences.show_study_time)
        self.assertFalse(preferences.show_goal_progress)
        self.assertEqual(preferences.chart_color_theme, "warm")

    def test_anonymous_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 302)
