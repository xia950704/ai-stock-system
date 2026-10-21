#!/bin/bash
# 批量处理科特勒营销管理 - 包装脚本
# 确保使用 Hermes 的 Python 环境

set -euo pipefail
HERMES_PYTHON="/Users/xiashuang/.hermes-web-ui/desktop-runtime/hermes/0.16.0/mac-arm64/python/bin/python3"

if [ ! -f "$HERMES_PYTHON" ]; then
    echo "❌ 错误: Hermes Python 未找到: $HERMES_PYTHON"
    exit 1
fi

export SENSENOVA_API_KEY="sk-j...exec "$HERMES_PYTHON" ~/.hermes/scripts/kotler_batch.py
