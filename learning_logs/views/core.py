"""首页、功能地图与命令面板搜索。"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from ..models import Entry, Flashcard, Topic
from ..services import search as search_service
from ..services import stats

logger = logging.getLogger(__name__)

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
    {"label": "学习时间线", "url": "/timeline/", "keywords": ["时间线", "timeline", "历史", "回顾"]},
    {"label": "学习洞察", "url": "/insights/", "keywords": ["洞察", "insight", "建议", "效率"]},
    {"label": "待办清单", "url": "/todos/", "keywords": ["待办", "todo", "清单", "checklist"]},
    {"label": "活动流", "url": "/activity/", "keywords": ["活动", "动态", "activity", "流水"]},
    {"label": "学习助手", "url": "/agent/", "keywords": ["助手", "agent", "工具", "agent"]},
]


FEATURE_GROUPS = [
    {
        "title": "记录与组织",
        "desc": "笔记与主题的组织方式",
        "items": [
            {"name": "主题", "url": "/topics/", "icon": "i-layers", "key": "t",
             "desc": "按主题拆分知识，一个主题一棵树"},
            {"name": "新建主题", "url": "/new_topic/", "icon": "i-plus", "key": "n",
             "desc": "开一个新的学习方向，配好标签"},
            {"name": "双链笔记", "url": "/features/", "icon": "i-layers", "key": "",
             "desc": "在笔记里写 [[主题名]] 即可互链，对方显示反向链接"},
            {"name": "版本历史", "url": "/features/", "icon": "i-clock", "key": "",
             "desc": "每次修改自动留痕，编辑页可预览与回滚旧版本"},
            {"name": "公开主页", "url": "/features/", "icon": "i-user", "key": "",
             "desc": "把已分享的主题聚合成只读主页"},
            {"name": "学习路径", "url": "/learning-paths/", "icon": "i-route", "key": "p",
             "desc": "把多个主题串成有顺序的路线"},
            {"name": "标签", "url": "/tags/", "icon": "i-tag", "key": "",
             "desc": "横向索引，跨主题复用同一套关键词"},
        ],
    },
    {
        "title": "复习与记忆",
        "desc": "间隔重复复习",
        "items": [
            {"name": "闪卡", "url": "/flashcards/", "icon": "i-cards", "key": "c",
             "desc": "管理所有卡片，支持批量生成"},
            {"name": "今日复习", "url": "/flashcards/review/", "icon": "i-brain", "key": "r",
             "desc": "SM-2 算法挑出今天该复习的卡"},
            {"name": "复习统计", "url": "/flashcards/stats/", "icon": "i-chart", "key": "",
             "desc": "掌握度分布与近 14 天复习节奏"},
            {"name": "导入中心", "url": "/import/", "icon": "i-plus", "key": "",
             "desc": "Markdown 笔记、批量建卡与 Anki CSV 导入"},
            {"name": "专注计时", "url": "/focus/", "icon": "i-timer", "key": "f",
             "desc": "番茄钟，结束即计入学习时长"},
            {"name": "AI 助教", "url": "/topics/", "icon": "i-spark", "key": "",
             "desc": "在主题页里与模型多轮对话"},
        ],
    },
    {
        "title": "洞察与回顾",
        "desc": "统计与可视化",
        "items": [
            {"name": "今日速览", "url": "/today/", "icon": "i-clock", "key": "o",
             "desc": "今日待办、连续天数与记忆闪回"},
            {"name": "仪表盘", "url": "/dashboard/", "icon": "i-chart", "key": "d",
             "desc": "热力图、时长分布与主题排行"},
            {"name": "学习分析", "url": "/analytics/", "icon": "i-chart", "key": "a",
             "desc": "更细的统计分析视角"},
            {"name": "学习洞察", "url": "/insights/", "icon": "i-spark", "key": "j",
             "desc": "黄金时段、集中度与下一步建议"},
            {"name": "知识图谱", "url": "/graph/", "icon": "i-graph", "key": "g",
             "desc": "主题之间的关联网络"},
            {"name": "学习花园", "url": "/garden/", "icon": "i-sprout", "key": "e",
             "desc": "知识树可视化"},
            {"name": "学习周报", "url": "/weekly/", "icon": "i-doc", "key": "w",
             "desc": "一周数据复盘与建议"},
            {"name": "学习成就", "url": "/achievements/", "icon": "i-target", "key": "b",
             "desc": "徽章体系，记录坚持的痕迹"},
            {"name": "提醒中心", "url": "/notifications/", "icon": "i-bell", "key": "",
             "desc": "到期复习、连续中断与目标临期提醒"},
            {"name": "学习时间线", "url": "/timeline/", "icon": "i-clock", "key": "l",
             "desc": "按月回看笔记、卡片与投入时长"},
            {"name": "待办清单", "url": "/todos/", "icon": "i-check", "key": "k",
             "desc": "汇总笔记里的 - [ ] 待办，勾选即写回原文"},
            {"name": "活动流", "url": "/activity/", "icon": "i-layers", "key": "v",
             "desc": "最近的学习动作，按天回看"},
            {"name": "学习助手", "url": "/agent/", "icon": "i-spark", "key": "q",
             "desc": "模型调用工具读写你的笔记、闪卡与待办"},
        ],
    },
    {
        "title": "工具与设置",
        "desc": "数据与导出",
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


def index(request):
    #学习笔记的主页
    context = {}
    if request.user.is_authenticated:
        user = request.user
        today = timezone.localdate()
        context = {
            "snapshot": {
                "topics": Topic.objects.filter(owner=user).count(),
                "entries": Entry.objects.filter(topic__owner=user).count(),
                "streak": stats.current_streak(user),
                "due_cards": Flashcard.objects.filter(user=user, due_date__lte=today).count(),
                "week_minutes": stats.range_minutes(user, 7),
                "cards": Flashcard.objects.filter(user=user).count(),
            },
            "recent_topics": Topic.objects.filter(owner=user).order_by("-date_added")[:4],
        }
    return render(request,'learning_logs/index.html', context)


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
