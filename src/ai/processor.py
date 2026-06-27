"""
AI 文本处理器

调用 DeepSeek API（OpenAI 兼容接口）进行字幕纠错、格式化、总结。
支持三阶段流水线处理和单次综合处理。
"""

import json
import logging
from typing import Optional

from openai import OpenAI

from .prompts import (
    PROMPT_CORRECT_SUBTITLES,
    PROMPT_FORMAT_ARTICLE,
    PROMPT_GENERATE_SUMMARY,
    PROMPT_ALL_IN_ONE,
    PROMPT_TRANSCRIPT,
)

logger = logging.getLogger(__name__)


def _format_duration(seconds: int) -> str:
    """将秒数格式化为 MM:SS 或 HH:MM:SS。"""
    if seconds < 0:
        return "00:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _subtitles_to_json(subtitles: list[dict]) -> str:
    """将字幕列表转为 JSON 字符串。"""
    # 截断过长的字幕（避免超出 token 限制）
    # 每条约 200 字，最多 500 条
    trimmed = subtitles[:500]
    return json.dumps(trimmed, ensure_ascii=False, indent=2)


def _subtitles_to_text_with_timestamps(subtitles: list[dict]) -> str:
    """将字幕列表转为带时间戳的纯文本格式。"""
    lines = []
    for sub in subtitles[:500]:
        from_sec = sub.get("from", 0)
        to_sec = sub.get("to", 0)
        content = sub.get("content", "")
        from_str = _format_duration(int(from_sec))
        lines.append(f"[{from_str}] {content}")
    return "\n".join(lines)


class AITextProcessor:
    """DeepSeek API 文本处理器。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 16384,
    ) -> str:
        """调用 DeepSeek Chat API。"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}")
            raise

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 分阶段处理
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def correct_subtitles(
        self,
        subtitles: list[dict],
        title: str = "",
    ) -> list[dict]:
        """
        阶段1：字幕纠错

        Args:
            subtitles: 原始字幕列表 [{"from": float, "to": float, "content": str}, ...]
            title: 视频标题

        Returns:
            纠错后的字幕列表（同格式）
        """
        if not subtitles:
            return []

        logger.info(f"阶段1：字幕纠错 - {len(subtitles)} 条字幕")

        subtitles_json = _subtitles_to_json(subtitles)
        user_prompt = PROMPT_CORRECT_SUBTITLES.format(
            title=title,
            subtitles_json=subtitles_json,
        )

        system_prompt = "你是一个专业的中文文字编辑，擅长文本纠错和排版。你只输出 JSON，不输出其他任何内容。"

        response = self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,  # 低温度保证确定性
        )

        # 解析 JSON 响应
        try:
            # 尝试提取 JSON 部分
            response = response.strip()
            if response.startswith("```"):
                # 去除 markdown 代码块标记
                lines = response.split("\n")
                response = "\n".join(lines[1:-1]) if len(lines) > 2 else response
                response = response.replace("```json", "").replace("```", "").strip()

            corrected = json.loads(response)
            logger.info(f"字幕纠错完成: {len(corrected)} 条")
            return corrected
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败，返回原始字幕: {e}")
            return subtitles

    def format_article(
        self,
        subtitles: list[dict],
        title: str = "",
        author: str = "",
    ) -> str:
        """
        阶段2：全文笔记格式化

        Args:
            subtitles: 已纠错的字幕列表
            title: 视频标题
            author: 视频作者

        Returns:
            格式化的全文笔记（Markdown）
        """
        if not subtitles:
            return "*（无内容）*"

        logger.info(f"阶段2：全文格式化 - {len(subtitles)} 条字幕")

        subtitle_text = _subtitles_to_text_with_timestamps(subtitles)
        user_prompt = PROMPT_FORMAT_ARTICLE.format(
            title=title,
            author=author,
            corrected_subtitles=subtitle_text,
        )

        system_prompt = "你是一个专业的知识管理专家，擅长将视频内容整理成结构化笔记。输出 Markdown 格式。"

        response = self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=16384,
        )

        logger.info("全文格式化完成")
        return response

    def generate_summary(
        self,
        formatted_article: str,
        title: str = "",
        author: str = "",
        duration: int = 0,
    ) -> str:
        """
        阶段3：生成总结 + 时间戳目录

        Args:
            formatted_article: 阶段2输出的全文笔记
            title: 视频标题
            author: 视频作者
            duration: 视频时长（秒）

        Returns:
            总结内容（Markdown）
        """
        if not formatted_article.strip():
            return "*（无内容）*"

        logger.info(f"阶段3：生成总结")

        user_prompt = PROMPT_GENERATE_SUMMARY.format(
            title=title,
            author=author,
            duration=_format_duration(duration),
            formatted_article=formatted_article,
        )

        system_prompt = "你是一个专业的知识提炼专家，擅长提取核心要点和制作内容目录。"

        response = self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.5,
            max_tokens=8192,
        )

        logger.info("总结生成完成")
        return response

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 综合处理（单次调用）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _merge_subtitles(self, subtitles: list[dict], max_gap: float = 1.0) -> list[dict]:
        """
        合并过短的相邻字幕片段，减少碎片化。

        Args:
            subtitles: 原始字幕列表
            max_gap: 合并的最大间隔（秒）

        Returns:
            合并后的字幕列表
        """
        if not subtitles:
            return []

        merged = []
        current = dict(subtitles[0])

        for i in range(1, len(subtitles)):
            nxt = subtitles[i]
            gap = nxt.get("from", 0) - current.get("to", 0)

            current_text = current.get("content", "")
            next_text = nxt.get("content", "")
            combined_len = len(current_text) + len(next_text)

            # 仅当间隔极小且合并后不超过80字才合并（一条完整句子）
            if gap <= max_gap and combined_len < 80:
                current["to"] = nxt.get("to", current["to"])
                current["content"] = current_text + next_text
            else:
                merged.append(current)
                current = dict(nxt)

        merged.append(current)
        logger.info(f"字幕合并: {len(subtitles)} -> {len(merged)} 条")
        return merged

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 纯时间戳全文（最轻量处理）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def process_transcript(
        self,
        subtitles: list[dict],
        title: str = "",
    ) -> str:
        """
        生成纯时间戳全文：只做错字修正，保留所有时间戳，不加标题和总结。

        Args:
            subtitles: 原始字幕列表
            title: 视频标题

        Returns:
            纯时间戳全文
        """
        if not subtitles:
            return "*（无内容）*"

        logger.info(f"生成时间戳全文: {len(subtitles)} 条字幕")

        subtitle_text = _subtitles_to_text_with_timestamps(subtitles)
        user_prompt = PROMPT_TRANSCRIPT.format(
            subtitles_raw=subtitle_text,
        )

        system_prompt = "你是一个字幕校对员，只修正错别字，保留原格式。"

        response = self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=8192,
        )

        # 给全文加上标题和尾部标注
        result = f"{title}\n\n{response}\n\n> 🤖 AI 校对 | 字幕来源：B站"
        logger.info("时间戳全文生成完成")
        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 综合处理（单次调用）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def process_all_in_one(
        self,
        subtitles: list[dict],
        title: str = "",
        author: str = "",
        duration: int = 0,
        subtitle_source: str = "B站官方字幕",
    ) -> str:
        """
        单次综合处理：纠错 + 格式化 + 总结。

        适合不太长的视频（<30分钟），一次调用完成所有处理。

        Args:
            subtitles: 原始字幕列表
            title: 视频标题
            author: 视频作者
            duration: 视频时长（秒）
            subtitle_source: 字幕来源描述

        Returns:
            完整的 Markdown 文章
        """
        if not subtitles:
            return f"""# 【视频笔记】{title}

## ⚠️ 无法处理

抱歉，该视频没有可用的字幕或音频转录内容。

- 视频：{title}
- 时长：{_format_duration(duration)}
- B站链接：https://www.bilibili.com/video/BV...

> 请检查视频是否有官方字幕，或手动提供字幕内容。
"""

        logger.info(f"综合处理: {title} | {len(subtitles)} 条字幕 | {_format_duration(duration)}")

        # 对于短字幕用 all-in-one prompt
        subtitle_text = _subtitles_to_text_with_timestamps(subtitles)

        user_prompt = PROMPT_ALL_IN_ONE.format(
            subtitles_raw=subtitle_text,
            title=title,
            author=author,
            duration=duration,
            duration_formatted=_format_duration(duration),
            subtitle_source=subtitle_source,
        )

        system_prompt = (
            "你是一个专业的知识管理专家，擅长将视频内容整理成结构化笔记。"
            "你输出完整的 Markdown 格式文章，不要添加额外解释。"
        )

        response = self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=16384,
        )

        logger.info("综合处理完成")
        return response

    def process_pipeline(
        self,
        subtitles: list[dict],
        title: str = "",
        author: str = "",
        duration: int = 0,
        subtitle_source: str = "B站官方字幕",
    ) -> dict:
        """
        三阶段流水线处理：纠错 → 格式化 → 总结。
        适合长视频，每阶段可独立检查和调试。

        Returns:
            dict: {
                "corrected_subtitles": list[dict],
                "formatted_article": str,
                "summary": str,
                "full_article": str  # 合并后的完整文章
            }
        """
        # 阶段1：纠错
        corrected = self.correct_subtitles(subtitles, title)

        # 阶段2：格式化全文
        formatted = self.format_article(corrected, title, author)

        # 阶段3：总结
        summary = self.generate_summary(formatted, title, author, duration)

        # 组装完整文章
        full_article = self._assemble_article(
            title=title,
            author=author,
            duration=duration,
            formatted_article=formatted,
            summary=summary,
            subtitle_source=subtitle_source,
        )

        return {
            "corrected_subtitles": corrected,
            "formatted_article": formatted,
            "summary": summary,
            "full_article": full_article,
        }

    def _assemble_article(
        self,
        title: str,
        author: str,
        duration: int,
        formatted_article: str,
        summary: str,
        subtitle_source: str = "B站官方字幕",
    ) -> str:
        """将格式化全文和总结组装成完整文章。"""
        duration_str = _format_duration(duration)

        return f"""# 【视频笔记】{title}

## 📺 视频信息

| 项目 | 内容 |
|------|------|
| 标题 | {title} |
| UP主 | {author} |
| 时长 | {duration_str} |
| 来源 | Bilibili |

---

{summary}

---

## 📝 全文笔记

{formatted_article}

---

> 🤖 本文由 AI 自动生成 | 字幕来源：{subtitle_source} | 生成时间：自动
"""
