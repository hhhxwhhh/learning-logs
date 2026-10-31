from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
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
    Comment,
    Entry,
    Flashcard,
    LearningGoal,
    LearningPath,
    PathStep,
    StepResource,
    StudySession,
    Topic,
)
from .services import stats

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
    
    context = {
        'topic': topic, 
        'entries': entries,
        'active_session': active_session,
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
           return redirect('learning_logs:topic', topic_id=topic_id)
   # 显示空表单或者指出表单的数据无效
   context = {'topic': topic, 'form': form}
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
            return redirect('learning_logs:topics')  # 重定向到主题页面topics
    # 显示空表单或者指出表单数据无效
    context = {'form': form}
    return render(request, 'learning_logs/new_topic.html', context)

@login_required
def edit_entry(request,entry_id):
    #编辑既有的条目
    entry = get_object_or_404(Entry, id=entry_id, topic__owner=request.user)
    topic = entry.topic
    if request.method!='POST':
        #初次请求，使用当前条目填充表单
        form=EntryForm(instance=entry)
    else:
        #POST提交的数据，对数据进行处理
        form=EntryForm(instance=entry,data=request.POST)
        if form.is_valid():
            form.save()
            return redirect('learning_logs:topic',topic_id=topic.id)
    context={'entry':entry,'topic':topic,'form':form}
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
