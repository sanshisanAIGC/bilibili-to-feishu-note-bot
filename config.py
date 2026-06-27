"""
B站视频 → 飞书文档 AI 笔记自动化系统 - 配置管理
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent / ".env")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 飞书配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DeepSeek API 配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B站配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BILIBILI_SESSDATA = os.getenv("BILIBILI_SESSDATA", "")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Whisper 配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny, base, small, medium, large
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # auto, cpu, cuda
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "auto")  # auto, float16, int8

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 音频下载配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUDIO_DOWNLOAD_DIR = os.getenv("AUDIO_DOWNLOAD_DIR", str(Path(__file__).parent / "downloads"))
AUDIO_COOKIE_BROWSER = os.getenv("AUDIO_COOKIE_BROWSER", "chrome")  # chrome, firefox, edge


def validate_config() -> list[str]:
    """验证必要的配置是否完整，返回缺失的配置项列表。"""
    missing = []

    if not FEISHU_APP_ID:
        missing.append("FEISHU_APP_ID")
    if not FEISHU_APP_SECRET:
        missing.append("FEISHU_APP_SECRET")
    if not DEEPSEEK_API_KEY:
        missing.append("DEEPSEEK_API_KEY")
    if not BILIBILI_SESSDATA:
        missing.append("BILIBILI_SESSDATA (B站 cookie，用于获取字幕)")

    return missing


def print_config():
    """打印当前配置状态（隐藏敏感信息）。"""
    print("=" * 50)
    print("  B站 → 飞书 AI笔记系统 - 配置状态")
    print("=" * 50)

    items = [
        ("FEISHU_APP_ID", FEISHU_APP_ID, True),
        ("FEISHU_APP_SECRET", FEISHU_APP_SECRET, False),
        ("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY, False),
        ("DEEPSEEK_MODEL", DEEPSEEK_MODEL, True),
        ("BILIBILI_SESSDATA", BILIBILI_SESSDATA, False),
        ("WHISPER_MODEL", WHISPER_MODEL, True),
        ("WHISPER_DEVICE", WHISPER_DEVICE, True),
        ("AUDIO_DOWNLOAD_DIR", AUDIO_DOWNLOAD_DIR, True),
    ]

    for name, value, show_full in items:
        if not value:
            status = "[MISSING]"
        elif show_full:
            status = f"[OK] {value}"
        else:
            masked = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
            status = f"[OK] {masked}"
        print(f"  {name:25s}: {status}")

    missing = validate_config()
    if missing:
        print(f"\n  [WARN] Missing config: {', '.join(missing)}")
        print("  Please edit .env file to configure")
    else:
        print(f"\n  [OK] All required configs are ready")


if __name__ == "__main__":
    print_config()
