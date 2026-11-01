"""大模型调用层。

统一走 OpenAI 兼容协议：
- 本地 Ollama：AI_BASE_URL=http://localhost:11434/v1
- DeepSeek / OpenAI / Moonshot / 任意兼容网关：改 AI_BASE_URL + AI_API_KEY 即可
- AI_PROVIDER=mock：离线演示，不发起任何网络请求
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Iterable, Iterator

from django.conf import settings

logger = logging.getLogger(__name__)


class AIError(RuntimeError):
    """AI 服务不可用或返回异常时抛出，消息面向用户。"""


@dataclass
class Message:
    """一条对话消息。

    tool_calls 与 tool_call_id 只有在工具调用场景下才会用到，
    普通问答不需要填。
    """

    role: str
    content: str = ""
    tool_calls: list | None = None
    tool_call_id: str | None = None
    name: str | None = None


def serialize_message(message: Message) -> dict:
    """把消息转成 OpenAI 兼容接口需要的格式。"""
    item: dict = {"role": message.role, "content": message.content or ""}
    if message.role == "assistant" and message.tool_calls:
        item["content"] = message.content or None
        item["tool_calls"] = [
            {
                "id": call.get("id", ""),
                "type": "function",
                "function": {
                    "name": call.get("name", ""),
                    "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False),
                },
            }
            for call in message.tool_calls
        ]
    elif message.role == "tool":
        item["tool_call_id"] = message.tool_call_id or ""
        if message.name:
            item["name"] = message.name
    return item


def available_models() -> list[dict]:
    models = getattr(settings, "AI_AVAILABLE_MODELS", [])
    if models:
        return models
    return [{"id": settings.AI_MODEL, "name": settings.AI_MODEL}]


def resolve_model(requested: str | None) -> str:
    """只允许使用配置中列出的模型，避免前端传入任意值。"""
    if requested:
        for item in available_models():
            if item["id"] == requested:
                return requested
    return settings.AI_MODEL


class MockProvider:
    """离线演示用：不联网，返回一段结构化的中文示例回答。"""

    name = "mock"

    def stream(
        self,
        messages: Iterable[Message],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        question = ""
        for message in messages:
            if message.role == "user":
                question = message.content
        # 真实请求里会把笔记上下文拼进 user 内容，演示模式只回显用户问题部分
        if "用户的问题：" in question:
            question = question.split("用户的问题：", 1)[1]
        text = (
            "**当前处于离线演示模式**（`AI_PROVIDER=mock`），没有调用任何真实模型。\n\n"
            f"你问的是：{question.strip()[:160] or '（空）'}\n\n"
            "## 接入真实模型的方法\n"
            "1. 本地启动 Ollama，执行 `ollama pull qwen2.5:7b`；\n"
            "2. 在 `.env` 中设置 `AI_PROVIDER=ollama`、`AI_BASE_URL=http://localhost:11434/v1`；\n"
            "3. 或改成云端兼容服务：`AI_PROVIDER=openai`、`AI_BASE_URL=https://api.deepseek.com/v1`、`AI_API_KEY=sk-…`。\n\n"
            "## 这段回答能做什么\n"
            "- 验证对话界面、流式渲染、Markdown 排版与历史记录；\n"
            "- 接入模型后，同样的入口会基于你的真实笔记回答。\n\n"
            "> 提示：配置好后重启服务，本页会自动切换到真实模型。"
        )
        for index in range(0, len(text), 3):
            yield text[index : index + 3]

    def complete(self, messages, model=None, temperature=None, max_tokens=None) -> str:
        return "".join(self.stream(messages, model, temperature, max_tokens))

    def chat(self, messages, model=None, tools=None) -> dict:
        """离线模式下的工具调用入口：直接给说明，不请求任何工具。"""
        return {"content": self.complete(messages), "tool_calls": []}

    def chat_stream(self, messages, model=None, tools=None) -> Iterator[dict]:
        """离线模式下的流式工具对话：逐段吐出说明文字。"""
        for text in self.stream(messages, model):
            yield {"type": "delta", "text": text}


class OpenAICompatibleProvider:
    """基于 openai SDK 的任意兼容服务。"""

    name = "openai-compatible"

    def __init__(self) -> None:
        self.base_url = settings.AI_BASE_URL
        self.api_key = settings.AI_API_KEY or "not-needed"

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise AIError("缺少 openai 依赖，请执行 pip install -r requirements.txt") from exc

        return OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=getattr(settings, "AI_TIMEOUT", 120),
            max_retries=1,
        )

    def _payload(self, messages, model, temperature, max_tokens):
        return {
            "model": model or settings.AI_MODEL,
            "messages": [serialize_message(m) for m in messages],
            "temperature": (
                settings.AI_TEMPERATURE if temperature is None else temperature
            ),
            "max_tokens": max_tokens or settings.AI_MAX_TOKENS,
            "stream": True,
        }

    def stream(
        self,
        messages: Iterable[Message],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        payload = self._payload(list(messages), model, temperature, max_tokens)
        try:
            client = self._client()
            response = client.chat.completions.create(**payload)
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except AIError:
            raise
        except Exception as exc:  # noqa: BLE001 - SDK 异常类型较多，统一收敛
            logger.warning("AI 调用失败: %s", exc)
            raise AIError(self._friendly_error(exc)) from exc

    def complete(self, messages, model=None, temperature=None, max_tokens=None) -> str:
        payload = self._payload(list(messages), model, temperature, max_tokens)
        payload["stream"] = False
        try:
            client = self._client()
            response = client.chat.completions.create(**payload)
            return response.choices[0].message.content or ""
        except AIError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 调用失败: %s", exc)
            raise AIError(self._friendly_error(exc)) from exc

    def chat(self, messages, model=None, tools=None) -> dict:
        """带工具的对话：返回文本与工具调用列表。"""
        payload = self._payload(list(messages), model, temperature=None, max_tokens=None)
        payload["stream"] = False
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            client = self._client()
            response = client.chat.completions.create(**payload)
        except AIError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 工具调用失败: %s", exc)
            raise AIError(self._friendly_error(exc)) from exc

        message = response.choices[0].message
        calls = []
        for call in getattr(message, "tool_calls", None) or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except (TypeError, ValueError):
                arguments = {}
            calls.append({"id": call.id, "name": call.function.name, "arguments": arguments})
        return {"content": message.content or "", "tool_calls": calls}

    def chat_stream(
        self,
        messages,
        model: str | None = None,
        tools=None,
    ) -> Iterator[dict]:
        """带工具的流式对话。

        逐段产出两种事件：
        - ``{"type": "delta", "text": ...}`` 文本增量
        - ``{"type": "tool_calls", "calls": [...]}`` 本轮的工具调用（收齐后再给）
        """
        payload = self._payload(list(messages), model, temperature=None, max_tokens=None)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": False}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        pending: dict[int, dict] = {}
        try:
            client = self._client()
            response = client.chat.completions.create(**payload)
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "delta", "text": content}
                for call in getattr(delta, "tool_calls", None) or []:
                    index = getattr(call, "index", 0) or 0
                    slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if getattr(call, "id", None):
                        slot["id"] = call.id
                    function = getattr(call, "function", None)
                    if function is None:
                        continue
                    if getattr(function, "name", None):
                        slot["name"] = function.name
                    if getattr(function, "arguments", None):
                        slot["arguments"] += function.arguments
        except AIError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 流式工具调用失败: %s", exc)
            raise AIError(self._friendly_error(exc)) from exc

        calls = []
        for slot in pending.values():
            try:
                arguments = json.loads(slot["arguments"] or "{}")
            except (TypeError, ValueError):
                arguments = {}
            calls.append({"id": slot["id"], "name": slot["name"], "arguments": arguments})
        if calls:
            yield {"type": "tool_calls", "calls": calls}

    def _friendly_error(self, exc: Exception) -> str:
        text = str(exc)
        if "Connection" in type(exc).__name__ or "connect" in text.lower():
            return (
                f"连不上 AI 服务（{self.base_url}）。请确认 Ollama 已启动，"
                "或在 .env 中改为可用的 AI_BASE_URL。"
            )
        if "401" in text or "invalid_api_key" in text.lower():
            return "API Key 无效或未配置，请检查 .env 中的 AI_API_KEY。"
        if "404" in text:
            return f"服务返回 404，可能是模型名不存在：{settings.AI_MODEL}。"
        return f"AI 服务返回异常：{text[:200]}"


def get_provider():
    if getattr(settings, "AI_PROVIDER", "ollama") == "mock":
        return MockProvider()
    return OpenAICompatibleProvider()
