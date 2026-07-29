import sys
import re
import difflib
from collections import defaultdict
from datetime import datetime
import json
import os

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
    tag_str = re.sub(r'\s*\(\d{4}-\d{2}-\d{2}\)\s*$', '', info_str).strip()
    m = re.match(r'^\[(.*?)\]\(.*?\)$', tag_str)
    if m:
        return m.group(1)
    return tag_str

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

class RepoChange:
    def __init__(self):
        self.name = None
        self.old_name = None
        self.repo_url = None
        self.old_repo_url = None
        self.homepage = None
        self.old_homepage = None
        self.desc = None
        self.old_desc = None
        self.tags = None
        self.old_tags = None
        self.license = None
        self.old_license = None
        self.release = None
        self.old_release = None
        self.has_old = False
        self.has_new = False
        self.source_lists = set()

    def merge_row(self, row, is_new, info_name):
        self.source_lists.add(info_name)
        if not self.name and is_new:
            self.name = row.name
        if not self.old_name and not is_new:
            self.old_name = row.name

        if is_new:
            self.has_new = True
            self.repo_url = row.repo_url
            self.homepage = row.homepage
            self.desc = row.desc
            self.tags = row.tags
            if info_name == 'license':
                self.license = row.extra_info
            elif info_name == 'latest release':
                self.release = row.extra_info
        else:
            self.has_old = True
            self.old_repo_url = row.repo_url
            self.old_homepage = row.homepage
            self.old_desc = row.desc
            self.old_tags = row.tags
            if info_name == 'license':
                self.old_license = row.extra_info
            elif info_name == 'latest release':
                self.old_release = row.extra_info

    @property
    def key(self):
        return self.name or self.old_name

    def get_tags_set(self, is_new):
        tags = self.tags if is_new else self.old_tags
        if not tags: return set()
        tags_str = re.sub(r'\s*\+\s*', ', ', tags)
        return set([t.strip() for t in tags_str.split(',') if t.strip()])


def format_card(repo, languages):
    output = []

    # Icons
    icons = []
    if 'latest release' in repo.source_lists:
        icons.append("⭐")
    if 'license' in repo.source_lists:
        icons.append("⚖️")
    icon_str = " ".join(icons) + " " if icons else ""

    # Header
    if repo.has_new:
        name_str = f"[{repo.name}]({repo.repo_url})" if repo.repo_url else repo.name
    else:
        name_str = f"[{repo.old_name}]({repo.old_repo_url})" if repo.old_repo_url else repo.old_name

    if repo.has_old and repo.has_new and repo.old_name and repo.old_name != repo.name:
        old_name_str = f"[{repo.old_name}]({repo.old_repo_url})" if repo.old_repo_url else repo.old_name
        output.append(f"### {icon_str}{name_str} (Formerly: {old_name_str})")
    elif repo.has_old and not repo.has_new:
        output.append(f"### {icon_str}~~{name_str}~~")
    else:
        output.append(f"### {icon_str}{name_str}")

    # Determine reasons
    reasons = []
    if not repo.has_old and repo.has_new:
        reasons.append("New Repo")
    elif repo.has_old and not repo.has_new:
        reasons.append("Removed Repo")
    else:
        if repo.desc != repo.old_desc: reasons.append("Updated Description")
        if repo.get_tags_set(False) != repo.get_tags_set(True): reasons.append("Updated Tags")
        if repo.homepage != repo.old_homepage: reasons.append("Updated URL")
        if repo.license != repo.old_license: reasons.append("Updated License")
        if repo.release != repo.old_release: reasons.append("New Release")
        if repo.name != repo.old_name or repo.repo_url != repo.old_repo_url:
            reasons.append("Renamed/Moved")

    if reasons:
        output.append(f"**Reason:** {', '.join(reasons)}")

    # Language
    repo_key = repo.key
    if repo_key in languages:
        output.append(f"**Language:** {languages[repo_key]}")

    def format_label(label, has_changed):
        return f"**{label}:**" if has_changed else f"{label}:"

    # Description
    desc_changed = repo.has_old and repo.has_new and repo.desc != repo.old_desc
    desc_label = format_label("Description", desc_changed)
    if repo.has_old and repo.has_new:
        if repo.desc != repo.old_desc:
            old_bold, new_bold = bold_difference(repo.old_desc, repo.desc)
            if len(new_bold) > 50 or '\n' in new_bold:
                output.append(f"{desc_label} \n> \\- {old_bold}\n> \\+ {new_bold}")
            else:
                output.append(f"{desc_label} {new_bold} (Formerly: {old_bold})")
        else:
            output.append(f"{desc_label} {repo.desc}")
    elif repo.has_new:
        output.append(f"{desc_label} {repo.desc}")
    elif repo.has_old:
        output.append(f"{desc_label} ~~{repo.old_desc}~~")

    # License
    lic_changed = repo.has_old and repo.has_new and repo.license != repo.old_license
    lic_label = format_label("License", lic_changed)
    if (repo.has_new and repo.license) or (repo.has_old and repo.old_license):
        if repo.has_old and repo.has_new:
            if repo.license != repo.old_license:
                if not repo.license:
                    output.append(f"{lic_label} (Removed) (Formerly: `{repo.old_license}`)")
                elif not repo.old_license:
                    output.append(f"{lic_label} `{repo.license}` (Newly added)")
                else:
                    output.append(f"{lic_label} `{repo.license}` (Formerly: `{repo.old_license}`)")
            else:
                if repo.license:
                    output.append(f"{lic_label} `{repo.license}`")
        elif repo.has_new:
            output.append(f"{lic_label} `{repo.license}`")
        elif repo.has_old:
            output.append(f"{lic_label} ~~`{repo.old_license}`~~")

    # Tags
    tags_changed = repo.has_old and repo.has_new and repo.get_tags_set(False) != repo.get_tags_set(True)
    tags_label = format_label("Tags", tags_changed)
    if repo.has_old and repo.has_new:
        d_tags = repo.get_tags_set(False)
        a_tags = repo.get_tags_set(True)
        if d_tags != a_tags:
            added = a_tags - d_tags
            removed = d_tags - a_tags
            kept = a_tags & d_tags

            tag_strs = []
            for t in sorted(kept):
                tag_strs.append(t)
            for t in sorted(added):
                tag_strs.append(f"**+{t}**")
            for t in sorted(removed):
                tag_strs.append(f"~~-{t}~~")
            output.append(f"{tags_label} {', '.join(tag_strs)}")
        else:
            if repo.tags:
                output.append(f"{tags_label} {repo.tags}")
    elif repo.has_new:
        if repo.tags:
            output.append(f"{tags_label} {repo.tags}")
    elif repo.has_old:
        if repo.old_tags:
            output.append(f"{tags_label} ~~{repo.old_tags}~~")

    # URL / Homepage
    url_changed = repo.has_old and repo.has_new and repo.homepage != repo.old_homepage
    url_label = format_label("URL", url_changed)
    if (repo.has_new and repo.homepage) or (repo.has_old and repo.old_homepage):
        if repo.has_old and repo.has_new:
            if repo.homepage != repo.old_homepage:
                hp = f"[{repo.homepage}]({repo.homepage})" if repo.homepage else "(None)"
                old_hp = f"[{repo.old_homepage}]({repo.old_homepage})" if repo.old_homepage else "(None)"
                output.append(f"{url_label} {hp} (Formerly: {old_hp})")
            else:
                if repo.homepage:
                    output.append(f"{url_label} [{repo.homepage}]({repo.homepage})")
        elif repo.has_new:
            output.append(f"{url_label} [{repo.homepage}]({repo.homepage})")
        elif repo.has_old:
            output.append(f"{url_label} ~~[{repo.old_homepage}]({repo.old_homepage})~~")

    # Latest Release
    rel_changed = repo.has_old and repo.has_new and repo.release != repo.old_release
    rel_label = format_label("Latest Release", rel_changed)

    def format_single_release(release_str, repo_url):
        if not release_str: return ""
        date_m = re.search(r'\s*\((\d{4}-\d{2}-\d{2})\)\s*$', release_str)
        link = get_release_link(release_str, repo_url)

        if date_m:
            return f"{link} ({date_m.group(1)})"
        return link

    if (repo.has_new and repo.release) or (repo.has_old and repo.old_release):
        if repo.has_old and repo.has_new:
            if repo.release != repo.old_release:
                rel_str = format_single_release(repo.release, repo.repo_url)
                if repo.old_release:
                    rel_str += f", Last: {format_single_release(repo.old_release, repo.old_repo_url or repo.repo_url)}"

                # Check for >100 days
                d_date = parse_date(repo.old_release)
                a_date = parse_date(repo.release)
                if a_date and d_date:
                    days = (a_date - d_date).days
                    rel_str += f", {days} days old"
                output.append(f"{rel_label} {rel_str}")
            else:
                if repo.release:
                    output.append(f"{rel_label} {format_single_release(repo.release, repo.repo_url)}")
        elif repo.has_new:
            output.append(f"{rel_label} {format_single_release(repo.release, repo.repo_url)}")
        elif repo.has_old:
            output.append(f"{rel_label} ~~{format_single_release(repo.old_release, repo.old_repo_url)}~~")

    return "\n".join(output)

def get_release_link(release_str, repo_url):
    tag = parse_release_tag(release_str)
    if tag and repo_url and repo_url.startswith("https://github.com/"):
        return f"[{tag}]({repo_url}/releases/tag/{tag})"
    return tag

def main(input_stream=None):
    if input_stream is None:
        input_stream = sys.stdin

    languages = {}
    if os.path.exists("repo_languages.json"):
        with open("repo_languages.json", "r") as f:
            try:
                languages = json.load(f)
            except json.JSONDecodeError:
                pass

    files_changed = {}
    current_file = None

    for line in input_stream:
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

    repo_changes = {}

    for filename, changes in files_changed.items():
        base_name = filename.split('/')[-1]
        if not base_name.endswith('.md'):
            continue

        info_name = "extra info"
        if base_name.lower() == 'licenses.md':
            info_name = "license"
        elif base_name.lower() == 'starred.md':
            info_name = "latest release"

        adds = changes['add']
        dels = changes['del']

        matched_adds = set()
        matched_dels = set()
        updates = []

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

        for a_idx, a in enumerate(adds):
            if a_idx not in matched_adds:
                key = a.name
                if key not in repo_changes:
                    repo_changes[key] = RepoChange()
                repo_changes[key].merge_row(a, True, info_name)

        for d_idx, d in enumerate(dels):
            if d_idx not in matched_dels:
                key = d.name
                if key not in repo_changes:
                    repo_changes[key] = RepoChange()
                repo_changes[key].merge_row(d, False, info_name)

        for d, a in updates:
            key = a.name
            if key not in repo_changes:
                repo_changes[key] = RepoChange()
            repo_changes[key].merge_row(a, True, info_name)
            repo_changes[key].merge_row(d, False, info_name)
            if d.name != a.name:
                repo_changes[key].old_name = d.name

    desc_updates = []
    tag_updates = []
    license_updates = []
    url_updates = []
    release_updates = []
    removed_repos = []
    added_repos = []

    for repo in repo_changes.values():
        if repo.repo_url:
            link = f"[{repo.key}]({repo.repo_url})"
        elif repo.old_repo_url:
            link = f"[{repo.key}]({repo.old_repo_url})"
        else:
            link = f"**{repo.key}**"

        if not repo.has_new:
            removed_repos.append(link)
            continue
        if not repo.has_old:
            added_repos.append(link)
            continue

        if repo.desc != repo.old_desc:
            desc_updates.append(link)

        d_tags = repo.get_tags_set(False)
        a_tags = repo.get_tags_set(True)
        if d_tags != a_tags:
            tag_updates.append((link, d_tags, a_tags))

        if repo.license != repo.old_license:
            license_updates.append(link)

        if repo.homepage != repo.old_homepage:
            url_updates.append(link)

        if repo.release != repo.old_release:
            release_updates.append(repo)

    if not repo_changes:
        return

    print("## Summary")

    if added_repos:
        print(f"\n**{len(added_repos)} repos added:**")
        print(", ".join(added_repos))

    if removed_repos:
        print(f"\n**{len(removed_repos)} repos removed:**")
        print(", ".join(removed_repos))

    if desc_updates:
        print(f"\n**{len(desc_updates)} repos had updated descriptions including:**")
        print(", ".join(desc_updates))

    if tag_updates:
        print(f"\n**{len(tag_updates)} repos had updated tags:**")
        all_added = set()
        all_removed = set()
        repos_added = []
        repos_removed = []
        repos_replaced = []
        for link, old, new in tag_updates:
            added = new - old
            removed = old - new
            all_added.update(added)
            all_removed.update(removed)
            if added and not removed:
                repos_added.append(link)
            elif removed and not added:
                repos_removed.append(link)
            else:
                repos_replaced.append(link)

        if repos_added:
            print(f"- Added: {len(repos_added)} repos added {len(all_added)} unique tags: {', '.join(repos_added)}")
        if repos_replaced:
            print(f"- Replaced: {len(repos_replaced)} repos modified tags: {', '.join(repos_replaced)}")
        if repos_removed:
            print(f"- Removed: {len(repos_removed)} repos removed {len(all_removed)} unique tags: {', '.join(repos_removed)}")

        tag_counts = defaultdict(lambda: {'added': 0, 'replaced': 0, 'removed': 0})
        for link, old, new in tag_updates:
            added = new - old
            removed = old - new
            for t in added:
                if removed: tag_counts[t]['replaced'] += 1
                else: tag_counts[t]['added'] += 1
            for t in removed:
                if not added: tag_counts[t]['removed'] += 1
                # If both, we count the removed ones under 'replaced' effectively, but let's just track removed specifically for the summary

        if tag_counts:
            print("\n**The tags were:**")
            for t, counts in sorted(tag_counts.items()):
                # Try to link if it's a version tag
                repo_url = None
                # Search all repo_changes to find a repo that has this tag
                for repo in repo_changes.values():
                    d_tags = repo.get_tags_set(False)
                    a_tags = repo.get_tags_set(True)
                    if t in d_tags or t in a_tags:
                        repo_url = repo.repo_url or repo.old_repo_url
                        if repo_url and repo_url.startswith("https://github.com/"):
                            break
                        else:
                            repo_url = None

                t_display = f"`{t}`"
                if repo_url and (t.startswith('v') or re.match(r'^[0-9]', t)):
                    link = get_release_link(t, repo_url)
                    # If it actually turned into a link, don't wrap it in backticks,
                    # otherwise it will break markdown link rendering
                    if link.startswith('['):
                        t_display = link
                    else:
                        t_display = f"`{link}`"

                print(f"- {t_display}: Added to {counts['added']}, replaced {counts['replaced']}, removed from {counts['removed']}")

    if url_updates:
        print(f"\n**{len(url_updates)} repos had updated URLs:**")
        print(", ".join(url_updates))

    if license_updates:
        print(f"\n**{len(license_updates)} repos had updated Licenses:**")
        print(", ".join(license_updates))

    if release_updates:
        print(f"\n**Release summary:**")
        print(f"There were {len(release_updates)} releases")
        long_releases = []
        for repo in release_updates:
            d_date = parse_date(repo.old_release)
            a_date = parse_date(repo.release)
            if a_date and d_date:
                days = (a_date - d_date).days
                if days >= 100:
                    if repo.repo_url:
                        link = f"[{repo.key}]({repo.repo_url})"
                    elif repo.old_repo_url:
                        link = f"[{repo.key}]({repo.old_repo_url})"
                    else:
                        link = f"**{repo.key}**"

                    old_tag_link = get_release_link(repo.old_release, repo.old_repo_url or repo.repo_url)
                    new_tag_link = get_release_link(repo.release, repo.repo_url)

                    long_releases.append(f"* {link} ({days} days {a_date.strftime('%Y-%m-%d')} {old_tag_link} -> {new_tag_link})")

        if long_releases:
            print("Repos with >100 day releases:")
            print("\n".join(long_releases))

    print("\n## Detailed Repository Changes\n")

    # Sort repos alphabetically
    sorted_repos = sorted(repo_changes.values(), key=lambda r: r.key.lower())
    for repo in sorted_repos:
        print(format_card(repo, languages))
        print()

if __name__ == '__main__':
    main()
