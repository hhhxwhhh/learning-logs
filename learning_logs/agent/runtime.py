"""Agent 运行时。

流程和函数调用（tool calling）一样：
模型要调用工具时返回 tool_calls，我们执行完把结果回填，再让模型继续；
模型不再要工具时，它给出的文本就是最终回答。

每一步都记在 steps 里，出问题能回看模型到底做了什么。
"""

from __future__ import annotations

import json
import logging

from learning_logs.ai.providers import Message, get_provider

from . import tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个学习记录助手，操作对象是当前用户自己的知迹数据。

规则：
- 需要事实时先调用工具，不要凭空编造笔记内容、统计数字或卡片内容；
- 写操作（新建笔记、闪卡、待办）前先用只读工具确认目标存在；
- 用户没说要写入时不要主动写入；
- 回答用中文，简洁给出结论，不要复述工具返回的原始 JSON；
- 工具报错时把问题说清楚，并说明下一步可以怎么做。"""

MAX_STEPS = 6


def run(user, prompt: str, provider=None, model: str | None = None, max_steps: int = MAX_STEPS) -> dict:
    """跑一轮 Agent，返回最终回答与工具调用轨迹。"""
    prompt = (prompt or "").strip()
    if not prompt:
        return {"answer": "请描述你想做的事。", "steps": [], "error": "empty_prompt"}

    provider = provider or get_provider()
    messages = [
        Message("system", SYSTEM_PROMPT),
        Message("user", prompt),
    ]
    steps: list[dict] = []

    for _ in range(max_steps):
        try:
            result = provider.chat(messages, model=model, tools=tools.specs())
        except Exception as exc:  # noqa: BLE001 - Provider 异常类型不统一
            logger.warning("Agent 调用失败", exc_info=True)
            return {
                "answer": "",
                "steps": steps,
                "error": str(exc),
            }

        calls = result.get("tool_calls") or []
        if not calls:
            return {"answer": result.get("content") or "", "steps": steps, "error": ""}

        messages.append(
            Message(
                "assistant",
                result.get("content") or "",
                tool_calls=calls,
            )
        )

        for call in calls:
            name = call.get("name", "")
            arguments = call.get("arguments") or {}
            output = tools.run(user, name, arguments)
            steps.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "output": output,
                }
            )
            messages.append(
                Message(
                    "tool",
                    json.dumps(output, ensure_ascii=False, default=str),
                    tool_call_id=call.get("id", ""),
                    name=name,
                )
            )

    return {
        "answer": "这次调用步数用完了，可以把问题拆小一点再问一次。",
        "steps": steps,
        "error": "max_steps",
    }
