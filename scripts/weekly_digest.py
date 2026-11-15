"""Human-readable weekly PR digest for changes to repository tables.

The diff parser supplies the canonical change records. This module renders a
quick-to-scan report and retains the full records in a collapsed appendix.
"""

import sys


RELEASE_PREVIEW_LIMIT = 12
METADATA_PREVIEW_LIMIT = 20


def _repo_link(repo):
    name = repo.key
    url = repo.repo_url or repo.old_repo_url
    return f"[{name}]({url})" if url else f"`{name}`"


def _short(value, escape_md, limit=130):
    value = " ".join((value or "").split())
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return escape_md(value) if value else "(none)"


def _labelled_release(repo, release, get_release_link, *, old=False):
    if not release:
        return "(none)"
    url = (repo.old_repo_url or repo.repo_url) if old else (repo.repo_url or repo.old_repo_url)
    return get_release_link(release, url) or "(none)"


def _gap_days(repo, parse_date):
    before = parse_date(repo.old_release)
    after = parse_date(repo.release)
    if before and after:
        return (after - before).days
    return None


def _release_line(repo, parse_date, get_release_link):
    old = _labelled_release(repo, repo.old_release, get_release_link, old=True)
    new = _labelled_release(repo, repo.release, get_release_link)
    days = _gap_days(repo, parse_date)
    interval = f" ({days} days between release dates)" if days is not None and days >= 0 else ""
    return f"- {_repo_link(repo)}: {old} → {new}{interval}"


def _print_items(out, label, items, limit=METADATA_PREVIEW_LIMIT):
    if not items:
        return
    print(f"\n**{label} ({len(items)})**", file=out)
    for item in items[:limit]:
        print(f"- {item}", file=out)
    if len(items) > limit:
        print(f"- _{len(items) - limit} more in the detailed records below._", file=out)


def render_report(repo_changes, languages, format_card, parse_date,
                  get_release_link, escape_md, out=None):
    """Print a substantive overview followed by the original complete cards."""
    if out is None:
        out = sys.stdout
    repos = sorted(repo_changes.values(), key=lambda r: (r.key or "").casefold())
    if not repos:
        print("No tracked repository changes were detected.", file=out)
        return

    added_stars, added_repos, removed_repos = [], [], []
    descriptions, tags, homepages, licenses, renames, releases = [], [], [], [], [], []
    for repo in repos:
        link = _repo_link(repo)
        if not repo.has_new:
            removed_repos.append(link)
            continue
        if not repo.has_old:
            lang = languages.get(repo.key)
            extra = f" ({escape_md(lang)})" if lang else ""
            line = f"{link}{extra} — {_short(repo.desc, escape_md)}"
            if repo.release:
                line += f"; latest {_labelled_release(repo, repo.release, get_release_link)}"
            if repo.is_star and repo.source_lists == {'latest release'}:
                added_stars.append(line)
            else:
                added_repos.append(line)
            continue

        if repo.old_name != repo.name or repo.old_repo_url != repo.repo_url:
            renames.append(f"{link}: formerly `{repo.old_name or repo.key}`")
        if repo.desc != repo.old_desc:
            descriptions.append(f"{link}: {_short(repo.desc, escape_md)} (was {_short(repo.old_desc, escape_md)})")
        before, after = repo.get_tags_set(False), repo.get_tags_set(True)
        if before != after:
            changes = [f"+`{escape_md(t)}`" for t in sorted(after - before)]
            changes += [f"−`{escape_md(t)}`" for t in sorted(before - after)]
            tags.append(f"{link}: {', '.join(changes)}")
        if repo.homepage != repo.old_homepage:
            homepages.append(
                f"{link}: {_short(repo.old_homepage, escape_md, 70)} → "
                f"{_short(repo.homepage, escape_md, 70)}"
            )
        if repo.license != repo.old_license:
            licenses.append(f"{link}: `{escape_md(repo.old_license or 'none')}` → "
                            f"`{escape_md(repo.license or 'none')}`")
        if repo.release != repo.old_release:
            releases.append(repo)

    print("## Weekly change overview\n", file=out)
    print("| Tracked changes | Count |", file=out)
    print("| --- | ---: |", file=out)
    for label, count in [
        ("Repositories with changes", len(repos)),
        ("New stars", len(added_stars)),
        ("Other repository additions", len(added_repos)),
        ("Removed repositories", len(removed_repos)),
        ("Description changes", len(descriptions)),
        ("Topic/tag changes", len(tags)),
        ("Homepage changes", len(homepages)),
        ("License changes", len(licenses)),
        ("Renames or transfers", len(renames)),
        ("Latest-release changes", len(releases)),
    ]:
        print(f"| {label} | {count} |", file=out)
    print("\nCounts describe changes to tracked records, not all releases published during the week.", file=out)

    if added_stars or added_repos or removed_repos:
        print("\n## Stars and repository membership", file=out)
        _print_items(out, "New stars", added_stars)
        _print_items(out, "Other additions", added_repos)
        _print_items(out, "Removed repositories", removed_repos)

    if descriptions or tags or homepages or licenses or renames:
        print("\n## Metadata changes", file=out)
        _print_items(out, "Descriptions", descriptions)
        _print_items(out, "Topics and tags (+added, −removed)", tags)
        _print_items(out, "Homepages", homepages)
        _print_items(out, "Licenses", licenses)
        _print_items(out, "Renames and transfers", renames)

    if releases:
        print("\n## Release digest\n", file=out)
        print(f"**{len(releases)} repositories changed their latest release.** "
              "Intervals compare the publication dates of the previously recorded and current latest releases; "
              "intermediate versions may have been skipped.", file=out)
        long_gap = sorted((r for r in releases if (_gap_days(r, parse_date) or 0) >= 100),
                          key=lambda r: (-_gap_days(r, parse_date), r.key.casefold()))
        other = [r for r in releases if r not in long_gap]
        other.sort(key=lambda r: (-(_gap_days(r, parse_date) or -1), r.key.casefold()))
        _print_items(out, "Long-gap releases (100+ days)",
                     [_release_line(r, parse_date, get_release_link)[2:] for r in long_gap],
                     limit=len(long_gap))
        _print_items(out, "Other release highlights",
                     [_release_line(r, parse_date, get_release_link)[2:] for r in other],
                     limit=RELEASE_PREVIEW_LIMIT)

    print("\n## Detailed Repository Changes\n", file=out)
    print("<details>", file=out)
    print(f"<summary>Expand all {len(repos)} repository records (reasons, languages, "
          "descriptions, releases, licenses, topics and URLs)</summary>\n", file=out)
    for repo in repos:
        print(format_card(repo, languages), file=out)
        print(file=out)
    print("</details>", file=out)
