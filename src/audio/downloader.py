"""
B站视频音频下载模块

使用 yt-dlp 下载视频音频，支持通过浏览器 cookie 认证。
"""

import logging
import os
from pathlib import Path
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)


def download_audio(
    url: str,
    output_dir: str = "./downloads",
    cookie_browser: Optional[str] = None,
    cookiefile: Optional[str] = None,
) -> dict:
    """
    下载 B站视频的音频。

    Args:
        url: B站视频 URL 或 BV 号
        output_dir: 输出目录
        cookie_browser: 浏览器名称（如 chrome, firefox）用于读取 cookie
        cookiefile: Cookie 文件路径（与 cookie_browser 二选一）

    Returns:
        dict: {
            "title": 视频标题,
            "duration": 时长（秒）,
            "filepath": 下载的音频文件路径,
            "ext": 文件扩展名
        }
    """
    os.makedirs(output_dir, exist_ok=True)

    # 输出模板
    outtmpl = str(Path(output_dir) / "%(title)s.%(ext)s")

    # yt-dlp 配置
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": False,
        "no_warnings": False,
        "extract_flat": False,

        # 音频后处理
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],

        # 只下载音频，不下载视频
        "extractaudio": True,
    }

    # Cookie 配置
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile
        logger.info(f"使用 cookie 文件: {cookiefile}")
    elif cookie_browser:
        ydl_opts["cookiesfrombrowser"] = (cookie_browser,)
        logger.info(f"使用浏览器 cookie: {cookie_browser}")

    # 如果不是完整 URL，构造完整的 B站 URL
    if not url.startswith("http"):
        url = f"https://www.bilibili.com/video/{url}"

    logger.info(f"开始下载音频: {url}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 先获取信息（不下载）
            info = ydl.extract_info(url, download=False)

            title = info.get("title", "unknown")
            duration = info.get("duration", 0)
            ext = "mp3"

            logger.info(f"视频: {title} | 时长: {duration}s | 分P数: {info.get('n_entries', 1)}")

            # 下载
            ydl.download([url])

        # 查找下载的文件
        download_dir = Path(output_dir)
        # yt-dlp 可能会修改文件名，查找最近创建的文件
        audio_files = sorted(
            download_dir.glob("*.mp3"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not audio_files:
            audio_files = sorted(
                download_dir.glob("*.*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

        filepath = str(audio_files[0]) if audio_files else ""

        result = {
            "title": title,
            "duration": duration,
            "filepath": filepath,
            "ext": ext,
        }

        logger.info(f"音频下载完成: {filepath}")
        return result

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "login" in error_msg.lower() or "cookie" in error_msg.lower():
            raise RuntimeError(
                "B站要求登录才能下载。请确保：\n"
                "1. 浏览器已登录 B站\n"
                "2. 浏览器已完全关闭（任务管理器中无进程残留）\n"
                "3. 或使用 cookie 文件方式"
            ) from e
        raise RuntimeError(f"yt-dlp 下载失败: {e}") from e


def download_subtitles(
    url: str,
    output_dir: str = "./downloads",
    cookie_browser: Optional[str] = None,
    cookiefile: Optional[str] = None,
) -> list[dict]:
    """
    使用 yt-dlp 下载 B站视频字幕（作为首选 fallback）。

    Args:
        url: B站视频 URL 或 BV 号
        output_dir: 输出目录
        cookie_browser: 浏览器名称
        cookiefile: Cookie 文件路径

    Returns:
        list[dict]: [{"from": float, "to": float, "content": str}, ...]
    """
    import json
    os.makedirs(output_dir, exist_ok=True)

    outtmpl = str(Path(output_dir) / "%(title)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["zh-Hans", "zh-CN", "zh", "ai-zh", "en"],
        "skip_download": True,   # 只下载字幕，不下载视频/音频
        "convertsubs": "json",   # 但 yt-dlp 默认转 srt，我们用 extract_info 取原始数据
    }

    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile
    elif cookie_browser:
        ydl_opts["cookiesfrombrowser"] = (cookie_browser,)

    if not url.startswith("http"):
        url = f"https://www.bilibili.com/video/{url}"

    logger.info(f"yt-dlp 尝试获取字幕: {url}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # 从 info 中提取字幕
        subtitles = info.get("subtitles", {})
        auto_subtitles = info.get("automatic_captions", {})

        # 合并手动字幕和自动字幕
        all_subs = {}
        all_subs.update(subtitles)
        all_subs.update(auto_subtitles)

        # 优先中文
        preferred_langs = ["zh-Hans", "zh-CN", "zh", "ai-zh", "zh-Hant", "en"]
        selected_subs = None

        for lang in preferred_langs:
            if lang in all_subs and all_subs[lang]:
                selected_subs = all_subs[lang]
                break

        if not selected_subs and all_subs:
            first_key = next(iter(all_subs))
            selected_subs = all_subs[first_key]

        if not selected_subs:
            logger.info("yt-dlp 未找到任何字幕")
            return []

        # 字幕格式: [{"ext": "json", "url": "...", "name": "..."}, ...]
        # 选择一个 JSON 格式的字幕
        sub_info = None
        for s in selected_subs:
            if s.get("ext") in ("json", "json3"):
                sub_info = s
                break
        if not sub_info:
            sub_info = selected_subs[0]

        # 下载字幕内容
        sub_url = sub_info.get("url", "")
        if not sub_url:
            return []

        import httpx
        resp = httpx.get(sub_url, timeout=30)
        resp.raise_for_status()
        sub_data = resp.json()

        # 解析字幕（兼容多种格式）
        entries = []

        # 格式1: B站 JSON {body: [{from, to, content}]}
        if "body" in sub_data:
            for item in sub_data["body"]:
                entries.append({
                    "from": item.get("from", 0),
                    "to": item.get("to", 0),
                    "content": item.get("content", ""),
                })
        # 格式2: events 数组 (JSON3)
        elif "events" in sub_data:
            for ev in sub_data.get("events", []):
                t_start = ev.get("tStartMs", 0) / 1000.0
                t_end = (ev.get("tStartMs", 0) + ev.get("dDurationMs", 0)) / 1000.0
                segs = ev.get("segs", [])
                text = "".join(s.get("utf8", "") for s in segs)
                entries.append({
                    "from": t_start,
                    "to": t_end,
                    "content": text,
                })

        logger.info(f"yt-dlp 获取到 {len(entries)} 条字幕")
        return entries

    except Exception as e:
        logger.warning(f"yt-dlp 字幕下载失败: {e}")
        return []


def download_audio_for_bvid(
    bvid: str,
    output_dir: str = "./downloads",
    cookie_browser: Optional[str] = None,
) -> dict:
    """通过 BV 号下载音频的便捷函数。"""
    url = f"https://www.bilibili.com/video/{bvid}"
    return download_audio(url, output_dir, cookie_browser)


def cleanup_audio(filepath: str) -> bool:
    """删除下载的音频文件。"""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"已清理音频文件: {filepath}")
            return True
    except OSError as e:
        logger.warning(f"清理音频文件失败: {e}")
    return False
