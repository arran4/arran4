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

COMMON_JQ='
  def interesting_tags: ["npm-package","golang-library","cli","web","image","library","gentoo","for-fun","dart-library","awesome-list","hugo","rss"];
  def tag_label($topics):
    ($topics // []) as $all
    | [ $all[] | select(. as $tag | (interesting_tags | index($tag)) != null) ] as $selected
    | if ($selected | length) == 0 then null
      elif ($selected | length) == 1 then $selected[0]
      else ($selected | sort | join(" + "))
      end;
  def grouped_tags($topics):
    ($topics // []) as $all
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
jq -r --arg user "$USER" "$COMMON_JQ"'
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
jq -r --arg user "$USER" "$COMMON_JQ"'
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
  [.[] | {label: tag_label(.topics), name: .name, description: .description, topics: .topics, homepage: .homepage, license: .license}] as $items
  | (
      $items
      | map(select(.label != null))
      | group_by(.label)
      | sort_by(.[0].label)
      | map(table_for_license(.[0].label; .))
    ) as $group_tables
  | (
      $items
      | map(select(.label == null))
      | table_for_license("Unmatched"; .)
    ) as $unmatched_table
  | ($group_tables + [$unmatched_table])
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

rm -rf "$TMP_DIR"
