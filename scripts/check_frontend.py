"""验证前端在真实页面里能挂载并渲染。

用登录态打开 /live/，检查返回的 HTML 里是否带上前端产物与首屏数据。
渲染本身由浏览器执行，这里只做服务端能确认的部分。
"""

from __future__ import annotations

import sys
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8900"
USERNAME = "e2e_user"
PASSWORD = "e2e-pass-12345"


def make_opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
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
    opener.open(request, timeout=10).read()


def main() -> int:
    base = BASE.rstrip("/")
    opener = make_opener()
    login(opener, base)

    with opener.open(f"{base}/live/", timeout=10) as response:
        html = response.read().decode("utf-8")

    checks = {
        "挂载点": 'id="live-app"' in html,
        "首屏数据": 'id="live-initial"' in html,
        "前端脚本": "live/app.js" in html,
        "前端样式": "live/app.css" in html,
        "WebSocket 地址": "/ws/live/" in html,
    }
    for label, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {label}")

    # 静态产物确实在磁盘上
    for path in ("static/live/app.js", "static/live/app.css"):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        exists = (root / path).exists()
        size = (root / path).stat().st_size if exists else 0
        print(f"  {'✓' if exists and size > 0 else '✗'} {path}（{size} 字节）")
        checks[path] = exists and size > 0

    if all(checks.values()):
        print("结果：前端资源与首屏数据就位")
        return 0
    print("结果：检查未通过")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
