"""Markdown 链接检查的核心逻辑。"""

from __future__ import annotations

import fnmatch
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

from mdlinkcheck.extract import Link, extract_links, strip_code

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
_USER_AGENT = "Mozilla/5.0 (compatible; md-link-check/0.1)"
DEFAULT_EXCLUDES = (".git", "node_modules", ".venv", "venv", "dist", "build")


class InputError(Exception):
    """输入路径无法处理时抛出。"""


@dataclass(frozen=True)
class Issue:
    """一个链接问题。"""

    path: str
    line: int
    target: str
    kind: str
    message: str


@dataclass(frozen=True)
class UrlResult:
    """外部链接的检查结果。"""

    ok: bool
    status: Optional[int] = None
    error: Optional[str] = None


def classify(target: str) -> str:
    """把链接目标归类为 external / local / anchor / empty / skip。"""
    if not target.strip():
        return "empty"
    if target.startswith("#"):
        return "anchor"
    if _SCHEME_RE.match(target):
        scheme = target.split(":", 1)[0].lower()
        return "external" if scheme in ("http", "https") else "skip"
    return "local"


def read_markdown(path: str) -> str:
    """读取 Markdown 文件（允许 UTF-8 BOM）。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise InputError("文件不存在: {0}".format(path)) from exc
    except IsADirectoryError as exc:
        raise InputError("这是一个目录，不是文件: {0}".format(path)) from exc
    except PermissionError as exc:
        raise InputError("没有权限读取: {0}".format(path)) from exc
    except UnicodeDecodeError as exc:
        raise InputError("不是 UTF-8 文本: {0}".format(path)) from exc
    except OSError as exc:
        raise InputError(
            "读取失败: {0} ({1})".format(path, exc.strerror or exc)
        ) from exc


def _is_excluded(path: str, patterns: Sequence[str]) -> bool:
    normalized = path.replace(os.sep, "/")
    parts = [part for part in normalized.split("/") if part]
    for pattern in patterns:
        if not pattern:
            continue
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
        if fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def iter_markdown_files(
    paths: Sequence[str], excludes: Sequence[str] = DEFAULT_EXCLUDES
) -> List[str]:
    """展开文件/目录参数，返回去重后的 Markdown 文件绝对路径。"""
    found: Set[str] = set()
    for raw in paths:
        if not os.path.exists(raw):
            raise InputError("路径不存在: {0}".format(raw))
        if os.path.isfile(raw):
            found.add(os.path.abspath(raw))
            continue
        if not os.path.isdir(raw):
            raise InputError("不支持的路径类型: {0}".format(raw))
        for root, dirs, files in os.walk(raw):
            dirs[:] = sorted(name for name in dirs if not _is_excluded(name, excludes))
            for name in sorted(files):
                if not name.lower().endswith(".md"):
                    continue
                full = os.path.join(root, name)
                if not _is_excluded(full, excludes):
                    found.add(os.path.abspath(full))
    return sorted(found)


def slugify(heading: str) -> str:
    """近似 GitHub 的标题锚点规则。"""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text)
    return text.strip("-")


def headings_of(text: str) -> Set[str]:
    """提取文档中所有标题的锚点。"""
    cleaned = strip_code(text)
    return {slugify(match.group(1)) for match in _HEADING_RE.finditer(cleaned)}


def _project_root(path: str) -> str:
    current = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.dirname(os.path.abspath(path))
        current = parent


def _headings_for(path: str, cache: Dict[str, Set[str]]) -> Set[str]:
    key = os.path.abspath(path)
    if key not in cache:
        try:
            cache[key] = headings_of(read_markdown(key))
        except InputError:
            cache[key] = set()
    return cache[key]


def _local_issue(
    path: str,
    link: Link,
    kind: str,
    cache: Dict[str, Set[str]],
) -> Optional[Issue]:
    if kind == "empty":
        return Issue(path, link.line, link.target, kind, "链接目标为空")

    if kind == "anchor":
        fragment = unquote(link.target[1:])
        if not fragment:
            return Issue(path, link.line, link.target, kind, "锚点为空")
        if fragment not in _headings_for(path, cache):
            return Issue(path, link.line, link.target, kind, "锚点不存在: #{0}".format(fragment))
        return None

    raw_path, _, fragment = link.target.partition("#")
    raw_path = unquote(raw_path.split("?", 1)[0])
    if not raw_path:
        return None

    base = os.path.dirname(os.path.abspath(path))
    if raw_path.startswith(("/", "\\")):
        base = _project_root(path)
        raw_path = raw_path.lstrip("/\\")
    target_path = os.path.normpath(os.path.join(base, raw_path))
    if not os.path.exists(target_path):
        return Issue(
            path, link.line, link.target, kind,
            "本地路径不存在: {0}".format(raw_path),
        )

    if fragment and target_path.lower().endswith((".md", ".markdown")):
        anchor = unquote(fragment)
        if anchor not in _headings_for(target_path, cache):
            return Issue(
                path, link.line, link.target, kind,
                "目标文件缺少锚点: #{0}".format(anchor),
            )
    return None


def check_url(url: str, timeout: float = 10.0) -> UrlResult:
    """检查一个 http(s) 链接。

    先发 HEAD 请求，遇到 403/405 等不支持 HEAD 的状态码时回退到 GET。
    """
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("只支持 http/https 链接: {0}".format(url))
    if timeout <= 0:
        raise ValueError("timeout 必须大于 0")

    headers = {"User-Agent": _USER_AGENT, "Accept": "*/*"}
    for method in ("HEAD", "GET"):
        request = Request(url, method=method, headers=headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 200))
                if 200 <= status < 400:
                    return UrlResult(ok=True, status=status)
                return UrlResult(ok=False, status=status, error="HTTP {0}".format(status))
        except HTTPError as exc:
            if method == "HEAD" and exc.code in (400, 403, 405, 501):
                continue
            return UrlResult(ok=False, status=exc.code, error="HTTP {0}".format(exc.code))
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return UrlResult(ok=False, status=None, error=str(reason))
    return UrlResult(ok=False, status=None, error="请求失败")


def check_files(
    paths: Sequence[str],
    offline: bool = False,
    timeout: float = 10.0,
    concurrency: int = 8,
    excludes: Sequence[str] = DEFAULT_EXCLUDES,
) -> List[Issue]:
    """检查一组文件或目录中的所有 Markdown 链接。

    Args:
        paths: 文件或目录路径。
        offline: 为 True 时跳过所有外部链接。
        timeout: 单个外部链接的超时时间（秒）。
        concurrency: 外部链接并发检查数量。
        excludes: 目录/文件排除规则。

    Raises:
        InputError: 路径不存在或无法读取。
        ValueError: 参数越界。
    """
    if timeout <= 0:
        raise ValueError("timeout 必须大于 0")
    if concurrency < 1:
        raise ValueError("concurrency 必须大于 0")

    files = iter_markdown_files(paths, excludes)
    cache: Dict[str, Set[str]] = {}
    issues: List[Issue] = []
    pending: List[Tuple[str, Link]] = []

    for path in files:
        text = read_markdown(path)
        for link in extract_links(text):
            kind = classify(link.target)
            if kind == "skip":
                continue
            if kind == "external":
                if not offline:
                    pending.append((path, link))
                continue
            issue = _local_issue(path, link, kind, cache)
            if issue is not None:
                issues.append(issue)

    if pending:
        targets = sorted({link.target for _, link in pending})
        workers = min(concurrency, len(targets))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(partial(check_url, timeout=timeout), targets))
        by_target = dict(zip(targets, results))
        for path, link in pending:
            result = by_target[link.target]
            if result.ok:
                continue
            message = result.error or "HTTP {0}".format(result.status)
            issues.append(
                Issue(path, link.line, link.target, "external", message)
            )

    issues.sort(key=lambda issue: (issue.path, issue.line))
    return issues
