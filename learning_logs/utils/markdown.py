"""Markdown 渲染工具。

统一用 markdown-it-py（CommonMark + GFM 表格/删除线 + 链接自动识别）。
禁用原始 HTML，避免 AI 或用户输入注入脚本。
"""

from __future__ import annotations

from markdown_it import MarkdownIt

_md = (
    MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    .enable(["table", "strikethrough"])
    .enable("linkify")
)


def render_markdown(text: str) -> str:
    """把 Markdown 文本渲染成安全的 HTML 片段。"""
    if not text:
        return ""
    return _md.render(text)
