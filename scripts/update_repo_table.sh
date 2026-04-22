#!/usr/bin/env bash
set -euo pipefail

USER="arran4"

TMP_DIR=$(mktemp -d)
PAGE=1
ALL="$TMP_DIR/all.json"
: > "$ALL"

while true; do
  PAGE_FILE="$TMP_DIR/page_${PAGE}.json"
  curl -fsSL \
    -H "Accept: application/vnd.github.mercy-preview+json" \
    "https://api.github.com/users/${USER}/repos?per_page=100&page=${PAGE}" > "$PAGE_FILE"
  COUNT=$(jq 'length' "$PAGE_FILE")
  jq -s 'add' "$ALL" "$PAGE_FILE" > "$ALL.tmp"
  mv "$ALL.tmp" "$ALL"
  if [ "$COUNT" -lt 100 ]; then
    break
  fi
  PAGE=$((PAGE+1))
  sleep 1
done

FILTERED="$TMP_DIR/filtered.json"
jq '[.[] | select(.fork == false and .archived == false)]' "$ALL" > "$FILTERED"

SORTED="$TMP_DIR/sorted.json"
jq 'sort_by(.name)' "$FILTERED" > "$SORTED"

SYNONYMS='{
  "golang": "go",
  "golang-library": ["go", "library"],
  "go-library": ["go", "library"],
  "util": "utility",
  "fun": "for-fun",
  "amusement": "for-fun",
  "rss-generator": "rss",
  "rss-gen": "rss",
  "awesome": "awesome-list",
  "dart-library": "dart",
  "dartlang": "dart",
  "tool": "utility",
  "github-action": "github-actions",
  "github-workflow": "github-actions",
  "githubpages": "github-pages",
  "gentoo-overlay": ["gentoo", "overlay"],
  "gentoo-portage-overlay": ["gentoo", "overlay"],
  "portage-overlay": ["gentoo", "overlay"],
  "google-appengine": "google-app-engine",
  "go-google-app-engine": ["go", "google-app-engine"],
  "cli-tool": "cli",
  "cli-app": "cli",
  "commandline-tool": "cli",
  "command-line": "cli",
  "desktop-app": "desktop",
  "desktop-util": "desktop",
  "dotfile": "dotfiles",
  "flutter-library": ["flutter", "library"],
  "testing": "test",
  "games": "game",
  "mac": "macos",
  "systemtray": "system-tray",
  "system-tray-icons": "system-tray",
  "sys-icon": "system-tray",
  "cheetsheet": "cheatsheet",
  "vimcheatsheet": ["vim", "cheatsheet"],
  "vim-cheatsheet": ["vim", "cheatsheet"]
}'
MIN_TAG_COUNT=3

INTERESTING_TAGS=$(jq -c --argjson synonyms "$SYNONYMS" --argjson min_count "$MIN_TAG_COUNT" '[.[].topics | select(. != null) | [ .[] | if $synonyms[.] then (if ($synonyms[.] | type) == "array" then $synonyms[.][] else $synonyms[.] end) else . end ] | unique | .[]] | group_by(.) | map({tag: .[0], count: length}) | sort_by(-.count) | map(select(.count >= $min_count)) | map(.tag)' "$SORTED")

COMMON_JQ='
  def interesting_tags: $ext_interesting_tags;
  def synonyms: $ext_synonyms;
  def normalize_topics($topics):
    ($topics // []) | [ .[] | if synonyms[.] then (if (synonyms[.] | type) == "array" then synonyms[.][] else synonyms[.] end) else . end ] | unique;
  def tag_label($topics):
    normalize_topics($topics) as $all
    | [ $all[] | select(. as $tag | (interesting_tags | index($tag)) != null) ] as $selected
    | if ($selected | length) == 0 then null
      elif ($selected | length) == 1 then $selected[0]
      else ($selected | sort | join(" + "))
      end;
  def grouped_tags($topics):
    normalize_topics($topics) as $all
    | (reduce $all[] as $tag (
        {selected: [], other: []};
        if ((interesting_tags | index($tag)) != null) then
          .selected += [$tag]
        else
          .other += [$tag]
        end
      )) as $parts
    | if ($parts.selected | length) >= 2 then
        [($parts.selected | sort | join(" + "))] + $parts.other
      else
        $parts.selected + $parts.other
      end;
'

TABLE="$TMP_DIR/table.md"
jq -r --arg user "$USER" --argjson ext_interesting_tags "$INTERESTING_TAGS" --argjson ext_synonyms "$SYNONYMS" "$COMMON_JQ"'
  def repo_row($repo):
    "| [" + $repo.name + "](https://github.com/" + $user + "/" + $repo.name + ")"
    + (if $repo.homepage != null and $repo.homepage != "" then " [🔗](" + $repo.homepage + ")" else "" end) + " | "
    + ($repo.description // "") + " | "
    + (grouped_tags($repo.topics) | join(", ")) + " |";
  def table_for($heading; $repos):
    if ($repos | length) == 0 then null
    else
      "### " + $heading + "\n"
      + "| Repository | Description | Tags |\n"
      + "|---|---|---|\n"
      + ($repos | map(repo_row(.)) | join("\n"))
      + "\n"
    end;
  [.[] | {label: tag_label(.topics), name: .name, description: .description, topics: .topics, homepage: .homepage}] as $items
  | (
      $items
      | map(select(.label != null))
      | group_by(.label)
      | sort_by(.[0].label)
      | map(table_for(.[0].label; .))
    ) as $group_tables
  | (
      $items
      | map(select(.label == null))
      | table_for("Unmatched"; .)
    ) as $unmatched_table
  | ($group_tables + [$unmatched_table])
  | map(select(. != null and . != ""))
  | join("\n")
' "$SORTED" > "$TABLE"

LICENSES_TABLE="$TMP_DIR/licenses_table.md"
jq -r --arg user "$USER" --argjson ext_interesting_tags "$INTERESTING_TAGS" --argjson ext_synonyms "$SYNONYMS" "$COMMON_JQ"'
  def repo_row_license($repo):
    "| [" + $repo.name + "](https://github.com/" + $user + "/" + $repo.name + ")"
    + (if $repo.homepage != null and $repo.homepage != "" then " [🔗](" + $repo.homepage + ")" else "" end) + " | "
    + ($repo.description // "") + " | "
    + ($repo.license.spdx_id // $repo.license.name // "") + " | "
    + (grouped_tags($repo.topics) | join(", ")) + " |";
  def table_for_license($heading; $repos):
    if ($repos | length) == 0 then null
    else
      "### " + $heading + "\n"
      + "| Repository | Description | License | Tags |\n"
      + "|---|---|---|---|\n"
      + ($repos | map(repo_row_license(.)) | join("\n"))
      + "\n"
    end;
  def license_group($license):
    if ($license == null or ($license.spdx_id == null and $license.name == null)) then "No License"
    else ($license.spdx_id // $license.name)
    end;
  [.[] | {label: license_group(.license), name: .name, description: .description, topics: .topics, homepage: .homepage, license: .license}] as $items
  | (
      $items
      | group_by(.label)
      | sort_by(.[0].label)
      | map(table_for_license(.[0].label; .))
    )
  | map(select(. != null and . != ""))
  | join("\n")
' "$SORTED" > "$LICENSES_TABLE"


README="README.md"
START='<!--repos-start-->'
END='<!--repos-end-->'

awk -v start="$START" -v end="$END" -v table_file="$TABLE" '
FNR==NR{lines[NR]=$0;next}
$0==start{print;for(i=1;i<=length(lines);i++)print lines[i];skip=1;next}
$0==end{skip=0;print;next}
!skip{print}
' "$TABLE" "$README" > "$README.tmp" && mv "$README.tmp" "$README"

LICENSES_MD="licenses.md"
if [ ! -f "$LICENSES_MD" ]; then
  echo "# Licenses" > "$LICENSES_MD"
  echo "" >> "$LICENSES_MD"
  echo "List of repositories and their licenses." >> "$LICENSES_MD"
  echo "" >> "$LICENSES_MD"
  echo "$START" >> "$LICENSES_MD"
  echo "$END" >> "$LICENSES_MD"
fi

awk -v start="$START" -v end="$END" -v table_file="$LICENSES_TABLE" '
FNR==NR{lines[NR]=$0;next}
$0==start{print;for(i=1;i<=length(lines);i++)print lines[i];skip=1;next}
$0==end{skip=0;print;next}
!skip{print}
' "$LICENSES_TABLE" "$LICENSES_MD" > "$LICENSES_MD.tmp" && mv "$LICENSES_MD.tmp" "$LICENSES_MD"

PAGE=1
ALL_STARRED="$TMP_DIR/all_starred.json"
: > "$ALL_STARRED"

while true; do
  PAGE_FILE="$TMP_DIR/page_starred_${PAGE}.json"
  curl -fsSL \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/users/${USER}/starred?per_page=100&page=${PAGE}" > "$PAGE_FILE"
  COUNT=$(jq 'length' "$PAGE_FILE")
  jq -s 'add' "$ALL_STARRED" "$PAGE_FILE" > "$ALL_STARRED.tmp"
  mv "$ALL_STARRED.tmp" "$ALL_STARRED"
  if [ "$COUNT" -lt 100 ]; then
    break
  fi
  PAGE=$((PAGE+1))
  sleep 1
done

SORTED_STARRED="$TMP_DIR/sorted_starred.json"
jq 'sort_by(.full_name // .name)' "$ALL_STARRED" > "$SORTED_STARRED"

STARRED_TABLE="$TMP_DIR/starred_table.md"
jq -r --argjson ext_interesting_tags "$INTERESTING_TAGS" --argjson ext_synonyms "$SYNONYMS" "$COMMON_JQ"'
  def repo_row_starred($repo):
    "| [" + ($repo.full_name // $repo.name) + "](" + $repo.html_url + ")"
    + (if $repo.homepage != null and $repo.homepage != "" then " [🔗](" + $repo.homepage + ")" else "" end) + " | "
    + ($repo.description // "") + " | "
    + (grouped_tags($repo.topics) | join(", ")) + " |";
  def table_for_starred($heading; $repos):
    if ($repos | length) == 0 then null
    else
      "### " + $heading + "\n"
      + "| Repository | Description | Tags |\n"
      + "|---|---|---|\n"
      + ($repos | map(repo_row_starred(.)) | join("\n"))
      + "\n"
    end;
  [.[] | {label: tag_label(.topics), name: .name, full_name: .full_name, description: .description, topics: .topics, homepage: .homepage, html_url: .html_url}] as $items
  | (
      $items
      | map(select(.label != null))
      | group_by(.label)
      | sort_by(.[0].label)
      | map(table_for_starred(.[0].label; .))
    ) as $group_tables
  | (
      $items
      | map(select(.label == null))
      | table_for_starred("Unmatched"; .)
    ) as $unmatched_table
  | ($group_tables + [$unmatched_table])
  | map(select(. != null and . != ""))
  | join("\n")
' "$SORTED_STARRED" > "$STARRED_TABLE"

STARRED_MD="starred.md"
if [ ! -f "$STARRED_MD" ]; then
  echo "# Starred Repositories" > "$STARRED_MD"
  echo "" >> "$STARRED_MD"
  echo "List of starred repositories." >> "$STARRED_MD"
  echo "" >> "$STARRED_MD"
  echo "$START" >> "$STARRED_MD"
  echo "$END" >> "$STARRED_MD"
fi

awk -v start="$START" -v end="$END" -v table_file="$STARRED_TABLE" '
FNR==NR{lines[NR]=$0;next}
$0==start{print;for(i=1;i<=length(lines);i++)print lines[i];skip=1;next}
$0==end{skip=0;print;next}
!skip{print}
' "$STARRED_TABLE" "$STARRED_MD" > "$STARRED_MD.tmp" && mv "$STARRED_MD.tmp" "$STARRED_MD"

rm -rf "$TMP_DIR"
