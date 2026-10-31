import logging
import random
import secrets
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .ai.providers import AIError
from .ai.service import generate_flashcards
from .forms import (
    CommentForm,
    EntryForm,
    LearningPathForm,
    PathStepForm,
    StepResourceForm,
    TopicForm,
)
from .models import (
    ApiToken,
    Comment,
    Entry,
    Flashcard,
    LearningGoal,
    LearningPath,
    Notification,
    PathStep,
    StepResource,
    StudySession,
    Tag,
    TaggedItem,
    Topic,
    WeeklyReport,
)
from .services import achievements as achievements_service
from .services import export as export_service
from .services import garden as garden_service
from .services import graph as graph_service
from .services import notifications as notifications_service
from .services import report as report_service
from .services import search as search_service
from .services import stats
from .services import tags as tags_service
from .utils.markdown import render_markdown

logger = logging.getLogger(__name__)

app_name = "learning_logs"
# Create your views here.
def index(request):
    #学习笔记的主页
    return render(request,'learning_logs/index.html')

@login_required
def topics(request):
    """显示所有的主题"""
    topics=Topic.objects.filter(owner=request.user).order_by('date_added')
    context={'topics':topics}
    return render(request,'learning_logs/topics.html',context)

@login_required
def topic(request, topic_id):
    """显示单个主题及其所有条目"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    
    entries = topic.entry_set.order_by('-date_added')
    
    # 更新主题进度
    topic.update_progress()
    
    # 检查是否有活动的学习会话
    active_session = None
    session_id = request.session.get('active_session_id')
    if session_id:
        try:
            active_session = StudySession.objects.get(id=session_id, user=request.user)
        except StudySession.DoesNotExist:
            pass
    
    if request.method == "POST" and "tags" in request.POST:
        tags_service.sync_tags(request.user, topic, request.POST.get("tags", ""))
        messages.success(request, "标签已更新。")
        return redirect("learning_logs:topic", topic_id=topic.id)

    entries = list(entries)
    for entry in entries:
        entry.tag_list = tags_service.tags_of(entry)

    context = {
        'topic': topic, 
        'entries': entries,
        'active_session': active_session,
        'topic_tags': tags_service.tags_of(topic),
    }
    return render(request, 'learning_logs/topic.html', context)

@login_required
def new_entry(request, topic_id):
   topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
   if request.method != 'POST':
       # 未提交数据，创建一个空表单
       form = EntryForm()
   else:
       # 利用POST提交的数据创建一个新的表单
       form = EntryForm(data=request.POST)
       if form.is_valid():
           new_entry = form.save(commit=False)
           new_entry.topic = topic
           new_entry.save()
           tags_service.sync_tags(request.user, new_entry, request.POST.get("tags", ""))
           return redirect('learning_logs:topic', topic_id=topic_id)
   # 显示空表单或者指出表单的数据无效
   context = {'topic': topic, 'form': form, 'tags_input': request.POST.get('tags', '')}
   return render(request, 'learning_logs/new_entry.html', context)

@login_required
def new_topic(request):
    # 添加新主题
    if request.method != 'POST':
        # 未提交数据：创建一个新表单
        form = TopicForm()
    else:
        # POST提交的数据，对数据进行处理
        form = TopicForm(data=request.POST)
        if form.is_valid():
            new_topic = form.save(commit=False)
            new_topic.owner = request.user
            new_topic.save()
            tags_service.sync_tags(request.user, new_topic, request.POST.get("tags", ""))
            return redirect('learning_logs:topics')  # 重定向到主题页面topics
    # 显示空表单或者指出表单数据无效
    context = {'form': form, 'tags_input': request.POST.get('tags', '')}
    return render(request, 'learning_logs/new_topic.html', context)

@login_required
def edit_entry(request,entry_id):
    #编辑既有的条目
    entry = get_object_or_404(Entry, id=entry_id, topic__owner=request.user)
    topic = entry.topic
    if request.method!='POST':
        #初次请求，使用当前条目填充表单
        form=EntryForm(instance=entry)
        tags_input = tags_service.tags_input_of(entry)
    else:
        #POST提交的数据，对数据进行处理
        form=EntryForm(instance=entry,data=request.POST)
        tags_input = request.POST.get('tags','')
        if form.is_valid():
            form.save()
            tags_service.sync_tags(request.user, entry, tags_input)
            return redirect('learning_logs:topic',topic_id=topic.id)
    context={'entry':entry,'topic':topic,'form':form,'tags_input':tags_input}
    return render(request,'learning_logs/edit_entry.html',context)

@login_required
@require_POST
def delete_entry(request, entry_id):
    entry = get_object_or_404(Entry, id=entry_id, topic__owner=request.user)
    topic = entry.topic
    if request.method == 'POST':
        entry.delete()
        return redirect('learning_logs:topic', topic_id=topic.id)
    # 如果不是 POST 请求，返回主题页面
    return redirect('learning_logs:topic', topic_id=topic.id)

@login_required
def search(request):
    query = request.GET.get('q', '').strip()
    # 只在自己的数据里搜索，避免越权读取他人笔记
    topics = Topic.objects.filter(owner=request.user, text__icontains=query)
    entries = Entry.objects.filter(
        topic__owner=request.user, text__icontains=query
    ).select_related('topic')
    context = {
        'query': query,
        'topics': topics,
        'entries': entries,
    }
    return render(request, 'learning_logs/search_results.html', context)

@login_required
def entry_comments(request, entry_id):
    entry = get_object_or_404(Entry, id=entry_id, topic__owner=request.user)
    comments = entry.comments.all()

    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.entry = entry
            comment.user = request.user
            comment.save()
            return redirect('learning_logs:entry_comments', entry_id=entry.id)
    else:
        form = CommentForm()

    context = {'entry': entry, 'comments': comments, 'form': form}
    return render(request, 'learning_logs/entry_comments.html', context)

@login_required
@require_POST
def delete_topic(request, topic_id):
    """删除指定的主题"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    if request.method == 'POST':
        topic.delete()
        return redirect('learning_logs:topics')
    return redirect('learning_logs:topics')

@login_required
def dashboard(request):
    """学习仪表盘：指标、热力图、趋势与待办。"""
    overview = stats.overview(request.user)

    weekly = stats.weekly_totals(request.user, weeks=8)

    context = {
        "overview": overview,
        "heatmap": stats.heatmap_weeks(request.user),
        "weekly": weekly,
        "topic_ranking": stats.topic_ranking(request.user),
        "recent_entries": Entry.objects.filter(topic__owner=request.user)
        .select_related("topic")
        .order_by("-date_added")[:5],
        "goals": stats.upcoming_goals(request.user),
        "paths": LearningPath.objects.filter(user=request.user).order_by("-updated_at")[:3],
        "format_minutes": stats.format_minutes,
    }
    return render(request, "learning_logs/dashboard.html", context)


@login_required
def goals(request):
    """管理学习目标"""
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        target_date = stats.parse_date(request.POST.get("target_date", ""))

        if not title:
            messages.error(request, "目标名称不能为空。")
        elif target_date is None:
            messages.error(request, "请选择合法的截止日期。")
        else:
            LearningGoal.objects.create(
                user=request.user,
                title=title,
                description=description,
                target_date=target_date,
            )
            messages.success(request, "目标已添加，记得给它留出时间。")
            return redirect("learning_logs:goals")

    return render(
        request,
        "learning_logs/goals.html",
        {"goals": LearningGoal.objects.filter(user=request.user).order_by("completed", "target_date")},
    )

@login_required
@require_POST
def toggle_goal(request, goal_id):
    """切换目标完成状态"""
    goal = get_object_or_404(LearningGoal, id=goal_id, user=request.user)
    goal.completed = not goal.completed
    goal.save()
    return redirect('learning_logs:goals')

@login_required
@require_POST
def start_session(request, topic_id):
    """开始一个学习会话"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    
    # 创建一个新会话
    session = StudySession.objects.create(
        user=request.user,
        topic=topic,
        start_time=timezone.now(),
        end_time=timezone.now()  # 将在结束时更新
    )
    
    request.session['active_session_id'] = session.id
    return redirect('learning_logs:topic', topic_id=topic.id)

@login_required
@require_POST
def end_session(request):
    """结束当前学习会话"""
    session_id = request.session.get('active_session_id')
    if session_id:
        try:
            session = StudySession.objects.get(id=session_id, user=request.user)
            session.end_time = timezone.now()
            session.save()  # 这将触发 save 方法计算 duration
            del request.session['active_session_id']
            
            # 提供反馈消息
            messages.success(request, f"学习会话已结束，持续了 {session.duration}")
        except StudySession.DoesNotExist:
            messages.error(request, "找不到活动的学习会话")
    
    return redirect('learning_logs:dashboard')

@login_required
def learning_paths(request):
    """显示用户的所有学习路径"""
    paths = LearningPath.objects.filter(user=request.user).order_by('-created_at')
    
    # 获取每个路径的进度
    for path in paths:
        path.progress = path.get_progress()
    
    context = {'paths': paths}
    return render(request, 'learning_logs/learning_paths.html', context)

@login_required
def new_learning_path(request):
    """创建新的学习路径"""
    if request.method == 'POST':
        form = LearningPathForm(request.POST)
        if form.is_valid():
            path = form.save(commit=False)
            path.user = request.user
            path.save()
            messages.success(request, f'学习路径 "{path.title}" 创建成功！')
            return redirect('learning_logs:learning_path_detail', path_id=path.id)
    else:
        form = LearningPathForm()
    
    context = {'form': form}
    return render(request, 'learning_logs/new_learning_path.html', context)

@login_required
def learning_path_detail(request, path_id):
    """显示特定学习路径的详情"""
    path = get_object_or_404(LearningPath, id=path_id, user=request.user)
    steps = path.pathstep_set.all()
    
    # 计算学习进度
    progress = path.get_progress()
    
    # 计算已学习时间
    completed_steps_time = sum([step.estimated_hours for step in steps if step.is_completed])
    
    # 如果是POST请求，添加新步骤
    if request.method == 'POST':
        # 检查是否是添加步骤的请求
        if 'add_step' in request.POST:
            step_form = PathStepForm(request.user, request.POST)
            if step_form.is_valid():
                step = step_form.save(commit=False)
                step.path = path
                step.order = steps.count() + 1
                step.save()
                messages.success(request, '新步骤添加成功！')
                return redirect('learning_logs:learning_path_detail', path_id=path.id)
        
        # 检查是否是更新路径状态的请求
        elif 'toggle_completion' in request.POST:
            path.is_completed = not path.is_completed
            path.save()
            status = "完成" if path.is_completed else "未完成"
            messages.success(request, f'学习路径状态已更新为{status}')
            return redirect('learning_logs:learning_path_detail', path_id=path.id)
    
    step_form = PathStepForm(request.user)
    
    context = {
        'path': path,
        'steps': steps,
        'progress': progress,
        'completed_hours': completed_steps_time,
        'step_form': step_form,
    }
    return render(request, 'learning_logs/learning_path_detail.html', context)

@login_required
@require_POST
def toggle_step_completion(request, step_id):
    """切换步骤的完成状态"""
    step = get_object_or_404(PathStep, id=step_id)
    
    # 确保用户有权限
    if step.path.user != request.user:
        raise Http404
    
    step.is_completed = not step.is_completed
    step.save()
    
    messages.success(request, f'步骤 "{step.topic.text}" 状态已更新')
    return redirect('learning_logs:learning_path_detail', path_id=step.path.id)

@login_required
def step_detail(request, step_id):
    """显示步骤的详细信息和资源"""
    step = get_object_or_404(PathStep, id=step_id)
    
    # 确保用户有权限
    if step.path.user != request.user:
        raise Http404
    
    resources = step.resources.all()
    
    # 处理添加资源表单
    if request.method == 'POST':
        resource_form = StepResourceForm(request.POST)
        if resource_form.is_valid():
            resource = resource_form.save(commit=False)
            resource.step = step
            resource.save()
            messages.success(request, f'资源 "{resource.title}" 添加成功！')
            return redirect('learning_logs:step_detail', step_id=step.id)
    else:
        resource_form = StepResourceForm()
    
    context = {
        'step': step,
        'resources': resources,
        'resource_form': resource_form,
    }
    return render(request, 'learning_logs/step_detail.html', context)

@login_required
@require_POST
def toggle_resource_completion(request, resource_id):
    """切换资源的完成状态"""
    resource = get_object_or_404(StepResource, id=resource_id)
    
    # 确保用户有权限
    if resource.step.path.user != request.user:
        raise Http404
    
    resource.is_completed = not resource.is_completed
    resource.save()
    
    return redirect('learning_logs:step_detail', step_id=resource.step.id)

@login_required
@require_POST
def delete_learning_path(request, path_id):
    """删除学习路径"""
    path = get_object_or_404(LearningPath, id=path_id, user=request.user)
    
    if request.method == 'POST':
        path_title = path.title
        path.delete()
        messages.success(request, f'学习路径 "{path_title}" 已删除')
        return redirect('learning_logs:learning_paths')
    
    return redirect('learning_logs:learning_path_detail', path_id=path.id)


@login_required
def achievements(request):
    """学习成就：徽章解锁情况。"""
    return render(
        request,
        "learning_logs/achievements.html",
        achievements_service.collect(request.user),
    )


@login_required
def garden(request):
    """学习花园：把主题与笔记可视化成一棵树。"""
    return render(request, "learning_logs/garden.html", garden_service.garden_context(request.user))


@login_required
def flashcards(request):
    """闪卡总览：今日待复习、卡片列表与 AI 生成入口。"""
    today = timezone.localdate()
    cards = Flashcard.objects.filter(user=request.user).select_related("topic")
    due_cards = cards.filter(due_date__lte=today)

    if request.method == "POST":
        front = (request.POST.get("front") or "").strip()
        back = (request.POST.get("back") or "").strip()
        topic_id = request.POST.get("topic")
        topic = Topic.objects.filter(id=topic_id, owner=request.user).first()
        if not front or not back or topic is None:
            messages.error(request, "请填写问题、答案并选择一个主题。")
        else:
            Flashcard.objects.create(
                user=request.user, topic=topic, front=front[:300], back=back
            )
            messages.success(request, "闪卡已添加。")
            return redirect("learning_logs:flashcards")

    context = {
        "cards": cards[:60],
        "total": cards.count(),
        "due_count": due_cards.count(),
        "learned": cards.filter(repetitions__gte=3).count(),
        "topics": Topic.objects.filter(owner=request.user).annotate(
            card_count=Count("flashcards")
        ),
        "today": today,
    }
    return render(request, "learning_logs/flashcards.html", context)


@login_required
def review(request):
    """今日复习队列，一次只显示一张卡。"""
    cards = (
        Flashcard.objects.filter(user=request.user, due_date__lte=timezone.localdate())
        .select_related("topic")
        .order_by("due_date", "id")
    )
    total = cards.count()
    card = cards.first()

    return render(
        request,
        "learning_logs/review.html",
        {"card": card, "remaining": total, "total": total},
    )


@login_required
@require_POST
def review_answer(request, card_id):
    card = get_object_or_404(Flashcard, id=card_id, user=request.user)
    try:
        quality = int(request.POST.get("quality", 3))
    except (TypeError, ValueError):
        quality = 3
    card.review(quality)
    return redirect("learning_logs:review")


@login_required
@require_POST
def delete_flashcard(request, card_id):
    card = get_object_or_404(Flashcard, id=card_id, user=request.user)
    card.delete()
    messages.success(request, "闪卡已删除。")
    return redirect("learning_logs:flashcards")


@login_required
@require_POST
def generate_cards(request, topic_id):
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    try:
        count = int(request.POST.get("count", 8))
    except (TypeError, ValueError):
        count = 8
    count = max(1, min(count, 15))

    try:
        created = generate_flashcards(topic, count=count)
    except AIError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"已为「{topic.text}」生成 {created} 张闪卡。")
    return redirect("learning_logs:flashcards")


API_ENDPOINTS = [
    {
        "method": "GET",
        "path": "/api/v1/me/",
        "desc": "账号信息与学习概览",
        "params": "无",
    },
    {
        "method": "GET",
        "path": "/api/v1/topics/",
        "desc": "全部主题及进度、标签",
        "params": "无",
    },
    {
        "method": "GET",
        "path": "/api/v1/entries/",
        "desc": "笔记列表，支持关键词与主题过滤",
        "params": "q=关键词&topic=主题ID&limit=50",
    },
    {
        "method": "GET",
        "path": "/api/v1/cards/due/",
        "desc": "今日到期与逾期的闪卡",
        "params": "无",
    },
    {
        "method": "GET",
        "path": "/api/v1/sessions/",
        "desc": "学习计时记录",
        "params": "limit=30",
    },
    {
        "method": "GET",
        "path": "/api/v1/stats/",
        "desc": "连续天数、时长、主题排行等统计",
        "params": "无",
    },
    {
        "method": "POST",
        "path": "/api/v1/entries/create/",
        "desc": "快速写入一条笔记（可自动建主题）",
        "params": "text=内容&topic=主题ID 或 topic_name=主题名",
    },
]


FEATURE_GROUPS = [
    {
        "title": "记录与组织",
        "desc": "把每天学到的东西放进来，并让它们彼此产生联系",
        "items": [
            {"name": "主题", "url": "/topics/", "icon": "i-layers", "key": "t",
             "desc": "按主题拆分知识，一个主题一棵树"},
            {"name": "新建主题", "url": "/new_topic/", "icon": "i-plus", "key": "n",
             "desc": "开一个新的学习方向，配好标签"},
            {"name": "学习路径", "url": "/learning-paths/", "icon": "i-route", "key": "p",
             "desc": "把多个主题串成一条有顺序的路线"},
            {"name": "标签", "url": "/tags/", "icon": "i-tag", "key": "",
             "desc": "横向索引，跨主题复用同一套关键词"},
        ],
    },
    {
        "title": "复习与记忆",
        "desc": "用间隔重复把短期记忆变成长期记忆",
        "items": [
            {"name": "闪卡", "url": "/flashcards/", "icon": "i-cards", "key": "c",
             "desc": "管理所有卡片，支持 AI 批量生成"},
            {"name": "今日复习", "url": "/flashcards/review/", "icon": "i-brain", "key": "r",
             "desc": "SM-2 算法挑出今天该复习的卡"},
            {"name": "复习统计", "url": "/flashcards/stats/", "icon": "i-chart", "key": "",
             "desc": "掌握度分布与近 14 天复习节奏"},
            {"name": "导入中心", "url": "/import/", "icon": "i-plus", "key": "",
             "desc": "Markdown 笔记、批量建卡与 Anki CSV 导入"},
            {"name": "专注计时", "url": "/focus/", "icon": "i-timer", "key": "f",
             "desc": "番茄钟，结束即计入学习时长"},
            {"name": "AI 助教", "url": "/topics/", "icon": "i-spark", "key": "",
             "desc": "在主题页里与 AI 多轮对话"},
        ],
    },
    {
        "title": "洞察与回顾",
        "desc": "看见自己的学习曲线，而不只是记流水账",
        "items": [
            {"name": "今日速览", "url": "/today/", "icon": "i-clock", "key": "o",
             "desc": "今日待办、连续天数与记忆闪回"},
            {"name": "仪表盘", "url": "/dashboard/", "icon": "i-chart", "key": "d",
             "desc": "热力图、时长分布与主题排行"},
            {"name": "学习分析", "url": "/analytics/", "icon": "i-chart", "key": "a",
             "desc": "更细的统计分析视角"},
            {"name": "知识图谱", "url": "/graph/", "icon": "i-graph", "key": "g",
             "desc": "主题之间的关联网络"},
            {"name": "学习花园", "url": "/garden/", "icon": "i-sprout", "key": "e",
             "desc": "把学习量长成一棵可视化的树"},
            {"name": "学习周报", "url": "/weekly/", "icon": "i-doc", "key": "w",
             "desc": "AI 参与的一周复盘与建议"},
            {"name": "学习成就", "url": "/achievements/", "icon": "i-target", "key": "b",
             "desc": "徽章体系，记录坚持的痕迹"},
            {"name": "提醒中心", "url": "/notifications/", "icon": "i-bell", "key": "",
             "desc": "到期复习、连续中断与目标临期提醒"},
        ],
    },
    {
        "title": "工具与设置",
        "desc": "数据属于你，随时可以带走",
        "items": [
            {"name": "学习目标", "url": "/goals/", "icon": "i-flag", "key": "",
             "desc": "给学习设一个截止日期"},
            {"name": "数据与备份", "url": "/data/", "icon": "i-doc", "key": "x",
             "desc": "Markdown / Anki / JSON 导出与导入"},
            {"name": "开放 API", "url": "/api/docs/", "icon": "i-spark", "key": "i",
             "desc": "用令牌把数据接到自己的工具链"},
            {"name": "API 令牌", "url": "/settings/api/", "icon": "i-user", "key": "",
             "desc": "签发、吊销个人访问令牌"},
            {"name": "功能地图", "url": "/features/", "icon": "i-book", "key": "m",
             "desc": "本站全部能力与快捷键一览"},
            {"name": "个人中心", "url": "/accounts/profile/", "icon": "i-user", "key": "u",
             "desc": "账号与偏好设置"},
        ],
    },
]


QUICK_ACTIONS = [
    {"label": "新建主题", "url": "/new_topic/", "keywords": ["新建", "主题", "create", "topic"]},
    {"label": "写一条笔记", "url": "/topics/", "keywords": ["笔记", "记录", "entry", "new"]},
    {"label": "仪表盘", "url": "/dashboard/", "keywords": ["仪表盘", "dashboard", "统计", "首页"]},
    {"label": "闪卡复习", "url": "/flashcards/review/", "keywords": ["闪卡", "复习", "review", "记忆"]},
    {"label": "学习路径", "url": "/learning-paths/", "keywords": ["路径", "计划", "path", "plan"]},
    {"label": "学习分析", "url": "/analytics/", "keywords": ["分析", "图表", "analytics", "数据"]},
    {"label": "学习目标", "url": "/goals/", "keywords": ["目标", "goal", " deadline"]},
    {"label": "今日速览", "url": "/today/", "keywords": ["今日", "today", "速览", "回顾"]},
    {"label": "知识图谱", "url": "/graph/", "keywords": ["图谱", "graph", "关联", "网络"]},
    {"label": "标签管理", "url": "/tags/", "keywords": ["标签", "tag", "分类"]},
    {"label": "专注计时", "url": "/focus/", "keywords": ["专注", "番茄", "focus", "计时"]},
    {"label": "功能地图", "url": "/features/", "keywords": ["功能", "地图", "快捷键", "features"]},
    {"label": "开放 API", "url": "/api/docs/", "keywords": ["api", "接口", "令牌", "token"]},
    {"label": "提醒中心", "url": "/notifications/", "keywords": ["提醒", "通知", "notification"]},
    {"label": "导入中心", "url": "/import/", "keywords": ["导入", "anki", "批量", "import"]},
]


@login_required
def api_search(request):
    """命令面板搜索接口：返回主题、笔记与快捷动作。"""
    query = (request.GET.get("q") or "").strip()[:80]
    data = search_service.search_all(request.user, query)

    terms = [term.lower() for term in data["terms"]]
    actions = [
        {"label": item["label"], "url": item["url"]}
        for item in QUICK_ACTIONS
        if not terms
        or any(term in item["label"].lower() or any(term in kw for kw in item["keywords"]) for term in terms)
    ][:5]
    data["actions"] = actions
    return JsonResponse(data)


@login_required
def data_tools(request):
    """数据导出与导入入口。"""
    topics = Topic.objects.filter(owner=request.user).annotate(entry_count=Count("entry"))
    context = {
        "topics": topics,
        "entry_count": Entry.objects.filter(topic__owner=request.user).count(),
        "card_count": Flashcard.objects.filter(user=request.user).count(),
        "path_count": LearningPath.objects.filter(user=request.user).count(),
    }
    return render(request, "learning_logs/data.html", context)


@login_required
def export_notes(request):
    """导出全部笔记为 Markdown zip。"""
    content = export_service.all_topics_zip(request.user)
    response = HttpResponse(content, content_type="application/zip")
    response["Content-Disposition"] = (
        f'attachment; filename="zhiji-notes-{timezone.localdate():%Y%m%d}.zip"'
    )
    return response


@login_required
def export_topic(request, topic_id):
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    content = export_service.topic_markdown(topic)
    response = HttpResponse(content, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="topic-{topic.id}.md"'
    return response


@login_required
def export_cards(request):
    content = export_service.flashcards_csv(request.user)
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="zhiji-flashcards-{timezone.localdate():%Y%m%d}.csv"'
    )
    return response


@login_required
def export_backup(request):
    content = export_service.backup_json(request.user)
    response = HttpResponse(content, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="zhiji-backup-{timezone.localdate():%Y%m%d}.json"'
    )
    return response


@login_required
@require_POST
def import_notes(request):
    """从 Markdown 文件导入笔记。"""
    upload = request.FILES.get("file")
    if upload is None:
        messages.error(request, "请选择要导入的 Markdown 文件。")
        return redirect("learning_logs:data_tools")

    if upload.size > 1024 * 1024:
        messages.error(request, "文件超过 1MB，请拆分后再导入。")
        return redirect("learning_logs:data_tools")

    try:
        text = upload.read().decode("utf-8-sig", errors="ignore")
    except Exception:  # noqa: BLE001
        messages.error(request, "文件无法解析，请确认是 UTF-8 编码的 Markdown。")
        return redirect("learning_logs:data_tools")

    topic = None
    topic_id = request.POST.get("topic")
    if topic_id and topic_id != "new":
        topic = Topic.objects.filter(id=topic_id, owner=request.user).first()
        if topic is None:
            messages.error(request, "选择的主题不存在。")
            return redirect("learning_logs:data_tools")

    if topic is None:
        title = (request.POST.get("title") or "").strip()
        default_name = upload.name.rsplit(".", 1)[0][:200]
        topic_title = title or default_name or f"导入的笔记 {timezone.localdate():%Y-%m-%d}"
        result = export_service.import_markdown(request.user, text, title=topic_title)
    else:
        result = export_service.import_markdown(request.user, text, topic=topic)

    if result["created"] == 0:
        messages.warning(request, "文件里没有识别到可导入的内容（需要 Markdown 标题分段）。")
    else:
        messages.success(
            request,
            f"已导入 {result['created']} 条笔记到「{result['topic'].text}」。",
        )
        return redirect("learning_logs:topic", topic_id=result["topic"].id)
    return redirect("learning_logs:data_tools")


@login_required
def weekly_report(request):
    """学习周报：本周数据 + AI 复盘。"""
    week_param = request.GET.get("week")
    start = report_service.week_start_of(stats.parse_date(week_param))
    data = report_service.collect(request.user, start)
    saved = WeeklyReport.objects.filter(user=request.user, week_start=start).first()

    today = timezone.localdate()
    next_week = start + timedelta(days=7)
    context = {
        "data": data,
        "saved": saved,
        "summary_html": render_markdown(saved.summary) if saved else "",
        "suggestions": report_service.suggestions(data),
        "week_start": start,
        "week_end": start + timedelta(days=6),
        "prev_week": start - timedelta(days=7),
        "next_week": next_week,
        "can_go_next": next_week <= report_service.week_start_of(today),
        "is_current": start == report_service.week_start_of(today),
        "models": getattr(settings, "AI_AVAILABLE_MODELS", []),
    }
    return render(request, "learning_logs/weekly.html", context)


@login_required
@require_POST
def weekly_report_generate(request):
    start = report_service.week_start_of(stats.parse_date(request.POST.get("week")))
    try:
        report_service.generate(request.user, start, model=request.POST.get("model"))
    except AIError as exc:
        messages.error(request, str(exc))
    except Exception:  # noqa: BLE001 - 模型服务异常不应让整页 500
        logger.exception("生成周报失败")
        messages.error(request, "生成失败，请检查 AI 配置或稍后重试。")
    else:
        messages.success(request, "周报已生成，可以随时重新生成覆盖。")
    return redirect(f"/weekly/?week={start:%Y-%m-%d}")


@login_required
@require_POST
def toggle_share(request, topic_id):
    """开启 / 关闭主题的只读分享链接。"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)

    if topic.share_token:
        topic.share_token = ""
        topic.shared_at = None
        messages.success(request, "已关闭分享链接，之前的地址立即失效。")
    else:
        topic.share_token = secrets.token_urlsafe(16)
        topic.shared_at = timezone.now()
        messages.success(request, "分享链接已生成，任何拿到链接的人都能只读查看。")

    topic.save(update_fields=["share_token", "shared_at"])
    return redirect("learning_logs:topic", topic_id=topic.id)


def shared_topic(request, token):
    """公开只读页面：不需要登录，不带任何用户信息。"""
    topic = (
        Topic.objects.filter(share_token=token)
        .exclude(share_token="")
        .first()
        if token
        else None
    )
    if topic is None:
        raise Http404("分享链接不存在或已失效")

    context = {
        "topic": topic,
        "entries": topic.entry_set.order_by("-date_added"),
        "entry_count": topic.total_items,
    }
    return render(request, "learning_logs/shared.html", context)


@login_required
def tags(request):
    """标签总览：标签云 + 最近打过标签的对象。"""
    return render(
        request,
        "learning_logs/tags.html",
        {
            "cloud": tags_service.cloud(request.user),
            "tag_count": Tag.objects.filter(user=request.user).count(),
            "tagged_topics": TaggedItem.objects.filter(
                tag__user=request.user,
                content_type=ContentType.objects.get_for_model(Topic),
            ).count(),
            "tagged_entries": TaggedItem.objects.filter(
                tag__user=request.user,
                content_type=ContentType.objects.get_for_model(Entry),
            ).count(),
        },
    )


@login_required
def tag_detail(request, tag_id):
    """单个标签下的主题与笔记。"""
    data = tags_service.objects_of(request.user, tag_id)
    if data["tag"] is None:
        raise Http404("标签不存在")
    return render(request, "learning_logs/tag_detail.html", data)


@login_required
def graph(request):
    """知识图谱：主题之间的关联网络。"""
    return render(request, "learning_logs/graph.html", graph_service.build(request.user))


@login_required
def features(request):
    """功能地图：把全站能力和快捷键汇总到一页。"""
    total = sum(len(group["items"]) for group in FEATURE_GROUPS)
    return render(
        request,
        "learning_logs/features.html",
        {"groups": FEATURE_GROUPS, "total": total},
    )


@login_required
def api_tokens(request):
    """个人 API 令牌管理：签发、吊销与用法示例。"""
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "revoke":
            token_id = request.POST.get("token_id")
            updated = ApiToken.objects.filter(id=token_id, user=request.user).update(
                revoked=True
            )
            messages.success(request, "令牌已吊销。" if updated else "令牌不存在。")
        else:
            name = (request.POST.get("name") or "默认令牌").strip()[:60]
            record = ApiToken.issue(request.user, name)
            request.session["new_api_token"] = record.token
            messages.success(request, f"已签发令牌「{record.name}」，请立即复制保存。")
        return redirect("learning_logs:api_tokens")

    new_token = request.session.pop("new_api_token", None)
    return render(
        request,
        "learning_logs/api_tokens.html",
        {
            "tokens": ApiToken.objects.filter(user=request.user),
            "new_token": new_token,
            "endpoints": API_ENDPOINTS,
        },
    )


@login_required
def api_docs(request):
    """开放 API 文档页。"""
    return render(
        request,
        "learning_logs/api_docs.html",
        {"endpoints": API_ENDPOINTS, "token_count": ApiToken.objects.filter(user=request.user, revoked=False).count()},
    )


@login_required
def notifications_view(request):
    """提醒中心：查看全部提醒并标记已读。"""
    notifications_service.generate(request.user)
    items = Notification.objects.filter(user=request.user)
    return render(
        request,
        "learning_logs/notifications.html",
        {
            "items": items[:40],
            "unread": items.filter(read_at__isnull=True).count(),
            "total": items.count(),
        },
    )


@login_required
def mark_notification_read(request, notification_id):
    """把单条提醒标记为已读，然后跳到它指向的页面。

    只对本人提醒生效，标记已读没有副作用，因此允许 GET 直达。
    """
    item = Notification.objects.filter(id=notification_id, user=request.user).first()
    if item is None:
        raise Http404("提醒不存在")

    updated = 0
    if item.is_unread:
        item.mark_read()
        updated = 1

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": bool(updated)})
    if item.link:
        return redirect(item.link)
    if not updated:
        messages.info(request, "这条提醒已经是已读状态。")
    return redirect("learning_logs:notifications")


@login_required
@require_POST
def mark_all_read(request):
    """一键清空未读。"""
    count = notifications_service.mark_all_read(request.user)
    messages.success(request, f"已把 {count} 条提醒标记为已读。")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "count": count})
    return redirect("learning_logs:notifications")


@login_required
def today(request):
    """今日速览：把今天该做的事和值得回看的旧笔记聚到一页。"""
    user = request.user
    today_date = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today_date, time.min))

    entries_today = Entry.objects.filter(topic__owner=user, date_added__gte=start)
    sessions_today = StudySession.objects.filter(
        user=user, start_time__gte=start, duration__isnull=False
    )
    minutes_today = sum(
        session.duration_minutes() for session in sessions_today
    )
    due_cards = Flashcard.objects.filter(user=user, due_date__lte=today_date)

    old_entries = list(
        Entry.objects.filter(topic__owner=user, date_added__lt=start - timedelta(days=30))
        .select_related("topic")
        .order_by("-date_added")[:60]
    )
    random.shuffle(old_entries)

    context = {
        "today": today_date,
        "entry_count_today": entries_today.count(),
        "minutes_today": minutes_today,
        "minutes_text": stats.format_minutes(minutes_today),
        "streak": stats.current_streak(user),
        "due_cards": due_cards[:5],
        "due_count": due_cards.count(),
        "flashbacks": old_entries[:3],
        "recent_topics": Topic.objects.filter(owner=user).order_by("-date_added")[:5],
        "goals": stats.upcoming_goals(user, limit=3),
        "week_minutes": stats.range_minutes(user, 7),
    }
    return render(request, "learning_logs/today.html", context)


@login_required
def focus(request):
    """专注计时（番茄钟）页面。"""
    sessions = StudySession.objects.filter(
        user=request.user, duration__isnull=False
    ).select_related("topic")[:8]
    today_date = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today_date, time.min))
    return render(
        request,
        "learning_logs/focus.html",
        {
            "topics": Topic.objects.filter(owner=request.user),
            "sessions": sessions,
            "minutes_today": sum(
                s.duration_minutes()
                for s in StudySession.objects.filter(
                    user=request.user, start_time__gte=start, duration__isnull=False
                )
            ),
            "today": today_date,
        },
    )


@login_required
@require_POST
def focus_log(request):
    """专注结束后写入一次学习会话。"""
    minutes = request.POST.get("minutes") or "0"
    try:
        minutes = max(0, min(600, int(float(minutes))))
    except (TypeError, ValueError):
        minutes = 0
    topic_id = request.POST.get("topic")
    topic = Topic.objects.filter(id=topic_id, owner=request.user).first()

    if minutes <= 0:
        return JsonResponse({"ok": False, "error": "时长太短，未记录。"}, status=400)
    if topic is None:
        return JsonResponse({"ok": False, "error": "请先选择一个主题。"}, status=400)

    end = timezone.now()
    StudySession.objects.create(
        user=request.user, topic=topic, start_time=end - timedelta(minutes=minutes), end_time=end
    )
    return JsonResponse(
        {
            "ok": True,
            "minutes": minutes,
            "topic": topic.text,
            "message": f"已记录 {minutes} 分钟专注：{topic.text}",
        }
    )


@login_required
def import_center(request):
    """导入中心：Markdown 笔记、批量文本建卡、Anki CSV 三种入口。"""
    topics = Topic.objects.filter(owner=request.user).annotate(
        card_count=Count("flashcards")
    )
    return render(
        request,
        "learning_logs/import.html",
        {
            "topics": topics,
            "entry_count": Entry.objects.filter(topic__owner=request.user).count(),
            "card_count": Flashcard.objects.filter(user=request.user).count(),
        },
    )


@login_required
@require_POST
def import_cards_view(request):
    """批量建卡：支持粘贴文本与上传 Anki CSV。"""
    topic_id = request.POST.get("topic")
    topic = Topic.objects.filter(id=topic_id, owner=request.user).first()
    if topic is None:
        messages.error(request, "请先选择一个属于自己的主题。")
        return redirect("learning_logs:import_center")

    text = (request.POST.get("cards") or "").strip()
    upload = request.FILES.get("file")

    if upload is not None:
        if upload.size > 1024 * 1024:
            messages.error(request, "文件超过 1MB，请拆分后再导入。")
            return redirect("learning_logs:import_center")
        content = upload.read().decode("utf-8-sig", errors="ignore")
        result = export_service.import_cards_csv(request.user, topic, content)
        source = upload.name
    elif text:
        result = export_service.import_cards(request.user, topic, text)
        source = "粘贴的文本"
    else:
        messages.error(request, "请粘贴卡片内容或上传 CSV 文件。")
        return redirect("learning_logs:import_center")

    if not result["created"]:
        messages.info(request, "没有新增卡片，可能是内容为空或正面重复。")
    else:
        messages.success(
            request,
            f"已从{source}导入 {result['created']} 张卡片"
            + (f"，跳过 {result['skipped']} 张重复卡。" if result["skipped"] else "。"),
        )
    return redirect("learning_logs:flashcards")


@login_required
def card_stats(request):
    """闪卡复习统计：掌握度分布、按主题分布与最近复习节奏。"""
    cards = Flashcard.objects.filter(user=request.user).select_related("topic")
    today = timezone.localdate()

    buckets = {"未开始": 0, "学习中": 0, "已掌握": 0}
    for card in cards:
        if card.repetitions == 0:
            buckets["未开始"] += 1
        elif card.repetitions >= 3:
            buckets["已掌握"] += 1
        else:
            buckets["学习中"] += 1

    by_topic = (
        cards.values("topic__text")
        .annotate(total=Count("id"), mastered=Count("id", filter=Q(repetitions__gte=3)))
        .order_by("-total")[:8]
    )

    daily = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        count = cards.filter(last_reviewed_at__date=day).count()
        daily.append({"date": day.strftime("%m-%d"), "count": count})

    reviewed = cards.filter(last_reviewed_at__isnull=False).count()
    context = {
        "total": cards.count(),
        "buckets": buckets,
        "by_topic": by_topic,
        "daily": daily,
        "reviewed": reviewed,
        "due_count": cards.filter(due_date__lte=today).count(),
        "max_daily": max((row["count"] for row in daily), default=0) or 1,
    }
    return render(request, "learning_logs/card_stats.html", context)
