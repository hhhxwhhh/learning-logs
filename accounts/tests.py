"""账号模块测试：注册、登录、登出与个人中心。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AuthFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pass-12345", email="a@example.com")

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newbie",
                "email": "new@example.com",
                "password1": "a-very-strong-pass-9527",
                "password2": "a-very-strong-pass-9527",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newbie").exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username="newbie").id)

    def test_register_rejects_mismatched_password(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newbie",
                "password1": "a-very-strong-pass-9527",
                "password2": "different-pass-9527",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_login_success_and_failure(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "alice", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户名或密码不正确")

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "alice", "password": "pass-12345"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.client.get(reverse("accounts:logout"))
        self.assertIn("_auth_user_id", self.client.session)

        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_edit_profile_updates_email(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("accounts:edit_profile"),
            {
                "username": "alice",
                "first_name": "Alice",
                "last_name": "Wang",
                "email": "new@example.com",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.first_name, "Alice")
