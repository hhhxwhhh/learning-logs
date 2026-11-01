"""一次性脚本：把 learning_logs/views.py 按业务域拆成包。

拆分后 learning_logs/views/ 是一个包，__init__.py 把各模块的视图重新导出，
所以 urls.py 里的 views.xxx 引用不用改。

用法：
    python scripts/split_views.py
"""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "learning_logs" / "views.py"
TARGET = ROOT / "learning_logs" / "views"

GROUPS: dict[str, list[str]] = {
    "core": [
        "index",
        "features",
        "api_search",
    ],
    "topics": [
        "topics",
        "topic",
        "new_topic",
        "new_entry",
        "edit_entry",
        "delete_entry",
        "delete_topic",
        "search",
        "entry_comments",
        "toggle_topic_flag",
        "entry_history",
        "restore_entry",
    ],
    "paths": [
        "learning_paths",
        "new_learning_path",
        "learning_path_detail",
        "toggle_step_completion",
        "step_detail",
        "toggle_resource_completion",
        "delete_learning_path",
    ],
    "cards": [
        "flashcards",
        "review",
        "review_answer",
        "delete_flashcard",
        "generate_cards",
        "card_stats",
        "import_cards_view",
    ],
    "dashboard": [
        "dashboard",
        "goals",
        "toggle_goal",
        "start_session",
        "end_session",
        "today",
        "focus",
        "focus_log",
    ],
    "overview": [
        "activity",
        "insights",
        "live_board",
        "achievements",
        "garden",
        "timeline",
    ],
    "todos": [
        "todos",
        "toggle_todo",
    ],
    "data": [
        "data_tools",
        "export_notes",
        "export_topic",
        "export_cards",
        "export_backup",
        "import_notes",
        "import_center",
    ],
    "report": [
        "weekly_report",
        "weekly_report_generate",
    ],
    "share": [
        "toggle_share",
        "shared_topic",
        "public_profile",
    ],
    "tags": [
        "tags",
        "tag_detail",
        "graph",
        "suggest_tags",
    ],
    "notifications": [
        "notifications_view",
        "mark_notification_read",
        "mark_all_read",
    ],
    "apiviews": [
        "api_tokens",
        "api_docs",
    ],
    "assistant": [
        "agent",
        "agent_stream",
    ],
}

CONSTANTS = {
    "API_ENDPOINTS_V2": "apiviews",
    "API_ENDPOINTS": "apiviews",
    "FEATURE_GROUPS": "core",
    "QUICK_ACTIONS": "core",
}

HEADER = '''"""{doc}"""

from __future__ import annotations

import logging

{imports}

logger = logging.getLogger(__name__)
'''

DOCS = {
    "core": "首页、功能地图与命令面板搜索。",
    "topics": "主题与笔记的增删改查。",
    "paths": "学习路径及其步骤、资源。",
    "cards": "闪卡的创建、复习与统计。",
    "dashboard": "仪表盘、学习目标、会话计时、今日速览与专注。",
    "overview": "活动流、学习洞察、实时看板、成就、花园与时间线。",
    "todos": "待办清单。",
    "data": "数据的导出与导入。",
    "report": "学习周报。",
    "share": "主题分享与公开主页。",
    "tags": "标签、知识图谱与标签建议。",
    "notifications": "提醒中心。",
    "apiviews": "开放接口的令牌管理与文档页。",
    "assistant": "学习助手对话页。",
}


def render_import(node: ast.stmt, names: set[str]) -> str:
    """按用到的名字重新生成 import 语句。

    拆分后模块位于 learning_logs/views/ 包内，原来的同级相对导入要升一级。
    """
    if isinstance(node, ast.Import):
        parts = []
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            if bound in names:
                parts.append(alias.name + (f" as {alias.asname}" if alias.asname else ""))
        return f"import {', '.join(parts)}" if parts else ""

    module = node.module or ""
    if node.level:
        module = "." * (node.level + 1) + module

    if node.module is None:
        # from . import events
        kept = [a.name for a in node.names if a.name in names]
        if not kept:
            return ""
        return f"from {module} import {', '.join(kept)}"

    kept = []
    for alias in node.names:
        bound = alias.asname or alias.name.split(".")[0]
        if bound not in names:
            continue
        kept.append(alias.name + (f" as {alias.asname}" if alias.asname else ""))
    if not kept:
        return ""
    return f"from {module} import {', '.join(kept)}"


def main() -> int:
    source = SRC.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    import_bindings: dict[str, ast.stmt] = {}
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                import_bindings[bound] = node

    blocks: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            blocks[node.name] = "\n".join(lines[start - 1 : node.end_lineno])

    const_blocks: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in CONSTANTS:
                    const_blocks[target.id] = ast.get_source_segment(source, node)

    group_code: dict[str, list[str]] = {name: [] for name in GROUPS}
    for group, names in GROUPS.items():
        for name in names:
            if name not in blocks:
                raise SystemExit(f"视图 {name} 没找到")
            group_code[group].append(blocks[name])
    for const, group in CONSTANTS.items():
        if const not in const_blocks:
            raise SystemExit(f"常量 {const} 没找到")
        group_code[group].insert(0, const_blocks[const])

    used: dict[str, set[str]] = {}
    for group, chunks in group_code.items():
        text = "\n".join(chunks)
        # 用 AST 判断名字是否被真正引用，避免正则把注释、字符串里的词也算上
        referenced: set[str] = set()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                pass
        used[group] = {
            bound for bound in import_bindings if bound in referenced
        }

    TARGET.mkdir(exist_ok=True)
    for group, chunks in group_code.items():
        stmt_ids = {id(import_bindings[n]) for n in used[group]}
        stmt_order = []
        seen = set()
        for node in tree.body:
            if id(node) in stmt_ids and id(node) not in seen:
                seen.add(id(node))
                stmt_order.append(node)
        imports = "\n".join(
            item for item in (render_import(n, used[group]) for n in stmt_order) if item
        )
        body = "\n\n\n".join(chunks)
        text = HEADER.format(doc=DOCS[group], imports=imports) + "\n" + body + "\n"
        (TARGET / f"{group}.py").write_text(text, encoding="utf-8")

    init_lines = [
        '"""视图层。',
        "",
        "按业务域拆成多个模块，这里统一重新导出，",
        "所以 urls.py 里的 views.xxx 不用跟着改。",
        '"""',
        "",
        "from __future__ import annotations",
        "",
    ]
    for group, names in GROUPS.items():
        init_lines.append(f"from .{group} import (  # noqa: F401")
        for name in names:
            init_lines.append(f"    {name},")
        init_lines.append(")")
        init_lines.append("")

    init_lines.append("__all__ = [")
    for group, names in GROUPS.items():
        for name in names:
            init_lines.append(f'    "{name}",')
    init_lines.append("]")
    init_lines.append("")

    (TARGET / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")
    print("已生成：", ", ".join(sorted(p.name for p in TARGET.glob("*.py"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
