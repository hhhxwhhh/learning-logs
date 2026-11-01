"""从 DRF 视图集生成 OpenAPI 3 文档。

手写文档容易和实现脱节，这里直接读视图集与序列化器的元数据来生成：
新增一个端点时，只要挂上路由，文档里自动多一段。
"""

from __future__ import annotations

from rest_framework import serializers

from .api_v2 import (
    CardViewSet,
    EntryViewSet,
    EventViewSet,
    SchemaView,
    SessionViewSet,
    StatsView,
    TopicViewSet,
)

# 视图集 → 路由前缀
ENDPOINTS = [
    (TopicViewSet, "/topics/", "主题"),
    (EntryViewSet, "/entries/", "笔记"),
    (CardViewSet, "/cards/", "闪卡"),
    (SessionViewSet, "/sessions/", "学习会话"),
    (EventViewSet, "/events/", "学习事件"),
]

QUERY_PARAMS = {
    "topics": [
        ("search", "string", "按主题名模糊搜索"),
        ("ordering", "string", "排序字段，支持 date_added、text"),
    ],
    "entries": [
        ("search", "string", "按笔记内容或主题名搜索"),
        ("q", "string", "笔记内容包含关键词"),
        ("topic", "integer", "按主题 ID 过滤"),
        ("ordering", "string", "排序字段，支持 date_added"),
    ],
    "cards": [
        ("due", "string", "传 1 或 true 只看到期闪卡"),
    ],
    "sessions": [],
    "events": [
        ("ordering", "string", "排序字段，支持 created_at"),
    ],
}


def _schema_for(serializer_class) -> dict:
    """把序列化器的字段描述成 JSON Schema。"""
    try:
        fields = serializer_class().fields
    except Exception:  # pragma: no cover - 序列化器异常时退化成空对象
        return {"type": "object"}

    required = []
    properties: dict = {}
    for name, field in fields.items():
        properties[name] = _field_schema(field)
        if getattr(field, "required", False):
            required.append(name)

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _field_schema(field) -> dict:
    if isinstance(field, serializers.ListSerializer):
        return {"type": "array", "items": _field_schema(field.child)}
    if isinstance(field, serializers.PrimaryKeyRelatedField):
        return {"type": "integer"}
    if isinstance(field, serializers.ManyRelatedField):
        return {"type": "array", "items": {"type": "integer"}}
    if isinstance(field, serializers.SerializerMethodField):
        return {"description": field.help_text or "计算字段"}
    if isinstance(field, serializers.ChoiceField):
        choices = list(field.choices or {})
        return {"type": "string", "enum": choices} if choices else {"type": "string"}
    if isinstance(field, serializers.DateTimeField):
        return {"type": "string", "format": "date-time"}
    if isinstance(field, serializers.DateField):
        return {"type": "string", "format": "date"}
    if isinstance(field, serializers.BooleanField):
        return {"type": "boolean"}
    if isinstance(field, serializers.IntegerField):
        return {"type": "integer"}
    if isinstance(field, serializers.FloatField):
        return {"type": "number"}
    mapping = {
        serializers.EmailField: "string",
        serializers.URLField: "string",
        serializers.CharField: "string",
        serializers.JSONField: "object",
    }
    for cls, json_type in mapping.items():
        if isinstance(field, cls):
            return {"type": json_type}
    return {"type": "string"}


def _query_params(key: str) -> list:
    params = [
        {"name": "page", "in": "query", "schema": {"type": "integer"}, "description": "页码"},
        {
            "name": "page_size",
            "in": "query",
            "schema": {"type": "integer", "maximum": 100},
            "description": "每页条数，最大 100",
        },
    ]
    for name, kind, description in QUERY_PARAMS.get(key, []):
        params.append(
            {
                "name": name,
                "in": "query",
                "schema": {"type": kind},
                "description": description,
            }
        )
    return params


def build_openapi() -> dict:
    """生成完整的 OpenAPI 3 文档。"""
    paths: dict = {}

    for viewset, prefix, label in ENDPOINTS:
        key = prefix.strip("/").split("/")[0]
        serializer = viewset.serializer_class
        list_schema = _schema_for(serializer)
        item_schema = list_schema

        get_params = _query_params(key)
        paths[prefix] = {
            "get": {
                "summary": f"{label}列表",
                "tags": [label],
                "parameters": get_params,
                "responses": {
                    "200": {
                        "description": "分页后的列表",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "count": {"type": "integer"},
                                        "next": {"type": "string", "nullable": True},
                                        "previous": {"type": "string", "nullable": True},
                                        "results": {"type": "array", "items": item_schema},
                                    },
                                }
                            }
                        },
                    },
                    "401": {"description": "令牌缺失或无效"},
                    "429": {"description": "超过限流"},
                },
            }
        }

        # 详情页
        detail_path = f"{prefix}{{id}}/"
        paths[detail_path] = {
            "get": {
                "summary": f"{label}详情",
                "tags": [label],
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
                ],
                "responses": {
                    "200": {
                        "description": "单个对象",
                        "content": {"application/json": {"schema": item_schema}},
                    },
                    "404": {"description": "不存在或不属于当前用户"},
                },
            }
        }

        if issubclass(viewset, EntryViewSet):
            create_schema = _schema_for(EntryViewSet.get_serializer_class)
            paths[prefix]["post"] = {
                "summary": "新建笔记",
                "tags": [label],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": create_schema}},
                },
                "responses": {
                    "201": {
                        "description": "已创建",
                        "content": {"application/json": {"schema": item_schema}},
                    },
                    "400": {"description": "参数不合法"},
                },
            }

    paths["/stats/"] = {
        "get": {
            "summary": "统计概览",
            "tags": ["统计"],
            "responses": {
                "200": {
                    "description": "统计结果",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "overview": {"type": "object"},
                                    "streak": {"type": "integer"},
                                    "week_minutes": {"type": "integer"},
                                    "topic_ranking": {"type": "array", "items": {"type": "object"}},
                                },
                            }
                        }
                    },
                }
            },
        }
    }
    paths["/schema/"] = {
        "get": {
            "summary": "接口文档",
            "tags": ["文档"],
            "responses": {"200": {"description": "OpenAPI 文档"}},
        }
    }

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "知迹开放 API",
            "version": "2.0.0",
            "description": "个人学习数据接口，需要 Bearer 令牌。所有查询只返回令牌所属用户的数据。",
        },
        "servers": [{"url": "/api/v2"}],
        "components": {
            "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
        },
        "security": [{"bearer": []}],
        "tags": [
            {"name": "主题"},
            {"name": "笔记"},
            {"name": "闪卡"},
            {"name": "学习会话"},
            {"name": "学习事件"},
            {"name": "统计"},
            {"name": "文档"},
        ],
        "paths": paths,
    }


__all__ = ["build_openapi", "StatsView", "SchemaView"]
