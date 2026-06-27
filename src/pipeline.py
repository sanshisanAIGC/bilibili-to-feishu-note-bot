"""
主流程编排模块

协调整个处理流水线：
1. 接收 B站视频链接
2. 获取字幕（优先 B站官方字幕 → fallback Whisper 转录）
3. AI 处理（纠错 + 格式化 + 总结）
4. 创建飞书文档
5. 返回文档链接
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

from .bilibili.fetcher import fetch_video_with_subtitles, VideoInfo, SubtitleEntry
from .ai.processor import AITextProcessor
from .feishu.doc_creator import create_video_note_document

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 进度回调
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

StatusCallback = Callable[[str], None]


@dataclass
class PipelineResult:
    """流水线处理结果"""
    success: bool
    doc_url: str = ""           # transcript doc URL
    notes_url: str = ""         # structured notes doc URL
    video_title: str = ""
    subtitle_source: str = ""
    error_message: str = ""
    duration_seconds: float = 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 流水线
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class VideoNotePipeline:
    """
    B站视频 → 飞书文档笔记 处理流水线。
    """

    def __init__(
        self,
        # B站
        bilibili_sessdata: str = "",
        # AI
        deepseek_api_key: str = "",
        deepseek_base_url: str = "https://api.deepseek.com",
        deepseek_model: str = "deepseek-chat",
        # Whisper
        whisper_model: str = "base",
        whisper_device: str = "auto",
        whisper_compute_type: str = "auto",
        # 音频下载
        audio_download_dir: str = "./downloads",
        audio_cookie_browser: str = "chrome",
        # 飞书
        feishu_app_id: str = "",
        feishu_app_secret: str = "",
    ):
        self.bilibili_sessdata = bilibili_sessdata

        # AI 处理器（延迟初始化）
        self.ai_processor = AITextProcessor(
            api_key=deepseek_api_key,
            base_url=deepseek_base_url,
            model=deepseek_model,
        )

        # Whisper 配置
        self.whisper_model = whisper_model
        self.whisper_device = whisper_device
        self.whisper_compute_type = whisper_compute_type

        # 音频下载配置
        self.audio_download_dir = audio_download_dir
        self.audio_cookie_browser = audio_cookie_browser

        # 飞书配置
        self.feishu_app_id = feishu_app_id
        self.feishu_app_secret = feishu_app_secret

    def process(
        self,
        url_or_bvid: str,
        status_callback: Optional[StatusCallback] = None,
        use_pipeline_mode: bool = False,
        user_open_id: str = "",
    ) -> PipelineResult:
        """
        处理一个 B站视频链接，生成飞书笔记文档。

        Args:
            url_or_bvid: B站视频 URL 或 BV 号
            status_callback: 进度回调函数（用于通知用户处理进度）
            use_pipeline_mode: 是否使用三阶段流水线（适合长视频）

        Returns:
            PipelineResult
        """
        start_time = time.time()

        def notify(msg: str):
            logger.info(msg)
            if status_callback:
                status_callback(msg)

        try:
            # ━━━━━━ Step 1: Get video info and subtitles ━━━━━━
            notify("Fetching video info and subtitles...")

            video_info = fetch_video_with_subtitles(
                url_or_bvid,
                sessdata=self.bilibili_sessdata,
            )

            notify(
                f"Video: {video_info.title} | "
                f"Author: {video_info.author} | "
                f"Duration: {video_info.duration // 60}m{video_info.duration % 60}s"
            )

            subtitle_source = video_info.subtitle_source
            raw_subtitles = []

            if video_info.subtitles:
                # 转为字典格式方便处理
                raw_subtitles = [
                    {"from": s.from_time, "to": s.to_time, "content": s.content}
                    for s in video_info.subtitles
                ]
                notify(f"Got {len(raw_subtitles)} Bilibili official subtitles")
            else:
                # ━━━━━━ Step 2a (fallback 1): yt-dlp 字幕下载 ━━━━━━
                notify("No official subtitles, trying yt-dlp subtitle download...")

                raw_subtitles = []
                try:
                    from .audio.downloader import download_subtitles

                    raw_subtitles = download_subtitles(
                        video_info.bvid,
                        output_dir=self.audio_download_dir,
                        cookie_browser=self.audio_cookie_browser,
                    )

                    if raw_subtitles:
                        subtitle_source = "yt-dlp subtitle download"
                        notify(f"Got {len(raw_subtitles)} subtitles via yt-dlp")
                except Exception as e:
                    logger.warning(f"yt-dlp subtitle download failed: {e}")

                # ━━━━━━ Step 2b (fallback 2): 音频 + Whisper ━━━━━━
                if not raw_subtitles:
                    notify("yt-dlp subtitles failed, falling back to audio + Whisper...")

                    try:
                        from .audio.downloader import download_audio_for_bvid
                        from .audio.transcriber import transcribe_audio

                        # 下载音频
                        notify("Downloading audio...")
                        audio_result = download_audio_for_bvid(
                            video_info.bvid,
                            output_dir=self.audio_download_dir,
                            cookie_browser=self.audio_cookie_browser,
                        )

                        notify(f"Audio downloaded: {audio_result['title']}")

                        # 转录音频
                        notify(f"Transcribing with Whisper ({self.whisper_model})...")
                        raw_subtitles = transcribe_audio(
                            audio_result["filepath"],
                            model_size=self.whisper_model,
                            device=self.whisper_device,
                            compute_type=self.whisper_compute_type,
                        )

                        subtitle_source = f"Whisper ({self.whisper_model})"
                        notify(f"Transcription done: {len(raw_subtitles)} segments")

                        # 清理音频文件
                        from .audio.downloader import cleanup_audio
                        cleanup_audio(audio_result["filepath"])

                    except Exception as e:
                        logger.error(f"Audio transcription failed: {e}")
                        notify(f"Audio transcription failed: {e}")
                    # 继续尝试，让 AI 处理空内容

            # ━━━━━━ Step 3: AI processing ━━━━━━
            if not raw_subtitles:
                return PipelineResult(
                    success=False,
                    video_title=video_info.title,
                    error_message="Cannot get subtitles or transcribe audio. Check if video has CC subtitles.",
                )

            # 合并碎片化字幕
            merged_subtitles = self.ai_processor._merge_subtitles(raw_subtitles)
            notify(f"Merged {len(raw_subtitles)} -> {len(merged_subtitles)} subtitles")

            # 格式 A：纯时间戳全文（最轻量处理，忠实原文）
            notify("Generating transcript (format A)...")
            transcript_md = self.ai_processor.process_transcript(
                subtitles=merged_subtitles,
                title=video_info.title,
            )
            notify("Transcript done")

            # 格式 B：结构化总结（分段、标题、要点）
            notify("Generating structured notes (format B)...")
            if len(merged_subtitles) > 100:
                result = self.ai_processor.process_pipeline(
                    subtitles=merged_subtitles,
                    title=video_info.title,
                    author=video_info.author,
                    duration=video_info.duration,
                    subtitle_source=subtitle_source,
                )
                notes_md = result["full_article"]
            else:
                notes_md = self.ai_processor.process_all_in_one(
                    subtitles=merged_subtitles,
                    title=video_info.title,
                    author=video_info.author,
                    duration=video_info.duration,
                    subtitle_source=subtitle_source,
                )
            notify("Structured notes done")

            # ━━━━━━ Step 4: Create TWO Feishu docs ━━━━━━
            notify("Creating Feishu documents...")

            # Doc A: 全文实录
            doc_url_a = create_video_note_document(
                app_id=self.feishu_app_id,
                app_secret=self.feishu_app_secret,
                title=f"【全文】{video_info.title}",
                markdown_content=transcript_md,
            )
            notify(f"Transcript doc created")

            # Doc B: 结构化笔记
            doc_url_b = create_video_note_document(
                app_id=self.feishu_app_id,
                app_secret=self.feishu_app_secret,
                title=f"【笔记】{video_info.title}",
                markdown_content=notes_md,
            )
            notify(f"Notes doc created")

            elapsed = time.time() - start_time
            notify(f"Done! Total time: {elapsed:.1f}s")

            # 通知用户
            if user_open_id:
                try:
                    from .feishu.doc_creator import send_feishu_message
                    msg_text = (
                        f"视频笔记已生成！\n\n"
                        f"视频：{video_info.title}\n"
                        f"UP主：{video_info.author}\n"
                        f"时长：{video_info.duration // 60}分{video_info.duration % 60}秒\n"
                        f"耗时：{elapsed:.1f}秒\n\n"
                        f"全文实录（带时间戳）：\n{doc_url_a}\n\n"
                        f"结构化笔记：\n{doc_url_b}"
                    )
                    send_feishu_message(
                        app_id=self.feishu_app_id,
                        app_secret=self.feishu_app_secret,
                        open_id=user_open_id,
                        text=msg_text,
                    )
                    notify("Notification sent to user")
                except Exception as e:
                    logger.warning(f"Failed to send notification: {e}")

            return PipelineResult(
                success=True,
                doc_url=doc_url_a,
                notes_url=doc_url_b,
                video_title=video_info.title,
                subtitle_source=subtitle_source,
                duration_seconds=elapsed,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = f"Pipeline error: {type(e).__name__}: {e}"
            logger.exception(error_msg)
            notify(f"[ERROR] {error_msg}")

            return PipelineResult(
                success=False,
                error_message=str(e),
                duration_seconds=elapsed,
            )
