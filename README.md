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
