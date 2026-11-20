"""mdlink 命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Sequence

from mdlinkcheck.checker import (
    Issue,
    InputError,
    check_files,
    iter_markdown_files,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdlink",
        description="检查 Markdown 中的本地链接、锚点和外部链接。",
    )
    parser.add_argument(
        "paths", nargs="*", metavar="PATH",
        help="Markdown 文件或目录，默认当前目录",
    )
    parser.add_argument(
        "--offline", action="store_true", help="只检查本地链接，不访问网络"
    )
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB",
        help="排除匹配的目录或文件，可重复传入",
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0, metavar="SEC",
        help="单个外部链接的超时时间，默认 10 秒",
    )
    parser.add_argument(
        "--concurrency", type=int, default=8, metavar="N",
        help="外部链接并发数，默认 8",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--quiet", action="store_true", help="只输出问题")
    return parser


def _print_issue(issue: Issue) -> None:
    print(
        "{0}:{1}  [{2}]  {3}  {4}".format(
            _relative(issue.path), issue.line, issue.kind, issue.target, issue.message
        )
    )


def _relative(path: str) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:
        return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    if args.concurrency < 1:
        parser.error("--concurrency 必须大于 0")

    targets: List[str] = list(args.paths) or ["."]
    try:
        files = iter_markdown_files(targets, args.exclude)
        issues = check_files(
            files,
            offline=args.offline,
            timeout=args.timeout,
            concurrency=args.concurrency,
        )
    except InputError as exc:
        print("错误: {0}".format(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print("错误: {0}".format(exc), file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "files": len(files),
            "issues": [
                {
                    "path": _relative(issue.path),
                    "line": issue.line,
                    "kind": issue.kind,
                    "target": issue.target,
                    "message": issue.message,
                }
                for issue in issues
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            _print_issue(issue)
        if issues:
            print()
            print("检查 {0} 个文件，发现 {1} 个链接问题".format(len(files), len(issues)))
        elif not args.quiet:
            print("检查 {0} 个文件，未发现链接问题".format(len(files)))

    return 1 if issues else 0
