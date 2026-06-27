"""
群聊轮询 Bot - 监听群里 @Bot 的 B站链接，自动处理回复
"""
import sys, os, json, re, time, logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv; load_dotenv()

import httpx

from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    BILIBILI_SESSDATA,
    WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    AUDIO_DOWNLOAD_DIR, AUDIO_COOKIE_BROWSER,
)
from src.pipeline import VideoNotePipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("poll_bot")

BOT_OPEN_ID = "ou_20041c6d8ce90f1fa8f7f0e24962862f"
POLL_INTERVAL = 5  # seconds

BVID_PATTERN = re.compile(r'(?:BV|bv)[A-Za-z0-9]{10}')
URL_PATTERN = re.compile(r'https?://(?:www\.)?bilibili\.com/video/(?:BV)?[A-Za-z0-9]{10}[^\s]*')
B23_PATTERN = re.compile(r'https?://b23\.tv/[A-Za-z0-9]+')


def get_token():
    r = httpx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    return r.json()["tenant_access_token"]


def resolve_b23(url):
    try:
        r = httpx.get(url, follow_redirects=True, timeout=10)
        return str(r.url)
    except:
        return url


def extract_link(text):
    for pat in [URL_PATTERN, B23_PATTERN, BVID_PATTERN]:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def send_to_chat(token, chat_id, text):
    r = httpx.post(
        f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        content=json.dumps({
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }, ensure_ascii=False),
        timeout=10,
    )
    return r.json().get("code") == 0


def main():
    print("=" * 60)
    print("  Group Poll Bot Starting...")
    print(f"  Bot ID: {BOT_OPEN_ID[:20]}...")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print("=" * 60)

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

    processed_msg_ids = set()

    while True:
        try:
            token = get_token()

            # Get all chats
            r = httpx.get(
                "https://open.feishu.cn/open-apis/im/v1/chats",
                headers={"Authorization": f"Bearer {token}"},
                params={"user_id_type": "open_id", "page_size": 20},
                timeout=10,
            )
            chats = r.json().get("data", {}).get("items", [])

            for chat in chats:
                chat_id = chat.get("chat_id", "")
                if not chat_id:
                    continue

                # Get recent messages
                r2 = httpx.get(
                    "https://open.feishu.cn/open-apis/im/v1/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "container_id_type": "chat",
                        "container_id": chat_id,
                        "page_size": 5,
                        "sort_type": "ByCreateTimeDesc",
                    },
                    timeout=10,
                )
                msgs = r2.json().get("data", {}).get("items", [])

                for msg in msgs:
                    msg_id = msg.get("message_id", "")
                    if msg_id in processed_msg_ids:
                        continue

                    mentions = msg.get("mentions", [])
                    mentioned = any(
                        m.get("id", "") == BOT_OPEN_ID for m in mentions
                    )

                    if not mentioned:
                        continue

                    # Extract text
                    content_str = msg.get("body", {}).get("content", "{}")
                    try:
                        ct = json.loads(content_str)
                        text = ct.get("text", "")
                    except:
                        text = ""

                    if not text:
                        continue

                    link = extract_link(text)
                    if not link:
                        continue

                    # Mark as processed
                    processed_msg_ids.add(msg_id)

                    chat_name = chat.get("name", "group")
                    logger.info(f"Processing @bot message in [{chat_name}]: {link[:60]}")

                    # Resolve b23 links
                    if "b23.tv" in link:
                        link = resolve_b23(link)

                    # Brief acknowledgment
                    send_to_chat(token, chat_id, "收到，正在总结...")

                    # Process silently
                    result = pipeline.process(link)

                    if result.success:
                        send_to_chat(
                            token,
                            chat_id,
                            f"视频笔记已生成！\n\n"
                            f"视频：{result.video_title}\n"
                            f"耗时：{result.duration_seconds:.0f}秒\n\n"
                            f"全文实录（带时间戳）：\n{result.doc_url}\n\n"
                            f"结构化笔记：\n{result.notes_url}",
                        )
                    else:
                        send_to_chat(
                            token,
                            chat_id,
                            f"处理失败：{result.error_message}",
                        )

        except Exception as e:
            logger.error(f"Poll cycle error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
