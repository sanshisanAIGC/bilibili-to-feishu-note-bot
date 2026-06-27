FROM python:3.11-slim

# 安装 ffmpeg（音频处理需要）
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 下载 Whisper base 模型（避免首次运行下载）
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')" || true

# 暴露端口（Web 界面用）
EXPOSE 7777

# 启动群聊轮询 Bot
CMD ["python", "poll_bot.py"]
