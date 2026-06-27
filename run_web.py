"""启动 Web 界面 - 手机浏览器可访问"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()

from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    BILIBILI_SESSDATA,
    WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    AUDIO_DOWNLOAD_DIR, AUDIO_COOKIE_BROWSER,
)
from src.pipeline import VideoNotePipeline
from src.bot.web_interface import start

pipeline = VideoNotePipeline(
    bilibili_sessdata=BILIBILI_SESSDATA,
    deepseek_api_key=DEEPSEEK_API_KEY,
    deepseek_base_url=DEEPSEEK_BASE_URL,
    deepseek_model=DEEPSEEK_MODEL,
    whisper_model=WHISPER_MODEL,
    whisper_device=WHISPER_DEVICE,
    whisper_compute_type=WHISPER_COMPUTE_TYPE,
    audio_download_dir=AUDIO_DOWNLOAD_DIR,
    audio_cookie_browser=AUDIO_COOKIE_BROWSER,
    feishu_app_id=FEISHU_APP_ID,
    feishu_app_secret=FEISHU_APP_SECRET,
)

start(pipeline)
