"""
音频转录模块

使用 faster-whisper 进行本地语音转文字，输出带时间戳的文本。
"""

import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """转录片段"""
    start: float     # 开始时间（秒）
    end: float       # 结束时间（秒）
    text: str        # 转录文本


@dataclass
class TranscriptionResult:
    """转录结果"""
    segments: list[TranscriptionSegment] = field(default_factory=list)
    full_text: str = ""     # 完整纯文本
    language: str = ""      # 检测到的语言
    duration: float = 0.0   # 音频时长（秒）


class WhisperTranscriber:
    """
    faster-whisper 转录器。

    支持模型: tiny, base, small, medium, large
    base 模型对中文效果尚可，速度快；small 效果更好。
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        """
        初始化转录器。

        Args:
            model_size: 模型大小 (tiny/base/small/medium/large)
            device: 运行设备 (auto/cpu/cuda)
            compute_type: 计算类型 (auto/float16/int8)
        """
        self.model_size = model_size
        self.device = device if device != "auto" else "cpu"
        self.compute_type = compute_type if compute_type != "auto" else "int8"
        self._model = None

    def _load_model(self):
        """延迟加载模型（首次使用时加载）。"""
        if self._model is not None:
            return

        from faster_whisper import WhisperModel

        logger.info(f"正在加载 Whisper 模型: {self.model_size} "
                     f"(device={self.device}, compute_type={self.compute_type})")

        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=None,  # 使用默认缓存目录
        )
        logger.info("Whisper 模型加载完成")

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = "zh",
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> TranscriptionResult:
        """
        转录音频文件。

        Args:
            audio_path: 音频文件路径
            language: 语言代码，None 为自动检测，推荐传 "zh"
            beam_size: Beam search 大小
            vad_filter: 是否启用 VAD（语音活动检测）过滤静音

        Returns:
            TranscriptionResult 对象
        """
        self._load_model()

        logger.info(f"开始转录: {audio_path}")
        logger.info(f"参数: language={language}, beam_size={beam_size}, vad_filter={vad_filter}")

        # 执行转录
        segments_iter, info = self._model.transcribe(
            audio_path,
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters=dict(
                min_silence_duration_ms=500,
            ),
        )

        logger.info(f"检测到语言: {info.language} (概率: {info.language_probability:.2%})")

        # 收集结果
        segments = []
        full_text_parts = []

        for segment in segments_iter:
            seg = TranscriptionSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text.strip(),
            )
            segments.append(seg)
            full_text_parts.append(segment.text.strip())

        result = TranscriptionResult(
            segments=segments,
            full_text="".join(full_text_parts),
            language=info.language,
            duration=info.duration,
        )

        logger.info(
            f"转录完成: {len(segments)} 个片段, "
            f"总时长 {info.duration:.1f}s, "
            f"语言 {info.language}"
        )

        return result

    def transcribe_to_subtitle_format(
        self,
        audio_path: str,
        language: Optional[str] = "zh",
    ) -> list[dict]:
        """
        转录音频并转换为 B站字幕格式。

        Args:
            audio_path: 音频文件路径
            language: 语言代码

        Returns:
            list[dict]: [{"from": float, "to": float, "content": str}, ...]
        """
        result = self.transcribe(audio_path, language=language)

        subtitles = []
        for seg in result.segments:
            subtitles.append({
                "from": seg.start,
                "to": seg.end,
                "content": seg.text,
            })

        return subtitles


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 便捷函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 全局单例（延迟初始化）
_transcriber: Optional[WhisperTranscriber] = None


def get_transcriber(
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "auto",
) -> WhisperTranscriber:
    """获取全局转录器单例。"""
    global _transcriber
    if _transcriber is None:
        _transcriber = WhisperTranscriber(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
        )
    return _transcriber


def transcribe_audio(
    audio_path: str,
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "auto",
) -> list[dict]:
    """
    转录音频文件，返回 B站字幕格式的数据。
    这是给 pipeline 调用的主入口。
    """
    transcriber = get_transcriber(model_size, device, compute_type)
    return transcriber.transcribe_to_subtitle_format(audio_path)
