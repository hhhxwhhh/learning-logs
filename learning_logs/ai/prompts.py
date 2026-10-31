"""提示词模板：尽量让模型「基于笔记回答」，而不是泛泛而谈。"""

from __future__ import annotations

from learning_logs.models import Entry, Topic

TUTOR_SYSTEM = (
    "你是一位严谨、耐心的中文学习助教。你的回答必须：\n"
    "1. 优先使用用户笔记中的内容，必要时用「笔记 2」这样的编号引用；\n"
    "2. 先给结论，再给推理或步骤，避免空话；\n"
    "3. 用 Markdown 组织：小标题、要点列表、代码块；\n"
    "4. 笔记中没有的信息，明确说明「笔记中未提到」，不要编造；\n"
    "5. 回答控制在 400 字以内，除非用户要求展开。"
)

SUMMARY_SYSTEM = (
    "你是学习笔记整理助手。请把用户的笔记整理成结构化摘要，必须包含四部分：\n"
    "## 核心概念（3-5 条）\n## 关键结论\n## 仍未解决的问题\n## 下一步建议\n"
    "只使用笔记中出现的信息，用中文，简洁具体。"
)

QUIZ_SYSTEM = (
    "你是出题老师。基于用户笔记生成 5 道自测题，难度由易到难，"
    "题型混合（选择、判断、简答、代码题）。每题给出「答案」与「解析」，"
    "解析要指出对应笔记中的哪一条。用 Markdown 输出，不要编造笔记之外的知识点。"
)

RECOMMEND_SYSTEM = (
    "你是学习规划顾问。基于用户已有的笔记，给出 3-5 条下一步建议："
    "可以补哪些前置知识、做哪些练习、读什么类型的资料。"
    "每条建议说明「为什么现在做这件事」，不要罗列泛泛的学习方法。"
)

PLAN_SYSTEM = (
    "你是课程设计专家。请根据用户目标输出学习路径，"
    "严格返回 JSON，不要包含 Markdown 代码块标记或任何解释文字。JSON 结构：\n"
    '{"title": "路径标题", "description": "一句话说明", "estimated_hours": 30, '
    '"steps": [{"topic": "步骤主题（不超过 20 字）", "description": "这一步要完成什么", '
    '"estimated_hours": 4, "resources": ["资源名称"]}]}\n'
    "steps 控制在 3-6 个，按学习顺序排列，符合循序渐进的原则。"
)

CONTEXT_LIMIT = 6000


def build_context(topic: Topic, limit: int = CONTEXT_LIMIT) -> str:
    """把主题下的笔记拼成上下文，按长度截断并保留最新内容。"""
    entries = list(
        Entry.objects.filter(topic=topic).order_by("-date_added")[:40]
    )
    entries.reverse()

    blocks = []
    used = 0
    for index, entry in enumerate(entries, start=1):
        status = "已掌握" if entry.completed else "进行中"
        block = f"【笔记 {index}｜{entry.date_added:%Y-%m-%d}｜{status}】\n{entry.text.strip()}"
        if used + len(block) > limit:
            blocks.append("（更早的笔记因长度限制已省略）")
            break
        blocks.append(block)
        used += len(block)

    header = f"主题：{topic.text}\n笔记数量：{len(entries)}\n\n"
    return header + "\n\n".join(blocks) if blocks else header + "（该主题暂无笔记）"


def tutor_prompt(question: str, context: str) -> str:
    return f"以下是用户的笔记：\n\n{context}\n\n---\n\n用户的问题：{question}"


def summary_prompt(context: str) -> str:
    return f"请整理以下笔记：\n\n{context}"


def quiz_prompt(context: str) -> str:
    return f"请基于以下笔记出题：\n\n{context}"


def recommend_prompt(context: str) -> str:
    return f"请基于以下笔记给出下一步建议：\n\n{context}"


def plan_prompt(goal: str, context: str = "") -> str:
    extra = f"\n\n可参考的已有笔记：\n{context}" if context else ""
    return f"我的学习目标：{goal}{extra}"


FLASHCARD_SYSTEM = (
    "你是记忆卡片设计师。请把笔记提炼成问答闪卡，"
    "严格返回 JSON，不要包含代码块标记或解释文字。JSON 结构：\n"
    '{"cards": [{"front": "问题（不超过 60 字，聚焦一个知识点）", '
    '"back": "答案（不超过 200 字，具体、可自测）"}]}\n'
    "每张卡只考一个点，问题要能脱离原文独立理解，答案要包含关键细节。"
)


def flashcard_prompt(context: str, count: int = 8) -> str:
    return f"请基于以下笔记生成 {count} 张闪卡：\n\n{context}"
