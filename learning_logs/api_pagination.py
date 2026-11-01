"""DRF 分页配置。"""

from __future__ import annotations

from rest_framework import pagination


class StandardPagination(pagination.PageNumberPagination):
    """默认每页 20 条，允许用 ``?page_size=`` 覆盖，最大 100。"""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
