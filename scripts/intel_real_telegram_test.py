#!/usr/bin/env python3
"""
Real Telegram Test Script
Tests Telegram bot and channel access, sends a test message.
"""
import sys
import os
import httpx
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_telegram():
    """Test Telegram bot and channel access"""
    # Get config from environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not set")
        return 1
    
    if not chat_id:
        print("❌ ERROR: TELEGRAM_CHAT_ID not set")
        return 1
    
    base_url = f"https://api.telegram.org/bot{bot_token}"
    
    print("🧪 Testing Telegram bot and channel access...")
    print(f"   Bot token: {bot_token[:20]}...")
    print(f"   Chat ID: {chat_id}")
    print()
    
    # Test 1: getMe
    print("1️⃣ Testing getMe (bot verification)...")
    try:
        url = f"{base_url}/getMe"
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
            response.raise_for_status()
            result = response.json()
            
            if result.get("ok"):
                bot_info = result.get("result", {})
                print(f"   ✅ Bot verified: @{bot_info.get('username')} (ID: {bot_info.get('id')})")
            else:
                print(f"   ❌ Bot verification failed: {result.get('description')}")
                return 1
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return 1
    
    # Test 2: getChat
    print("\n2️⃣ Testing getChat (channel access)...")
    try:
        url = f"{base_url}/getChat"
        payload = {"chat_id": chat_id}
        with httpx.Client(timeout=5.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            
            if result.get("ok"):
                chat_info = result.get("result", {})
                print(f"   ✅ Channel access verified: {chat_info.get('title')} (Type: {chat_info.get('type')})")
            else:
                print(f"   ❌ Channel access failed: {result.get('description')}")
                return 1
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return 1
    
    # Test 3: sendMessage
    print("\n3️⃣ Testing sendMessage (real message)...")
    try:
        test_message = f"🧪 Steam Intel system test - {datetime.utcnow().isoformat()}"
        url = f"{base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": test_message,
            "parse_mode": "HTML"
        }
        
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            
            if result.get("ok"):
                message_id = result.get("result", {}).get("message_id")
                print(f"   ✅ Message sent successfully!")
                print(f"   📨 Message ID: {message_id}")
                print(f"   💬 Message: {test_message[:50]}...")
                return 0
            else:
                print(f"   ❌ Message send failed: {result.get('description')}")
                return 1
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = test_telegram()
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Tests failed!")
    sys.exit(exit_code)
