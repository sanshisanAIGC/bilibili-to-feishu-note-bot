"""
B站视频信息与字幕获取模块

支持两种获取方式：
1. 直接调用 B站 API 获取官方 CC 字幕（推荐）
2. 通过 yt-dlp 获取字幕（备用）

返回统一的字幕数据格式：list[dict] 其中 dict = {from, to, content}
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from .wbi import enc_wbi, COMMON_HEADERS, clear_wbi_cache

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 数据模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class SubtitleEntry:
    """单条字幕"""
    from_time: float   # 开始时间（秒）
    to_time: float      # 结束时间（秒）
    content: str        # 字幕文本


@dataclass
class VideoInfo:
    """B站视频信息"""
    bvid: str
    aid: int
    cid: int
    title: str
    description: str = ""
    duration: int = 0        # 总时长（秒）
    cover_url: str = ""
    author: str = ""
    subtitles: list[SubtitleEntry] = field(default_factory=list)
    subtitle_source: str = ""  # "bilibili_official", "yt_dlp", "none"
    pages: list[dict] = field(default_factory=list)  # 多P信息


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BV 号提取与验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_BV_PATTERN = re.compile(r'(?:BV|bv)([A-Za-z0-9]{10})')
_B23_PATTERN = re.compile(r'b23\.tv/[A-Za-z0-9]+')
_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?bilibili\.com/video/(?:BV|bv)?([A-Za-z0-9]{10})'
)


def extract_bvid(text: str) -> Optional[str]:
    """从任意文本中提取 B站视频 BV 号。"""
    # 尝试完整 URL
    match = _URL_PATTERN.search(text)
    if match:
        return f"BV{match.group(1)}" if not match.group(0).upper().startswith("BV") else match.group(1)

    # 尝试纯 BV 号
    match = _BV_PATTERN.search(text)
    if match:
        return match.group(0)

    return None


def extract_url(text: str) -> Optional[str]:
    """从文本中提取 B站视频链接（b23.tv 短链或完整 URL）。"""
    # b23.tv 短链
    match = _B23_PATTERN.search(text)
    if match:
        return match.group(0)

    # 完整 URL
    url_pattern = re.compile(
        r'https?://(?:www\.)?bilibili\.com/video/(?:BV|bv)?[A-Za-z0-9]{10}[^\s]*'
    )
    match = url_pattern.search(text)
    if match:
        return match.group(0)

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B站 API 字幕获取
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_cookies(sessdata: str) -> dict:
    """构建 B站请求所需的 Cookie。"""
    cookies = {}
    if sessdata:
        cookies["SESSDATA"] = sessdata
    return cookies


def get_video_info(bvid: str, sessdata: str = "") -> dict:
    """
    获取 B站视频基本信息。

    Args:
        bvid: 视频 BV 号
        sessdata: B站 SESSDATA cookie

    Returns:
        视频信息字典 {aid, cid, title, description, duration, cover, author, pages}
    """
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    cookies = _build_cookies(sessdata)

    with httpx.Client(timeout=30, headers=COMMON_HEADERS, cookies=cookies) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"获取视频信息失败: {data.get('message', '未知错误')}")

    video_data = data["data"]
    return {
        "aid": video_data["aid"],
        "cid": video_data["cid"],
        "bvid": video_data["bvid"],
        "title": video_data["title"],
        "description": video_data.get("desc", ""),
        "duration": video_data.get("duration", 0),
        "cover": video_data.get("pic", ""),
        "author": video_data.get("owner", {}).get("name", ""),
        "pages": video_data.get("pages", []),
        "videos": video_data.get("videos", 1),  # 分P数
    }


def fetch_subtitles(aid: int, cid: int, sessdata: str = "") -> list[SubtitleEntry]:
    """
    通过 B站 API 获取视频的官方字幕。

    Args:
        aid: 视频 aid
        cid: 视频分P cid
        sessdata: B站 SESSDATA cookie

    Returns:
        字幕条目列表
    """
    cookies = _build_cookies(sessdata)

    with httpx.Client(timeout=30, headers=COMMON_HEADERS, cookies=cookies) as client:
        subtitle_list = None

        # ━━━━━ 方式 1：WBI 签名 API ━━━━━
        try:
            clear_wbi_cache()  # 清除无 cookie 的缓存，用 SESSDATA 重新获取
            params = enc_wbi({"aid": aid, "cid": cid}, sessdata=sessdata)
            url = "https://api.bilibili.com/x/player/wbi/v2"

            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") == 0:
                subtitle_data = data.get("data", {}).get("subtitle", {})
                subtitle_list = subtitle_data.get("subtitles", [])
            else:
                logger.debug(f"WBI API: {data.get('message')}")
        except Exception as e:
            logger.debug(f"WBI API 失败: {e}，尝试旧版 API...")

        # ━━━━━ 方式 2：旧版 API（无需 WBI 签名，部分视频可用）━━━━━
        if not subtitle_list:
            try:
                url = f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}"
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

                if data.get("code") == 0:
                    subtitle_data = data.get("data", {}).get("subtitle", {})
                    subtitle_list = subtitle_data.get("subtitles", [])
                    if subtitle_list:
                        logger.info("通过旧版 API 获取到字幕列表")
                else:
                    logger.debug(f"旧版 API: {data.get('message')}")
            except Exception as e:
                logger.debug(f"旧版 API 也失败: {e}")

        if not subtitle_list:
            logger.info("该视频没有官方字幕（所有 API 均未返回字幕）")
            return []

        # 优先选择中文字幕
        selected = None
        for sub in subtitle_list:
            if sub.get("lan") in ("zh-Hans", "zh-CN", "zh", "ai-zh"):
                selected = sub
                break

        if selected is None:
            selected = subtitle_list[0]  # 取第一个可用字幕

        subtitle_url = selected.get("subtitle_url", "")
        if not subtitle_url:
            return []

        # 第三步：下载并解析字幕 JSON
        if subtitle_url.startswith("//"):
            subtitle_url = f"https:{subtitle_url}"

        resp = client.get(subtitle_url)
        resp.raise_for_status()
        subtitle_json = resp.json()

        # 解析字幕条目
        entries = []
        for item in subtitle_json.get("body", []):
            entries.append(SubtitleEntry(
                from_time=item.get("from", 0),
                to_time=item.get("to", 0),
                content=item.get("content", "")
            ))

        return entries


def fetch_video_with_subtitles(url_or_bvid: str, sessdata: str = "") -> VideoInfo:
    """
    一键获取视频信息 + 字幕。主入口函数。

    Args:
        url_or_bvid: B站视频 URL 或 BV 号
        sessdata: B站 SESSDATA cookie

    Returns:
        VideoInfo 对象，包含视频信息和字幕
    """
    # 提取 BV 号
    bvid = extract_bvid(url_or_bvid)
    if not bvid:
        # 尝试作为短链接处理
        extracted_url = extract_url(url_or_bvid)
        if extracted_url:
            # 需要先解析短链接（这里简化为提取 BV 号）
            bvid = extract_bvid(extracted_url)
        if not bvid:
            raise ValueError(f"无法从输入中提取 B站视频 BV 号: {url_or_bvid}")

    logger.info(f"获取视频信息: {bvid}")

    # 获取视频信息
    info = get_video_info(bvid, sessdata)

    # 尝试获取字幕（遍历所有分P）
    all_subtitles = []
    pages = info["pages"]
    if not pages:
        pages = [{"cid": info["cid"]}]

    subtitle_source = "bilibili_official"

    for page in pages:
        page_cid = page.get("cid", info["cid"])
        try:
            subs = fetch_subtitles(info["aid"], page_cid, sessdata)
            all_subtitles.extend(subs)
        except Exception as e:
            logger.warning(f"获取分P cid={page_cid} 字幕失败: {e}")

    if not all_subtitles:
        subtitle_source = "none"
        logger.info("未获取到任何字幕，需要使用 Whisper 转录")

    video_info = VideoInfo(
        bvid=info["bvid"],
        aid=info["aid"],
        cid=info["cid"],
        title=info["title"],
        description=info.get("description", ""),
        duration=info.get("duration", 0),
        cover_url=info.get("cover", ""),
        author=info.get("author", ""),
        subtitles=all_subtitles,
        subtitle_source=subtitle_source,
        pages=pages,
    )

    logger.info(
        f"视频: {video_info.title} | "
        f"分P: {len(pages)} | "
        f"字幕: {len(all_subtitles)}条 | "
        f"来源: {subtitle_source}"
    )

    return video_info
