import urllib.request
import urllib.error
import json
import datetime
import os
import sys

USER = os.environ.get('GITHUB_REPOSITORY_OWNER', 'arran4')

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

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                if not data:
                    break
                repos.extend(data)
                if len(data) < 100:
                    break
                page += 1
        except urllib.error.URLError as e:
            print(f"Error fetching repos: {e}")
            if hasattr(e, 'read'):
                print(e.read().decode('utf-8'))
            sys.exit(1)

    return repos

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
    groups = {
        "More than 2 years": [],
        "More than 1 year": [],
        "More than 6 months": [],
        "More than 3 months": [],
        "More than 1 month": []
    }

    for repo in repos_list:
        delta_days = (now - repo['pushed_at']).days
        if delta_days >= 730:
            groups["More than 2 years"].append(repo)
        elif delta_days >= 365:
            groups["More than 1 year"].append(repo)
        elif delta_days >= 182:
            groups["More than 6 months"].append(repo)
        elif delta_days >= 91:
            groups["More than 3 months"].append(repo)
        else:
            groups["More than 1 month"].append(repo)

    return groups

def generate_markdown(repos):
    non_forks = [r for r in repos if not r['fork']]
    forks = [r for r in repos if r['fork']]

    lines = [f"Hi @{USER}, here is your monthly repository report!"]
    lines.append("\nThese public, non-archived repositories haven't seen activity in the last month.")

    def add_repo_groups(repo_list):
        if not repo_list:
            lines.append("No repositories to report.")
            return

        groups = group_repos_by_milestone(repo_list)

        for milestone, repos_in_group in groups.items():
            if not repos_in_group:
                continue
            lines.append(f"- **{milestone}**")
            for repo in repos_in_group:
                lines.append(f"  - [{repo['name']}]({repo['url']}) - Last activity: {repo['pushed_at'].strftime('%Y-%m-%d')}")

    lines.append("\n## Non-Forks")
    add_repo_groups(non_forks)

    lines.append("\n## Forks")
    add_repo_groups(forks)

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
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"Issue created successfully: {result.get('html_url')}")
    except urllib.error.URLError as e:
        print(f"Error creating issue: {e}")
        if hasattr(e, 'read'):
            print(e.read().decode('utf-8'))
        sys.exit(1)

def main():
    repos = fetch_repos()
    filtered_repos = filter_and_sort_repos(repos)
    markdown_body = generate_markdown(filtered_repos)

    title = f"Monthly Repository Report - {datetime.datetime.now(datetime.timezone.utc).strftime('%B %Y')}"

    if os.environ.get('DRY_RUN'):
        print(f"Title: {title}")
        print("\nBody:")
        print(markdown_body)
    else:
        create_issue(title, markdown_body)

if __name__ == '__main__':
    main()
