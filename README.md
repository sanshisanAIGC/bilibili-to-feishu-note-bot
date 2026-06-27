# B站视频 → 飞书文档 AI 笔记自动化系统

分享 B站视频链接到飞书与自己聊天，AI 自动获取字幕、纠错整理、生成结构化笔记，并输出到飞书文档。

## ✨ 功能

- 🔗 **分享即触发**：在飞书给 Bot 发送 B站视频链接，自动开始处理
- 📝 **智能字幕获取**：优先使用 B站官方字幕，无字幕时自动下载音频并用 Whisper 转录
- 🤖 **AI 优化**：DeepSeek 进行字幕纠错、同音字修正、语法优化
- 📚 **两种文章格式**：
  - **全文笔记**：完整字幕整理为结构化文章（分段、加标题、标注时间戳）
  - **主要内容总结**：核心要点 + 金句摘录 + 时间戳目录
- 📄 **飞书文档输出**：自动创建格式化文档，支持标题、加粗、引用、表格等

## 🏗️ 架构

```
手机分享B站链接到飞书 → 飞书Bot(WebSocket) → 提取BV号
  → B站API获取视频信息+字幕
  → 无字幕? → yt-dlp下载音频 → faster-whisper转录
  → DeepSeek API: 纠错 → 格式化 → 总结
  → 飞书文档API创建格式化文档 → 回复文档链接
```

## 📋 前置准备

### 1. 飞书应用

1. 打开 [飞书开放平台](https://open.feishu.cn)，登录你的飞书账号
2. 点击「创建企业自建应用」，填写应用名称（如「视频笔记助手」）
3. 在应用页面左侧菜单：
   - **添加应用能力** → 开启「机器人」
   - **事件与回调** → 添加事件 `接收消息`（`im.message.receive_v1`）
     - 协议选择 **WebSocket**（无需公网地址）
   - **权限管理** → 添加以下权限：
     - `im:message` — 获取消息
     - `im:message:send_as_bot` — 发送消息
     - `docx:document` — 创建文档
   - **安全设置** → 复制 App ID 和 App Secret
4. 点击「创建版本」→「发布应用」
5. 在飞书客户端中搜索你的应用名称，发起对话

### 2. DeepSeek API

1. 打开 [DeepSeek 开放平台](https://platform.deepseek.com)
2. 注册并充值（最低几块钱即可）
3. 在 API Keys 页面创建 Key，复制保存

### 3. B站 Cookie (SESSDATA)

1. 在浏览器中登录 [B站](https://www.bilibili.com)
2. 按 F12 打开开发者工具
3. Application → Cookies → `bilibili.com` → 找到 `SESSDATA`
4. 复制 SESSDATA 的值

## 🚀 安装与运行

### 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 需要系统安装 ffmpeg（yt-dlp 音频转换和 Whisper 需要）
# Windows: winget install ffmpeg  或从 https://ffmpeg.org 下载
# macOS: brew install ffmpeg
# Linux: apt install ffmpeg 或 yum install ffmpeg
```

### 配置

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入你的实际值
# FEISHU_APP_ID=cli_xxxxx
# FEISHU_APP_SECRET=xxxxx
# DEEPSEEK_API_KEY=sk-xxxxx
# BILIBILI_SESSDATA=xxxxx
```

### 运行

```bash
# 检查配置
python main.py --config

# 启动飞书 Bot（WebSocket 模式，长期运行）
python main.py

# 测试模式：不通过飞书，直接处理一个视频
python main.py --test BV1xx411c7mD
```

## 📖 使用方式

1. 确保 `python main.py` 在运行
2. 在手机上打开 B站 App，复制视频链接
3. 打开飞书 → 搜索你的 Bot 名称 → 粘贴链接发送
4. Bot 回复处理进度，几分钟后返回飞书文档链接
5. 点击链接查看生成的笔记文档

## 📄 生成的文档格式

参考 B站 UP主「竖土不立」的笔记风格：

```
# 【视频笔记】{标题}

## 📺 视频信息
| 项目 | 内容 |
|------|------|
| 标题 | ... |
| UP主 | ... |
| 时长 | ... |

---

## 📋 时间戳目录
| 时间戳 | 章节内容 |
|--------|---------|
| 02:10 | 使用流程 |
| 03:52 | 图生视频 |
| ... | ... |

---

## 📝 全文笔记
### [02:10] 使用流程
详细内容（关键概念**加粗**，金句> 引用）

---

## 🎯 主要内容总结
### 核心要点
1. **要点**：说明
2. ...

### 💬 金句摘录
> "经典语句"
> —— [MM:SS]
```

## ⚙️ 配置说明

| 环境变量 | 必填 | 说明 | 默认值 |
|---------|------|------|--------|
| `FEISHU_APP_ID` | ✅ | 飞书应用 App ID | — |
| `FEISHU_APP_SECRET` | ✅ | 飞书应用 App Secret | — |
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API Key | — |
| `BILIBILI_SESSDATA` | ✅ | B站登录 Cookie | — |
| `WHISPER_MODEL` | ❌ | Whisper 模型大小 | `base` |
| `WHISPER_DEVICE` | ❌ | 运行设备 | `auto` |
| `AUDIO_COOKIE_BROWSER` | ❌ | 浏览器 cookie 来源 | `chrome` |

### Whisper 模型选择

| 模型 | 大小 | 速度 | 中文效果 | 适用场景 |
|------|------|------|----------|---------|
| `tiny` | ~1GB | 最快 | 一般 | 测试用 |
| `base` | ~2GB | 快 | 尚可 | 日常使用 |
| `small` | ~5GB | 中等 | 好 | 质量优先 |
| `medium` | ~7GB | 慢 | 很好 | 专业转录 |

## 🔧 常见问题

### Bot 收不到消息？
- 检查飞书应用是否已发布新版本
- 检查事件订阅是否配置了 `im.message.receive_v1`
- 检查权限是否包含 `im:message`

### B站字幕获取失败？
- 确认 SESSDATA cookie 未过期
- 部分老视频没有官方字幕，会自动触发 Whisper 转录

### 音频下载失败？
- 确保浏览器已登录 B站
- 关闭浏览器所有进程（任务管理器中检查），让 yt-dlp 能读取 cookie
- 或改用 cookie 文件方式

### Whisper 转录太慢？
- 尝试 `base` 或 `tiny` 模型
- 有 NVIDIA GPU 时设置 `WHISPER_DEVICE=cuda` 加速

## 📦 项目结构

```
first-cc/
├── main.py                    # 入口程序
├── config.py                  # 配置管理
├── requirements.txt           # 依赖列表
├── .env.example               # 配置模板
├── README.md                  # 本文档
├── src/
│   ├── bot/
│   │   └── feishu_bot.py      # 飞书 WebSocket Bot
│   ├── bilibili/
│   │   ├── fetcher.py          # B站视频+字幕获取
│   │   └── wbi.py              # WBI 签名算法
│   ├── audio/
│   │   ├── downloader.py       # yt-dlp 音频下载
│   │   └── transcriber.py     # faster-whisper 转录
│   ├── ai/
│   │   ├── processor.py        # DeepSeek API 处理
│   │   └── prompts.py          # Prompt 模板
│   ├── feishu/
│   │   └── doc_creator.py      # 飞书文档创建
│   └── pipeline.py             # 流程编排
```
