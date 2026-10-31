"""学习日志核心功能测试。"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    ApiToken,
    ChatSession,
    Entry,
    Flashcard,
    LearningPath,
    Notification,
    StudySession,
    Tag,
    Topic,
    snapshot_entry,
)
from .services import (
    achievements,
    export,
    garden,
    graph,
    insights,
    links,
    notifications,
    report,
    search,
    stats,
    tags,
    timeline,
)


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
        # 同一毫秒创建的主题时间戳可能相同，显式拉开时间以保证排序稳定
        Topic.objects.filter(id=newer.id).update(
            date_added=timezone.now() + timedelta(minutes=1)
        )
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


class WeeklyReportTests(BaseTestCase):
    def test_week_start_is_monday(self):
        start = report.week_start_of()
        self.assertEqual(start.weekday(), 0)

    def test_collect_returns_seven_days(self):
        data = report.collect(self.alice, report.week_start_of())
        self.assertEqual(len(data["days"]), 7)
        self.assertGreaterEqual(data["week_minutes"], 5)
        self.assertEqual(data["entry_count"], 1)

    def test_suggestions_are_rule_based(self):
        data = report.collect(self.alice, report.week_start_of())
        tips = report.suggestions(data)
        self.assertTrue(tips)
        self.assertTrue(all(isinstance(tip, str) for tip in tips))

    def test_generate_saves_report(self):
        with patch("learning_logs.ai.service.get_provider", return_value=FakeProvider()):
            with patch("learning_logs.services.report.get_provider", return_value=FakeProvider()):
                saved = report.generate(self.alice, report.week_start_of())
        self.assertTrue(saved.summary)
        self.assertEqual(saved.week_start.weekday(), 0)
        self.assertEqual(saved.stats["entry_count"], 1)

    def test_weekly_page(self):
        response = self.client.get(reverse("learning_logs:weekly_report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "学习周报")
        self.assertContains(response, "每日投入")

    def test_generate_endpoint_handles_ai_error(self):
        with patch(
            "learning_logs.services.report.get_provider",
            side_effect=Exception("boom"),
        ):
            response = self.client.post(
                reverse("learning_logs:weekly_generate"),
                {"week": report.week_start_of().isoformat()},
            )
        self.assertEqual(response.status_code, 302)


class AchievementTests(BaseTestCase):
    def test_first_badge_unlocked_with_achieved_date(self):
        data = achievements.collect(self.alice)
        first = next(item for item in data["badges"] if item.key == "first_entry")
        self.assertTrue(first.unlocked)
        self.assertIsNotNone(first.achieved_at)
        self.assertEqual(first.progress, 100)

    def test_locked_badge_reports_progress(self):
        data = achievements.collect(self.alice)
        ten = next(item for item in data["badges"] if item.key == "entries_10")
        self.assertFalse(ten.unlocked)
        self.assertEqual(ten.current, 1)
        self.assertEqual(ten.progress, 10)

    def test_unlocked_sorted_first(self):
        data = achievements.collect(self.alice)
        keys = [item.key for item in data["badges"]]
        unlocked_flags = [item.unlocked for item in data["badges"]]
        # 已解锁的一定排在未解锁之前
        self.assertEqual(unlocked_flags, sorted(unlocked_flags, reverse=True))
        self.assertIn("first_entry", keys)

    def test_achievements_page(self):
        response = self.client.get(reverse("learning_logs:achievements"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "学习成就")


class ShareTests(BaseTestCase):
    def test_toggle_share_creates_and_revokes(self):
        url = reverse("learning_logs:toggle_share", args=[self.topic.id])
        self.client.post(url)
        self.topic.refresh_from_db()
        token = self.topic.share_token
        self.assertTrue(token)
        self.assertIsNotNone(self.topic.shared_at)

        self.client.post(url)
        self.topic.refresh_from_db()
        self.assertEqual(self.topic.share_token, "")
        self.assertIsNone(self.topic.shared_at)

    def test_toggle_requires_post(self):
        url = reverse("learning_logs:toggle_share", args=[self.topic.id])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_other_user_cannot_toggle(self):
        self.client.force_login(self.bob)
        response = self.client.post(reverse("learning_logs:toggle_share", args=[self.topic.id]))
        self.assertEqual(response.status_code, 404)

    def test_public_page_works_without_login(self):
        self.topic.share_token = "public-token-for-test"
        self.topic.save(update_fields=["share_token"])
        anonymous = Client()
        response = anonymous.get(reverse("learning_logs:shared_topic", args=[self.topic.share_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django ORM")
        self.assertContains(response, "只读分享")

    def test_revoked_link_returns_404(self):
        self.topic.share_token = "temp-token"
        self.topic.save(update_fields=["share_token"])
        url = reverse("learning_logs:shared_topic", args=["temp-token"])
        self.assertEqual(Client().get(url).status_code, 200)

        self.topic.share_token = ""
        self.topic.save(update_fields=["share_token"])
        self.assertEqual(Client().get(url).status_code, 404)


class PWATests(TestCase):
    def test_manifest(self):
        response = self.client.get(reverse("manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/manifest+json", response["Content-Type"])
        self.assertIn("知迹", response.content.decode())

    def test_service_worker_scope_header(self):
        response = self.client.get(reverse("service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")

    def test_offline_page(self):
        response = self.client.get(reverse("offline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "没有网络")


class TagTests(BaseTestCase):
    """标签解析、同步与标签云。"""

    def test_parse_tags_dedup_and_limit(self):
        names = tags.parse_tags("算法, 面试 算法、Python，Python / 复盘")
        self.assertEqual(names[:2], ["算法", "面试"])
        self.assertEqual(names.count("Python"), 1)
        self.assertLessEqual(len(names), tags.MAX_TAGS)

    def test_sync_tags_replaces_previous(self):
        tags.sync_tags(self.alice, self.topic, "后端, 数据库")
        self.assertEqual(sorted(t.name for t in tags.tags_of(self.topic)), ["后端", "数据库"])

        tags.sync_tags(self.alice, self.topic, "后端, 缓存")
        self.assertEqual(sorted(t.name for t in tags.tags_of(self.topic)), ["后端", "缓存"])

    def test_prune_removes_orphan_tags(self):
        tags.sync_tags(self.alice, self.topic, "临时")
        self.assertEqual(Tag.objects.filter(user=self.alice, name="临时").count(), 1)
        tags.sync_tags(self.alice, self.topic, "")
        self.assertEqual(Tag.objects.filter(user=self.alice, name="临时").count(), 0)

    def test_tags_are_per_user(self):
        tags.sync_tags(self.alice, self.topic, "共享")
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        tags.sync_tags(self.bob, bob_topic, "共享")
        self.assertEqual(Tag.objects.filter(name="共享").count(), 2)

    def test_cloud_weights_and_pages(self):
        tags.sync_tags(self.alice, self.topic, "核心")
        Entry.objects.create(topic=self.topic, text="另一条")
        tags.sync_tags(self.alice, self.entry, "核心")
        cloud = tags.cloud(self.alice)
        self.assertEqual(cloud[0]["name"], "核心")
        self.assertEqual(cloud[0]["count"], 2)

        response = self.client.get(reverse("learning_logs:tags"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "核心")

    def test_tag_detail_page(self):
        tags.sync_tags(self.alice, self.topic, "图谱测试")
        tag = Tag.objects.get(user=self.alice, name="图谱测试")
        response = self.client.get(reverse("learning_logs:tag_detail", args=[tag.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django ORM")

    def test_tag_detail_isolates_users(self):
        tags.sync_tags(self.alice, self.topic, "私有")
        tag = Tag.objects.get(user=self.alice, name="私有")
        self.client.force_login(self.bob)
        response = self.client.get(reverse("learning_logs:tag_detail", args=[tag.id]))
        self.assertEqual(response.status_code, 404)

    def test_topic_page_can_update_tags(self):
        response = self.client.post(
            reverse("learning_logs:topic", args=[self.topic.id]), {"tags": "页面, 表单"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(sorted(t.name for t in tags.tags_of(self.topic)), ["表单", "页面"])

    def test_new_entry_keeps_tags(self):
        self.client.post(
            reverse("learning_logs:new_entry", args=[self.topic.id]),
            {"text": "带标签的笔记", "tags": "笔记标签"},
        )
        entry = Entry.objects.get(text="带标签的笔记")
        self.assertEqual([t.name for t in tags.tags_of(entry)], ["笔记标签"])


class GraphTests(BaseTestCase):
    """知识图谱的坐标计算与关联边。"""

    def test_shared_tags_create_edges(self):
        second = Topic.objects.create(text="Redis 缓存", owner=self.alice)
        tags.sync_tags(self.alice, self.topic, "缓存, 后端")
        tags.sync_tags(self.alice, second, "缓存")
        data = graph.build(self.alice)

        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(len(data["edges"]), 1)
        self.assertEqual(data["edges"][0]["weight"], 1)
        self.assertEqual(data["linked"], 2)
        self.assertEqual(data["isolated"], [])

        for node in data["nodes"]:
            self.assertGreaterEqual(node["x"], 0)
            self.assertLessEqual(node["x"], data["width"])
            self.assertGreaterEqual(node["y"], 0)
            self.assertLessEqual(node["y"], data["height"])

    def test_graph_page_renders(self):
        tags.sync_tags(self.alice, self.topic, "渲染")
        response = self.client.get(reverse("learning_logs:graph"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django ORM")

    def test_empty_graph_is_safe(self):
        Topic.objects.filter(owner=self.alice).delete()
        data = graph.build(self.alice)
        self.assertEqual(data["nodes"], [])
        self.assertEqual(data["edges"], [])


class TodayTests(BaseTestCase):
    def test_today_page(self):
        response = self.client.get(reverse("learning_logs:today"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "今日速览")

    def test_counts_today_only(self):
        Entry.objects.create(topic=self.topic, text="今天写的")
        old = Entry.objects.create(topic=self.topic, text="很久以前写的")
        Entry.objects.filter(id=old.id).update(date_added=timezone.now() - timedelta(days=60))

        response = self.client.get(reverse("learning_logs:today"))
        self.assertEqual(response.status_code, 200)
        # 基类已经创建了一条今天的笔记，这里应该是 2
        self.assertEqual(response.context["entry_count_today"], 2)


class FocusTests(BaseTestCase):
    def test_focus_page(self):
        response = self.client.get(reverse("learning_logs:focus"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "专注")

    def test_focus_log_records_session(self):
        response = self.client.post(
            reverse("learning_logs:focus_log"),
            {"minutes": "25", "topic": self.topic.id},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        session = StudySession.objects.get(user=self.alice)
        self.assertEqual(session.duration_minutes(), 25)

    def test_focus_log_rejects_bad_input(self):
        response = self.client.post(
            reverse("learning_logs:focus_log"), {"minutes": "0", "topic": self.topic.id}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudySession.objects.filter(user=self.alice).count(), 0)

    def test_focus_log_requires_own_topic(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        response = self.client.post(
            reverse("learning_logs:focus_log"), {"minutes": "10", "topic": bob_topic.id}
        )
        self.assertEqual(response.status_code, 400)


class FeatureMapTests(BaseTestCase):
    def test_features_page_lists_capabilities(self):
        response = self.client.get(reverse("learning_logs:features"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "功能地图")
        self.assertContains(response, "知识图谱")
        self.assertGreaterEqual(response.context["total"], 15)

    def test_feature_urls_are_reachable(self):
        response = self.client.get(reverse("learning_logs:features"))
        urls = [
            item["url"]
            for group in response.context["groups"]
            for item in group["items"]
        ]
        self.assertTrue(urls)
        for url in urls:
            page = self.client.get(url)
            self.assertIn(page.status_code, (200, 302), url)


class MarkdownEditorTests(BaseTestCase):
    def test_entry_form_has_editor(self):
        response = self.client.get(reverse("learning_logs:new_entry", args=[self.topic.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-md-editor")
        self.assertContains(response, "editor.js")


class ApiTokenTests(BaseTestCase):
    """开放 API：鉴权、只读接口与快速写入。"""

    def setUp(self):
        super().setUp()
        self.token = ApiToken.issue(self.alice, "测试令牌")

    def auth(self, token=None):
        return {"HTTP_AUTHORIZATION": "Bearer " + (token or self.token.token)}

    def test_requires_token(self):
        response = self.client.get(reverse("learning_logs:api_topics"))
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["ok"])

    def test_invalid_token_rejected(self):
        response = self.client.get(
            reverse("learning_logs:api_topics"), HTTP_AUTHORIZATION="Bearer nope"
        )
        self.assertEqual(response.status_code, 401)

    def test_topics_endpoint_returns_own_data(self):
        response = self.client.get(reverse("learning_logs:api_topics"), **self.auth())
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["text"], "Django ORM")

    def test_data_is_isolated_between_users(self):
        Topic.objects.create(text="Bob 的主题", owner=self.bob)
        payload = self.client.get(
            reverse("learning_logs:api_topics"), **self.auth()
        ).json()
        self.assertEqual([row["text"] for row in payload["results"]], ["Django ORM"])

    def test_entries_endpoint_filters(self):
        response = self.client.get(
            reverse("learning_logs:api_entries"), {"q": "QuerySet"}, **self.auth()
        )
        payload = response.json()
        self.assertEqual(payload["count"], 1)

        response = self.client.get(
            reverse("learning_logs:api_entries"), {"q": "不存在的内容"}, **self.auth()
        )
        self.assertEqual(response.json()["count"], 0)

    def test_quick_entry_creates_note(self):
        response = self.client.post(
            reverse("learning_logs:api_quick_entry"),
            {"topic_name": "新主题", "text": "来自 API 的笔记"},
            **self.auth(),
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Entry.objects.filter(text="来自 API 的笔记").exists())

    def test_quick_entry_rejects_empty_text(self):
        response = self.client.post(
            reverse("learning_logs:api_quick_entry"),
            {"topic": self.topic.id, "text": "  "},
            **self.auth(),
        )
        self.assertEqual(response.status_code, 400)

    def test_revoked_token_stops_working(self):
        self.token.revoked = True
        self.token.save()
        response = self.client.get(reverse("learning_logs:api_topics"), **self.auth())
        self.assertEqual(response.status_code, 401)

    def test_token_page_issues_and_revokes(self):
        response = self.client.post(
            reverse("learning_logs:api_tokens"), {"action": "create", "name": "脚本"}
        )
        self.assertEqual(response.status_code, 302)
        created = ApiToken.objects.get(user=self.alice, name="脚本")
        self.assertNotEqual(created.token, "")

        response = self.client.post(
            reverse("learning_logs:api_tokens"),
            {"action": "revoke", "token_id": created.id},
        )
        self.assertEqual(response.status_code, 302)
        created.refresh_from_db()
        self.assertTrue(created.revoked)

    def test_token_page_shows_only_own_tokens(self):
        ApiToken.issue(self.bob, "Bob 的令牌")
        response = self.client.get(reverse("learning_logs:api_tokens"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "测试令牌")
        self.assertNotContains(response, "Bob 的令牌")

    def test_docs_page(self):
        response = self.client.get(reverse("learning_logs:api_docs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/api/v1/topics/")

    def test_due_cards_and_stats(self):
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="Q", back="A")
        due = self.client.get(reverse("learning_logs:api_due_cards"), **self.auth()).json()
        self.assertEqual(due["count"], 1)

        payload = self.client.get(reverse("learning_logs:api_stats"), **self.auth()).json()
        self.assertTrue(payload["ok"])
        self.assertIn("streak", payload)


class NotificationTests(BaseTestCase):
    """站内提醒的生成、已读与隔离。"""

    def test_due_cards_notification(self):
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="Q", back="A")
        created = notifications.generate(self.alice)
        self.assertGreaterEqual(created, 1)
        item = Notification.objects.filter(user=self.alice, kind=Notification.KIND_DUE).first()
        self.assertIsNotNone(item)
        self.assertIn("闪卡", item.title)

    def test_generate_is_idempotent_per_day(self):
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="Q", back="A")
        self.assertGreaterEqual(notifications.generate(self.alice), 1)
        before = Notification.objects.filter(user=self.alice).count()
        self.assertEqual(notifications.generate(self.alice), 0)
        self.assertEqual(Notification.objects.filter(user=self.alice).count(), before)

    def test_streak_notification_when_no_entry_today(self):
        Entry.objects.filter(id=self.entry.id).update(
            date_added=timezone.now() - timedelta(days=3)
        )
        notifications.generate(self.alice)
        self.assertTrue(
            Notification.objects.filter(
                user=self.alice, kind=Notification.KIND_STREAK
            ).exists()
        )

    def test_notifications_page_and_mark_read(self):
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="Q", back="A")
        notifications.generate(self.alice)
        response = self.client.get(reverse("learning_logs:notifications"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "闪卡")

        item = Notification.objects.filter(user=self.alice).first()
        response = self.client.post(
            reverse("learning_logs:notification_read", args=[item.id])
        )
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertFalse(item.is_unread)

    def test_mark_all_read(self):
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="Q", back="A")
        notifications.generate(self.alice)
        self.assertGreater(notifications.unread_count(self.alice), 0)
        self.client.post(reverse("learning_logs:notifications_read_all"))
        self.assertEqual(notifications.unread_count(self.alice), 0)

    def test_cannot_read_others_notification(self):
        bob_card_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        Flashcard.objects.create(user=self.bob, topic=bob_card_topic, front="Q", back="A")
        notifications.generate(self.bob)
        item = Notification.objects.get(user=self.bob)

        response = self.client.post(
            reverse("learning_logs:notification_read", args=[item.id])
        )
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertTrue(item.is_unread)

    def test_unread_count_in_context(self):
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="Q", back="A")
        notifications.generate(self.alice)
        response = self.client.get(reverse("learning_logs:notifications"))
        self.assertGreaterEqual(response.context["unread_count"], 1)
        self.assertContains(response, "bell__dot")

    def test_prune_keeps_recent(self):
        for index in range(45):
            Notification.objects.create(
                user=self.alice, kind=Notification.KIND_DUE, title=f"提醒 {index}"
            )
        notifications.prune(self.alice)
        self.assertLessEqual(Notification.objects.filter(user=self.alice).count(), 40)


class ImportCenterTests(BaseTestCase):
    """批量建卡与 Anki CSV 导入。"""

    def test_parse_card_lines(self):
        pairs = export.parse_card_lines(
            "# 注释\n问题 A | 答案 A\n问题 B\t答案 B\n没有分隔符\n"
        )
        self.assertEqual(pairs, [("问题 A", "答案 A"), ("问题 B", "答案 B")])

    def test_import_cards_skips_duplicates(self):
        result = export.import_cards(self.alice, self.topic, "Q1 | A1\nQ1 | A1\nQ2 | A2")
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["skipped"], 1)

    def test_import_cards_csv_with_header(self):
        content = "Front,Back\nCSV 问题,CSV 答案\n"
        result = export.import_cards_csv(self.alice, self.topic, content)
        self.assertEqual(result["created"], 1)
        card = Flashcard.objects.get(front="CSV 问题")
        self.assertEqual(card.back, "CSV 答案")

    def test_import_rejects_foreign_topic(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        result = export.import_cards(self.alice, bob_topic, "Q | A")
        self.assertEqual(result["created"], 0)
        self.assertEqual(Flashcard.objects.filter(user=self.bob).count(), 0)

    def test_import_page_and_action(self):
        response = self.client.get(reverse("learning_logs:import_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "导入中心")

        response = self.client.post(
            reverse("learning_logs:import_cards"),
            {"topic": self.topic.id, "cards": "页面问题 | 页面答案"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Flashcard.objects.filter(front="页面问题").exists())

    def test_import_requires_own_topic(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        response = self.client.post(
            reverse("learning_logs:import_cards"),
            {"topic": bob_topic.id, "cards": "Q | A"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Flashcard.objects.count(), 0)


class CardStatsTests(BaseTestCase):
    def test_stats_page(self):
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="Q1", back="A1")
        mastered = Flashcard.objects.create(
            user=self.alice, topic=self.topic, front="Q2", back="A2"
        )
        mastered.repetitions = 4
        mastered.interval_days = 20
        mastered.save()
        mastered.review(5)

        response = self.client.get(reverse("learning_logs:card_stats"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 2)
        self.assertEqual(response.context["buckets"]["已掌握"], 1)
        self.assertEqual(response.context["buckets"]["未开始"], 1)
        self.assertContains(response, "复习统计")

    def test_daily_series_has_two_weeks(self):
        response = self.client.get(reverse("learning_logs:card_stats"))
        self.assertEqual(len(response.context["daily"]), 14)


class HomeSnapshotTests(BaseTestCase):
    def test_home_shows_snapshot_for_logged_user(self):
        response = self.client.get(reverse("learning_logs:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的学习快照")
        self.assertEqual(response.context["snapshot"]["topics"], 1)
        self.assertEqual(response.context["snapshot"]["entries"], 1)

    def test_home_is_public_for_anonymous(self):
        client = Client()
        response = client.get(reverse("learning_logs:index"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "我的学习快照")


class TopicFilterTests(BaseTestCase):
    def test_topic_page_has_filter_toolbar(self):
        tags.sync_tags(self.alice, self.topic, "筛选测试")
        response = self.client.get(reverse("learning_logs:topic", args=[self.topic.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-entry-filter")
        self.assertContains(response, "data-entry-item")
        self.assertContains(response, "筛选测试")


class PwaUpdateTests(BaseTestCase):
    def test_service_worker_caches_new_assets(self):
        response = self.client.get(reverse("service_worker"))
        body = response.content.decode()
        self.assertIn("zhiji-shell-v2", body)
        self.assertIn("editor.js", body)
        self.assertIn("focus.js", body)

    def test_offline_page_links_key_pages(self):
        response = self.client.get(reverse("offline"))
        self.assertContains(response, "/today/")
        self.assertContains(response, "/graph/")

    def test_manifest_still_valid(self):
        response = self.client.get(reverse("manifest"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["name"])
        self.assertTrue(payload["icons"])


class TagSearchTests(BaseTestCase):
    def test_search_returns_tag_group(self):
        tags.sync_tags(self.alice, self.topic, "搜索标签")
        data = search.search_all(self.alice, "搜索标签")
        self.assertTrue(data["tags"])
        self.assertEqual(data["tags"][0]["title"], "#搜索标签")
        self.assertIn("/tags/", data["tags"][0]["url"])
        self.assertGreater(data["total"], 0)

    def test_api_search_includes_tags(self):
        tags.sync_tags(self.alice, self.topic, "接口标签")
        response = self.client.get(
            reverse("learning_logs:api_search"), {"q": "接口标签"}
        )
        payload = response.json()
        self.assertTrue(payload["tags"])
        self.assertEqual(payload["tags"][0]["title"], "#接口标签")

    def test_search_without_terms_returns_empty(self):
        data = search.search_all(self.alice, "  ")
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["tags"], [])

    def test_tag_search_is_isolated(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        tags.sync_tags(self.bob, bob_topic, "Bob 的标签")
        data = search.search_all(self.alice, "Bob 的标签")
        self.assertEqual(data["tags"], [])


class TopicsPageTests(BaseTestCase):
    def test_topics_page_has_filter_and_sort(self):
        tags.sync_tags(self.alice, self.topic, "列表标签")
        response = self.client.get(reverse("learning_logs:topics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-topic-filter")
        self.assertContains(response, "data-topic-sort")
        self.assertContains(response, "列表标签")

    def test_topics_shows_only_own(self):
        Topic.objects.create(text="Bob 的主题", owner=self.bob)
        response = self.client.get(reverse("learning_logs:topics"))
        self.assertContains(response, "Django ORM")
        self.assertNotContains(response, "Bob 的主题")


class FakeTagProvider(FakeProvider):
    def complete(self, messages, model=None, **kwargs):
        return json.dumps({"tags": ["惰性求值", "查询优化", "惰性求值"]}, ensure_ascii=False)


class FakeBrokenTagProvider(FakeProvider):
    def complete(self, messages, model=None, **kwargs):
        return "这不是 JSON"


class AiTagTests(BaseTestCase):
    """AI 建议标签：正常返回、异常兜底与越权。"""

    @patch("learning_logs.ai.service.get_provider", return_value=FakeTagProvider())
    def test_suggest_tags_merges_into_topic(self, _provider):
        response = self.client.post(
            reverse("learning_logs:suggest_tags", args=[self.topic.id])
        )
        payload = response.json()
        self.assertTrue(payload["ok"])
        # 建议里重复的「惰性求值」应被去重
        self.assertEqual(
            sorted(tag.name for tag in tags.tags_of(self.topic)),
            sorted(["查询优化", "惰性求值"]),
        )

    @patch("learning_logs.ai.service.get_provider", return_value=FakeBrokenTagProvider())
    def test_suggest_tags_handles_bad_response(self, _provider):
        response = self.client.post(
            reverse("learning_logs:suggest_tags", args=[self.topic.id])
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_suggest_tags_requires_own_topic(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        response = self.client.post(
            reverse("learning_logs:suggest_tags", args=[bob_topic.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_topic_page_has_ai_tag_button(self):
        response = self.client.get(reverse("learning_logs:topic", args=[self.topic.id]))
        self.assertContains(response, "data-ai-tags")


class NoteTemplateTests(BaseTestCase):
    def test_new_entry_page_has_template_picker(self):
        response = self.client.get(reverse("learning_logs:new_entry", args=[self.topic.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-template-picker")
        self.assertContains(response, "templates_picker.js")


class AccessibilityTests(BaseTestCase):
    def test_skip_link_and_main_landmark(self):
        response = self.client.get(reverse("learning_logs:topics"))
        self.assertContains(response, "skip-link")
        self.assertContains(response, 'id="main-content"')

    def test_current_page_is_announced(self):
        response = self.client.get(reverse("learning_logs:topics"))
        self.assertContains(response, 'aria-current="page"')

    def test_forms_have_labels(self):
        response = self.client.get(reverse("learning_logs:new_entry", args=[self.topic.id]))
        body = response.content.decode()
        self.assertIn("<label", body)
        self.assertIn("csrfmiddlewaretoken", body)


class SmokeTests(BaseTestCase):
    """关键页面一次性冒烟：确保导航能到的地方都能打开。"""

    PATHS = [
        "/",
        "/topics/",
        "/new_topic/",
        "/learning-paths/",
        "/goals/",
        "/dashboard/",
        "/analytics/",
        "/garden/",
        "/graph/",
        "/tags/",
        "/today/",
        "/focus/",
        "/flashcards/",
        "/flashcards/review/",
        "/flashcards/stats/",
        "/import/",
        "/data/",
        "/notifications/",
        "/features/",
        "/timeline/",
        "/api/docs/",
        "/settings/api/",
        "/weekly/",
        "/achievements/",
        "/healthz/",
        "/offline/",
    ]

    def test_pages_open(self):
        for path in self.PATHS:
            response = self.client.get(path)
            self.assertIn(
                response.status_code,
                (200, 302),
                f"{path} 返回了 {response.status_code}",
            )

    def test_topic_and_entry_pages(self):
        self.assertEqual(
            self.client.get(f"/topic/{self.topic.id}").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/new_entry/{self.topic.id}").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/edit_entry/{self.entry.id}").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/entry/{self.entry.id}/comments/").status_code, 200
        )

    def test_anonymous_is_redirected(self):
        anonymous = Client()
        for path in ["/topics/", "/graph/", "/today/", "/notifications/"]:
            self.assertEqual(anonymous.get(path).status_code, 302, path)


class TimelineTests(BaseTestCase):
    def test_timeline_groups_by_month(self):
        data = timeline.build(self.alice, months=12)
        self.assertEqual(data["total_entries"], 1)
        self.assertEqual(len(data["months"]), 1)
        self.assertIn("Django ORM", data["months"][0]["topics"])

    def test_timeline_page_renders(self):
        response = self.client.get(reverse("learning_logs:timeline"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "学习时间线")
        self.assertEqual(response.context["range_months"], 12)

    def test_timeline_range_switch(self):
        response = self.client.get(reverse("learning_logs:timeline"), {"months": "6"})
        self.assertEqual(response.context["range_months"], 6)

    def test_timeline_only_own_data(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        Entry.objects.create(topic=bob_topic, text="Bob 的笔记")
        data = timeline.build(self.alice, months=12)
        self.assertEqual(data["total_entries"], 1)
        self.assertNotIn("Bob 的主题", data["months"][0]["topics"])


class WikiLinkTests(BaseTestCase):
    """[[双链]] 渲染与反向链接。"""

    def test_extract_names(self):
        self.assertEqual(links.extract("参考 [[Django ORM]] 与 [[缓存]] 还有 [[Django ORM]]"), ["Django ORM", "缓存"])

    def test_render_links_to_existing_topic(self):
        target = Topic.objects.create(text="缓存策略", owner=self.alice)
        text = "这里要配合 [[缓存策略]] 一起看。"
        rendered = links.render(text, self.alice)
        self.assertIn(f"[/缓存策略](/topic/{target.id})".replace("/缓存策略", "缓存策略"), rendered)
        self.assertNotIn("[[", rendered)

    def test_render_keeps_unknown_topic_as_text(self):
        rendered = links.render("指向 [[不存在的主题]]", self.alice)
        self.assertIn("[[不存在的主题]]", rendered)

    def test_backlinks_finds_referring_entries(self):
        other = Topic.objects.create(text="缓存策略", owner=self.alice)
        Entry.objects.create(topic=other, text="参见 [[Django ORM]] 的惰性求值")
        found = links.backlinks(self.topic)
        self.assertEqual(len(found), 1)
        self.assertIn("Django ORM", found[0].text)

    def test_backlinks_ignores_other_users(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        Entry.objects.create(topic=bob_topic, text="参见 [[Django ORM]]")
        self.assertEqual(links.backlinks(self.topic), [])

    def test_topic_page_shows_backlinks(self):
        other = Topic.objects.create(text="缓存策略", owner=self.alice)
        Entry.objects.create(topic=other, text="参见 [[Django ORM]] 的实现")
        response = self.client.get(reverse("learning_logs:topic", args=[self.topic.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "反向链接")
        self.assertEqual(len(response.context["backlinks"]), 1)

    def test_entry_page_renders_link(self):
        target = Topic.objects.create(text="缓存策略", owner=self.alice)
        entry = Entry.objects.create(topic=self.topic, text="参考 [[缓存策略]]")
        response = self.client.get(reverse("learning_logs:entry_comments", args=[entry.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/topic/{target.id}")


class TopicFlagTests(BaseTestCase):
    """主题置顶与归档。"""

    def test_toggle_pinned(self):
        url = reverse("learning_logs:toggle_topic_flag", args=[self.topic.id, "pinned"])
        self.client.post(url)
        self.topic.refresh_from_db()
        self.assertTrue(self.topic.pinned)

        self.client.post(url)
        self.topic.refresh_from_db()
        self.assertFalse(self.topic.pinned)

    def test_toggle_archived_hides_from_default_list(self):
        url = reverse("learning_logs:toggle_topic_flag", args=[self.topic.id, "archived"])
        self.client.post(url)
        self.topic.refresh_from_db()
        self.assertTrue(self.topic.archived)

        response = self.client.get(reverse("learning_logs:topics"))
        self.assertNotContains(response, "Django ORM")

        response = self.client.get(reverse("learning_logs:topics"), {"archived": "1"})
        self.assertContains(response, "Django ORM")

    def test_unknown_flag_is_404(self):
        response = self.client.post(
            reverse("learning_logs:toggle_topic_flag", args=[self.topic.id, "nope"])
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_flag_others_topic(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        response = self.client.post(
            reverse("learning_logs:toggle_topic_flag", args=[bob_topic.id, "pinned"])
        )
        self.assertEqual(response.status_code, 404)
        bob_topic.refresh_from_db()
        self.assertFalse(bob_topic.pinned)

    def test_pinned_topic_comes_first(self):
        other = Topic.objects.create(text="另一个主题", owner=self.alice)
        other.pinned = True
        other.save(update_fields=["pinned"])
        response = self.client.get(reverse("learning_logs:topics"))
        titles = [item.text for item in response.context["topics"]]
        self.assertEqual(titles[0], "另一个主题")


class PublicProfileTests(BaseTestCase):
    """公开主页：只聚合主动分享的主题。"""

    def test_404_when_nothing_shared(self):
        anonymous = Client()
        response = anonymous.get(reverse("learning_logs:public_profile", args=["alice"]))
        self.assertEqual(response.status_code, 404)

    def test_lists_shared_topics_only(self):
        shared = Topic.objects.create(text="公开的主题", owner=self.alice)
        shared.share_token = "token-abc"
        shared.save(update_fields=["share_token"])
        Topic.objects.create(text="私有的主题", owner=self.alice)

        anonymous = Client()
        response = anonymous.get(reverse("learning_logs:public_profile", args=["alice"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "公开的主题")
        self.assertNotContains(response, "私有的主题")

    def test_profile_hides_private_entries(self):
        shared = Topic.objects.create(text="公开的主题", owner=self.alice)
        shared.share_token = "token-xyz"
        shared.save(update_fields=["share_token"])
        Entry.objects.create(topic=shared, text="公开的笔记内容")

        anonymous = Client()
        response = anonymous.get(reverse("learning_logs:public_profile", args=["alice"]))
        self.assertContains(response, "公开的笔记内容")
        self.assertNotContains(response, "QuerySet 是惰性的")

    def test_unknown_user_is_404(self):
        anonymous = Client()
        response = anonymous.get(reverse("learning_logs:public_profile", args=["nobody"]))
        self.assertEqual(response.status_code, 404)


class EntryRevisionTests(BaseTestCase):
    """笔记版本历史：留痕、预览与回滚。"""

    def test_edit_creates_revision(self):
        self.client.post(
            reverse("learning_logs:edit_entry", args=[self.entry.id]),
            {"text": "修改后的内容", "tags": ""},
        )
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.text, "修改后的内容")
        self.assertEqual(self.entry.revisions.count(), 1)
        self.assertEqual(self.entry.revisions.first().text, "QuerySet 是惰性的")

    def test_no_revision_when_text_unchanged(self):
        self.client.post(
            reverse("learning_logs:edit_entry", args=[self.entry.id]),
            {"text": "QuerySet 是惰性的", "tags": ""},
        )
        self.assertEqual(self.entry.revisions.count(), 0)

    def test_history_page_and_preview(self):
        self.client.post(
            reverse("learning_logs:edit_entry", args=[self.entry.id]),
            {"text": "第二版内容", "tags": ""},
        )
        revision = self.entry.revisions.first()
        response = self.client.get(reverse("learning_logs:entry_history", args=[self.entry.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "历史版本")

        response = self.client.get(
            reverse("learning_logs:entry_history", args=[self.entry.id]),
            {"preview": revision.id},
        )
        self.assertEqual(response.context["preview"].text, "QuerySet 是惰性的")

    def test_restore_rolls_back(self):
        self.client.post(
            reverse("learning_logs:edit_entry", args=[self.entry.id]),
            {"text": "被改坏的内容", "tags": ""},
        )
        revision = self.entry.revisions.first()

        response = self.client.post(
            reverse("learning_logs:restore_entry", args=[revision.id])
        )
        self.assertEqual(response.status_code, 302)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.text, "QuerySet 是惰性的")
        # 回滚前的「被改坏的内容」也应留痕
        self.assertEqual(self.entry.revisions.count(), 2)

    def test_cannot_restore_others_revision(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        bob_entry = Entry.objects.create(topic=bob_topic, text="Bob 的笔记")
        bob_entry.text = "Bob 改过的内容"
        snapshot_entry(bob_entry, self.bob)
        bob_entry.save()

        response = self.client.post(
            reverse("learning_logs:restore_entry", args=[bob_entry.revisions.first().id])
        )
        self.assertEqual(response.status_code, 404)

    def test_history_page_requires_ownership(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        bob_entry = Entry.objects.create(topic=bob_topic, text="Bob 的笔记")
        response = self.client.get(
            reverse("learning_logs:entry_history", args=[bob_entry.id])
        )
        self.assertEqual(response.status_code, 404)


class InsightsTests(BaseTestCase):
    def test_insights_page(self):
        response = self.client.get(reverse("learning_logs:insights"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "学习洞察")
        self.assertTrue(response.context["suggestions"])

    def test_insights_detects_best_hour(self):
        # 洞察按本地时区聚合小时，这里也用本地时间构造，避免 UTC/Local 偏移
        base = timezone.localtime(timezone.now()).replace(
            hour=21, minute=0, second=0, microsecond=0
        )
        StudySession.objects.create(
            user=self.alice,
            topic=self.topic,
            start_time=base,
            end_time=base + timedelta(minutes=45),
        )
        data = insights.build(self.alice)
        hour_card = next(card for card in data["cards"] if card["title"] == "黄金时段")
        self.assertIn("21", hour_card["value"])

    def test_insights_flags_idle_topics(self):
        old_topic = Topic.objects.create(text="被搁置的主题", owner=self.alice)
        Entry.objects.create(topic=old_topic, text="很久以前写的")
        Entry.objects.filter(topic=old_topic).update(
            date_added=timezone.now() - timedelta(days=40)
        )
        data = insights.build(self.alice)
        self.assertIn("被搁置的主题", data["idle_topics"])

    def test_insights_review_health(self):
        Flashcard.objects.create(user=self.alice, topic=self.topic, front="Q", back="A")
        data = insights.build(self.alice)
        self.assertEqual(data["review"]["total"], 1)
        self.assertEqual(data["review"]["due"], 1)

    def test_insights_is_user_scoped(self):
        bob_topic = Topic.objects.create(text="Bob 的主题", owner=self.bob)
        StudySession.objects.create(
            user=self.bob,
            topic=bob_topic,
            start_time=timezone.now().replace(hour=6, minute=0, second=0, microsecond=0),
            end_time=timezone.now().replace(hour=6, minute=30, second=0, microsecond=0),
        )
        data = insights.build(self.alice)
        hour_card = next(card for card in data["cards"] if card["title"] == "黄金时段")
        self.assertEqual(hour_card["value"], "暂无数据")
