"""链接检查逻辑与 CLI 的单元测试。"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from mdlinkcheck.checker import (
    InputError,
    UrlResult,
    check_files,
    check_url,
    classify,
    headings_of,
    iter_markdown_files,
    slugify,
)
from mdlinkcheck.cli import main


def _write(directory, name, content):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class ClassifyTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify("https://example.com"), "external")
        self.assertEqual(classify("HTTP://example.com"), "external")
        self.assertEqual(classify("mailto:a@b.com"), "skip")
        self.assertEqual(classify("docs/a.md"), "local")
        self.assertEqual(classify("#标题"), "anchor")
        self.assertEqual(classify("  "), "empty")


class SlugTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")
        self.assertEqual(slugify("快速开始"), "快速开始")

    def test_headings_ignore_code(self):
        text = "# 标题\n```\n# 不是标题\n```\n## 二级 标题\n"
        self.assertEqual(headings_of(text), {"标题", "二级-标题"})


class LocalCheckTests(unittest.TestCase):
    def test_existing_and_missing_local_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "guide.md", "# 快速开始\n")
            source = _write(
                tmp,
                "README.md",
                "[ok](guide.md)\n[bad](nope.md)\n",
            )
            issues = check_files([source], offline=True)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].target, "nope.md")
        self.assertEqual(issues[0].line, 2)

    def test_anchor_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _write(
                tmp,
                "README.md",
                "# 顶部\n[ok](guide.md#快速开始)\n[bad](guide.md#不存在)\n[self](#顶部)\n[self-bad](#没有)\n",
            )
            _write(tmp, "guide.md", "# 快速开始\n")
            issues = check_files([source], offline=True)
        targets = [issue.target for issue in issues]
        self.assertIn("guide.md#不存在", targets)
        self.assertIn("#没有", targets)
        self.assertNotIn("guide.md#快速开始", targets)
        self.assertNotIn("#顶部", targets)

    def test_external_links_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _write(
                tmp,
                "README.md",
                "[a](https://ok.example)\n[b](https://bad.example)\n",
            )

            def fake_check(url, timeout=10.0):
                if "bad" in url:
                    return UrlResult(ok=False, error="timeout")
                return UrlResult(ok=True, status=200)

            with mock.patch("mdlinkcheck.checker.check_url", side_effect=fake_check):
                issues = check_files([source])
        self.assertEqual([issue.target for issue in issues], ["https://bad.example"])

    def test_offline_skips_external_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _write(tmp, "README.md", "[a](https://bad.example)\n")
            with mock.patch("mdlinkcheck.checker.check_url") as mocked:
                issues = check_files([source], offline=True)
        self.assertEqual(issues, [])
        mocked.assert_not_called()

    def test_missing_path_raises(self):
        with self.assertRaises(InputError):
            check_files(["definitely-not-here"], offline=True)

    def test_invalid_arguments_raise(self):
        with self.assertRaises(ValueError):
            check_files(["."], timeout=0)
        with self.assertRaises(ValueError):
            check_files(["."], concurrency=0)

    def test_excludes_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "node_modules"))
            _write(os.path.join(tmp, "node_modules"), "x.md", "[a](a.md)")
            _write(tmp, "README.md", "# ok\n")
            files = iter_markdown_files([tmp])
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith("README.md"))


class UrlCheckTests(unittest.TestCase):
    def test_rejects_non_http_scheme(self):
        with self.assertRaises(ValueError):
            check_url("ftp://example.com")

    def test_rejects_non_positive_timeout(self):
        with self.assertRaises(ValueError):
            check_url("https://example.com", timeout=0)

    def test_http_error_is_reported(self):
        from urllib.error import HTTPError

        error = HTTPError("https://example.com", 404, "Not Found", None, None)
        with mock.patch("mdlinkcheck.checker.urlopen", side_effect=error):
            result = check_url("https://example.com")
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 404)

    def test_head_403_falls_back_to_get(self):
        from urllib.error import HTTPError

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        error = HTTPError("https://example.com", 403, "Forbidden", None, None)
        with mock.patch(
            "mdlinkcheck.checker.urlopen", side_effect=[error, FakeResponse()]
        ):
            result = check_url("https://example.com")
        self.assertTrue(result.ok)


class CliTests(unittest.TestCase):
    def _run(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_clean_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "README.md", "# 标题\n[自己](#标题)\n")
            code, out, _ = self._run([tmp, "--offline"])
        self.assertEqual(code, 0)
        self.assertIn("未发现链接问题", out)

    def test_broken_link_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "README.md", "[坏](nope.md)\n")
            code, out, _ = self._run([tmp, "--offline"])
        self.assertEqual(code, 1)
        self.assertIn("nope.md", out)
        self.assertIn("本地路径不存在", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "README.md", "[坏](nope.md)\n")
            code, out, _ = self._run([tmp, "--offline", "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["files"], 1)
        self.assertEqual(payload["issues"][0]["target"], "nope.md")

    def test_missing_path_exits_two(self):
        code, _, err = self._run(["/definitely/not/here", "--offline"])
        self.assertEqual(code, 2)
        self.assertIn("路径不存在", err)

    def test_invalid_timeout_is_rejected(self):
        with self.assertRaises(SystemExit):
            self._run(["--timeout", "0"])


if __name__ == "__main__":
    unittest.main()
