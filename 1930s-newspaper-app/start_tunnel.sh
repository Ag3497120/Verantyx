#!/bin/bash

# ==========================================
# Verantyx Hybrid Tunneling (Plan A)
# ==========================================

echo "🧠 Booting Verantyx 1930s API (FastAPI)..."
python3 -m uvicorn api:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!

# Wait for FastAPI to start
sleep 3

echo "🌐 Checking Cloudflare Tunnel (cloudflared)..."
if ! command -v cloudflared &> /dev/null; then
    echo "cloudflared not found. Please install it with: brew install cloudflare/cloudflare/cloudflared"
    kill $FASTAPI_PID
    exit 1
fi

echo "🚀 Opening Tunnel to the World and intercepting the URL..."
# Run cloudflared in the background and pipe output to a log file
cloudflared tunnel --protocol http2 --url http://localhost:8000 2>&1 | tee tunnel.log &
TUNNEL_PID=$!

# Continuously read the log until the URL is generated
echo "🔍 Waiting for Cloudflare to assign a URL..."
TUNNEL_URL=""
while [ -z "$TUNNEL_URL" ]; do
    sleep 1
    # Extract the trycloudflare URL, filter out 'api.trycloudflare.com', and get the last match
    TUNNEL_URL=$(grep -a -o 'https://[-a-zA-Z0-9]*\.trycloudflare\.com' tunnel.log | grep -v 'api\.trycloudflare\.com' | tail -n 1)
done

echo "✅ Tunnel URL successfully extracted: $TUNNEL_URL"

# ==========================================
# 📝 Inject URL directly into verantyx.ai (Next.js)
# ==========================================
echo "🔄 Automatically updating verantyx.ai frontend with the new URL..."

export TUNNEL_URL
python3 -c "
import re
import os
tunnel_url = os.environ.get('TUNNEL_URL')
path = '/Users/motonishikoudai/verantyx-site/src/app/apps/talkiepress/page.tsx'
with open(path, 'r') as f:
    content = f.read()

# Replace the default API URL in the React state
new_content = re.sub(
    r'const \[apiUrl, setApiUrl\] = useState\(\".*?\"\);',
    f'const [apiUrl, setApiUrl] = useState(\"{tunnel_url}/api/generate\");',
    content
)

# Update the old Ollama label to reflect the new MLX architecture
new_content = re.sub(
    r'Offload Gemma4 to Ollama API for explosive generation speed',
    'Direct Verantyx MLX Native Tunneling for explosive generation speed',
    new_content
)

with open(path, 'w') as f:
    f.write(new_content)
"

echo "✨ verantyx.ai has been successfully updated locally!"

# ==========================================
# 🚀 Auto-Deploy to Cloudflare Pages (Direct Wrangler Push)
# ==========================================
echo "📦 Building Next.js Static Site and Deploying directly to Cloudflare Pages..."
cd /Users/motonishikoudai/verantyx-site
npm run build
npx wrangler pages deploy out --project-name verantyx-site --branch master --commit-dirty=true

echo "✅ Deployment complete! The new frontend is now LIVE at verantyx.ai (Reload the page!)"

# Push to GitHub just for backup
git add .
git commit -m "Auto-update: Tunnel URL via DDNS Script" || true
git push || true
cd - > /dev/null

# Wait for cloudflared to finish (it runs forever until Ctrl+C)
wait $TUNNEL_PID

echo "Shutting down..."
kill $FASTAPI_PID
rm -f tunnel.log
