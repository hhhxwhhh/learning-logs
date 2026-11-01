"""主题与笔记的增删改查。"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from ..forms import CommentForm, EntryForm, TopicForm
from ..models import EntryRevision, Entry, StudySession, snapshot_entry, Topic
from .. import events
from ..services import cache as cache_service
from ..services import links as links_service
from ..services import tags as tags_service

logger = logging.getLogger(__name__)

@login_required
def topics(request):
    """显示所有的主题"""
    show_archived = request.GET.get("archived") == "1"
    queryset = Topic.objects.filter(owner=request.user)
    if not show_archived:
        queryset = queryset.filter(archived=False)
    topics = list(queryset.order_by("-pinned", "date_added"))
    for item in topics:
        item.tag_list = tags_service.tags_of(item)
    context = {
        'topics': topics,
        'show_archived': show_archived,
        'archived_count': Topic.objects.filter(owner=request.user, archived=True).count(),
    }
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
        'backlinks': links_service.backlinks(topic),
    }
    return render(request, 'learning_logs/topic.html', context)


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
            events.publish(
                "topic_created",
                request.user,
                f"新建主题「{new_topic.text}」",
                topic=new_topic,
            )
            cache_service.invalidate(request.user.id)
            return redirect('learning_logs:topics')  # 重定向到主题页面topics
    # 显示空表单或者指出表单数据无效
    context = {'form': form, 'tags_input': request.POST.get('tags', '')}
    return render(request, 'learning_logs/new_topic.html', context)


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
           events.publish(
               "entry_created",
               request.user,
               f"在「{topic.text}」写了一条笔记",
               topic=topic,
               payload={"entry_id": new_entry.id},
           )
           cache_service.invalidate(request.user.id)
           return redirect('learning_logs:topic', topic_id=topic_id)
   # 显示空表单或者指出表单的数据无效
   context = {'topic': topic, 'form': form, 'tags_input': request.POST.get('tags', '')}
   return render(request, 'learning_logs/new_entry.html', context)


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
            snapshot_entry(entry, request.user)
            form.save()
            tags_service.sync_tags(request.user, entry, tags_input)
            events.publish(
                "entry_updated",
                request.user,
                f"修改了「{topic.text}」里的笔记",
                topic=topic,
                payload={"entry_id": entry.id},
            )
            cache_service.invalidate(request.user.id)
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
@require_POST
def delete_topic(request, topic_id):
    """删除指定的主题"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    if request.method == 'POST':
        topic.delete()
        return redirect('learning_logs:topics')
    return redirect('learning_logs:topics')


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
def toggle_topic_flag(request, topic_id, flag):
    """切换主题的置顶 / 归档状态。"""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    if flag == "pinned":
        topic.pinned = not topic.pinned
        topic.save(update_fields=["pinned"])
        messages.success(request, "已置顶这个主题。" if topic.pinned else "已取消置顶。")
    elif flag == "archived":
        topic.archived = not topic.archived
        topic.save(update_fields=["archived"])
        messages.success(request, "主题已归档。" if topic.archived else "主题已恢复。")
    else:
        raise Http404("未知的状态")
    return redirect(request.POST.get("next") or "learning_logs:topics")


@login_required
def entry_history(request, entry_id):
    """笔记的历史版本列表，可预览某个旧版本。"""
    entry = get_object_or_404(Entry, id=entry_id, topic__owner=request.user)
    revisions = entry.revisions.select_related("edited_by")[:30]
    preview = None
    preview_id = request.GET.get("preview")
    if str(preview_id or "").isdigit():
        preview = EntryRevision.objects.filter(
            id=int(preview_id), entry=entry
        ).first()
    return render(
        request,
        "learning_logs/entry_history.html",
        {"entry": entry, "topic": entry.topic, "revisions": revisions, "preview": preview},
    )


@login_required
@require_POST
def restore_entry(request, revision_id):
    """把笔记回滚到某个历史版本（回滚前同样留一份当前内容）。"""
    revision = get_object_or_404(
        EntryRevision, id=revision_id, entry__topic__owner=request.user
    )
    entry = revision.entry
    current = Entry.objects.filter(id=entry.id).values_list("text", flat=True).first()
    if current and current != revision.text:
        EntryRevision.objects.create(entry=entry, text=current, edited_by=request.user)
    entry.text = revision.text
    entry.save()
    messages.success(request, "已回滚到该历史版本，当前内容也保留了一份。")
    return redirect("learning_logs:entry_history", entry_id=entry.id)
