"""
B站视频 → 飞书文档 AI 笔记自动化系统

使用方法：
    python main.py              # 启动飞书 Bot（WebSocket 模式）
    python main.py --test BVxxx # 测试模式：用指定 BV 号测试处理流程
    python main.py --config     # 检查配置状态

依赖安装：
    pip install -r requirements.txt

首次使用：
    1. 复制 .env.example 为 .env
    2. 填入你的飞书 App ID/Secret、DeepSeek API Key、B站 SESSDATA
    3. 运行 python main.py 启动 Bot
"""

import sys
import logging
import argparse
from pathlib import Path

# 将项目根目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    BILIBILI_SESSDATA,
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    AUDIO_DOWNLOAD_DIR,
    AUDIO_COOKIE_BROWSER,
    validate_config,
    print_config,
)
from src.pipeline import VideoNotePipeline
from src.bot.feishu_bot import FeishuBot

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def create_pipeline() -> VideoNotePipeline:
    """根据配置创建处理流水线。"""
    return VideoNotePipeline(
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


def run_bot():
    """启动飞书 WebSocket Bot。"""
    # 检查配置
    missing = validate_config()
    if missing:
        print("\n❌ 缺少必要配置：")
        for m in missing:
            print(f"   - {m}")
        print("\n请在 .env 文件中配置后重试（参考 .env.example）")
        sys.exit(1)

    # 创建流水线和 Bot
    pipeline = create_pipeline()
    bot = FeishuBot(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        pipeline=pipeline,
    )

    # 启动 Bot（阻塞）
    bot.start()


def run_test(bvid: str):
    """测试模式：处理指定 BV 号并输出到控制台。"""
    print(f"\n[TEST] Processing video: {bvid}\n")

    pipeline = create_pipeline()

    def print_status(msg):
        print(f"  >> {msg}")

    result = pipeline.process(
        bvid,
        status_callback=print_status,
        user_open_id="ou_8f095b2b3e6f57cc218fd91e003b831c",
    )

    print("\n" + "=" * 60)
    if result.success:
        print(f"  [SUCCESS]")
        print(f"  Title: {result.video_title}")
        print(f"  Time: {result.duration_seconds:.1f}s")
        print(f"  Transcript: {result.doc_url}")
        print(f"  Notes: {result.notes_url}")
    else:
        print(f"  [FAILED]: {result.error_message}")
    print("=" * 60)


def run_test_with_file(subtitle_file: str, title: str = "Test Video", author: str = "Test Author", duration: int = 457):
    """测试模式：使用本地字幕文件测试 AI 处理和飞书文档创建。"""
    import json
    print(f"\n[TEST] Processing subtitle file: {subtitle_file}\n")

    with open(subtitle_file, "r", encoding="utf-8") as f:
        subtitles = json.load(f)

    print(f"Loaded {len(subtitles)} subtitle entries")

    pipeline = create_pipeline()

    def print_status(msg):
        print(f"  >> {msg}")

    # 直接调用 AI 处理
    print_status("AI processing subtitles...")
    markdown_content = pipeline.ai_processor.process_all_in_one(
        subtitles=subtitles,
        title=title,
        author=author,
        duration=duration,
        subtitle_source="Test subtitles",
    )

    print_status("AI processing done")

    # 创建飞书文档
    print_status("Creating Feishu document...")
    from src.feishu.doc_creator import create_video_note_document

    doc_title = f"【视频笔记】{title}"
    doc_url = create_video_note_document(
        app_id=pipeline.feishu_app_id,
        app_secret=pipeline.feishu_app_secret,
        title=doc_title,
        markdown_content=markdown_content,
    )

    print("\n" + "=" * 60)
    print(f"  [SUCCESS]")
    print(f"  Title: {title}")
    print(f"  Document: {doc_url}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="B站视频 → 飞书文档 AI 笔记自动化系统"
    )
    parser.add_argument(
        "--test",
        metavar="BVID",
        help="测试模式：处理指定的 B站视频 BV 号或链接",
    )
    parser.add_argument(
        "--subtitle-file",
        metavar="FILE",
        help="使用本地字幕 JSON 文件测试 AI 处理和飞书文档创建",
    )
    parser.add_argument(
        "--title",
        default="学生时代最重要的三次选择是什么？",
        help="视频标题（配合 --subtitle-file 使用）",
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="检查配置状态",
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="测试时使用三阶段流水线模式（适合长视频）",
    )

    args = parser.parse_args()

    if args.config:
        print_config()
        return

    if args.subtitle_file:
        run_test_with_file(args.subtitle_file, title=args.title)
        return

    if args.test:
        run_test(args.test)
        return

    # 默认：启动 Bot
    run_bot()


if __name__ == "__main__":
    main()
