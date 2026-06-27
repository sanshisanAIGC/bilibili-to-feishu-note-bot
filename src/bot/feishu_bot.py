"""
飞书 Bot WebSocket 事件处理模块

使用飞书 WebSocket 方式接收消息（无需公网 URL）。
监听 im.message.receive_v1 事件，处理 B站视频链接分享。
"""

import json
import logging
import re
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1,
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from ..pipeline import VideoNotePipeline, PipelineResult
from ..bilibili.fetcher import extract_bvid, extract_url

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Bot 配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 视频链接正则（支持多种 B站链接格式）
BILIBILI_URL_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?bilibili\.com/video/(?:BV|bv)?[A-Za-z0-9]{10}[^\s]*'
)
B23_URL_PATTERN = re.compile(r'https?://b23\.tv/[A-Za-z0-9]+')
BV_PATTERN = re.compile(r'(?:BV|bv)[A-Za-z0-9]{10}')


class FeishuBot:
    """飞书 WebSocket Bot。"""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        pipeline: VideoNotePipeline,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.pipeline = pipeline
        self._ws_client: Optional[lark.ws.Client] = None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 消息处理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _extract_bilibili_link(self, text: str) -> Optional[str]:
        """从消息文本中提取 B站视频链接。"""
        # 尝试提取完整 URL
        match = BILIBILI_URL_PATTERN.search(text)
        if match:
            return match.group(0)

        # 尝试提取 b23.tv 短链接
        match = B23_URL_PATTERN.search(text)
        if match:
            return match.group(0)

        # 尝试提取 BV 号
        match = BV_PATTERN.search(text)
        if match:
            return match.group(0)

        return None

    def _send_message(self, open_id: str, text: str):
        """向用户发送文本消息。"""
        try:
            # 限制消息长度（飞书文本消息限制）
            if len(text) > 15000:
                text = text[:15000] + "\n\n... (消息过长已截断)"

            content = json.dumps({"text": text}, ensure_ascii=False)

            request = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                        .receive_id(open_id)
                        .msg_type("text")
                        .content(content)
                        .build()
                ).build()

            response = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .domain(lark.FEISHU_DOMAIN) \
                .build() \
                .im.v1.message.create(request)

            if not response.success():
                logger.error(f"发送消息失败: {response.code} - {response.msg}")

        except Exception as e:
            logger.error(f"发送消息异常: {e}")

    def _handle_message(self, data: P2ImMessageReceiveV1):
        """
        处理收到的飞书消息。

        流程：
        1. 解析消息内容
        2. 提取 B站链接
        3. 触发流水线处理
        4. 回复结果
        """
        event = data.event
        message = event.message

        # 获取发送者信息
        sender_id = event.sender.sender_id
        open_id = sender_id.open_id if sender_id else None
        chat_type = message.chat_type  # "p2p" 单聊, "group" 群聊

        if not open_id:
            logger.warning("无法获取发送者 open_id")
            return

        # 解析消息内容
        try:
            content_str = message.content
            message_content = json.loads(content_str) if isinstance(content_str, str) else content_str
        except json.JSONDecodeError:
            logger.warning(f"消息内容解析失败: {message.content}")
            return

        # 获取消息文本
        msg_type = message.msg_type
        text = ""

        if msg_type == "text":
            text = message_content.get("text", "")
        elif msg_type == "post":
            # 富文本消息，提取纯文本
            text = self._extract_text_from_post(message_content)
        else:
            # 不支持的消息类型，忽略
            return

        if not text.strip():
            return

        logger.info(f"收到消息 [{chat_type}]: {text[:100]}...")

        # 检查是否包含 B站链接
        bilibili_link = self._extract_bilibili_link(text)
        if not bilibili_link:
            return  # 不包含 B站链接，忽略

        logger.info(f"检测到 B站链接: {bilibili_link}")

        # 发送"处理中"消息
        self._send_message(open_id, "🔍 正在处理你的 B站视频链接...\n\n请稍候，这可能需要 1-5 分钟。")

        # 定义进度回调
        def progress_callback(msg: str):
            self._send_message(open_id, msg)

        # 执行流水线
        result = self.pipeline.process(
            bilibili_link,
            status_callback=progress_callback,
            user_open_id=open_id,
        )

        # 发送结果
        if result.success:
            final_msg = (
                f"✅ 视频笔记已生成！\n\n"
                f"📹 视频：{result.video_title}\n"
                f"🎙️ 字幕来源：{result.subtitle_source}\n"
                f"⏱️ 处理耗时：{result.duration_seconds:.1f} 秒\n\n"
                f"📄 飞书文档：{result.doc_url}"
            )
            self._send_message(open_id, final_msg)
        else:
            self._send_message(
                open_id,
                f"❌ 处理失败\n\n错误：{result.error_message}\n\n请检查链接是否有效，或尝试其他视频。"
            )

    def _extract_text_from_post(self, post_content: dict) -> str:
        """从飞书富文本消息中提取纯文本。"""
        text_parts = []
        try:
            content = post_content.get("content", {})
            # post 消息的内容是嵌套的段落结构
            if isinstance(content, list):
                for section in content:
                    if isinstance(section, list):
                        for item in section:
                            if isinstance(item, dict):
                                text_parts.append(item.get("text", ""))
                    elif isinstance(section, dict):
                        text_parts.append(section.get("text", ""))
        except Exception:
            pass
        return "".join(text_parts)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 启动/停止
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def start(self):
        """启动飞书 WebSocket Bot（阻塞运行）。"""
        logger.info("Starting Feishu WebSocket Bot...")
        print("=" * 60)
        print("  Feishu Bot Starting...")
        print(f"  App ID: {self.app_id[:8]}****")
        print("  Mode: WebSocket")
        print("  Feature: Bilibili link -> AI notes -> Feishu doc")
        print("=" * 60)

        # 创建事件处理器
        event_handler = (
            lark.EventDispatcherHandler.builder("", "cI33KaSEzT6w3JtpXy9yROSBIbSkJQak")
            .register_p2_im_message_receive_v1(self._handle_message)
            .build()
        )

        # 创建 WebSocket 客户端
        self._ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
        )

        try:
            self._ws_client.start()
        except KeyboardInterrupt:
            logger.info("收到停止信号")
            self.stop()

    def stop(self):
        """停止 Bot。"""
        logger.info("正在停止飞书 Bot...")
        if self._ws_client:
            self._ws_client.stop()
        logger.info("飞书 Bot 已停止")
