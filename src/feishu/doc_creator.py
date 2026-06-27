"""
飞书文档创建模块

将 AI 生成的 Markdown 文章转换为飞书 Docx 文档。
使用飞书开放平台 HTTP API（绕过 lark-oapi SDK 的 block 操作 bug）。
"""

import re
import json
import logging
from typing import Optional

import httpx
import lark_oapi as lark
from lark_oapi.api.docx.v1 import (
    CreateDocumentRequest,
    CreateDocumentRequestBody,
    Block,
    Text,
    TextElement,
    TextRun,
    Divider,
    Callout,
)

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 飞书客户端（HTTP 直调）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FeishuDocClient:
    """飞书文档创建客户端。"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: Optional[str] = None
        self._http = httpx.Client(timeout=30)

    def _get_token(self) -> str:
        """获取 tenant_access_token。"""
        if self._token:
            return self._token

        resp = self._http.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取飞书 token 失败: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        return self._token

    def _api(self, method: str, path: str, **kwargs) -> dict:
        """通用 API 调用。"""
        token = self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Content-Type", "application/json")

        resp = self._http.request(method, f"https://open.feishu.cn{path}", headers=headers, **kwargs)
        return resp.json()

    def create_document(self, title: str) -> str:
        """
        创建一个新的飞书文档。

        Returns:
            document_id
        """
        result = self._api(
            "POST",
            "/open-apis/docx/v1/documents",
            content=json.dumps({"title": title}),
        )

        if result.get("code") != 0:
            raise RuntimeError(f"创建飞书文档失败: {result.get('msg')}")

        doc_id = result["data"]["document"]["document_id"]
        logger.info(f"文档创建成功: {doc_id}")
        return doc_id

    def append_blocks(self, document_id: str, blocks: list[dict]) -> bool:
        """向文档根节点追加块（直接 HTTP，绕过 SDK）。"""
        if not blocks:
            return True

        BATCH_SIZE = 50
        root_id = document_id

        for i in range(0, len(blocks), BATCH_SIZE):
            batch = blocks[i:i + BATCH_SIZE]

            result = self._api(
                "POST",
                f"/open-apis/docx/v1/documents/{document_id}/blocks/{root_id}/children",
                content=json.dumps({"children": batch}, ensure_ascii=False),
            )

            if result.get("code") != 0:
                logger.error(f"添加块失败 (batch {i // BATCH_SIZE}): {result.get('msg')}")
                return False

        logger.info(f"成功添加 {len(blocks)} 个块到文档 {document_id}")
        return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Markdown → JSON 块转换（直接出 dict，不走 SDK Block）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_inline_text(text: str) -> list[dict]:
    """解析行内 Markdown（**加粗**），返回 Feishu elements 列表。"""
    elements = []
    pattern = re.compile(r'(\*\*(.+?)\*\*)')
    parts = pattern.split(text)

    i = 0
    while i < len(parts):
        part = parts[i]
        if not part:
            i += 1
            continue

        if part.startswith('**') and part.endswith('**') and i + 1 < len(parts):
            bold_text = parts[i + 1]
            elements.append({
                "text_run": {
                    "content": bold_text,
                    "text_element_style": {"bold": True}
                }
            })
            i += 2
        else:
            if part and not (part.startswith('**') and part.endswith('**')):
                elements.append({
                    "text_run": {
                        "content": part,
                        "text_element_style": {}
                    }
                })
            i += 1

    if not elements:
        elements.append({"text_run": {"content": "", "text_element_style": {}}})

    return elements


def _text_block(text: str) -> dict:
    """文本段落 (block_type=2)。"""
    return {
        "block_type": 2,
        "text": {
            "elements": _parse_inline_text(text),
            "style": {}
        }
    }


def _heading_block(level: int, text: str) -> dict:
    """标题块 (H1=3, H2=4, H3=5)。"""
    bt = {1: 3, 2: 4, 3: 5}.get(level, 3)
    field = {3: "heading1", 4: "heading2", 5: "heading3"}[bt]
    return {
        "block_type": bt,
        field: {
            "elements": _parse_inline_text(text),
            "style": {}
        }
    }


def _bullet_block(text: str) -> dict:
    """无序列表项 (block_type=12)。"""
    return {
        "block_type": 12,
        "bullet": {
            "elements": _parse_inline_text(text),
            "style": {}
        }
    }


def _quote_block(text: str) -> dict:
    """引用块 (block_type=25, Callout)。"""
    return {
        "block_type": 25,
        "callout": {}
    }
    # 注意：callout 不支持内联文本，需要添加子块。简化为空 callout + 后续文本块。
    # 实际上这里我们用一个带 ▶ 前缀的文本块代替


def _divider_block() -> dict:
    """分割线 (用文本块代替，飞书 API 不支持空 divider 作为子块)。"""
    return {
        "block_type": 2,
        "text": {
            "elements": [{"text_run": {"content": "————————————————————", "text_element_style": {}}}],
            "style": {}
        }
    }


def _is_special_line(line: str) -> bool:
    """Check if a line starts a special block."""
    s = line.strip()
    if not s:
        return True
    if s.startswith('#'): return True
    if s.startswith('> '): return True
    if s.startswith('>'): return True
    if s.startswith('- ') or s.startswith('* '): return True
    if re.match(r'^\d+\.\s+', s): return True
    if re.match(r'^[-*]{3,}\s*$', s): return True
    if s.startswith('|'): return True
    return False


def markdown_to_feishu_blocks(markdown: str) -> list[dict]:
    """
    Convert Markdown to Feishu blocks (dict format).
    Simple line-by-line processor, no nested while loops.
    """
    blocks = []
    lines = markdown.split('\n')
    n = len(lines)

    # First pass: merge consecutive text lines into paragraphs
    merged = []  # list of (line_idx, line_text)
    i = 0
    while i < n:
        line = lines[i]
        s = line.strip()

        if not s:
            merged.append(('empty', ''))
            i += 1
            continue

        if s.startswith('#'):
            merged.append(('heading', s))
            i += 1
            continue

        if s.startswith('> ') or s.startswith('>'):
            merged.append(('quote', s))
            i += 1
            continue

        if s.startswith('- ') or s.startswith('* '):
            merged.append(('bullet', s))
            i += 1
            continue

        if re.match(r'^\d+\.\s+', s):
            merged.append(('bullet', s))
            i += 1
            continue

        if re.match(r'^[-*]{3,}\s*$', s):
            merged.append(('divider', ''))
            i += 1
            continue

        if s.startswith('|'):
            merged.append(('table', s))
            i += 1
            continue

        # Timestamp line: "[MM:SS] text" or "MM:SS" or "HH:MM:SS"
        if re.match(r'^(\[\d{1,2}:\d{2}(:\d{2})?\]|^\d{1,2}:\d{2}(:\d{2})?)\s', s):
            merged.append(('timestamp', s))
        # Bare timestamp on its own line like "00:00" or "01:15:30"
        elif re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', s):
            merged.append(('timestamp', s))
        else:
            # Text line
            merged.append(('text', s))
        i += 1

    # Second pass: build blocks
    para_parts = []
    table_rows = []

    def flush_table():
        nonlocal table_rows
        if not table_rows:
            return
        for row in table_rows:
            if re.match(r'^\|[\s\-:]+\|$', row):
                continue
            cells = [c.strip() for c in row.split('|')[1:-1]]
            blocks.append(_text_block('  |  '.join(cells)))
        table_rows = []

    def flush_para():
        nonlocal para_parts
        if para_parts:
            blocks.append(_text_block(' '.join(para_parts)))
            para_parts = []

    for kind, text in merged:
        if kind != 'table' and table_rows:
            flush_table()

        if kind not in ('text', 'timestamp') and para_parts:
            flush_para()

        if kind == 'timestamp':
            flush_para()
            blocks.append(_text_block(text))

        if kind == 'empty':
            flush_para()
            flush_table()

        elif kind == 'heading':
            m = re.match(r'^(#{1,3})\s+(.+)$', text)
            if m:
                level = len(m.group(1))
                blocks.append(_heading_block(level, m.group(2).strip()))

        elif kind == 'quote':
            qt = text[1:].strip() if text[1] != ' ' else text[2:].strip()
            blocks.append(_text_block(f"💬 {qt}"))

        elif kind == 'bullet':
            m = re.match(r'^(?:[-*]|\d+\.)\s+(.+)$', text)
            if m:
                blocks.append(_bullet_block(m.group(1).strip()))

        elif kind == 'divider':
            blocks.append(_divider_block())

        elif kind == 'table':
            table_rows.append(text)

        elif kind == 'text':
            para_parts.append(text)

    # Final flush
    flush_table()
    flush_para()

    return blocks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_video_note_document(
    app_id: str,
    app_secret: str,
    title: str,
    markdown_content: str,
) -> str:
    """
    创建视频笔记文档。

    Args:
        app_id: 飞书应用 App ID
        app_secret: 飞书应用 App Secret
        title: 文档标题
        markdown_content: Markdown 格式文章

    Returns:
        文档 URL
    """
    client = FeishuDocClient(app_id, app_secret)
    doc_id = client.create_document(title)

    blocks = markdown_to_feishu_blocks(markdown_content)
    if blocks:
        client.append_blocks(doc_id, blocks)

    doc_url = f"https://bytedance.feishu.cn/docx/{doc_id}"
    logger.info(f"视频笔记文档创建完成: {doc_url}")

    return doc_url


def send_feishu_message(
    app_id: str,
    app_secret: str,
    open_id: str,
    text: str,
) -> bool:
    """发送飞书消息给指定用户。"""
    client = FeishuDocClient(app_id, app_secret)

    if len(text) > 15000:
        text = text[:15000] + "\n\n... (过长已截断)"

    result = client._api(
        "POST",
        "/open-apis/im/v1/messages?receive_id_type=open_id",
        content=json.dumps({
            "receive_id": open_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }, ensure_ascii=False),
    )

    if result.get("code") != 0:
        logger.error(f"发送消息失败: {result.get('msg')}")
        return False

    logger.info(f"消息已发送给 {open_id}")
    return True
