"""学习日志核心功能测试。"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ChatSession, Entry, Flashcard, LearningPath, Topic
from .services import export, garden, search, stats


class FakeProvider:
    """测试用假模型，避免任何网络请求。"""

    def stream(self, messages, model=None, **kwargs):
        for part in ["这是", "一段", "回答"]:
            yield part

    def complete(self, messages, model=None, **kwargs):
        return json.dumps(
            {
                "title": "测试路径",
                "description": "由测试生成",
                "estimated_hours": 12,
                "steps": [
                    {"topic": "基础语法", "description": "过一遍语法", "estimated_hours": 3,
                     "resources": ["官方教程"]},
                    "小项目",
                ],
            },
            ensure_ascii=False,
        )


class FakeCardProvider(FakeProvider):
    def complete(self, messages, model=None, **kwargs):
        return json.dumps(
            {"cards": [{"front": "什么是惰性 QuerySet？", "back": "只有被求值时才查询数据库"}]},
            ensure_ascii=False,
        )


class BaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.alice = user_model.objects.create_user("alice", password="pass-12345")
        self.bob = user_model.objects.create_user("bob", password="pass-12345")
        self.topic = Topic.objects.create(text="Django ORM", owner=self.alice)
        self.entry = Entry.objects.create(topic=self.topic, text="QuerySet 是惰性的")
        self.client.force_login(self.alice)


class TopicModelTests(BaseTestCase):
    def test_entry_save_updates_progress(self):
        Entry.objects.create(topic=self.topic, text="第二条", completed=True)
        self.topic.refresh_from_db()
        self.assertEqual(self.topic.total_items, 2)
        self.assertEqual(self.topic.completed_items, 1)
        self.assertEqual(self.topic.progress_percentage(), 50)

    def test_topic_str_and_ordering(self):
        self.assertEqual(str(self.topic), "Django ORM")
        newer = Topic.objects.create(text="Python 异步", owner=self.alice)
        self.assertEqual(list(Topic.objects.filter(owner=self.alice))[0], newer)


class AccessControlTests(BaseTestCase):
    def test_login_required(self):
        anonymous = Client()
        response = anonymous.get(reverse("learning_logs:topics"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_cannot_read_others_topic(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("learning_logs:topic", args=[self.topic.id]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_others_entry(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("learning_logs:edit_entry", args=[self.entry.id]))
        self.assertEqual(response.status_code, 404)

    def test_search_only_returns_own_entries(self):
        Entry.objects.create(topic=self.topic, text="Django 的 QuerySet")
        Entry.objects.create(
            topic=Topic.objects.create(text="bob 的主题", owner=self.bob),
            text="Django 也很好",
        )
        response = self.client.get(reverse("learning_logs:search"), {"q": "Django"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["entries"]), 1)
        self.assertEqual(response.context["entries"][0].topic.owner, self.alice)

    def test_delete_entry_requires_post(self):
        response = self.client.get(reverse("learning_logs:delete_entry", args=[self.entry.id]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Entry.objects.filter(id=self.entry.id).exists())


class DashboardTests(BaseTestCase):
    def test_dashboard_context(self):
        response = self.client.get(reverse("learning_logs:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["overview"]["topic_count"], 1)
        self.assertGreaterEqual(response.context["overview"]["week_minutes"], 5)

    def test_heatmap_has_seven_days_per_week(self):
        weeks = stats.heatmap_weeks(self.alice, weeks=4)
        self.assertEqual(len(weeks), 4)
        self.assertTrue(all(len(week) == 7 for week in weeks))

    def test_streak_counts_consecutive_days(self):
        today = timezone.localdate()
        Entry.objects.create(topic=self.topic, text="昨天")
        Entry.objects.filter(text="昨天").update(date_added=timezone.now() - timedelta(days=1))
        self.assertEqual(stats.current_streak(self.alice), 2)
        self.assertGreaterEqual(stats.range_minutes(self.alice, 7), 10)


class FlashcardTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.card = Flashcard.objects.create(
            user=self.alice, topic=self.topic, front="select_related 的作用？", back="减少 N+1 查询"
        )

    def test_new_card_is_due_today(self):
        self.assertTrue(self.card.is_due())

    def test_sm2_interval_grows(self):
        self.card.review(4)
        self.assertEqual(self.card.interval_days, 1)
        self.card.review(5)
        self.assertEqual(self.card.interval_days, 6)
        self.card.review(5)
        self.assertGreater(self.card.interval_days, 6)
        self.assertEqual(self.card.repetitions, 3)

    def test_forgetting_resets_progress(self):
        self.card.review(5)
        self.card.review(5)
        self.card.review(1)
        self.assertEqual(self.card.interval_days, 1)
        self.assertEqual(self.card.repetitions, 0)
        self.assertEqual(self.card.lapses, 1)
        self.assertGreaterEqual(self.card.ease_factor, 1.3)

    def test_review_flow(self):
        response = self.client.get(reverse("learning_logs:review"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "select_related")

        response = self.client.post(
            reverse("learning_logs:review_answer", args=[self.card.id]), {"quality": 5}
        )
        self.assertEqual(response.status_code, 302)
        self.card.refresh_from_db()
        self.assertFalse(self.card.is_due())

    def test_generate_cards_uses_ai(self):
        with patch("learning_logs.ai.service.get_provider", return_value=FakeCardProvider()):
            response = self.client.post(
                reverse("learning_logs:generate_cards", args=[self.topic.id]), {"count": 3}
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Flashcard.objects.filter(user=self.alice).count(), 2)
        self.assertTrue(
            Flashcard.objects.filter(user=self.alice, front__contains="惰性 QuerySet").exists()
        )

    def test_other_user_cannot_delete_card(self):
        self.client.force_login(self.bob)
        response = self.client.post(reverse("learning_logs:delete_flashcard", args=[self.card.id]))
        self.assertEqual(response.status_code, 404)


@override_settings(AI_PROVIDER="mock")
class AIStreamTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(user=self.alice, topic=self.topic, title="新的对话")

    def test_stream_creates_messages_and_emits_events(self):
        response = self.client.post(
            reverse("learning_logs:ai_stream", args=[self.session.id]),
            data=json.dumps({"message": "帮我总结这条笔记"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")

        body = b"".join(response.streaming_content).decode()
        self.assertIn("event: delta", body)
        self.assertIn("event: done", body)

        self.session.refresh_from_db()
        self.assertEqual(self.session.messages.count(), 2)
        self.assertEqual(self.session.messages.last().role, "assistant")
        self.assertNotEqual(self.session.title, "新的对话")

    def test_stream_rejects_empty_message(self):
        response = self.client.post(
            reverse("learning_logs:ai_stream", args=[self.session.id]),
            data=json.dumps({"message": "  "}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_stream_others_session(self):
        self.client.force_login(self.bob)
        response = self.client.post(
            reverse("learning_logs:ai_stream", args=[self.session.id]),
            data=json.dumps({"message": "hi"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_assistant_page_renders(self):
        response = self.client.get(reverse("learning_logs:ai_assistant", args=[self.topic.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI 助教")


class AIPathGenerationTests(BaseTestCase):
    def test_generate_learning_path_parses_structured_json(self):
        with patch("learning_logs.ai.service.get_provider", return_value=FakeProvider()):
            from learning_logs.ai import service

            path = service.generate_learning_path(self.alice, "三个月入门后端")

        self.assertIsInstance(path, LearningPath)
        self.assertEqual(path.title, "测试路径")
        self.assertEqual(path.pathstep_set.count(), 2)
        self.assertTrue(Topic.objects.filter(owner=self.alice, text="基础语法").exists())


class SearchApiTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        Entry.objects.create(
            topic=self.topic, text="QuerySet 是惰性的，select_related 解决 N+1 查询"
        )

    def test_api_requires_login(self):
        anonymous = Client()
        response = anonymous.get(reverse("learning_logs:api_search"), {"q": "QuerySet"})
        self.assertEqual(response.status_code, 302)

    def test_returns_highlighted_entries(self):
        response = self.client.get(reverse("learning_logs:api_search"), {"q": "QuerySet"})
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["entries"])
        self.assertIn("<mark>", data["entries"][0]["snippet"])
        self.assertEqual(data["entries"][0]["id"], Entry.objects.latest("id").id)

    def test_empty_query_returns_actions(self):
        data = self.client.get(reverse("learning_logs:api_search"), {"q": ""}).json()
        self.assertTrue(data["actions"])
        self.assertEqual(data["topics"], [])

    def test_multi_term_query(self):
        terms = search.tokenize("惰性 查询")
        self.assertEqual(terms, ["惰性", "查询"])
        result = search.search_all(self.alice, "惰性 查询")
        self.assertGreaterEqual(result["total"], 1)

    def test_search_does_not_leak_other_users(self):
        Entry.objects.create(
            topic=Topic.objects.create(text="秘密", owner=self.bob),
            text="QuerySet 属于别人",
        )
        data = self.client.get(reverse("learning_logs:api_search"), {"q": "QuerySet"}).json()
        self.assertEqual(len(data["entries"]), 2)  # 只有 alice 的两条
        for row in data["entries"]:
            self.assertNotIn("属于别人", row["snippet"])


class GardenTests(BaseTestCase):
    def test_stage_thresholds(self):
        self.assertEqual(garden.stage_of(0)["name"], "种子")
        self.assertEqual(garden.stage_of(1)["name"], "嫩芽")
        self.assertEqual(garden.stage_of(6)["name"], "小树")
        self.assertEqual(garden.stage_of(18)["name"], "大树")
        self.assertEqual(garden.stage_of(45)["name"], "森林")
        self.assertEqual(garden.stage_of(45)["next_name"], None)

    def test_stage_progress_between_levels(self):
        stage = garden.stage_of(3)  # 嫩芽(1) → 小树(6)
        self.assertEqual(stage["progress"], 40)
        self.assertEqual(stage["remaining"], 3)

    def test_tree_has_branch_and_leaves(self):
        Entry.objects.create(topic=self.topic, text="第二条")
        tree = garden.tree_data(self.alice)
        self.assertEqual(len(tree["branches"]), 1)
        branch = tree["branches"][0]
        self.assertTrue(branch["path"].startswith("M"))
        self.assertGreaterEqual(len(branch["leaves"]), 2)
        self.assertEqual(branch["entry_count"], 2)

    def test_tree_limits_branches(self):
        for index in range(10):
            Topic.objects.create(text=f"主题 {index}", owner=self.alice)
        self.assertEqual(len(garden.tree_data(self.alice, max_branches=5)["branches"]), 5)

    def test_on_this_day_picks_previous_month(self):
        import calendar

        entry = Entry.objects.create(topic=self.topic, text="上个月的今天")
        today = timezone.localdate()
        year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        day = min(today.day, calendar.monthrange(year, month)[1])
        past = timezone.make_aware(datetime(year, month, day, 12, 0))
        Entry.objects.filter(id=entry.id).update(date_added=past)

        picked = garden.on_this_day(self.alice)
        self.assertIn(entry.id, [item.id for item in picked])

    def test_garden_page(self):
        response = self.client.get(reverse("learning_logs:garden"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "学习花园")
        self.assertContains(response, "知识树")


class ExportImportTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="问题", back="答案")

    def test_topic_markdown_contains_entry(self):
        markdown = export.topic_markdown(self.topic)
        self.assertIn("# Django ORM", markdown)
        self.assertIn("QuerySet 是惰性的", markdown)

    def test_zip_contains_one_file_per_topic(self):
        import io as _io
        import zipfile

        payload = export.all_topics_zip(self.alice)
        archive = zipfile.ZipFile(_io.BytesIO(payload))
        names = archive.namelist()
        self.assertIn("README.md", names)
        self.assertTrue(any(name.endswith(".md") for name in names))

    def test_flashcards_csv_has_bom_and_header(self):
        content = export.flashcards_csv(self.alice)
        self.assertTrue(content.startswith("\ufeff"))
        self.assertIn("front,back,tags", content)
        self.assertIn("问题", content)

    def test_backup_json_structure(self):
        payload = json.loads(export.backup_json(self.alice))
        self.assertEqual(payload["format"], "zhiji-learning-log")
        self.assertEqual(len(payload["topics"]), 1)
        self.assertEqual(payload["flashcards"][0]["front"], "问题")

    def test_export_topic_is_owner_only(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("learning_logs:export_topic", args=[self.topic.id]))
        self.assertEqual(response.status_code, 404)

    def test_import_markdown_creates_entries(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(
            "note.md",
            "## 第一条\n内容一\n## 第二条\n内容二".encode(),
            content_type="text/markdown",
        )
        response = self.client.post(
            reverse("learning_logs:import_notes"),
            {"file": upload, "topic": self.topic.id},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.topic.entry_set.count(), 3)

    def test_import_creates_new_topic(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("新主题.md", "## 只有一条\n内容".encode())
        self.client.post(
            reverse("learning_logs:import_notes"),
            {"file": upload, "topic": "new", "title": "导入测试"},
        )
        topic = Topic.objects.filter(owner=self.alice, text="导入测试").first()
        self.assertIsNotNone(topic)
        self.assertEqual(topic.entry_set.count(), 1)

    def test_data_page(self):
        response = self.client.get(reverse("learning_logs:data_tools"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "数据与备份")
