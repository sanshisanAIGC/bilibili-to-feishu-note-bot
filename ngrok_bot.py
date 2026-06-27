"""
启动 Flask HTTP 回调服务器 + ngrok 隧道
飞书事件会通过 ngrok 公网 URL 推送到本地 Flask 服务器
"""
import sys, os, json, logging, re
from threading import Thread

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, Response
from pyngrok import ngrok

from src.pipeline import VideoNotePipeline
from src.feishu.doc_creator import send_feishu_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ngrok_bot")

app = Flask(__name__)
pipeline = None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 消息处理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BILIBILI_URL = re.compile(
    r'(?:https?://)?(?:www\.)?bilibili\.com/video/(?:BV|bv)?[A-Za-z0-9]{10}[^\s]*'
)
B23_URL = re.compile(r'https?://b23\.tv/[A-Za-z0-9]+')
BV_PATTERN = re.compile(r'(?:BV|bv)[A-Za-z0-9]{10}')


def extract_bilibili_link(text: str):
    for pat in [BILIBILI_URL, B23_URL, BV_PATTERN]:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


@app.route("/webhook", methods=["POST"])
def webhook():
    """接收飞书事件回调"""
    try:
        body = request.get_json(force=True)
        logger.info(f"Webhook received: {json.dumps(body, ensure_ascii=False)[:500]}")

        # 处理 URL 验证
        if body.get("type") == "url_verification":
            challenge = body.get("challenge", "")
            token = body.get("token", "")
            logger.info(f"URL verification: token={token}")
            return Response(
                json.dumps({"challenge": challenge}),
                content_type="application/json"
            )

        # 处理事件
        event = body.get("event", {})
        event_type = event.get("type", "")

        if event_type == "im.message.receive_v1":
            msg = event.get("message", {})
            msg_type = msg.get("msg_type", "")
            content_str = msg.get("content", "{}")
            try:
                content = json.loads(content_str)
            except:
                content = {}
            text = content.get("text", "")

            sender_id = event.get("sender", {}).get("sender_id", {})
            open_id = sender_id.get("open_id", "")

            logger.info(f"Message from {open_id}: {text[:100]}")

            if open_id and text:
                link = extract_bilibili_link(text)
                if link:
                    logger.info(f"Processing B站 link: {link}")
                    Thread(target=process_video, args=(link, open_id)).start()

                # 不管有没有链接都回复一下，让用户知道 bot 在线
                if not hasattr(handle_message, 'replied'):
                    handle_message.replied = True
                    send_feishu_message(
                        app_id=FEISHU_APP_ID,
                        app_secret=FEISHU_APP_SECRET,
                        open_id=open_id,
                        text="已收到消息！如果你发送了B站链接，正在处理中..."
                    )

        return Response("ok", content_type="text/plain")

    except Exception as e:
        logger.exception(f"Webhook error: {e}")
        return Response("error", content_type="text/plain", status=500)


def process_video(link: str, open_id: str):
    """处理视频链接"""
    try:
        def progress(msg):
            try:
                send_feishu_message(
                    app_id=FEISHU_APP_ID,
                    app_secret=FEISHU_APP_SECRET,
                    open_id=open_id,
                    text=msg,
                )
            except:
                pass

        pipeline.process(link, status_callback=progress, user_open_id=open_id)
    except Exception as e:
        logger.exception(f"Process error: {e}")
        send_feishu_message(
            app_id=FEISHU_APP_ID,
            app_secret=FEISHU_APP_SECRET,
            open_id=open_id,
            text=f"处理失败：{e}",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    from config import (
        FEISHU_APP_ID, FEISHU_APP_SECRET,
        DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
        BILIBILI_SESSDATA,
        WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
        AUDIO_DOWNLOAD_DIR, AUDIO_COOKIE_BROWSER,
    )

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

    # 启动 ngrok 隧道
    try:
        public_url = ngrok.connect(7777).public_url
        webhook_url = f"{public_url}/webhook"
        print("=" * 60)
        print("  NGROK TUNNEL ACTIVE")
        print(f"  Webhook URL: {webhook_url}")
        print("=" * 60)
        print()
        print("  Copy this URL to Feishu:")
        print(f"  https://open.feishu.cn/app/cli_a4a505fe56ff500d")
        print(f"  -> 事件与回调 -> 请求网址: {webhook_url}")
        print()
    except Exception as e:
        logger.warning(f"ngrok failed: {e}")
        print("ngrok not available. Running Flask on localhost only.")
        webhook_url = f"http://localhost:7777/webhook"

    # 启动 Flask
    print("Starting Flask server on port 7777...")
    app.run(host="0.0.0.0", port=7777, debug=False)
