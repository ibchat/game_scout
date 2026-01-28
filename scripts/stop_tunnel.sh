#!/bin/bash
# Stop public tunnel (ngrok or Cloudflare)
# Usage: bash scripts/stop_tunnel.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Stopping public tunnel...${NC}"

# Stop ngrok
if [ -f .runtime/ngrok.pid ]; then
    NGROK_PID=$(cat .runtime/ngrok.pid)
    if ps -p $NGROK_PID > /dev/null 2>&1; then
        kill $NGROK_PID 2>/dev/null || true
        echo -e "${GREEN}Stopped ngrok (PID: $NGROK_PID)${NC}"
    fi
    rm -f .runtime/ngrok.pid
fi

# Kill any remaining ngrok processes
pkill -f "ngrok http" 2>/dev/null || true

# Stop cloudflared
if [ -f .runtime/cloudflared.pid ]; then
    CLOUDFLARE_PID=$(cat .runtime/cloudflared.pid)
    if ps -p $CLOUDFLARE_PID > /dev/null 2>&1; then
        kill $CLOUDFLARE_PID 2>/dev/null || true
        echo -e "${GREEN}Stopped cloudflared (PID: $CLOUDFLARE_PID)${NC}"
    fi
    rm -f .runtime/cloudflared.pid
fi

# Kill any remaining cloudflared processes
pkill -f "cloudflared tunnel" 2>/dev/null || true

# Clear URL file
if [ -f .runtime/public_tunnel_url.txt ]; then
    rm -f .runtime/public_tunnel_url.txt
    echo -e "${GREEN}Cleared tunnel URL file${NC}"
fi

echo -e "${GREEN}✓ Tunnel stopped${NC}"
