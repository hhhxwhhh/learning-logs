"""视图层。

按业务域拆成多个模块，这里统一重新导出，
所以 urls.py 里的 views.xxx 不用跟着改。
"""

from __future__ import annotations

from .core import (  # noqa: F401
    index,
    features,
    api_search,
)

from .topics import (  # noqa: F401
    topics,
    topic,
    new_topic,
    new_entry,
    edit_entry,
    delete_entry,
    delete_topic,
    search,
    entry_comments,
    toggle_topic_flag,
    entry_history,
    restore_entry,
)

from .paths import (  # noqa: F401
    learning_paths,
    new_learning_path,
    learning_path_detail,
    toggle_step_completion,
    step_detail,
    toggle_resource_completion,
    delete_learning_path,
)

from .cards import (  # noqa: F401
    flashcards,
    review,
    review_answer,
    delete_flashcard,
    generate_cards,
    card_stats,
    import_cards_view,
)

from .dashboard import (  # noqa: F401
    dashboard,
    goals,
    toggle_goal,
    start_session,
    end_session,
    today,
    focus,
    focus_log,
)

from .overview import (  # noqa: F401
    activity,
    insights,
    live_board,
    achievements,
    garden,
    timeline,
)

from .todos import (  # noqa: F401
    todos,
    toggle_todo,
)

from .data import (  # noqa: F401
    data_tools,
    export_notes,
    export_topic,
    export_cards,
    export_backup,
    import_notes,
    import_center,
)

from .report import (  # noqa: F401
    weekly_report,
    weekly_report_generate,
)

from .share import (  # noqa: F401
    toggle_share,
    shared_topic,
    public_profile,
)

from .tags import (  # noqa: F401
    tags,
    tag_detail,
    graph,
    suggest_tags,
)

from .notifications import (  # noqa: F401
    notifications_view,
    mark_notification_read,
    mark_all_read,
)

from .apiviews import (  # noqa: F401
    api_tokens,
    api_docs,
)

from .assistant import (  # noqa: F401
    agent,
    agent_stream,
)

__all__ = [
    "index",
    "features",
    "api_search",
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
    "learning_paths",
    "new_learning_path",
    "learning_path_detail",
    "toggle_step_completion",
    "step_detail",
    "toggle_resource_completion",
    "delete_learning_path",
    "flashcards",
    "review",
    "review_answer",
    "delete_flashcard",
    "generate_cards",
    "card_stats",
    "import_cards_view",
    "dashboard",
    "goals",
    "toggle_goal",
    "start_session",
    "end_session",
    "today",
    "focus",
    "focus_log",
    "activity",
    "insights",
    "live_board",
    "achievements",
    "garden",
    "timeline",
    "todos",
    "toggle_todo",
    "data_tools",
    "export_notes",
    "export_topic",
    "export_cards",
    "export_backup",
    "import_notes",
    "import_center",
    "weekly_report",
    "weekly_report_generate",
    "toggle_share",
    "shared_topic",
    "public_profile",
    "tags",
    "tag_detail",
    "graph",
    "suggest_tags",
    "notifications_view",
    "mark_notification_read",
    "mark_all_read",
    "api_tokens",
    "api_docs",
    "agent",
    "agent_stream",
]
