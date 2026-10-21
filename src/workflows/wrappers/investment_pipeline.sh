#!/bin/bash
# Wrapper: investment-pipeline-daily
set -euo pipefail
export PATH="$HOME/.hermes-web-ui/desktop-runtime/hermes/$(ls "$HOME/.hermes-web-ui/desktop-runtime/hermes" | sort -V | tail -1)/mac-arm64/python/bin:$PATH"
SCRIPT_OUTPUT=$(python3 ~/.hermes/scripts/investment_pipeline.py 2>&1)
EXIT_CODE=$?
echo "$SCRIPT_OUTPUT"
bash ~/.hermes/scripts/imsg_notify.sh "投资流水线" "$SCRIPT_OUTPUT"
exit $EXIT_CODE
