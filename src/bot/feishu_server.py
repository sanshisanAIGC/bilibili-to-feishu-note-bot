"""
飞书 HTTP 回调服务器
使用 Flask + lark-oapi adapter 接收事件，不再依赖 WebSocket。
"""
import json
import logging
from flask import Flask, request, Response

from lark_oapi.adapter.flask import parse_req, parse_resp
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from ..pipeline import VideoNotePipeline

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 全局变量，由 start() 设置
pipeline: VideoNotePipeline = None
VERIFICATION_TOKEN = ""


@app.route("/webhook", methods=["POST"])
def webhook():
    """接收飞书事件回调"""
    data = request.get_data(as_text=True)
    logger.info(f"收到回调: {data[:200]}")

    # 使用 lark-oapi 解析请求
    req = parse_req()

    # 处理事件
    resp = EVENT_HANDLER.do(req)

    return parse_resp(resp)


# 事件处理器
EVENT_HANDLER = None


def handle_message(data: P2ImMessageReceiveV1):
    """处理收到的消息"""
    event = data.event
    message = event.message
    sender = event.sender

    open_id = sender.sender_id.open_id if sender and sender.sender_id else None
    if not open_id:
        logger.warning("无法获取发送者 open_id")
        return

    msg_type = message.msg_type
    try:
        content = json.loads(message.content) if isinstance(message.content, str) else message.content
    except json.JSONDecodeError:
        return

    text = content.get("text", "")
    logger.info(f"收到消息 [{msg_type}]: {text[:100]}")

    if not text.strip():
        return

    # 提取 B站链接
    from ..bilibili.fetcher import extract_bvid, extract_url
    import re
    BILIBILI_URL = re.compile(r'(?:https?://)?(?:www\.)?bilibili\.com/video/(?:BV)?[A-Za-z0-9]{10}[^\s]*')
    B23_URL = re.compile(r'https?://b23\.tv/[A-Za-z0-9]+')
    BV_PATTERN = re.compile(r'(?:BV|bv)[A-Za-z0-9]{10}')

    link = None
    for pat in [BILIBILI_URL, B23_URL, BV_PATTERN]:
        m = pat.search(text)
        if m:
            link = m.group(0)
            break

    if not link:
        return

    logger.info(f"检测到 B站链接: {link}")

    # 发送处理中消息
    from ..feishu.doc_creator import send_feishu_message, FeishuDocClient
    send_feishu_message(
        app_id=pipeline.feishu_app_id,
        app_secret=pipeline.feishu_app_secret,
        open_id=open_id,
        text="收到链接，正在处理...",
    )

    # 执行流水线
    def progress(msg):
        try:
            send_feishu_message(
                app_id=pipeline.feishu_app_id,
                app_secret=pipeline.feishu_app_secret,
                open_id=open_id,
                text=msg,
            )
        except Exception as e:
            logger.warning(f"Progress notification failed: {e}")

    result = pipeline.process(link, status_callback=progress, user_open_id=open_id)

    if not result.success:
        send_feishu_message(
            app_id=pipeline.feishu_app_id,
            app_secret=pipeline.feishu_app_secret,
            open_id=open_id,
            text=f"处理失败：{result.error_message}",
        )


def start(p: VideoNotePipeline, app_id: str, app_secret: str,
          verification_token: str = "", port: int = 7777):
    """启动 HTTP 回调服务器"""
    global pipeline, EVENT_HANDLER

    pipeline = p

    EVENT_HANDLER = (
        EventDispatcherHandler.builder("", verification_token)
        .register_p2_im_message_receive_v1(handle_message)
        .build()
    )

    print("=" * 60)
    print("  Feishu HTTP Callback Server Starting...")
    print(f"  App ID: {app_id[:8]}****")
    print(f"  Mode: HTTP Webhook")
    print(f"  Port: {port}")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=False)
