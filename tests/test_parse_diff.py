import unittest
import io
import sys
from scripts.parse_diff import main, RepoChange, Row

class TestParseDiff(unittest.TestCase):
    def test_end_to_end_parse(self):
        diff_input = """+++ b/README.md
@@ -1,2 +1,2 @@
 | Repository | Description | Tags |
 |---|---|---|
-| [user/repo](https://github.com/user/repo) | old_desc_with_chars * | tag5 |
+| [user2/repo](https://github.com/user2/repo) | new_desc | tag5, tag6 |
"""

        # Save standard output and standard input
        original_stdout = sys.stdout
        original_stdin = sys.stdin

        try:
            sys.stdin = io.StringIO(diff_input)
            sys.stdout = io.StringIO()

            main(sys.stdin)

            output = sys.stdout.getvalue()

            # Check for header
            self.assertIn("| Description changes | 1 |", output)
            self.assertIn("| Topic/tag changes | 1 |", output)
            self.assertIn("## Detailed Repository Changes", output)
            self.assertIn("<details>", output)
            self.assertIn("<summary>Expand all 1 repository records", output)

            # Check for repo output
            self.assertIn("### [user2/repo](https://github.com/user2/repo) (Formerly: [user/repo](https://github.com/user/repo))", output)
            self.assertIn("**Description:** **new**\\_desc (Formerly: ~~old~~\\_desc~~\\_with\\_chars \\*~~)", output)
            self.assertIn("**Tags:** tag5, **+tag6**", output)
        finally:
            sys.stdout = original_stdout
            sys.stdin = original_stdin

if __name__ == '__main__':
    unittest.main()
