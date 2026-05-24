#!/bin/bash
# verantyx start - Ping the Verantyx IDE to sync workspace context

PORT=5420
URL="http://127.0.0.1:$PORT/api/handshake"

WORKSPACE_PATH=$(pwd)
SKILLS_PATH="$WORKSPACE_PATH/.agents/skills"

# 1. ~/.verantyx/config.json へのキャッシュ書き込み
mkdir -p ~/.verantyx
cat <<JSON > ~/.verantyx/config.json
{
  "cortex_workspace_path": "$WORKSPACE_PATH",
  "cortex_skills_path": "$SKILLS_PATH"
}
JSON

# 2. IDEへのPing送信 (HTTP POST)
PAYLOAD=$(cat <<JSON
{
  "status": "cortex_ready",
  "workspace_path": "$WORKSPACE_PATH",
  "skills_path": "$SKILLS_PATH",
  "swarm_active": true
}
JSON
)

echo "📡 Sending Cortex Ping to IDE ($URL)..."
echo "$PAYLOAD"

# curlでJSONをPOSTする
RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$URL" || echo "failed")

if [[ "$RESPONSE" == "failed" ]]; then
    echo "⚠️ Verantyx IDE is not running or port $PORT is unreachable."
    echo "Using config.json fallback for next IDE launch."
else
    echo "✅ IDE Handshake successful! Response: $RESPONSE"
    echo "Swarm is now synchronized to: $WORKSPACE_PATH"
fi
