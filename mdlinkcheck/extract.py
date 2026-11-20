"""从 Markdown 文本中提取链接，自动跳过代码块与行内代码。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Match

_FENCE_RE = re.compile(
    r"^[ \t]*(?:```|~~~).*?^[ \t]*(?:```|~~~)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_INLINE_LINK_RE = re.compile(
    r"(!?)\[([^\[\]\n]*)\]\(\s*<?([^()\s<>]+)>?"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^()]*\)))?\s*\)"
)
_REF_DEF_RE = re.compile(
    r"^[ \t]{0,3}\[([^\[\]\n]+)\]:[ \t]*<?(\S+?)>?(?:[ \t]+.*)?$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Link:
    """Markdown 中出现的一个链接。"""

    line: int
    column: int
    text: str
    target: str
    is_image: bool = False


def _blank(match: Match[str]) -> str:
    """用空白覆盖匹配内容，保留换行以便行号保持不变。"""
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_code(text: str) -> str:
    """把代码块和行内代码替换成等长空白，避免误判其中的链接。"""
    without_fences = _FENCE_RE.sub(_blank, text)
    return _INLINE_CODE_RE.sub(_blank, without_fences)


def _locate(text: str, offset: int) -> "tuple[int, int]":
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    return line, offset - last_newline


def extract_links(text: str) -> List[Link]:
    """提取行内链接、图片和引用式链接定义。

    Args:
        text: Markdown 原文。

    Raises:
        TypeError: text 不是字符串。
    """
    if not isinstance(text, str):
        raise TypeError("text 必须是 str")

    cleaned = strip_code(text)
    links: List[Link] = []

    for match in _INLINE_LINK_RE.finditer(cleaned):
        line, column = _locate(cleaned, match.start())
        links.append(
            Link(
                line=line,
                column=column,
                text=match.group(2),
                target=match.group(3),
                is_image=match.group(1) == "!",
            )
        )

    for match in _REF_DEF_RE.finditer(cleaned):
        line, column = _locate(cleaned, match.start())
        links.append(
            Link(
                line=line,
                column=column,
                text=match.group(1),
                target=match.group(2),
                is_image=False,
            )
        )

    links.sort(key=lambda link: (link.line, link.column))
    return links
