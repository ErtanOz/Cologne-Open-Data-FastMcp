#!/bin/bash
set -euo pipefail

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
export CACHE_TTL=${CACHE_TTL:-300}
export HTTP_TIMEOUT=${HTTP_TIMEOUT:-8}
export HTTP_RETRIES=${HTTP_RETRIES:-3}

echo "Starting fastMCP Köln Presse Server..."
echo "Cache TTL: ${CACHE_TTL}s"
echo "HTTP Timeout: ${HTTP_TIMEOUT}s"
echo "HTTP Retries: ${HTTP_RETRIES}"

python -m koeln_presse.server