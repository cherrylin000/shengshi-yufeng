# 喜马拉雅专辑文稿：盛世裕丰

- 专辑 ID：41054149
- 主播：盛世裕丰财富之道
- 音频总数：392
- 成功生成文稿：318
- 未生成/失败：74

## 文件说明

- `index.csv`：每条音频的抓取状态、字符数、文稿路径、发布时间、播放量。
- `tracks.json`：专辑音频列表原始元数据（含 `playCount`、`publishedAt`）。
- `errors.json`：未生成文稿的音频及错误原因。
- `investment_system.md`：基于可用文稿整理出的盛世裕丰投资体系。
- `transcripts/`：逐条音频 Markdown 文稿。
- `polished/`：润色后的结构化文字稿与章节目录（按文意分段，单段一般不超过 160 字）。
- `asr_raw/`：本地 Whisper ASR 原始结果。
- `../index.html`：可对外分享的静态网页（仓库根），含投资体系与文稿检索。
- `article.html`：单篇文稿阅读页（`../data-index.js` + `articles/{序号}.json`）。
- `articles/`：单篇文稿正文与简介/速览（由 `scripts/site/data_bundle.py` 生成）。
- `../webapp/`：注册登录、已读状态、浏览记录与高亮笔记（Flask + SQLite）。

> 文稿来自页面公开返回的 AI/ASR 文稿数据，或本地 faster-whisper 识别；可能存在同音字、断句和识别错误。
