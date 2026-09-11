# 盛世裕丰：Vercel 同域部署注册登录与勾画笔记

provenance: self  
日期：2026-09-11  
状态：已获用户口头确认各节；待用户审阅本文档后进入实现计划

## 背景与目标

公开站目前在 Vercel 上仅为**静态文稿**（`shengshi-yufeng.vercel.app`）。注册、登录、已读、浏览记录、勾画笔记、脑图上传依赖本地 Flask + SQLite（`webapp/`），GitHub Pages / 纯静态无法运行。

目标：在**同一 Vercel 域名**上提供完整账号能力，与文稿同站同 Cookie；线上使用免费 Postgres（Neon）；本地可继续用 SQLite 开发。本地已有账号**不迁移、作废即可**。

## 已选方案

保留现有 Flask 应用，以 Vercel Python Serverless 挂载；数据层支持 `DATABASE_URL`（Postgres）与本地 SQLite 双后端。不采用「拆多个无状态函数重写 API」或「Serverless 上硬用 SQLite」。

## 1. 整体架构与请求分流

同一域名同时提供静态文稿与账号能力。

### 分流（`vercel.json`）

| 类别 | 路径 | 处理 |
|------|------|------|
| 静态 | `/`、`/index.html`、`/data-index.js`、`/content/**` 等 | Vercel 静态托管 |
| 动态 | `/register`、`/login`、`/logout`、`/notes`、`/api/**`、上传相关路径、`webapp` 静态资源（如 auth.css） | Flask Serverless |

### 运行形态

- 入口：`api/index.py`（或等价）挂载现有 `webapp` Flask `app`
- 本地：无 `DATABASE_URL` 时用 SQLite，可继续 `python webapp/app.py`
- 线上：`DATABASE_URL` + `SECRET_KEY`；session 使用环境变量密钥，不依赖本机 `secret.key` 文件提交到仓库

### 会话

继续 Flask cookie session：`HttpOnly` + `SameSite=Lax`；生产环境启用 `Secure`。

### 前端

`content/article.html` 已用 `credentials: 'same-origin'` 调用 `/api/*`；部署后保持同域，无需改 API 基址（除非发现相对路径问题再小修）。

## 2. 库表与环境变量

### 表（语义与现网一致；Postgres / SQLite 共用）

| 表 | 用途 |
|----|------|
| `users` | 用户名、密码哈希、创建时间 |
| `article_state` | 每篇已读（user + article_index 唯一） |
| `browse_history` | 浏览记录；**每人只保留最近 50 条**（写入时裁剪） |
| `notes` | 勾画笔记：选中原文、想法、可选图片引用、文稿索引/标题 |

启动时 `CREATE TABLE IF NOT EXISTS` 自动建表；不要求手跑迁移脚本。

### 双后端

- 存在 `DATABASE_URL` → Postgres（线上 Neon）
- 否则 → SQLite（仅本地）

### 环境变量（Vercel）

| 变量 | 必需 | 说明 |
|------|------|------|
| `DATABASE_URL` | 是 | Neon（或 Vercel Postgres）连接串 |
| `SECRET_KEY` | 是 | Flask session 密钥（随机长串） |
| `BLOB_READ_WRITE_TOKEN` | 否 | 脑图走 Vercel Blob 时使用 |

### 明确不做

- 不从本机 SQLite 导入用户/笔记
- 不把 `webapp/data/` 提交进 git
- 本机 `app.db` 可直接删除

## 3. 页面 / API 与图片

### 路径行为（与现有本地版对齐）

| 路径 | 作用 |
|------|------|
| `/register` `/login` `/logout` | 注册、登录、退出 |
| `/notes` | 我的笔记（需登录） |
| `/api/me` | 当前登录态 |
| `/api/read-state` | 已读读写 |
| `/api/history` | 浏览记录；保留最近 **50** 条/人 |
| `/api/notes`、`/api/notes/<id>` | 勾画笔记 CRUD |
| `/api/notes/<id>/image` | 脑图上传/删除 |

文稿页勾画 UX（选区浅蓝、保存后黄底、「取消高亮」「确认」）本次不重做。不做微信/短信登录。

### 图片策略

1. 优先：配置了 `BLOB_READ_WRITE_TOKEN` → Vercel Blob，`notes` 存 URL  
2. 降级：未配置 → 小图（建议 ≤500KB）写入库字段或等价存储；超限提示压缩  
3. 本地：可继续写 `webapp/data/uploads/`

### 安全

- 密码：现有 werkzeug 哈希
- Session：见上
- 笔记/图片接口校验资源归属当前用户

## 4. 部署步骤与验收

### 用户一次性配置（免费档）

1. 创建 Neon（或 Vercel Storage Postgres）免费库，取得 `DATABASE_URL`
2. 在 Vercel 项目 `shengshi-yufeng` 配置 `DATABASE_URL`、`SECRET_KEY`（及可选 Blob token）
3. 代码合并并 push `main` 后自动部署

### 实现侧改动范围

- `vercel.json` 动态路由 rewrite
- `api/` Flask 入口
- `webapp/db.py` Postgres + SQLite；history 裁剪为 50
- Session / 上传适配线上
- 面向 Vercel 的精简 Python 依赖（Flask、驱动等；**不含** whisper / yt-dlp 等同步流水线重依赖）
- README 或短文档说明环境变量与本地删除 `app.db`

### 验收标准

- 正式域名可浏览文稿
- `/register` 可注册并登录；`/notes` 可见笔记
- 文稿页：已读、勾画保存、笔记列表与脑图（在策略允许范围内）可用
- 刷新或换窗口同账号数据仍在（证明持久化到 Postgres）
- 未登录访问需登录的 API 返回未授权/引导登录
- 本地无 `DATABASE_URL` 时 SQLite 仍可用

### 风险与边界

- Hobby 冷启动可能有 1–3 秒延迟
- 未配 Blob 时大图受限
- 无本地数据迁移

## 非目标

- 不改造喜马拉雅周更 / ASR / 润色流水线
- 不实现第三方 OAuth / 短信登录
- 不把 GitHub Pages 作为账号后端

## 决策记录

| 项 | 决定 |
|----|------|
| 托管 | Vercel 同域，方案 A |
| 应用形态 | 保留 Flask Serverless |
| 数据库 | Neon Postgres（线上）+ SQLite（本地） |
| 浏览记录 | 每人最近 50 条 |
| 本地账号 | 删除/作废，不迁移 |
| 图片 | Blob 优先，小图降级存库 |
