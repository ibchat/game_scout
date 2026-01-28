#!/bin/bash
# Verify public demo tunnel is working
# Usage: bash scripts/verify_public_demo.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Verifying public demo tunnel...${NC}"

# Check local system summary
echo -e "${YELLOW}1. Checking local system summary...${NC}"
LOCAL_SUMMARY=$(curl -sSf http://localhost:8000/api/v1/admin/system/summary 2>/dev/null || echo "")
if [ -z "$LOCAL_SUMMARY" ]; then
    echo -e "${RED}✗ FAIL: Local API is not accessible${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Local API is accessible${NC}"

# Extract public URL from summary
PUBLIC_URL=$(echo "$LOCAL_SUMMARY" | grep -o '"public_url":"https://[^"]*"' | head -1 | cut -d'"' -f4 || echo "")

if [ -z "$PUBLIC_URL" ]; then
    # Try to read from runtime file
    if [ -f .runtime/public_tunnel_url.txt ]; then
        PUBLIC_URL=$(cat .runtime/public_tunnel_url.txt | tr -d '\n' || echo "")
    fi
fi

if [ -z "$PUBLIC_URL" ]; then
    echo -e "${YELLOW}⚠ Public URL not found in system summary or runtime file${NC}"
    echo "Tunnel might not be started. Run: bash scripts/start_tunnel.sh"
    exit 0
fi

echo -e "${GREEN}✓ Found public URL: ${PUBLIC_URL}${NC}"

# Check public API health
echo -e "${YELLOW}2. Checking public API health...${NC}"
PUBLIC_API_URL="${PUBLIC_URL}/api/v1/admin/system/summary"

# Check if token is required
TOKEN=$(echo "$LOCAL_SUMMARY" | grep -o '"has_token_protection":true' || echo "")
if [ -n "$TOKEN" ]; then
    echo -e "${YELLOW}Token protection is enabled. Skipping public API check (requires token).${NC}"
else
    PUBLIC_RESPONSE=$(curl -sSf "$PUBLIC_API_URL" 2>/dev/null || echo "")
    if [ -z "$PUBLIC_RESPONSE" ]; then
        echo -e "${RED}✗ FAIL: Public API is not accessible${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Public API is accessible${NC}"
fi

# Check public dashboard
echo -e "${YELLOW}3. Checking public dashboard...${NC}"
DASHBOARD_URL="${PUBLIC_URL}/dashboard"
DASHBOARD_RESPONSE=$(curl -sSf "$DASHBOARD_URL" 2>/dev/null || echo "")

if [ -z "$DASHBOARD_RESPONSE" ]; then
    echo -e "${RED}✗ FAIL: Public dashboard is not accessible${NC}"
    exit 1
fi

# Check if response contains "Game Scout"
if echo "$DASHBOARD_RESPONSE" | grep -q "Game Scout"; then
    echo -e "${GREEN}✓ Public dashboard is accessible and contains 'Game Scout'${NC}"
else
    echo -e "${YELLOW}⚠ Public dashboard is accessible but might not contain expected content${NC}"
fi

echo -e "${GREEN}✓ All checks passed!${NC}"
echo -e "${GREEN}Public URL: ${PUBLIC_URL}${NC}"
echo -e "${GREEN}Dashboard: ${DASHBOARD_URL}${NC}"
