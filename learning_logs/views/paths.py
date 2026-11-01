"""学习路径及其步骤、资源。"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from ..forms import LearningPathForm, PathStepForm, StepResourceForm
from ..models import LearningPath, PathStep, StepResource

logger = logging.getLogger(__name__)

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
