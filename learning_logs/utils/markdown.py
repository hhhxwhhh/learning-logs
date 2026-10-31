"""Markdown 渲染工具。

统一用 markdown-it-py（CommonMark + GFM 表格/删除线）。
禁用原始 HTML，避免 AI 或用户输入注入脚本；linkify 依赖 linkify-it-py，缺失时自动降级。
"""

from __future__ import annotations

from markdown_it import MarkdownIt

try:  # linkify 是可选依赖，缺失时不影响渲染
    import linkify_it  # noqa: F401

    _LINKIFY = True
except ImportError:  # pragma: no cover
    _LINKIFY = False

_md = (
    MarkdownIt(
        "commonmark",
        {"html": False, "linkify": _LINKIFY, "typographer": True},
    )
    .enable(["table", "strikethrough"])
)
if _LINKIFY:
    _md.enable("linkify")


def render_markdown(text: str) -> str:
    """把 Markdown 文本渲染成安全的 HTML 片段。"""
    if not text:
        return ""
    return _md.render(text)
