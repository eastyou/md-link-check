"""链接提取的单元测试。"""

import unittest

from mdlinkcheck.extract import extract_links, strip_code


class ExtractTests(unittest.TestCase):
    def test_inline_link_and_image(self):
        links = extract_links("看 [文档](docs/guide.md) 和 ![图](img/a.png)\n")
        self.assertEqual([link.target for link in links], ["docs/guide.md", "img/a.png"])
        self.assertFalse(links[0].is_image)
        self.assertTrue(links[1].is_image)
        self.assertEqual(links[0].line, 1)

    def test_fenced_code_is_ignored(self):
        text = "```\n[坏](missing.md)\n```\n[好](ok.md)\n"
        links = extract_links(text)
        self.assertEqual([link.target for link in links], ["ok.md"])
        self.assertEqual(links[0].line, 4)

    def test_inline_code_is_ignored(self):
        links = extract_links("`[坏](x.md)` 与 [好](y.md)")
        self.assertEqual([link.target for link in links], ["y.md"])

    def test_reference_definition(self):
        links = extract_links('[ref]: https://example.com "标题"\n')
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].text, "ref")
        self.assertEqual(links[0].target, "https://example.com")

    def test_title_is_not_part_of_target(self):
        links = extract_links('[a](docs/a.md "标题")')
        self.assertEqual(links[0].target, "docs/a.md")

    def test_angle_bracket_target(self):
        links = extract_links("[a](<docs/a.md>)")
        self.assertEqual(links[0].target, "docs/a.md")

    def test_multiple_links_are_sorted(self):
        links = extract_links("[a](a.md)\n[b](b.md)\n[c](c.md)")
        self.assertEqual([link.target for link in links], ["a.md", "b.md", "c.md"])

    def test_strip_code_keeps_line_count(self):
        text = "```\na\nb\n```\n正文"
        self.assertEqual(strip_code(text).count("\n"), text.count("\n"))

    def test_non_string_input(self):
        with self.assertRaises(TypeError):
            extract_links(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
