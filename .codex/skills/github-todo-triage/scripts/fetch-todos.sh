#!/usr/bin/env bash
set -euo pipefail

repo="${1:-}"
if [[ -z "$repo" ]]; then
  repo="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
fi
if [[ -z "$repo" ]]; then
  repo="$(git remote get-url origin | sed -E 's#^git@github.com:##; s#^https://github.com/##; s#\.git$##')"
fi
if [[ -z "$repo" ]]; then
  echo "Could not determine GitHub repo. Pass owner/name as the first argument." >&2
  exit 1
fi

out_dir=".codex/github-todos"
mkdir -p "$out_dir"

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

gh issue list --repo "$repo" --state open --limit 100 \
  --json number,title,state,author,labels,assignees,createdAt,updatedAt,url,body \
  > "$out_dir/issues-open.json"

gh pr list --repo "$repo" --state open --limit 100 \
  --json number,title,state,author,labels,assignees,createdAt,updatedAt,url,body,isDraft,reviewDecision,headRefName,baseRefName,mergeStateStatus,mergeable \
  > "$out_dir/prs-open.json"

gh issue list --repo "$repo" --state all --limit 50 \
  --json number,title,state,author,labels,createdAt,updatedAt,closedAt,url \
  > "$out_dir/issues-recent.json"

gh pr list --repo "$repo" --state all --limit 50 \
  --json number,title,state,author,labels,createdAt,updatedAt,closedAt,mergedAt,url,isDraft,reviewDecision,headRefName,baseRefName \
  > "$out_dir/prs-recent.json"

{
  echo "repo	$repo"
  echo "refreshed_at	$timestamp"
  echo
  echo "open_issues"
  gh issue list --repo "$repo" --state open --limit 100 \
    --json number,title,labels,author,updatedAt,url \
    --jq '.[] | "#\(.number)\t\(.title)\t\([.labels[].name] | join(","))\t@\(.author.login)\t\(.updatedAt)\t\(.url)"'
  echo
  echo "open_prs"
  gh pr list --repo "$repo" --state open --limit 100 \
    --json number,title,author,updatedAt,url,headRefName,baseRefName,isDraft,reviewDecision \
    --jq '.[] | "#\(.number)\t\(.title)\t\(.headRefName)->\(.baseRefName)\tdraft=\(.isDraft)\treview=\(.reviewDecision // "")\t@\(.author.login)\t\(.updatedAt)\t\(.url)"'
} > "$out_dir/summary.tsv"

echo "Wrote GitHub todo snapshots for $repo to $out_dir"
