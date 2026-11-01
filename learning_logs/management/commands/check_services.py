"""检查各依赖是否可用。

    python manage.py check_services
    python manage.py check_services --json
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from ll_project.health import collect


class Command(BaseCommand):
    help = "检查数据库、缓存、Celery、Kafka、通道层等依赖的状态"

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="以 JSON 输出，便于脚本消费",
        )
        parser.add_argument(
            "--no-cache",
            action="store_true",
            help="忽略缓存，重新探测一次",
        )

    def handle(self, *args, **options):
        report = collect(use_cache=not options["no_cache"])

        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        self.stdout.write(f"整体状态：{report['status']}")
        width = max(len(name) for name in report["checks"])
        for name, item in report["checks"].items():
            self.stdout.write(
                f"  {name.ljust(width)}  {item['status']:<8} {item['ms']:>8.1f}ms  {item['detail']}"
            )
