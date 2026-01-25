#!/bin/bash
# Probe Steam API from worker network
# Tests appdetails and reviews endpoints

set -e

echo "=== Steam API Probe (from worker network) ==="
echo ""

# Test appdetails for app 620 (Portal 2)
echo "1. Testing appdetails for app 620..."
docker compose exec -T worker python3 <<'PYTHON'
import requests
import json

url = "https://store.steampowered.com/api/appdetails"
params = {"appids": 620, "cc": "us", "l": "en"}

try:
    response = requests.get(url, params=params, timeout=15)
    print(f"   HTTP Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        app_data = data.get("620", {}).get("data", {})
        if app_data:
            print(f"   ✓ Success: {app_data.get('name', 'N/A')}")
            print(f"   Release date: {app_data.get('release_date', {}).get('date', 'N/A')}")
        else:
            print(f"   ✗ No data in response")
    else:
        print(f"   ✗ HTTP Error: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   ✗ Error: {e}")
PYTHON

echo ""
echo "2. Testing reviews endpoint for app 620..."
docker compose exec -T worker python3 <<'PYTHON'
import requests
import json

url = "https://store.steampowered.com/appreviews/620"
params = {"json": 1, "language": "all", "num_per_page": 0, "purchase_type": "all"}

try:
    response = requests.get(url, params=params, timeout=15)
    print(f"   HTTP Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        query_summary = data.get("query_summary", {})
        if query_summary:
            total = query_summary.get("total_reviews", 0)
            positive = query_summary.get("total_positive", 0)
            print(f"   ✓ Success: total_reviews={total}, total_positive={positive}")
        else:
            print(f"   ✗ No query_summary in response")
    else:
        print(f"   ✗ HTTP Error: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   ✗ Error: {e}")
PYTHON

echo ""
echo "=== Probe Complete ==="
