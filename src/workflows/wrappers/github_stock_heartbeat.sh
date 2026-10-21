#!/bin/bash
# GitHub stock workflow heartbeater — 保持 fork workflow 活跃
# 每4小时手动触发一次，防止60天政策禁用
set -euo pipefail

REPO="xia950704/daily_stock_analysis"
WORKFLOW_ID=301272192

echo "=== Heartbeat: $(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M:%S') ==="

# 检查上次成功运行时间
LAST_SUCCESS=$(gh run list --repo "$REPO" --workflow "$WORKFLOW_ID" --limit 5 --json createdAt,conclusion --jq '[.[] | select(.conclusion=="success")][0].createdAt' 2>/dev/null || echo "unknown")
echo "Last success: $LAST_SUCCESS"

# 触发 workflow
echo "Triggering workflow..."
echo '{"ref":"main"}' > /tmp/dispatch_$$.json
gh api "repos/$REPO/actions/workflows/$WORKFLOW_ID/dispatches" --method POST --input /tmp/dispatch_$$.json >/dev/null
rm -f /tmp/dispatch_$$.json

echo "Triggered successfully"
echo "=== Heartbeat complete ==="
