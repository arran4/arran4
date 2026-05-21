import sys
import re

class Row:
    def __init__(self, line):
        self.line = line
        parts = line.strip().split('|')
        if len(parts) > 1 and parts[0].strip() == '':
            parts = parts[1:]
        if len(parts) > 0 and parts[-1].strip() == '':
            parts = parts[:-1]

        self.cols = [c.strip() for c in parts]
        col0 = self.cols[0] if len(self.cols) > 0 else ""

        links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', col0)
        self.name = links[0][0] if len(links) > 0 else col0.strip()
        self.repo_url = links[0][1] if len(links) > 0 else ""
        self.homepage = links[1][1] if len(links) > 1 else ""

        self.repo_only = self.name.split('/')[-1] if '/' in self.name else self.name
        self.owner = self.name.split('/')[0] if '/' in self.name else ""

        self.desc = self.cols[1] if len(self.cols) > 1 else ""
        self.tags = self.cols[-1] if len(self.cols) > 2 else ""
        if len(self.cols) > 3:
             self.license = self.cols[2]
             self.tags = self.cols[3]
        else:
             self.license = ""
             self.tags = self.cols[2] if len(self.cols) > 2 else ""

    def get_tags_set(self):
        if not self.tags: return set()
        return set([t.strip() for t in self.tags.split(',') if t.strip()])

def main():
    diff_text = sys.stdin.read()
    if not diff_text:
        return

    files_changed = {}
    current_file = None

    for line in diff_text.split('\n'):
        if line.startswith('+++ b/'):
            current_file = line[6:]
            files_changed[current_file] = {'add': [], 'del': []}
        elif line.startswith('+') and not line.startswith('+++'):
            content = line[1:].strip()
            if current_file and content.startswith('|') and '---|' not in content and '| Repository |' not in content:
                files_changed[current_file]['add'].append(Row(content))
        elif line.startswith('-') and not line.startswith('---'):
            content = line[1:].strip()
            if current_file and content.startswith('|') and '---|' not in content and '| Repository |' not in content:
                files_changed[current_file]['del'].append(Row(content))

    output = []
    for filename, changes in files_changed.items():
        adds = changes['add']
        dels = changes['del']

        if not adds and not dels:
            continue

        output.append(f"### Changes in `{filename}`\n")

        matched_adds = set()
        matched_dels = set()
        updates = []

        # Exact name
        for i, d in enumerate(dels):
            for j, a in enumerate(adds):
                if j in matched_adds: continue
                if d.name == a.name:
                    updates.append((d, a))
                    matched_dels.add(i)
                    matched_adds.add(j)
                    break

        # repo_only and desc
        for i, d in enumerate(dels):
            if i in matched_dels: continue
            for j, a in enumerate(adds):
                if j in matched_adds: continue
                if d.repo_only == a.repo_only and d.desc == a.desc:
                    updates.append((d, a))
                    matched_dels.add(i)
                    matched_adds.add(j)
                    break

        # repo_only
        for i, d in enumerate(dels):
            if i in matched_dels: continue
            for j, a in enumerate(adds):
                if j in matched_adds: continue
                if d.repo_only == a.repo_only:
                    updates.append((d, a))
                    matched_dels.add(i)
                    matched_adds.add(j)
                    break

        for j, a in enumerate(adds):
            if j not in matched_adds:
                output.append(f"- **Added** [{a.name}]({a.repo_url}): {a.desc}")

        for i, d in enumerate(dels):
            if i not in matched_dels:
                output.append(f"- **Removed** [{d.name}]({d.repo_url})")

        for d, a in updates:
            changes_list = []
            if d.name != a.name:
                if d.repo_only == a.repo_only and d.owner != a.owner:
                    changes_list.append(f"Changed owner from `{d.owner}` to `{a.owner}`")
                else:
                    changes_list.append(f"Renamed from `{d.name}` to `{a.name}`")
            if d.desc != a.desc:
                changes_list.append(f"Updated description")
            if d.homepage != a.homepage:
                if d.homepage or a.homepage:
                    changes_list.append(f"Updated homepage from `{d.homepage}` to `{a.homepage}`")
            if d.license != a.license:
                changes_list.append(f"Changed license from `{d.license}` to `{a.license}`")

            d_tags = d.get_tags_set()
            a_tags = a.get_tags_set()
            if d_tags != a_tags:
                added_tags = a_tags - d_tags
                removed_tags = d_tags - a_tags
                tag_changes = []
                if removed_tags:
                    tag_changes.append(f"removing `{', '.join(sorted(removed_tags))}`")
                if added_tags:
                    tag_changes.append(f"adding `{', '.join(sorted(added_tags))}`")
                changes_list.append(f"Updated tags by {' and '.join(tag_changes)}")

            if not changes_list:
                changes_list.append("Row formatted or modified")

            output.append(f"- **Updated** [{a.name}]({a.repo_url}): {'; '.join(changes_list)}")

        output.append("\n")

    if output:
        print("\n".join(output))

if __name__ == '__main__':
    main()
