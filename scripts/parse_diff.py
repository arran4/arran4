import sys
import re
import difflib
from collections import defaultdict

def escape_md(text):
    if not text: return ""
    res = text.replace("\\", "\\\\")
    for c in "_*`[]<>":
        res = res.replace(c, "\\" + c)
    return res

def bold_difference(old_str, new_str):
    old_str = old_str or ""
    new_str = new_str or ""
    if not old_str and not new_str:
        return "", ""

    sm = difflib.SequenceMatcher(None, old_str, new_str)
    res_old = []
    res_new = []
    for opcode, a0, a1, b0, b1 in sm.get_opcodes():
        if opcode == 'equal':
            res_old.append(escape_md(old_str[a0:a1]))
            res_new.append(escape_md(new_str[b0:b1]))
        elif opcode == 'insert':
            res_new.append(f"**{escape_md(new_str[b0:b1])}**")
        elif opcode == 'delete':
            res_old.append(f"~~{escape_md(old_str[a0:a1])}~~")
        elif opcode == 'replace':
            res_old.append(f"~~{escape_md(old_str[a0:a1])}~~")
            res_new.append(f"**{escape_md(new_str[b0:b1])}**")

    return "".join(res_old), "".join(res_new)

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
            self.extra_info = self.cols[2]
        else:
            self.extra_info = ""

    def get_tags_set(self):
        if not self.tags: return set()
        return set([t.strip() for t in self.tags.split(',') if t.strip()])

def main():
    files_changed = {}
    current_file = None

    for line in sys.stdin:
        line = line.rstrip('\n')
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

    summary_output = []
    output = []
    for filename, changes in files_changed.items():
        adds = changes['add']
        dels = changes['del']

        if not adds and not dels:
            continue

        import os
        base_name = os.path.basename(filename)
        file_title = base_name.split('.')[0].capitalize()
        if base_name.lower() == 'readme.md':
            file_title = 'README'
        elif base_name.lower() == 'licenses.md':
            file_title = 'Licenses'
        elif base_name.lower() == 'starred.md':
            file_title = 'Starred'

        output.append(f"# {file_title}\n")

        matched_adds = set()
        matched_dels = set()
        updates = []

        # Matching heuristics
        match_criteria = [
            lambda d, a: d.name == a.name,
            lambda d, a: d.repo_only == a.repo_only and d.desc == a.desc,
            lambda d, a: d.repo_only == a.repo_only
        ]
        for criteria in match_criteria:
            for d_idx, d in enumerate(dels):
                if d_idx in matched_dels: continue
                for a_idx, a in enumerate(adds):
                    if a_idx in matched_adds: continue
                    if criteria(d, a):
                        updates.append((d, a))
                        matched_dels.add(d_idx)
                        matched_adds.add(a_idx)
                        break

        unmatched_adds = [a for a_idx, a in enumerate(adds) if a_idx not in matched_adds]
        if unmatched_adds:
            output.append("## Added\n")
            for a in unmatched_adds:
                if a.desc:
                    output.append(f"- [{a.name}]({a.repo_url}): {a.desc}")
                else:
                    output.append(f"- [{a.name}]({a.repo_url})")
            output.append("")

        if updates:
            output.append("## Modified\n")
            change_groups = defaultdict(list)
            info_name = "extra info"
            if base_name.lower() == 'licenses.md':
                info_name = "license"
            elif base_name.lower() == 'starred.md':
                info_name = "latest release"

            for d, a in updates:
                changes_list = []
                if d.name != a.name:
                    if d.repo_only == a.repo_only and d.owner != a.owner:
                        changes_list.append(f"Changed owner from `{d.owner}` to `{a.owner}`")
                    else:
                        changes_list.append(f"Renamed from `{d.name}` to `{a.name}`")
                d_desc_clean = d.desc if d.desc else ''
                a_desc_clean = a.desc if a.desc else ''
                if d_desc_clean != a_desc_clean:
                    if not d_desc_clean and a_desc_clean:
                        changes_list.append(f"Added description:\n\n> {escape_md(a_desc_clean)}\n\n")
                    elif d_desc_clean and not a_desc_clean:
                        changes_list.append(f"Removed description")
                    else:
                        bold_old, bold_new = bold_difference(d_desc_clean, a_desc_clean)
                        changes_list.append(f"Updated description:\n\n> - {bold_old}\n> + {bold_new}\n\n")
                if d.homepage != a.homepage:
                    if d.homepage or a.homepage:
                        changes_list.append(f"Updated homepage from `{d.homepage}` to `{a.homepage}`")
                if d.extra_info != a.extra_info:
                    if not d.extra_info:
                        changes_list.append(f"Added {info_name}: `{a.extra_info}`")
                    elif not a.extra_info:
                        changes_list.append(f"Removed {info_name}: `{d.extra_info}`")
                    else:
                        changes_list.append(f"Changed {info_name} from `{d.extra_info}` to `{a.extra_info}`")

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

                # Categorize the change
                if len(changes_list) == 1:
                    change_cat = changes_list[0]
                    # To group by generic change categories, e.g. 'Removed latest release' instead of 'Removed latest release: v1.0.0'
                    if change_cat.startswith(f"Removed {info_name}:"):
                        change_groups[f"Removed {info_name}"].append((a, change_cat))
                    elif change_cat.startswith(f"Added {info_name}:"):
                        change_groups[f"Added {info_name}"].append((a, change_cat))
                    elif change_cat.startswith(f"Changed {info_name}"):
                        change_groups[f"Changed {info_name}"].append((a, change_cat))
                    elif change_cat.startswith("Updated tags"):
                        change_groups["Updated tags"].append((a, change_cat))
                    elif change_cat.startswith("Updated description"):
                        change_groups["Updated description"].append((a, change_cat))
                    elif change_cat.startswith("Added description"):
                        change_groups["Added description"].append((a, change_cat))
                    elif change_cat.startswith("Removed description"):
                        change_groups["Removed description"].append((a, change_cat))
                    elif change_cat.startswith("Changed owner"):
                        change_groups["Changed owner"].append((a, change_cat))
                    elif change_cat.startswith("Renamed from"):
                        change_groups["Renamed repository"].append((a, change_cat))
                    elif change_cat.startswith("Updated homepage"):
                        change_groups["Updated homepage"].append((a, change_cat))
                    elif change_cat == "Row formatted or modified":
                        change_groups["Row formatted or modified"].append((a, change_cat))
                    else:
                        change_groups["Other changes"].append((a, change_cat))
                else:
                    change_groups["Multiple changes"].append((a, changes_list))

            # Now output grouped changes
            for group_name, items in sorted(change_groups.items()):
                output.append(f"### {group_name}\n")

                wrap_in_details = len(items) > 15
                if wrap_in_details:
                    output.append(f"<details><summary>View {len(items)} repositories</summary>\n")

                for a, change in items:
                    if isinstance(change, list):
                        output.append(f"- [{a.name}]({a.repo_url}):")
                        for c in change:
                            if '\n' in c:
                                formatted_change = c.strip().replace('\n', '\n    ')
                                output.append(f"  - {formatted_change}")
                            else:
                                output.append(f"  - {c}")
                    else:
                        if '\n' in change:
                            # For single changes with newlines (like added/updated description)
                            formatted_change = change.strip().replace('\n', '\n  ')
                            output.append(f"- [{a.name}]({a.repo_url}):\n  - {formatted_change}")
                        else:
                            # If we grouped by category, the full change message is still here
                            output.append(f"- [{a.name}]({a.repo_url}): {change}")

                if wrap_in_details:
                    output.append("\n</details>\n")
                else:
                    output.append("")

        unmatched_dels = [d for d_idx, d in enumerate(dels) if d_idx not in matched_dels]
        if unmatched_dels:
            output.append("## Removed\n")
            for d in unmatched_dels:
                output.append(f"- [{d.name}]({d.repo_url})")
            output.append("")

        num_added = len(adds) - len(matched_adds)
        num_removed = len(dels) - len(matched_dels)
        num_updated = len(updates)

        parts = []
        if num_added > 0:
            parts.append(f"{num_added} added")
        if num_removed > 0:
            parts.append(f"{num_removed} removed")
        if num_updated > 0:
            parts.append(f"{num_updated} updated")

        if parts:
            summary_output.append(f"- `{filename}`: {', '.join(parts)}")

    if summary_output:
        print("**Repository Changes Summary:**\n")
        print("\n".join(summary_output))
        print("\n<details><summary>Detailed Repository Changes</summary>\n")

        details_str = "\n".join(output)
        if len(details_str) > 60000:
            truncate_index = details_str.rfind('\n', 0, 60000)
            if truncate_index == -1:
                truncate_index = 60000
            print(details_str[:truncate_index])
            print("\n... (Detailed changes truncated due to GitHub limits) ...")
        else:
            print(details_str)

        print("\n</details>\n")

if __name__ == '__main__':
    main()
