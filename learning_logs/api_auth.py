"""DRF 接入层共用的认证。

开放 API 的令牌沿用现有 ApiToken 表，认证逻辑集中在
``learning_logs.services.api_access``，视图与 DRF 共用同一套规则。
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from learning_logs.models import ApiToken
from learning_logs.services import api_access


class ApiTokenAuthentication(BaseAuthentication):
    """支持两种传法：``Authorization: Bearer <token>`` 与 ``?token=<token>``。

    查询参数形式是为脚本和命令行调试准备的，正式集成建议用请求头。
    """

    keyword = "Bearer"

    def authenticate(self, request):
        raw = api_access.token_from_request(request)
        if not raw:
            return None

        record = ApiToken.objects.filter(token=raw, revoked=False).select_related("user").first()
        if record is None:
            raise AuthenticationFailed("令牌无效或已被吊销。")

        ApiToken.objects.filter(id=record.id).update(last_used_at=timezone.now())
        request.api_token = record
        return record.user, record

    def authenticate_header(self, request) -> str:
        return self.keyword
