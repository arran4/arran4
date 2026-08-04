import urllib.request
import urllib.error
import json
import datetime
import os
import sys
import time

USER = os.environ.get('GITHUB_REPOSITORY_OWNER', 'arran4')

def fetch_with_backoff(req, max_retries=5, ignore_errors=None):
    method = req.get_method().upper()
    is_idempotent = method in ('GET', 'HEAD', 'PUT', 'DELETE', 'OPTIONS')
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            status_code = e.code
            if status_code in [403, 429] or (is_idempotent and 500 <= status_code < 600):
                retry_after = e.headers.get('Retry-After')
                reset_time = e.headers.get('x-ratelimit-reset')

                sleep_time = 2 ** attempt

                if ignore_errors and status_code in ignore_errors:
                    return None

                if attempt == max_retries - 1:
                    print(f"HTTP Error {status_code} (Max retries reached)", file=sys.stderr)
                    sys.exit(1)

                if retry_after:
                    try:
                        sleep_time = int(retry_after)
                    except ValueError:
                        pass
                elif reset_time:
                    try:
                        reset_timestamp = int(reset_time)
                        current_timestamp = int(time.time())
                        if reset_timestamp > current_timestamp:
                            sleep_time = reset_timestamp - current_timestamp + 1
                    except ValueError:
                        pass

                print(f"HTTP Error {status_code}. Retrying in {sleep_time} seconds (attempt {attempt + 1}/{max_retries})...", file=sys.stderr)
                time.sleep(sleep_time)
            else:
                if ignore_errors and status_code in ignore_errors:
                    return None
                print(f"HTTP Error: {e}", file=sys.stderr)
                if hasattr(e, 'read'):
                    print(e.read().decode('utf-8'), file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Error fetching data: {e}", file=sys.stderr)
            if attempt == max_retries - 1:
                sys.exit(1)
            sleep_time = 2 ** attempt
            print(f"Retrying in {sleep_time} seconds (attempt {attempt + 1}/{max_retries})...", file=sys.stderr)
            time.sleep(sleep_time)

    print("Max retries exceeded.", file=sys.stderr)
    sys.exit(1)

def fetch_repos():
    repos = []
    page = 1
    while True:
        url = f'https://api.github.com/users/{USER}/repos?per_page=100&page={page}'
        req = urllib.request.Request(url)
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Accept', 'application/vnd.github.v3+json')

        response_data = fetch_with_backoff(req)
        data = json.loads(response_data)
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1

    return repos



def fetch_prs_for_month():
    now = datetime.datetime.now(datetime.timezone.utc)
    first_day_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month = first_day_of_this_month - datetime.timedelta(days=1)
    first_day_of_last_month = last_month.replace(day=1)

    date_str = first_day_of_last_month.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_date_str = (first_day_of_this_month - datetime.timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')

    print(f"Fetching PRs created between {date_str} and {end_date_str}...", file=sys.stderr)

    prs_by_repo = {}
    page = 1
    while True:
        url = f'https://api.github.com/search/issues?q=user:{USER}+type:pr+created:{date_str}..{end_date_str}&per_page=100&page={page}'
        req = urllib.request.Request(url)
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Accept', 'application/vnd.github.v3+json')

        response_data = fetch_with_backoff(req)
        if not response_data:
            break

        data = json.loads(response_data)
        items = data.get('items', [])
        if not items:
            break

        for item in items:
            repo_url = item.get('repository_url', '')
            repo_name = repo_url.split('/')[-1]
            if repo_name not in prs_by_repo:
                prs_by_repo[repo_name] = {'count': 0, 'url': f'https://github.com/{USER}/{repo_name}'}
            prs_by_repo[repo_name]['count'] += 1

        if len(items) < 100:
            break
        page += 1

    sorted_prs = [(k, v['url'], v['count']) for k, v in prs_by_repo.items()]
    sorted_prs.sort(key=lambda x: x[2], reverse=True)
    return sorted_prs



def fetch_commits_ahead(repos):
    print("Fetching commits ahead of latest release for repositories...", file=sys.stderr)
    ahead_list = []

    for repo in repos:
        repo_name = repo.get('name')
        repo_url = repo.get('html_url', f'https://github.com/{USER}/{repo_name}')
        full_name = f"{USER}/{repo_name}"

        # Get latest release
        rel_url = f'https://api.github.com/repos/{full_name}/releases/latest'
        req = urllib.request.Request(rel_url)
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Accept', 'application/vnd.github.v3+json')

        rel_data = fetch_with_backoff(req, ignore_errors=[404])
        if not rel_data:
            continue

        rel_json = json.loads(rel_data)
        tag_name = rel_json.get('tag_name')
        if not tag_name:
            continue

        # Get compare ahead
        comp_url = f'https://api.github.com/repos/{full_name}/compare/{tag_name}...HEAD'
        req = urllib.request.Request(comp_url)
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        req.add_header('Accept', 'application/vnd.github.v3+json')

        comp_data = fetch_with_backoff(req, ignore_errors=[404])
        if not comp_data:
            continue

        comp_json = json.loads(comp_data)
        ahead_by = comp_json.get('ahead_by')

        if ahead_by is not None and ahead_by > 0:
            ahead_list.append((repo_name, repo_url, ahead_by, tag_name))

    ahead_list.sort(key=lambda x: x[2], reverse=True)
    return ahead_list

def filter_and_sort_repos(repos):
    now = datetime.datetime.now(datetime.timezone.utc)
    thirty_days_ago = now - datetime.timedelta(days=30)

    filtered_repos = []
    for repo in repos:
        # Exclude private and archived repos
        if repo.get('private') or repo.get('archived'):
            continue

        # Parse last pushed/updated date
        pushed_at_str = repo.get('pushed_at') or repo.get('updated_at')
        if not pushed_at_str:
            continue

        pushed_at = datetime.datetime.strptime(pushed_at_str, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)

        # Exclude repos with activity in the last 30 days
        if pushed_at >= thirty_days_ago:
            continue

        filtered_repos.append({
            'name': repo.get('name'),
            'url': repo.get('html_url'),
            'pushed_at': pushed_at,
            'fork': repo.get('fork', False)
        })

    # Sort ascending by last modified date
    filtered_repos.sort(key=lambda x: x['pushed_at'])
    return filtered_repos

def group_repos_by_milestone(repos_list):
    now = datetime.datetime.now(datetime.timezone.utc)
    milestones = [
        (730, "More than 2 years"),
        (365, "More than 1 year"),
        (182, "More than 6 months"),
        (91, "More than 3 months"),
        (0, "More than 1 month")
    ]
    groups = {label: [] for _, label in milestones}

    for repo in repos_list:
        delta_days = (now - repo['pushed_at']).days
        for threshold, label in milestones:
            if delta_days >= threshold:
                groups[label].append(repo)
                break

    return groups

def generate_markdown(repos, prs, commits_ahead):
    non_forks = [r for r in repos if not r['fork']]
    forks = [r for r in repos if r['fork']]

    lines = [f"Hi @{USER}, here is your monthly repository report!"]
    lines.append("\nThese public, non-archived repositories haven't seen activity in the last month.")

    def add_repo_groups(repo_list, repo_type):
        if not repo_list:
            lines.append(f"No {repo_type} to report.")
            return

        groups = group_repos_by_milestone(repo_list)

        for milestone, repos_in_group in groups.items():
            if not repos_in_group:
                continue
            lines.append(f"- **{milestone}**")
            for repo in repos_in_group:
                lines.append(f"  - [{repo['name']}]({repo['url']}) - Last activity: {repo['pushed_at'].strftime('%Y-%m-%d')}")

    lines.append("\n## Non-Forks")
    add_repo_groups(non_forks, "non-forks")

    lines.append("\n## Forks")
    add_repo_groups(forks, "forks")

    if prs:
        lines.append("\n## Pull Requests This Month")
        for repo_name, url, count in prs:
            lines.append(f"- [{repo_name}]({url}): {count} PR(s)")

    if commits_ahead:
        lines.append("\n## Commits Ahead of Latest Release")
        for repo_name, url, ahead_by, tag_name in commits_ahead:
            lines.append(f"- [{repo_name}]({url}): {ahead_by} commits ahead of {tag_name}")

    return '\n'.join(lines)

def create_issue(title, body):
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY', f'{USER}/arran4') # fallback

    if not token:
        print("GITHUB_TOKEN not set. Skipping issue creation.")
        print(body)
        return

    url = f'https://api.github.com/repos/{repo}/issues'
    data = json.dumps({'title': title, 'body': body}).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Accept', 'application/vnd.github.v3+json')
    req.add_header('Content-Type', 'application/json')

    try:
        response_data = fetch_with_backoff(req)
        result = json.loads(response_data)
        print(f"Issue created successfully: {result.get('html_url')}")
    except Exception as e:
        print(f"Error creating issue: {e}")
        sys.exit(1)

def main():
    repos = fetch_repos()
    filtered_repos = filter_and_sort_repos(repos)

    prs = fetch_prs_for_month()
    commits_ahead = fetch_commits_ahead(repos)

    markdown_body = generate_markdown(filtered_repos, prs, commits_ahead)

    title = f"Monthly Repository Report - {datetime.datetime.now(datetime.timezone.utc).strftime('%B %Y')}"

    if os.environ.get('DRY_RUN'):
        print(f"Title: {title}")
        print("\nBody:")
        print(markdown_body)
    else:
        create_issue(title, markdown_body)

if __name__ == '__main__':
    main()
