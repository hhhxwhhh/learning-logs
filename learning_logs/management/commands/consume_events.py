"""从消息总线消费学习事件并落库。

用法：
    python manage.py consume_events --source=auto --once
    python manage.py consume_events --source=kafka --limit=500
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from learning_logs.messaging import consumer


class Command(BaseCommand):
    help = "消费 Kafka / Redis Stream 里的学习事件并写入事件表"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["auto", "kafka", "redis"],
            default="auto",
            help="事件来源，默认按配置自动选择",
        )
        parser.add_argument("--limit", type=int, default=100, help="单次最多处理多少条")
        parser.add_argument("--once", action="store_true", help="只跑一轮就退出")
        parser.add_argument("--interval", type=float, default=2.0, help="循环模式下的间隔秒数")

    def handle(self, *args, **options):
        source = options["source"]
        limit = options["limit"]

        while True:
            created = consumer.consume(source=source, limit=limit)
            if created:
                self.stdout.write(f"写入 {created} 条事件")
            if options["once"]:
                break
            time.sleep(options["interval"])
