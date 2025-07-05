#!/usr/bin/env bash
set -euo pipefail

USER="arran4"

TMP_DIR=$(mktemp -d)
PAGE=1
ALL="$TMP_DIR/all.json"
: > "$ALL"

while true; do
  PAGE_FILE="$TMP_DIR/page_${PAGE}.json"
  curl -fsSL "https://api.github.com/users/${USER}/repos?per_page=100&page=${PAGE}" > "$PAGE_FILE"
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

TABLE="$TMP_DIR/table.md"
echo "| Repository | Description |" > "$TABLE"
echo "|---|---|" >> "$TABLE"
jq -r '.[] | "| [" + .name + "](https://github.com/'"${USER}"'/" + .name + ") | " + (.description // "") + " |"' "$SORTED" >> "$TABLE"

README="README.md"
START='<!--repos-start-->'
END='<!--repos-end-->'

awk -v start="$START" -v end="$END" -v table_file="$TABLE" '
FNR==NR{lines[NR]=$0;next}
$0==start{print;for(i=1;i<=length(lines);i++)print lines[i];skip=1;next}
$0==end{skip=0;print;next}
!skip{print}
' "$TABLE" "$README" > "$README.tmp" && mv "$README.tmp" "$README"

rm -rf "$TMP_DIR"
