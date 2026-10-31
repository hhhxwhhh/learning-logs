"""模板过滤器：Markdown 渲染、纯文本摘要、时长格式化等。"""

import re

from django import template
from django.utils.safestring import mark_safe

from learning_logs.utils.markdown import render_markdown

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(value):
    """把 Markdown 文本渲染为安全 HTML。"""
    return mark_safe(render_markdown(value or ""))


@register.filter(name="hours")
def hours_filter(value):
    """把 timedelta 格式化为「X 小时 Y 分」。"""
    if not value:
        return "0 分钟"
    total_minutes = int(value.total_seconds() // 60)
    h, m = divmod(total_minutes, 60)
    if h and m:
        return f"{h} 小时 {m} 分"
    if h:
        return f"{h} 小时"
    return f"{m} 分钟"


@register.filter(name="minutes")
def minutes_filter(value):
    """把 timedelta 转成分钟数（数字）。"""
    if not value:
        return 0
    return int(value.total_seconds() // 60)


@register.filter(name="md_plain")
def md_plain_filter(value):
    """去掉常见 Markdown 标记，用于列表摘要。"""
    if not value:
        return ""
    text = re.sub(r"```.*?```", " ", str(value), flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"[*_>#~]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@register.filter(name="dur")
def dur_filter(minutes):
    """分钟数格式化为「X 小时 Y 分」。"""
    try:
        minutes = int(minutes or 0)
    except (TypeError, ValueError):
        return "0 分钟"
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} 小时 {mins} 分"
    if hours:
        return f"{hours} 小时"
    return f"{mins} 分钟"
