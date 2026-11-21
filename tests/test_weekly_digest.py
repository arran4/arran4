import io
import unittest
from datetime import datetime
from scripts.weekly_digest import render_report


class Repo:
    def __init__(self, name, *, star=False, added=False, release=None,
                 old_release=None, desc='unchanged', old_desc='unchanged',
                 tags=(), old_tags=()):
        self.key = self.name = name
        self.old_name = None if added else name
        self.repo_url = f'https://github.com/{name}'
        self.old_repo_url = None if added else self.repo_url
        self.homepage = self.old_homepage = None
        self.desc, self.old_desc = desc, (None if added else old_desc)
        self.tags, self.old_tags = tags, old_tags
        self.license = self.old_license = None
        self.release, self.old_release = release, old_release
        self.has_new, self.has_old = True, not added
        self.is_star = star
        self.source_lists = {'latest release'} if star else {'extra info'}

    def get_tags_set(self, is_new):
        return set(self.tags if is_new else self.old_tags)


def dates(value):
    if value and '(' in value:
        return datetime.strptime(value.split('(')[-1].rstrip(')'), '%Y-%m-%d')


def links(release, url):
    return release.split(' (')[0] if release else ''


def render(*repos):
    out = io.StringIO()
    render_report({r.key: r for r in repos}, {}, lambda r, languages: f'### {r.key}\nFull description',
                  dates, links, lambda s: s, out=out)
    return out.getvalue()


class TestWeeklyDigest(unittest.TestCase):
    def test_release_summary_keeps_comparisons_without_appendix(self):
        repo = Repo('example/repo', release='v2 (2026-11-14)',
                    old_release='v1 (2026-01-01)', desc='new description',
                    old_desc='old description', tags=('new',), old_tags=('old',))
        text = render(repo)
        self.assertIn('| Latest-release changes | 1 |', text)
        self.assertIn('Long-gap releases (100+ days)', text)
        self.assertIn('`v1` → `v2` (+317d)', text)
        self.assertIn('Topics and tags (+added, −removed)', text)
        self.assertIn('+`new`, −`old`', text)
        self.assertIn('<details>', text)
        self.assertNotIn('## Detailed Repository Changes', text)
        self.assertNotIn('Full description', text)
        self.assertIn('**Before:** old description', text)
        self.assertIn('**After:** new description', text)
        self.assertTrue(text.endswith('</details>\n'))

    def test_new_star_has_description_and_release(self):
        star = Repo('example/star', star=True, added=True, desc='Useful tool',
                    release='v4 (2026-11-12)')
        text = render(star)
        self.assertIn('| New stars | 1 |', text)
        self.assertIn('Useful tool; latest v4', text)
        self.assertIn('| Latest-release changes | 0 |', text)

    def test_all_release_comparisons_visible_without_truncation(self):
        repos = [Repo(f'example/r{i:02}', release='v2 (2026-11-14)',
                      old_release='v1 (2026-11-01)') for i in range(20)]
        text = render(*repos)
        self.assertNotIn('more in the detailed records', text)
        self.assertEqual(text.count('`v1` → `v2`'), 20)
        self.assertEqual(text.count('example/r'), 20)

    def test_full_description_is_not_truncated(self):
        old = 'Old version ' + 'a' * 250
        new = 'New version ' + 'b' * 250
        text = render(Repo('example/long', desc=new, old_desc=old))
        self.assertIn(old, text)
        self.assertIn(new, text)
        self.assertNotIn('…', text)

    def test_empty_change_set(self):
        self.assertIn('No tracked repository changes', render())


if __name__ == '__main__':
    unittest.main()
