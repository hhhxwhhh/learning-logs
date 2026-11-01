"""端到端验证：登录 → 连 WebSocket → 写笔记 → 收到推送。

需要一个跑起来的 ASGI 服务（uvicorn ll_project.asgi:application）。

    python scripts/e2e_live.py http://127.0.0.1:8900
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

import websockets

USERNAME = "e2e_user"
PASSWORD = "e2e-pass-12345"


def make_opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    # 本机设了 http_proxy 环境变量，不绕过代理的话访问 127.0.0.1 会被代理挡成 502
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(jar),
    )
    opener.cookiejar = jar
    return opener


def csrf_token(opener, base: str) -> str:
    with opener.open(f"{base}/topics/", timeout=10) as response:
        html = response.read().decode("utf-8")
    marker = 'name="csrfmiddlewaretoken" value="'
    index = html.find(marker)
    if index < 0:
        return ""
    start = index + len(marker)
    return html[start : html.find('"', start)]


def login(opener, base: str) -> None:
    token = csrf_token(opener, base)
    data = urllib.parse.urlencode(
        {"username": USERNAME, "password": PASSWORD, "csrfmiddlewaretoken": token}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/accounts/login/",
        data=data,
        headers={"Referer": f"{base}/accounts/login/"},
    )
    try:
        with opener.open(request, timeout=10) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"登录失败：HTTP {exc.code}") from exc


def ensure_user(base: str) -> None:
    """用管理命令建好用户，避免脚本直接碰数据库。"""
    import subprocess
    import sys as _sys

    subprocess.run(
        [
            _sys.executable,
            "manage.py",
            "shell",
            "-c",
            (
                "from django.contrib.auth import get_user_model;"
                "U=get_user_model();"
                f"U.objects.filter(username='{USERNAME}').exists() or "
                f"U.objects.create_user('{USERNAME}', password='{PASSWORD}')"
            ),
        ],
        check=True,
        capture_output=True,
    )


def latest_topic_id() -> int:
    """取刚创建的主题 id。

    new_topic 成功后重定向到主题列表页，不含 id，所以这里从库里取最新的一个。
    """
    import subprocess
    import sys as _sys

    result = subprocess.run(
        [
            _sys.executable,
            "manage.py",
            "shell",
            "-c",
            (
                "from learning_logs.models import Topic;"
                f"print(Topic.objects.filter(owner__username='{USERNAME}')"
                ".order_by('-id').values_list('id', flat=True).first() or '')"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    raw = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if not raw.isdigit():
        raise SystemExit(f"没能取到主题 id，输出：{result.stdout!r}")
    return int(raw)


def create_topic(base: str, opener) -> int:
    token = csrf_token(opener, base)
    data = urllib.parse.urlencode(
        {"text": f"E2E 主题 {USERNAME}", "csrfmiddlewaretoken": token}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/new_topic/",
        data=data,
        headers={"Referer": f"{base}/new_topic/"},
    )
    with opener.open(request, timeout=10) as response:
        response.read()
    return latest_topic_id()


def create_entry(base: str, opener, topic_id: int) -> None:
    token = csrf_token(opener, base)
    data = urllib.parse.urlencode(
        {"text": "端到端测试写入的笔记", "csrfmiddlewaretoken": token}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/new_entry/{topic_id}",
        data=data,
        headers={"Referer": f"{base}/new_entry/{topic_id}"},
    )
    opener.open(request, timeout=10).read()


async def listen(base: str, cookie: str, topic_id: int) -> bool:
    ws_base = base.replace("http://", "ws://").replace("https://", "wss://")
    headers = {"Cookie": cookie}
    uri = f"{ws_base}/ws/live/"

    async with websockets.connect(uri, additional_headers=headers) as socket:
        ready = await asyncio.wait_for(socket.recv(), timeout=10)
        print(f"  握手响应：{ready}")

        await asyncio.sleep(0.3)
        # 在另一个线程里写笔记，这里等推送
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, create_entry, base, OPENER, topic_id)

        for _ in range(20):
            raw = await asyncio.wait_for(socket.recv(), timeout=10)
            payload = json.loads(raw)
            if payload.get("type") == "event":
                event = payload.get("event") or {}
                print(f"  收到事件：{event.get('kind')} · {event.get('summary')}")
                if not event.get("kind"):
                    print(f"  原始负载：{raw}")
                return True
    return False


OPENER = None


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8900"
    base = base.rstrip("/")

    global OPENER
    ensure_user(base)
    OPENER = make_opener()
    login(OPENER, base)
    print("  登录成功")

    topic_id = create_topic(base, OPENER)
    print(f"  主题已创建：{topic_id}")

    cookie = "; ".join(
        f"{item.name}={item.value}" for item in OPENER.cookiejar
    )

    ok = asyncio.run(listen(base, cookie, topic_id))
    if ok:
        print("结果：WebSocket 实时推送正常")
        return 0
    print("结果：没有收到事件推送")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
