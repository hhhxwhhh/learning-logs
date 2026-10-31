"""账号相关视图：注册、登录、个人中心、修改密码。"""

from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from learning_logs.models import Entry, StudySession, Topic

from .forms import CustomUserChangeForm, CustomUserCreationForm


def register(request):
    if request.user.is_authenticated:
        return redirect("learning_logs:dashboard")

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "欢迎加入，开始记录你的第一条学习笔记吧。")
            return redirect("learning_logs:topics")
    else:
        form = CustomUserCreationForm()

    return render(request, "accounts/register.html", {"form": form})


def user_login(request):
    if request.user.is_authenticated:
        return redirect("learning_logs:dashboard")

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect("learning_logs:dashboard")
        error = "用户名或密码不正确，请重试。"

    return render(
        request,
        "accounts/login.html",
        {"error": error, "next": request.GET.get("next", "")},
    )


def logout(request):
    """登出必须是 POST，避免被第三方页面 GET 触发。"""
    if request.method == "POST":
        auth_logout(request)
        messages.info(request, "你已安全退出登录。")
    return redirect("learning_logs:index")


@login_required
def profile(request):
    topics = Topic.objects.filter(owner=request.user)
    context = {
        "topic_count": topics.count(),
        "entry_count": Entry.objects.filter(topic__owner=request.user).count(),
        "session_count": StudySession.objects.filter(user=request.user).count(),
        "completed_entries": Entry.objects.filter(
            topic__owner=request.user, completed=True
        ).count(),
        "top_topics": topics.annotate(entry_count=Count("entry")).order_by("-entry_count")[:5],
        "password_form": PasswordChangeForm(request.user),
    }
    return render(request, "accounts/profile.html", context)


@login_required
def edit_profile(request):
    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "资料已更新。")
            return redirect("accounts:profile")
    else:
        form = CustomUserChangeForm(instance=request.user)
    return render(request, "accounts/edit_profile.html", {"form": form})


@login_required
def change_password(request):
    if request.method != "POST":
        return redirect(reverse("accounts:profile") + "#security")

    form = PasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "密码修改成功。")
    else:
        messages.error(
            request,
            "密码修改失败，请检查输入："
            + "；".join(f"{field}: {', '.join(errors)}" for field, errors in form.errors.items()),
        )
    return redirect(reverse("accounts:profile") + "#security")
