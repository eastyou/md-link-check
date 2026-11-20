"""md-link-check: 检查 Markdown 链接是否可用。"""

from mdlinkcheck.checker import Issue, UrlResult, check_files, check_url
from mdlinkcheck.extract import Link, extract_links

__all__ = ["Issue", "Link", "UrlResult", "check_files", "check_url", "extract_links"]
__version__ = "0.1.0"
