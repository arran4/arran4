import os
import sys
import json
import urllib.request
import urllib.error
import time

def fetch_releases(repos, token):
    if not token:
        # If no token, just return empty dict to skip rate limiting issues
        return {}

    url = "https://api.github.com/graphql"
    results = {}

    # Process in chunks of 50 to avoid hitting limits or complex queries
    chunk_size = 50
    for i in range(0, len(repos), chunk_size):
        chunk = repos[i:i+chunk_size]

        query_parts = []
        for j, repo in enumerate(chunk):
            if '/' not in repo:
                continue
            owner, name = repo.split('/', 1)
            # Use alias to avoid naming collisions and invalid GraphQL keys
            # Escape owner/name properly if needed, but normally they are valid strings
            # GraphQL aliases must match [_A-Za-z][_0-9A-Za-z]*
            alias = f"repo_{j}"
            query_parts.append(f"""
            {alias}: repository(owner: "{owner}", name: "{name}") {{
                nameWithOwner
                latestRelease {{
                    tagName
                    publishedAt
                }}
            }}
            """)

        if not query_parts:
            continue

        query = "query { " + " ".join(query_parts) + " }"

        req = urllib.request.Request(url, data=json.dumps({"query": query}).encode("utf-8"), headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        })

        max_retries = 5
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())
                    if 'data' in data:
                        for alias, repo_data in data['data'].items():
                            if repo_data and repo_data.get('latestRelease'):
                                results[repo_data['nameWithOwner'].lower()] = repo_data['latestRelease']
                    break # Success, exit retry loop
            except urllib.error.HTTPError as e:
                status_code = e.code
                if status_code in [403, 429] or 500 <= status_code < 600:
                    retry_after = e.headers.get('Retry-After')
                    reset_time = e.headers.get('x-ratelimit-reset')

                    sleep_time = 2 ** attempt # Default exponential backoff

                    if attempt == max_retries - 1:
                        print(f"HTTP Error {status_code} fetching GraphQL for releases (Max retries reached)", file=sys.stderr)
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

                    print(f"HTTP Error {status_code} fetching GraphQL for releases. Retrying in {sleep_time} seconds (attempt {attempt + 1}/{max_retries})...", file=sys.stderr)
                    time.sleep(sleep_time)
                else:
                    print(f"Error fetching GraphQL for releases: {e}", file=sys.stderr)
                    sys.exit(1)
            except Exception as e:
                print(f"Error fetching GraphQL for releases: {e}", file=sys.stderr)
                if attempt == max_retries - 1:
                    sys.exit(1)
                sleep_time = 2 ** attempt
                print(f"Retrying in {sleep_time} seconds (attempt {attempt + 1}/{max_retries})...", file=sys.stderr)
                time.sleep(sleep_time)
        else:
            print("Max retries exceeded for fetching releases.", file=sys.stderr)
            sys.exit(1)

    return results

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 fetch_starred_releases.py <input_json> <output_json>", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {input_file}: {e}", file=sys.stderr)
        sys.exit(1)

    repos = []
    for item in data:
        full_name = item.get('full_name')
        if full_name:
            repos.append(full_name)

    token = os.environ.get('GITHUB_TOKEN')
    releases = fetch_releases(repos, token)

    # To avoid case sensitivity issues we map lowercase as well or just output as is
    with open(output_file, 'w') as f:
        json.dump(releases, f, indent=2)
