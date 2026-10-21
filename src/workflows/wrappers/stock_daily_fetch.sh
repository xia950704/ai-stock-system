#!/bin/bash
# stock-daily-data-fetch wrapper — 腾讯实时价 + 锚价更新
# 替代原 agent 任务（被 DeepSeek 429 打挂，failure_streak=10）
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
cd /Users/xiashuang/harness/stock_daily
python3 update_anchor.py 2>&1
