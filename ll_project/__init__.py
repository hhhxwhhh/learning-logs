"""项目包入口。

在这里引入 Celery 应用，worker 才能通过 ``-A ll_project`` 找到任务。
"""

from learning_logs.celery_app import app as celery_app

__all__ = ["celery_app"]
