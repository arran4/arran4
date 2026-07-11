import sys
import re
import difflib
from collections import defaultdict
from datetime import datetime

def escape_md(text):
    if not text: return ""
    res = text.replace("\\", "\\\\")
    for c in "_*`[]<>":
        res = res.replace(c, "\\" + c)
    return res

def format_change(text, tag_start, tag_end, escape_func):
    if not text: return ""
    match = re.match(r'^(\s*)(.*?)(\s*)$', text, re.DOTALL)
    if match:
        leading, core, trailing = match.groups()
        if core:
            return f"{leading}{tag_start}{escape_func(core)}{tag_end}{trailing}"
        else:
            return f"{leading}{trailing}"
    return f"{tag_start}{escape_func(text)}{tag_end}"

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
            res_new.append(format_change(new_str[b0:b1], "**", "**", escape_md))
        elif opcode == 'delete':
            res_old.append(format_change(old_str[a0:a1], "~~", "~~", escape_md))
        elif opcode == 'replace':
            res_old.append(format_change(old_str[a0:a1], "~~", "~~", escape_md))
            res_new.append(format_change(new_str[b0:b1], "**", "**", escape_md))

    return "".join(res_old), "".join(res_new)

def parse_release_tag(info_str):
    if not isinstance(info_str, str) or not info_str:
        return ""
    return re.sub(r'\s*\(\d{4}-\d{2}-\d{2}\)\s*$', '', info_str).strip()

def parse_date(info_str):
    if not isinstance(info_str, str):
        return None
    m = re.search(r'\((\d{4}-\d{2}-\d{2})\)', info_str)
    if m:
        try:
            return datetime.strptime(m.group(1), '%Y-%m-%d')
        except ValueError:
            pass
    return None

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
        tags_str = re.sub(r'\s*\+\s*', ', ', self.tags)
        return set([t.strip() for t in tags_str.split(',') if t.strip()])

def main():
    files_changed = {}
    license_changes_summary = []
    description_changes_summary = []
    tag_changes_summary = []
    homepage_changes_summary = []
    owner_rename_changes_summary = []
    latest_release_changes_summary = []
    extra_info_changes_summary = []
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
                repo_link = f"[{a.name}]({a.repo_url})" if a.repo_url else a.name
                changes_list = []
                if d.name != a.name:
                    if d.repo_only == a.repo_only and d.owner != a.owner:
                        changes_list.append(f"Changed owner from `{d.owner}` to `{a.owner}`")
                        owner_rename_changes_summary.append(f"- {repo_link}: Changed owner from `{d.owner}` to `{a.owner}`")
                    else:
                        changes_list.append(f"Renamed from `{d.name}` to `{a.name}`")
                        owner_rename_changes_summary.append(f"- {repo_link}: Renamed from `{d.name}` to `{a.name}`")
                d_desc_clean = d.desc if d.desc else ''
                a_desc_clean = a.desc if a.desc else ''
                if d_desc_clean != a_desc_clean:
                    if not d_desc_clean and a_desc_clean:
                        changes_list.append(f"Added description:\n\n> {escape_md(a_desc_clean)}\n\n")
                        description_changes_summary.append(f"- {repo_link}: Added description:\n  > {escape_md(a_desc_clean).replace('\n', '\n  > ')}")
                    elif d_desc_clean and not a_desc_clean:
                        changes_list.append(f"Removed description")
                        description_changes_summary.append(f"- {repo_link}: Removed description")
                    else:
                        bold_old, bold_new = bold_difference(d_desc_clean, a_desc_clean)
                        changes_list.append(f"Updated description:\n\n> \\- {bold_old}\n> \\+ {bold_new}\n\n")
                        description_changes_summary.append(f"- {repo_link}: Updated description:\n  > \\- {bold_old.replace('\n', '\n  > ')}\n  > \\+ {bold_new.replace('\n', '\n  > ')}")
                if d.homepage != a.homepage:
                    if d.homepage or a.homepage:
                        changes_list.append(f"Updated homepage from `{d.homepage}` to `{a.homepage}`")
                        homepage_changes_summary.append(f"- {repo_link}: Updated homepage from `{d.homepage}` to `{a.homepage}`")
                if d.extra_info != a.extra_info:
                    if info_name == "latest release":
                        d_tag = parse_release_tag(d.extra_info)
                        a_tag = parse_release_tag(a.extra_info)
                        if d.extra_info and a.extra_info and d_tag != a_tag:
                            d_date = parse_date(d.extra_info)
                            a_date = parse_date(a.extra_info)
                            days_diff_str = ""
                            days_diff = -1
                            if d_date and a_date:
                                days_diff = (a_date - d_date).days
                                days_diff_str = f"{days_diff} days"

                            group_type = "Changed latest release (>= 100 days)" if days_diff >= 100 else "Changed latest release"
                            changes_list.append({
                                "type": group_type,
                                "prev": d.extra_info,
                                "curr": a.extra_info,
                                "days": days_diff_str
                            })
                            change_text = f"- {repo_link}: Changed latest release from `{d.extra_info}` to `{a.extra_info}`"
                            if days_diff_str:
                                change_text += f" ({days_diff_str.strip()})"

                            latest_release_changes_summary.append({
                                'date': a_date,
                                'name': a.name,
                                'text': change_text
                            })
                        elif d.extra_info and a.extra_info:
                            changes_list.append(f"Updated latest release metadata from `{d.extra_info}` to `{a.extra_info}`")
                        elif a.extra_info:
                            changes_list.append(f"Added latest release metadata: `{a.extra_info}`")
                        elif d.extra_info:
                            changes_list.append(f"Removed latest release metadata: `{d.extra_info}`")
                    elif not d.extra_info:
                        changes_list.append(f"Added {info_name}: `{a.extra_info}`")
                        if info_name == "license":
                            license_changes_summary.append(f"- {repo_link}: Added license `{a.extra_info}`")
                        else:
                            extra_info_changes_summary.append(f"- {repo_link}: Added {info_name} `{a.extra_info}`")
                    elif not a.extra_info:
                        changes_list.append(f"Removed {info_name}: `{d.extra_info}`")
                        if info_name == "license":
                            license_changes_summary.append(f"- {repo_link}: Removed license `{d.extra_info}`")
                        else:
                            extra_info_changes_summary.append(f"- {repo_link}: Removed {info_name} `{d.extra_info}`")
                    else:
                        changes_list.append(f"Changed {info_name} from `{d.extra_info}` to `{a.extra_info}`")
                        if info_name == "license":
                            license_changes_summary.append(f"- {repo_link}: Changed license from `{d.extra_info}` to `{a.extra_info}`")
                        else:
                            extra_info_changes_summary.append(f"- {repo_link}: Changed {info_name} from `{d.extra_info}` to `{a.extra_info}`")

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
                    changes_str = f"Updated tags by {' and '.join(tag_changes)}"
                    changes_list.append(changes_str)
                    tag_changes_summary.append(f"- {repo_link}: {changes_str}")

                if not changes_list:
                    changes_list.append("Row formatted or modified")

                # Categorize the change
                if len(changes_list) == 1:
                    change_cat = changes_list[0]
                    if isinstance(change_cat, dict):
                        change_groups[change_cat["type"]].append((a, change_cat))
                    else:
                        # To group by generic change categories
                        if change_cat.startswith(f"Removed {info_name}:") or change_cat.startswith("Removed latest release metadata:"):
                            change_groups[f"Removed {info_name}"].append((a, change_cat))
                        elif change_cat.startswith(f"Added {info_name}:") or change_cat.startswith("Added latest release metadata:"):
                            change_groups[f"Added {info_name}"].append((a, change_cat))
                        elif change_cat.startswith(f"Changed {info_name}"):
                            change_groups[f"Changed {info_name}"].append((a, change_cat))
                        elif change_cat.startswith("Updated latest release metadata"):
                            change_groups["Updated latest release metadata"].append((a, change_cat))
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

                if group_name in ("Changed latest release", "Changed latest release (>= 100 days)"):
                    output.append("| Repository | Previous | Current | Time Since Last |")
                    output.append("|---|---|---|---|")
                    for a, change in items:
                        output.append(f"| [{a.name}]({a.repo_url}) | {change['prev']} | {change['curr']} | {change['days']} |")
                else:
                    for a, change in items:
                        if isinstance(change, list):
                            output.append(f"- [{a.name}]({a.repo_url}):")
                            for c in change:
                                if isinstance(c, dict):
                                    c_str = f"Changed latest release from `{c['prev']}` to `{c['curr']}`"
                                    if c.get('days'):
                                        c_str += f" ({c['days']})"
                                else:
                                    c_str = c
                                if '\n' in c_str:
                                    formatted_change = c_str.strip().replace('\n', '\n    ')
                                    output.append(f"  - {formatted_change}")
                                else:
                                    output.append(f"  - {c_str}")
                        else:
                            if '\n' in change:
                                formatted_change = change.strip().replace('\n', '\n  ')
                                output.append(f"- [{a.name}]({a.repo_url}):\n  - {formatted_change}")
                            else:
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

        if license_changes_summary:
            print("\n**License Changes:**\n")
            print("\n".join(license_changes_summary))

        if description_changes_summary:
            print("\n**Description Changes:**\n")
            print("\n".join(description_changes_summary))

        if tag_changes_summary:
            print("\n**Tag Changes:**\n")
            print("\n".join(tag_changes_summary))

        if homepage_changes_summary:
            print("\n**Homepage Changes:**\n")
            print("\n".join(homepage_changes_summary))

        if owner_rename_changes_summary:
            print("\n**Owner/Rename Changes:**\n")
            print("\n".join(owner_rename_changes_summary))

        if latest_release_changes_summary:
            print("\n**Latest Release Changes:**\n")
            grouped_releases = defaultdict(list)
            for item in latest_release_changes_summary:
                d_str = item['date'].strftime('%Y-%m-%d') if item['date'] else "Unknown Date"
                grouped_releases[d_str].append(item)

            sorted_dates = sorted(
                grouped_releases.keys(),
                key=lambda x: (1, x) if x != "Unknown Date" else (0, ""),
                reverse=True
            )

            for d_str in sorted_dates:
                print(f"- **{d_str}**")
                items = sorted(grouped_releases[d_str], key=lambda x: x['name'].lower())
                for item in items:
                    print(f"  {item['text']}")

        if extra_info_changes_summary:
            print("\n**Other Info Changes:**\n")
            print("\n".join(extra_info_changes_summary))

        print("\n### Detailed Repository Changes\n")

        details_str = "\n".join(output)
        if len(details_str) > 60000:
            truncate_index = details_str.rfind('\n', 0, 60000)
            if truncate_index == -1:
                truncate_index = 60000
            print(details_str[:truncate_index])
            print("\n... (Detailed changes truncated due to GitHub limits) ...")
        else:
            print(details_str)

if __name__ == '__main__':
    main()
