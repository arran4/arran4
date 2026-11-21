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

            # Check for change-only comparisons within the PR description
            self.assertIn("**Descriptions (1)**", output)
            self.assertIn("**Before:**", output)
            self.assertIn("**After:**", output)
            self.assertIn("+`tag6`", output)
            self.assertNotIn("Detailed Repository Changes", output)
            self.assertNotIn("weekly-repo-details.md", output)
        finally:
            sys.stdout = original_stdout
            sys.stdin = original_stdin

if __name__ == '__main__':
    unittest.main()
