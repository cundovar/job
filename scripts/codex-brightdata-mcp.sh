#!/usr/bin/env bash

set -euo pipefail

if [[ -z "${BRIGHTDATA_API_TOKEN:-}" ]]; then
  echo "BRIGHTDATA_API_TOKEN is not set." >&2
  echo "Export your Bright Data token before launching Codex." >&2
  exit 1
fi

exec npx -y @brightdata/mcp
