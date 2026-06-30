# shengshi-yufeng

盛世裕丰老师喜马拉雅音频总结而来的投资体系。

## 在线浏览

本仓库可启用 GitHub Pages（**仓库根目录**为站点根目录）。根目录仅保留 `index.html` 作为默认首页；单篇文稿页位于 `content/article.html`，站内链接已统一指向该路径。

- [投资体系与文稿库](index.html)

启用 Pages 后的典型地址：<https://cherrylin000.github.io/shengshi-yufeng/>

## 目录结构

```
├── index.html / data-index.js            # 首页（轻量索引，不含全文稿）
├── content/article.html                  # 单篇阅读页（按篇加载 articles/*.json）
├── content/articles/                     # 单篇文稿 JSON（构建生成）
├── content/                              # 专辑文稿与 investment_system.md
└── scripts/
    ├── site/                             # 构建 data-index.js、体系链接
    └── transcripts/                      # 文稿规范化与 Show Notes 回退
```

## 本地预览

```bash
python -m http.server 8080
# 浏览器打开 http://localhost:8080/index.html
```

## 维护命令

```bash
# 喜马拉雅专辑有更新：刷新 tracks.json / index.csv，并为新音频生成 md 文稿
python scripts/transcripts/sync_album_from_api.py --fetch-transcripts --delay 2

# 补抓未拿到全文的文稿（373+ 等需登录 Cookie 才能拉「原文文稿」）
# 先设置环境变量 XIMALAYA_COOKIE（见下方说明），再执行：
python scripts/transcripts/sync_album_from_api.py --skip-tracks-json --refetch-incomplete --from-index 373 --delay 2

# 单条测试原文文稿 API：
python scripts/transcripts/fetch_aidoc.py 980020064

# 从 content/transcripts 全量同步到 data-index.js + content/articles/（按篇 JSON）
python scripts/site/sync_data_from_content.py

# 或一键：文稿 + 播放量/发布时间（来自 tracks.json 与 Markdown）
python scripts/site/rebuild_data_js.py

# 若仅有旧版 data.js，可一次性拆分为索引 + 单篇 JSON：
python scripts/site/data_bundle.py

# 仅补充 intro / outline（旧命令，不含全文稿）
python scripts/site/enrich_data.py

# 从 API 拉取发布时间并写入全项目（约 4 分钟，支持 --resume）
python scripts/site/sync_track_meta.py --resume --delay 0.4

# 体系内代表文稿 → content/article.html（含 investment_system.md）
python scripts/site/link_system_articles.py
python scripts/site/link_system_articles.py --labels-only

# 投资体系 HTML 表格化 / 列表修复
python scripts/site/enhance_system_tables.py
python scripts/site/fix_system_lists.py
python scripts/site/split_system_sections.py

# 文稿 ASR 规范化（术语表在 scripts/transcripts/）
python scripts/transcripts/normalize_transcripts.py
```

## 自动同步（GitHub Actions）

仓库含 [`.github/workflows/sync-ximalaya.yml`](.github/workflows/sync-ximalaya.yml)：默认**每周一 10:00（北京时间）**检查喜马拉雅专辑是否有新音频，若有则抓取文稿、重建 `data-index.js` / `content/articles/` 并提交到 `main`（GitHub Pages 会随之更新）。

手动触发：GitHub 仓库 → **Actions** → **Sync Ximalaya album** → **Run workflow**。

首次启用需在仓库 **Settings → Actions → General → Workflow permissions** 中选择 **Read and write permissions**。

### 原文文稿（373 集及以后）

手机 App 里的「原文文稿」来自 `anchor-works-web/aiDoc/page`，**需要登录 Cookie**，公开 Show Notes API 往往没有 `aiDocUrl`。

1. 浏览器登录 [喜马拉雅](https://www.ximalaya.com)，打开**有「原文文稿」的音频页**（如 [第 377 集](https://www.ximalaya.com/sound/980020064)）。
2. F12 → **Network** → 刷新 → 任选同域请求 → 复制请求头整段 **Cookie**（需含登录态；仅首页 Cookie 可能不够）。
3. 本地：`$env:XIMALAYA_COOKIE="..."`；GitHub：**Settings → Secrets → Actions** → `XIMALAYA_COOKIE`。
4. 验证：`python scripts/transcripts/fetch_aidoc.py 980020064 --debug`（应看到 `chars:` 与正文预览）。
5. 补抓：`python scripts/transcripts/sync_album_from_api.py --skip-tracks-json --refetch-incomplete --from-index 373 --delay 2`

若本地公司网络拦截 `m.ximalaya.com`（Fortinet 等），请在 GitHub Actions 手动运行 workflow 测试；或手机热点后再跑本地命令。

Cookie 仅用于抓取您有权访问的专辑文稿，**不要**粘贴到 Issue/聊天；过期后重新复制更新 Secret。
