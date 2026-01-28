#!/bin/bash
# Start public tunnel (ngrok or Cloudflare) for Game Scout Dashboard
# Usage: ENABLE_PUBLIC_TUNNEL=1 PUBLIC_TUNNEL_PROVIDER=ngrok bash scripts/start_tunnel.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if tunnel is enabled
if [ "${ENABLE_PUBLIC_TUNNEL:-0}" != "1" ]; then
    echo -e "${YELLOW}Public tunnel is disabled (ENABLE_PUBLIC_TUNNEL=0)${NC}"
    exit 0
fi

# Check if PUBLIC_TUNNEL_URL is set manually
if [ -n "${PUBLIC_TUNNEL_URL:-}" ]; then
    echo -e "${GREEN}Using manual PUBLIC_TUNNEL_URL: ${PUBLIC_TUNNEL_URL}${NC}"
    mkdir -p .runtime
    echo "${PUBLIC_TUNNEL_URL}" > .runtime/public_tunnel_url.txt
    echo -e "${GREEN}Public URL saved to .runtime/public_tunnel_url.txt${NC}"
    exit 0
fi

# Check if API is accessible
echo -e "${YELLOW}Checking API availability...${NC}"
if ! curl -sSf http://localhost:8000/api/v1/admin/system/summary > /dev/null 2>&1; then
    echo -e "${RED}Error: API is not accessible at http://localhost:8000${NC}"
    echo "Please start the API first: docker-compose up api"
    exit 1
fi
echo -e "${GREEN}API is accessible${NC}"

# Create .runtime directory
mkdir -p .runtime

# Determine provider
PROVIDER="${PUBLIC_TUNNEL_PROVIDER:-ngrok}"

if [ "$PROVIDER" = "ngrok" ]; then
    # Check if ngrok is installed
    if ! command -v ngrok > /dev/null 2>&1; then
        echo -e "${RED}Error: ngrok is not installed${NC}"
        echo "Install: brew install ngrok/ngrok/ngrok"
        exit 1
    fi
    
    # Check if ngrok is already running
    if pgrep -f "ngrok http" > /dev/null; then
        echo -e "${YELLOW}ngrok is already running${NC}"
        # Try to get URL from ngrok API
        sleep 2
        NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
        if [ -n "$NGROK_URL" ]; then
            echo "$NGROK_URL" > .runtime/public_tunnel_url.txt
            echo -e "${GREEN}Using existing ngrok tunnel: ${NGROK_URL}${NC}"
            echo -e "${GREEN}Dashboard: ${NGROK_URL}/dashboard${NC}"
            exit 0
        fi
    fi
    
    # Start ngrok in background
    echo -e "${YELLOW}Starting ngrok...${NC}"
    ngrok http 8000 > .runtime/ngrok.log 2>&1 &
    NGROK_PID=$!
    echo $NGROK_PID > .runtime/ngrok.pid
    
    # Wait for ngrok to start
    sleep 3
    
    # Get public URL from ngrok API
    MAX_RETRIES=10
    RETRY=0
    NGROK_URL=""
    
    while [ $RETRY -lt $MAX_RETRIES ]; do
        NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
        if [ -n "$NGROK_URL" ]; then
            break
        fi
        sleep 1
        RETRY=$((RETRY + 1))
    done
    
    if [ -z "$NGROK_URL" ]; then
        echo -e "${RED}Error: Failed to get ngrok URL${NC}"
        kill $NGROK_PID 2>/dev/null || true
        exit 1
    fi
    
    echo "$NGROK_URL" > .runtime/public_tunnel_url.txt
    echo -e "${GREEN}ngrok started (PID: $NGROK_PID)${NC}"
    echo -e "${GREEN}Public URL: ${NGROK_URL}${NC}"
    echo -e "${GREEN}Dashboard: ${NGROK_URL}/dashboard${NC}"
    echo -e "${GREEN}API health: ${NGROK_URL}/api/v1/admin/system/summary${NC}"
    
elif [ "$PROVIDER" = "cloudflare" ]; then
    # Check if cloudflared is installed
    if ! command -v cloudflared > /dev/null 2>&1; then
        echo -e "${RED}Error: cloudflared is not installed${NC}"
        echo "Install: brew install cloudflare/cloudflare/cloudflared"
        exit 1
    fi
    
    # Check if cloudflared is already running
    if pgrep -f "cloudflared tunnel" > /dev/null; then
        echo -e "${YELLOW}cloudflared is already running${NC}"
        # Try to read URL from file
        if [ -f .runtime/public_tunnel_url.txt ]; then
            CLOUDFLARE_URL=$(cat .runtime/public_tunnel_url.txt)
            echo -e "${GREEN}Using existing cloudflared tunnel: ${CLOUDFLARE_URL}${NC}"
            echo -e "${GREEN}Dashboard: ${CLOUDFLARE_URL}/dashboard${NC}"
            exit 0
        fi
    fi
    
    # Start cloudflared in background
    echo -e "${YELLOW}Starting cloudflared...${NC}"
    cloudflared tunnel --url http://localhost:8000 > .runtime/cloudflared.log 2>&1 &
    CLOUDFLARE_PID=$!
    echo $CLOUDFLARE_PID > .runtime/cloudflared.pid
    
    # Wait for cloudflared to start and extract URL
    sleep 5
    
    MAX_RETRIES=10
    RETRY=0
    CLOUDFLARE_URL=""
    
    while [ $RETRY -lt $MAX_RETRIES ]; do
        # Extract URL from log file
        CLOUDFLARE_URL=$(grep -o 'https://[^[:space:]]*\.trycloudflare\.com' .runtime/cloudflared.log 2>/dev/null | head -1 || echo "")
        if [ -n "$CLOUDFLARE_URL" ]; then
            break
        fi
        sleep 1
        RETRY=$((RETRY + 1))
    done
    
    if [ -z "$CLOUDFLARE_URL" ]; then
        echo -e "${RED}Error: Failed to get cloudflared URL${NC}"
        echo "Check logs: cat .runtime/cloudflared.log"
        kill $CLOUDFLARE_PID 2>/dev/null || true
        exit 1
    fi
    
    echo "$CLOUDFLARE_URL" > .runtime/public_tunnel_url.txt
    echo -e "${GREEN}cloudflared started (PID: $CLOUDFLARE_PID)${NC}"
    echo -e "${GREEN}Public URL: ${CLOUDFLARE_URL}${NC}"
    echo -e "${GREEN}Dashboard: ${CLOUDFLARE_URL}/dashboard${NC}"
    echo -e "${GREEN}API health: ${CLOUDFLARE_URL}/api/v1/admin/system/summary${NC}"
    
else
    echo -e "${RED}Error: Unknown provider: $PROVIDER${NC}"
    echo "Supported providers: ngrok, cloudflare"
    exit 1
fi

echo -e "${GREEN}✓ Tunnel started successfully${NC}"
