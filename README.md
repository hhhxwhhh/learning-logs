# 知迹 · Learning Log

一个自己用的学习记录系统：把笔记、学习路径、时间投入、间隔复习串成闭环，
数据留在本地，服务端可以拆成多个进程跑。

## 功能

| 模块 | 说明 |
| --- | --- |
| 学习主题 / 笔记 | 主题下记录条目，支持 Markdown、完成状态、评论、全文搜索与 `[[双链]]` |
| 学习路径 | 手动编排步骤、预计学时与资源，记录完成进度 |
| 学习计时 | 开始 / 结束会话，累计真实学习时长 |
| 学习分析 | 热力图、12 周投入、时段分布、主题投入排行 |
| 闪卡复习 | SM-2 间隔重复，键盘评分，支持按主题看掌握度 |
| 学习目标 | 截止日期、剩余天数、逾期提醒 |
| 学习花园 | SVG 知识树与成长阶段 |
| 学习周报 | 本周 / 上周数据对比 |
| 全局搜索 | `⌘K` 命令面板，主题 / 笔记 / 功能页混合检索 |
| 数据导出 | Markdown ZIP、Anki CSV、JSON 完整备份，支持 Markdown 导入 |
| 标签体系 | Tag + GenericForeignKey，主题与笔记共用一套标签 |
| 知识图谱 | 服务端力导向布局，共享标签的主题自动连线 |
| 今日速览 | 今日笔记、专注时长、连续天数、待复习卡片、待办、30 天前记忆闪回 |
| 专注计时 | 番茄钟（25/5 分钟），结束写入学习会话并进入统计 |
| Markdown 编辑器 | 零依赖工具条 + 实时预览 |
| 功能地图 | 全部能力分组汇总、关键词筛选，兼作快捷键速查表 |
| 学习时间线 | 按月聚合笔记、卡片与时长，6/12/24 个月切换 |
| 学习洞察 | 规则引擎算出黄金时段、最活跃星期、投入集中度、复习健康度 |
| 待办清单 | 汇总笔记里的 `- [ ]`，勾选写回原文并留版本 |
| 双链笔记 | `[[主题名]]` 自动链接，目标页显示反向链接 |
| 置顶与归档 | 主题可置顶排序、归档后隐藏，可一键恢复 |
| 版本历史 | 笔记每次修改留痕，支持预览与回滚 |
| 公开主页 | `/u/<用户名>/` 聚合已分享主题的只读页 |
| 站内提醒 | 到期复习、连续中断、目标临期、主题搁置等提醒 |
| 导入中心 | 批量文本建卡、Anki CSV 上传、Markdown 笔记导入，按正面去重 |
| 开放 API v1 | 个人令牌鉴权，JSON 接口 + 文档页 + 令牌管理 |
| 开放 API v2 | DRF 实现，视图集、过滤、排序、分页、统一错误结构、限流与调用审计 |
| 活动流 | 学习动作统一落 `EventLog`，按天回看 |
| 实时看板 | WebSocket 推送，Vue 3 单页展示当前指标与事件流 |
| 学习助手 | 模型调用工具读写笔记、闪卡与待办，带调用轨迹 |
| PWA | manifest + Service Worker，页面访问后自动缓存 |

## 技术栈

**服务端**

- Django 5.2 + Python 3.13，SQLite（可换 PostgreSQL）
- DRF 3.16：v2 API 的序列化器、视图集、过滤、排序、分页
- Channels 4.3 + channels-redis：WebSocket 广播
- Celery 5.5 + Redis：定时任务与异步执行
- kafka-python：学习事件投递到 Kafka
- uvicorn：ASGI 进程

**前端**

- Vue 3 + Vite 5：实时看板单页应用，构建产物落在 `static/live/`
- 其余页面仍是 Django 服务端渲染，CSS 设计系统在 `static/css/app.css`
- 无 CDN 依赖，字体与图标本地化

**模型接入**

- OpenAI 兼容接口（Ollama / DeepSeek / OpenAI 等）
- 无模型时用 `AI_PROVIDER=mock` 离线运行，功能自动降级

## 架构

```
浏览器
  │
  ├─ HTTP ──▶ Django（SSR 页面 + /api/v1/ + /api/v2/）
  │             │
  │             ├─▶ Redis（缓存：统计 / 洞察 / 图谱）
  │             ├─▶ Celery worker（提醒、周报、洞察刷新）
  │             └─▶ Kafka（学习事件 topic: zhiji.learning.events）
  │
  └─ WS ───▶ Channels ──▶ Redis channel layer
                 ▲
                 └── group_send("live-<user_id>")

events 服务：消费 Kafka（无 Kafka 时读 Redis Stream）→ 幂等落 EventLog
```

每一层都能缺省运行：

| 组件 | 不配置时的行为 |
| --- | --- |
| Redis | 进程内缓存（LocMemCache）+ 同步任务 + 单进程通道层 |
| Celery broker | 任务在请求里同步执行（`CELERY_TASK_ALWAYS_EAGER`） |
| Kafka | 事件写入 Redis Stream |
| 模型服务 | `mock` provider，不发网络请求 |

## 快速开始

```bash
# 1. 环境（建议 3.12+）
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. 配置
cp .env.example .env             # 至少换掉 DJANGO_SECRET_KEY

# 3. 初始化
python manage.py migrate
python manage.py createsuperuser

# 4. 启动（开发）
python manage.py runserver
```

访问 <http://127.0.0.1:8000>。

### 带上 Redis

```bash
redis-server --port 6379
export REDIS_URL=redis://127.0.0.1:6379/0
export CELERY_BROKER_URL=redis://127.0.0.1:6379/1
export CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2
celery -A ll_project worker --loglevel=info
```

### 带上 Kafka

```bash
export KAFKA_ENABLED=1
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
python manage.py consume_events --source=auto
```

### 构建前端看板

```bash
cd frontend
npm install
npm run build          # 产物输出到 ../static/live/
```

## 模型配置

```env
AI_PROVIDER=ollama
AI_BASE_URL=http://localhost:11434/v1
AI_API_KEY=ollama
AI_MODEL=qwen2.5:7b
```

切到云端兼容服务只改这三行：

```env
AI_PROVIDER=openai
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-xxxx
AI_MODEL=deepseek-chat
```

没有模型也能用界面：`AI_PROVIDER=mock`。

> 提示词里只会拼入当前主题最近 40 条笔记（约 6000 字）。用本地 Ollama 时数据不出内网。

## 项目结构

```
ll_project/            项目配置、健康检查、ASGI 入口
accounts/              自定义用户、注册登录、个人中心
analytics/             学习分析（总览 / 时间统计 / 进度报告 / 主题分析）
learning_logs/
  ai/                  Provider 抽象、提示词、流式编排
  agent/               工具注册表与工具调用运行时
  messaging/           Kafka 生产者、Redis Stream、事件总线
  services/            统计、检索、图谱、周报、导出、标签、通知、
                       双链、时间线、洞察、待办、缓存、API 鉴权
  api_v2.py            DRF 视图集（/api/v2/）
  api_views.py         /api/v1/ 接口
  events.py            事件落库、投递、实时广播
  tasks.py             Celery 任务
  consumers.py         WebSocket 消费者
  management/commands/consume_events.py   事件消费命令
frontend/              Vue 3 + Vite 源码
static/live/           前端构建产物（入库）
static/css/app.css     设计系统
static/js/             主题切换、命令面板、快捷键、编辑器、番茄钟、SW
```

## 测试

```bash
python manage.py test
```

覆盖模型进度、SM-2 算法、越权访问、缓存失效、事件幂等、DRF 接口鉴权与分页、
Agent 工具调用、导入去重、洞察规则、待办回写等。AI 调用全部使用假 Provider，不联网。

## 快捷键

| 快捷键 | 作用 |
| --- | --- |
| `⌘K` / `Ctrl+K` | 全局搜索 |
| `?` | 功能地图与快捷键速查 |
| `G` + `T`/`D`/`R`/`F`/`G`/`M` | 主题 / 仪表盘 / 复习 / 专注 / 图谱 / 功能地图 |
| `G` + `L`/`J`/`K`/`S`/`O` | 时间线 / 洞察 / 待办 / 标签 / 今日速览 |
| `G` + `V`/`Q` | 活动流 / 学习助手 |
| `Esc` | 关闭弹层 |

## 页面地图

| 路径 | 用途 |
| --- | --- |
| `/` | 首页，登录用户额外看到学习快照 |
| `/topics/` `/topic/<id>` | 主题列表与详情 |
| `/dashboard/` `/analytics/` | 仪表盘与学习分析 |
| `/today/` `/focus/` | 今日速览、专注计时 |
| `/flashcards/` `/flashcards/review/` `/flashcards/stats/` | 闪卡管理、复习、统计 |
| `/learning-paths/` `/garden/` `/graph/` | 路径编排、知识树、知识图谱 |
| `/tags/` `/timeline/` `/insights/` `/todos/` | 标签、时间线、洞察、待办 |
| `/weekly/` `/achievements/` `/notifications/` | 周报、成就、提醒 |
| `/import/` `/data/` | 导入中心、导出备份 |
| `/activity/` `/live/` `/agent/` | 活动流、实时看板、学习助手 |
| `/entry/<id>/history/` | 笔记版本历史 |
| `/u/<用户名>/` | 公开主页 |
| `/settings/api/` `/api/docs/` | API 令牌管理、接口文档 |
| `/features/` | 功能地图 |

## 开放接口

- `v1`：`/api/v1/`，原有的 JSON 接口，契约保持不变
- `v2`：`/api/v2/`，DRF 实现，视图集 + 过滤 + 排序 + 分页 + 统一错误结构
- 鉴权：`Authorization: Bearer <token>` 或 `?token=<token>`（命令行调试用）
- 限流：按令牌计数，没有令牌时按 IP，默认 `240/min`，用 `API_THROTTLE_RATE` 调整
- 审计：每次调用写入 `ApiAccessLog`，可在后台按时间与状态码查看

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/v2/entries/?search=orm&page_size=20"
```

## 运维

```bash
python manage.py check_services          # 逐项检查依赖状态
python manage.py check_services --json   # 机器可读
curl -s localhost:8000/healthz/          # 存活探针：只看数据库
curl -s localhost:8000/readyz/           # 就绪探针：全部依赖
```

`/healthz/` 只探数据库，用于容器 liveness；`/readyz/` 探数据库、缓存、Celery broker、
Kafka 与通道层，缺可选依赖时状态为 `degraded`，缺必需依赖才是 `down`。
探针结果缓存 10 秒，避免监控高频拉取时反复建连。

请求日志默认输出文本行，`DJANGO_LOG_FORMAT=json` 时改为 JSON，
每条带 `request_id`，响应头也回写 `X-Request-Id`。

## 部署

```bash
docker compose up -d --build
docker compose logs -f web
```

编排包含 `web`（uvicorn ASGI）、`worker`（celery）、`beat`（celery beat）、
`events`（事件消费）、`redis`、`kafka`（KRaft 单节点）。Redis 与 Kafka 只在容器网络内暴露。

单容器运行：

```bash
docker build -t learning-log .
docker run --rm -p 8000:8000 \
  -e DJANGO_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(50))')" \
  -e DJANGO_ALLOWED_HOSTS=your-domain.com \
  -v "$PWD/data:/app/data" \
  learning-log
```

生产要点：`DJANGO_DEBUG=0`、设置 `DJANGO_SECRET_KEY` 与 `DJANGO_ALLOWED_HOSTS`、
反向代理终止 HTTPS（默认开启 `SECURE_SSL_REDIRECT` 与 HSTS）。

## 已知取舍

- **分层降级而非强制依赖**：Redis / Kafka / Celery / 模型都可选，缺一个不影响主流程，
  但也意味着部署时要多确认一次配置。
- **缓存靠数据指纹 + epoch 双保险**：避免每个写入口手动失效，代价是每次读要多一次计数查询。
- **v1 API 契约保持不变**：v2 用 DRF 重写，两者并存，旧客户端不受影响。
- **数据不上云**：没有第三方分析脚本，字体与图标本地化。

## License

MIT
