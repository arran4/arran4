import unittest
from datetime import datetime
from scripts.parse_diff import parse_date, escape_md, bold_difference, Row

class TestParseDiff(unittest.TestCase):
    def test_parse_date(self):
        # Valid date
        self.assertEqual(parse_date("v1.0.0 (2024-03-01)"), datetime(2024, 3, 1))

        # Invalid input type
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date(123))

        # Missing date format
        self.assertIsNone(parse_date("v1.0.0"))

        # Invalid date values
        self.assertIsNone(parse_date("(2024-13-01)")) # Invalid month
        self.assertIsNone(parse_date("(2024-03-32)")) # Invalid day

    def test_escape_md(self):
        self.assertEqual(escape_md(""), "")
        self.assertEqual(escape_md("normal text"), "normal text")
        self.assertEqual(escape_md("text_with*markdown[chars]"), r"text\_with\*markdown\[chars\]")

    def test_bold_difference(self):
        old_str = "hello world"
        new_str = "hello brave world"
        old_res, new_res = bold_difference(old_str, new_str)
        self.assertEqual(old_res, "hello world")
        self.assertEqual(new_res, "hello **brave **world")

    def test_row_parsing(self):
        # A typical markdown table row
        line = "| [repo](https://github.com/a/repo) [🔗](http://a.com) | desc | v1.0.0 (2024-01-01) | tag1, tag2 |"
        row = Row(line)
        self.assertEqual(row.name, "repo")
        self.assertEqual(row.repo_url, "https://github.com/a/repo")
        self.assertEqual(row.homepage, "http://a.com")
        self.assertEqual(row.desc, "desc")
        self.assertEqual(row.extra_info, "v1.0.0 (2024-01-01)")
        self.assertEqual(row.tags, "tag1, tag2")
        self.assertEqual(row.get_tags_set(), {"tag1", "tag2"})

if __name__ == '__main__':
    unittest.main()
