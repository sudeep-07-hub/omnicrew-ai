#!/usr/bin/env bash
# OmniCrew AI — Live Deployment GenAI Usage Verifier.
#
# Hits the deployed `/query` endpoint to force an LLM call, then
# queries `/diagnostics/genai-usage` to prove that the call was
# recorded with real token counts (not a stub).

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <deployed-url> <command-center-api-key>"
    echo "Example: $0 https://omnicrew.web.app test-cmdctr-key-004"
    exit 1
fi

BASE_URL="${1%/}"
API_KEY="$2"

echo "=========================================================="
echo " OmniCrew AI — GenAI Usage Verification"
echo "=========================================================="
echo "Target URL: $BASE_URL"
echo ""

echo "1. Triggering a live query (this forces a GenAI call)..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "There is a massive crowd backing up at Gate C. It is becoming unsafe.",
    "role": "command-center",
    "location": "Command Center Ops",
    "language": "en"
  }')

if [ "$HTTP_STATUS" -ne 200 ]; then
    echo "❌ Failed to trigger query. HTTP Status: $HTTP_STATUS"
    exit 1
fi
echo "✅ Query successful."

echo ""
echo "2. Fetching GenAI telemetry logs..."

# Fetch the diagnostics JSON.
DIAG_OUTPUT=$(curl -s -X GET "$BASE_URL/diagnostics/genai-usage" \
  -H "X-API-Key: $API_KEY")

# Check if call_count exists and is > 0
CALL_COUNT=$(echo "$DIAG_OUTPUT" | grep -o '"call_count": *[0-9]*' | awk -F':' '{print $2}' | tr -d ' ' || echo "0")

if [ "$CALL_COUNT" -eq 0 ]; then
    echo "❌ Verification failed. Telemetry buffer is empty (call_count = 0)."
    echo "Output was: $DIAG_OUTPUT"
    exit 1
fi

echo "✅ Telemetry buffer has $CALL_COUNT records."

# Check if any call has total_tokens > 0 (proving it's a real LLM call, not a mock returning 0)
TOKENS=$(echo "$DIAG_OUTPUT" | grep -o '"total_tokens": *[0-9]*' | awk -F':' '{print $2}' | tr -d ' ' | sort -n | tail -1 || echo "0")

if [ "$TOKENS" -eq 0 ]; then
    echo "❌ Verification failed. Token counts are zero. Are you using a mock LLM in production?"
    echo "Output was: $DIAG_OUTPUT"
    exit 1
fi

echo "✅ Found real token consumption (max total_tokens: $TOKENS)."
echo ""
echo "=========================================================="
echo "🎉 SUCCESS: The deployment is genuinely calling a GenAI model."
echo "=========================================================="
echo ""
echo "Raw Diagnostics Output:"
echo "$DIAG_OUTPUT" | jq . || echo "$DIAG_OUTPUT"
