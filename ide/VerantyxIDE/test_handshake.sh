#!/bin/bash
curl -X POST http://127.0.0.1:5420/api/handshake \
-H "Content-Type: application/json" \
-d '{
  "workspace_path": "/Users/motonishikoudai/test_workspace",
  "skills_path": "/Users/motonishikoudai/test_skills",
  "swarm_active": true
}'
echo ""
