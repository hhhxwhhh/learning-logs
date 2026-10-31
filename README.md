# 知迹 · Learning Log

一个把「学习笔记 → 学习路径 → 时间投入 → AI 复盘 → 间隔复习」串成闭环的学习记录系统。
Django 服务端渲染，零前端框架依赖，可完全离线运行，也可以接任意 OpenAI 兼容大模型。

## 功能

| 模块 | 说明 |
| --- | --- |
| 学习主题 / 笔记 | 主题下记录条目，支持 Markdown 渲染、完成状态、评论与全文搜索 |
| AI 助教 | 基于当前主题笔记的多轮对话，SSE 流式输出，支持摘要 / 自测题 / 下一步建议 |
| AI 生成学习路径 | 让模型把目标拆成 3-6 个步骤，自动创建主题、步骤与资源 |
| 学习路径 | 手动编排步骤、预计学时与资源，记录完成进度 |
| 学习计时 | 开始 / 结束会话，自动累计学习时长 |
| 学习分析 | 热力图、12 周投入、时段分布、主题投入排行、自动洞察 |
| 闪卡复习 | SM-2 间隔重复算法，AI 一键从笔记生成卡片，支持键盘评分 |
| 学习目标 | 截止日期、剩余天数、逾期提醒 |
| 学习花园 | SVG 知识树、成长阶段（种子→森林）、今日回顾 |
| 学习周报 | 本周/上周数据对比，AI 三段式复盘，无模型时给规则建议 |
| 全局搜索 | ⌘K 命令面板，主题/笔记/功能页混合检索，关键词高亮 |
| 数据导出 | Markdown ZIP、Anki CSV、JSON 完整备份，支持 Markdown 导入 |
| 标签体系 | Tag + GenericForeignKey，主题与笔记共用一套标签，标签云与标签详情页 |
| 知识图谱 | 服务端力导向布局，共享标签的主题自动连线，输出强关联与孤立知识 |
| 今日速览 | 今日笔记、专注时长、连续天数、待复习卡片与 30 天前记忆闪回 |
| 专注计时 | 番茄钟（25/5 分钟），结束即写入学习会话并进入统计 |
| Markdown 编辑器 | 零依赖工具条 + 实时预览，支持列表、待办、代码与引用 |
| 功能地图 | 19+ 项能力分组汇总、关键词筛选，兼作快捷键速查表 |
| 键盘快捷键 | `⌘K` 搜索、`?` 打开功能地图、`G` 前缀直达各页面 |
| 开放 API | 个人令牌鉴权，`/api/v1/` 七个 JSON 接口 + 文档页 + 令牌管理 |
| 站内提醒 | 到期复习、连续中断、周报待生成、目标临期、主题搁置五类提醒，顶栏未读铃铛 |
| 导入中心 | 批量文本建卡、Anki CSV 上传、Markdown 笔记导入，按正面去重 |
| 复习统计 | 掌握度三档分布、近 14 天复习量柱图、按主题掌握进度 |
| PWA | manifest + Service Worker + 离线兜底页，页面访问后自动缓存 |

## 技术栈

- **Django 5.2** + Python 3.13，SQLite（可直接切换 PostgreSQL）
- **markdown-it-py** 渲染笔记与 AI 回答（禁用原始 HTML，避免 XSS）
- **openai SDK** 统一访问 Ollama / DeepSeek / OpenAI 等兼容服务
- **SSE** 流式输出，原生 `fetch` + `ReadableStream` 增量渲染
- **自研 CSS 设计系统**：设计令牌、明暗主题、`:has()` 与 `color-mix()`，无 Bootstrap / Tailwind 依赖
- **Gunicorn + WhiteNoise** 生产部署，容器内非 root 运行，带 `/healthz` 探活
- **PWA**：Web App Manifest + Service Worker，页面访问后自动缓存，断网可回看
- **零依赖前端组件**：Markdown 编辑器、知识图谱力导向布局、番茄钟、命令面板全部自研

## 快速开始

```bash
# 1. 准备环境（建议 3.12+）
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env             # 按需修改，至少换掉 DJANGO_SECRET_KEY

# 3. 初始化数据库
python manage.py migrate
python manage.py createsuperuser

# 4. 启动
python manage.py runserver
```

访问 <http://127.0.0.1:8000>，注册后即可开始记录。

## AI 配置

AI 能力全部由环境变量驱动，默认对接本地 Ollama 的 OpenAI 兼容接口：

```env
AI_PROVIDER=ollama
AI_BASE_URL=http://localhost:11434/v1
AI_API_KEY=ollama
AI_MODEL=qwen2.5:7b
```

本地模型准备：

```bash
ollama pull qwen2.5:7b
ollama serve
```

切换到云端兼容服务只需要改三行：

```env
AI_PROVIDER=openai
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-xxxx
AI_MODEL=deepseek-chat
AI_MODELS=deepseek-chat|DeepSeek V3,deepseek-reasoner|DeepSeek R1
```

没有模型也能用界面：设置 `AI_PROVIDER=mock` 进入离线演示模式，不发起任何网络请求。

> 隐私说明：只有当前主题的笔记（最近 40 条、约 6000 字）会被拼进提示词发给模型服务。
> 使用本地 Ollama 时数据不出内网。

## 项目结构

```
ll_project/            项目配置（settings 全部来自环境变量）、健康检查
learning_logs/         主题、笔记、路径、计时、闪卡、统计服务
  ai/                  Provider 抽象、提示词、流式编排、AI 视图
  services/stats.py    热力图 / 连续天数 / 时段分布等统计口径
  services/search.py   多关键词检索、相关度排序与高亮片段
  services/garden.py   知识树几何计算、成长阶段、今日回顾
  services/report.py   学习周报统计与 AI 复盘生成
  services/export.py   Markdown / CSV / JSON 导出与导入（含批量建卡、Anki CSV）
  services/tags.py     标签解析、同步与标签云
  services/graph.py    知识图谱的关联边与力导向布局
  services/notifications.py  站内提醒的生成、幂等与裁剪
  services/api_access.py     开放 API 的鉴权与序列化
  api_views.py         /api/v1/ 只读与写入接口
  context_processors.py      把未读提醒带进所有页面
  templatetags/        Markdown、时长格式化过滤器
accounts/              自定义用户、注册登录、个人中心
analytics/             学习分析（总览 / 时间统计 / 进度报告 / 主题分析）
templates/partials/    图标精灵、表单字段等共享片段
static/css/app.css     设计系统（2000 行，无外部依赖）
static/js/app.js       主题切换、Toast、命令面板、快捷键导航
static/js/editor.js    Markdown 编辑器工具条与实时预览
static/js/focus.js     番茄钟计时与写入学习会话
static/js/sw.js        Service Worker：静态缓存 + 页面回退
```

## 测试

```bash
python manage.py test
```

121 个测试用例，覆盖模型进度计算、SM-2 间隔算法、越权访问、标签与图谱、通知幂等、
开放 API 鉴权、导入去重、AI 流式接口与结构化输出解析（AI 调用全部使用假 Provider，不联网）。

## 页面地图

| 路径 | 用途 |
| --- | --- |
| `/` | 产品首页，登录用户额外看到「我的学习快照」 |
| `/topics/` `/topic/<id>` | 主题列表与主题详情（含条目搜索、状态/标签筛选） |
| `/dashboard/` `/analytics/` | 仪表盘与学习分析 |
| `/today/` | 今日速览：待办、连续天数、记忆闪回 |
| `/focus/` | 专注计时（番茄钟） |
| `/flashcards/` `/flashcards/review/` `/flashcards/stats/` | 闪卡管理、今日复习、复习统计 |
| `/learning-paths/` | 学习路径编排 |
| `/garden/` `/graph/` | 学习花园（知识树）与知识图谱 |
| `/tags/` `/tags/<id>/` | 标签云与标签详情 |
| `/weekly/` `/achievements/` | 学习周报与成就徽章 |
| `/import/` `/data/` | 导入中心与导出备份 |
| `/notifications/` | 提醒中心 |
| `/settings/api/` `/api/docs/` | API 令牌管理与接口文档 |
| `/features/` | 功能地图与快捷键速查 |

## 部署

```bash
docker build -t learning-log .
docker run --rm -p 8000:8000 \
  -e DJANGO_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(50))')" \
  -e DJANGO_ALLOWED_HOSTS=your-domain.com \
  -v "$PWD/data:/app/data" \
  learning-log
```

首次启动前执行迁移：

```bash
docker run --rm -v "$PWD/data:/app/data" learning-log python manage.py migrate
```

生产环境要点：`DJANGO_DEBUG=0`、设置 `DJANGO_SECRET_KEY` 与 `DJANGO_ALLOWED_HOSTS`、
反向代理终止 HTTPS（默认开启 `SECURE_SSL_REDIRECT` 与 HSTS）。

## 设计取舍

- **不用前端构建**：模板足够快，少一层工具链，学习项目更容易长期维护。
- **数据永不上云**：没有第三方分析脚本，字体与图标全部本地化。
- **AI 只是助手**：所有回答都标注来源笔记，模型不可用时功能自动降级而不是整页崩溃。

## License

MIT
