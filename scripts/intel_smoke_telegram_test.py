#!/usr/bin/env python3
"""
Smoke test for Telegram bot and channel access.
Tests getMe/getChat and optionally sends test message.
"""
import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.db.session import SessionLocal
from apps.intel.services.publishers.telegram_publisher import TelegramPublisher

def main():
    parser = argparse.ArgumentParser(description="Test Telegram bot and channel access")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Only check access, don't send message")
    parser.add_argument("--send", action="store_true", help="Actually send test message")
    args = parser.parse_args()
    
    dry_run = not args.send
    
    db = SessionLocal()
    
    try:
        print("=== Telegram Access Test ===")
        print()
        
        publisher = TelegramPublisher(db)
        
        # Check access
        print("Checking Telegram access...")
        ok, error, details = publisher.check_telegram_access()
        
        if not ok:
            print(f"❌ FAILED: {error}")
            return 1
        
        print("✅ Telegram access OK")
        print(f"   Bot: @{details.get('bot_username', 'unknown')}")
        print(f"   Chat: {details.get('chat_title', 'unknown')} ({details.get('chat_type', 'unknown')})")
        print()
        
        if dry_run:
            print("✅ DRY RUN: Access verified, no message sent")
            return 0
        
        # Send test message
        print("Sending test message...")
        from datetime import datetime
        test_message = f"🧪 Game Scout Intel test - {datetime.utcnow().isoformat()}"
        
        success, message_id, error = publisher._send_to_telegram(test_message)
        
        if success:
            print(f"✅ Test message sent successfully")
            print(f"   Message ID: {message_id}")
            return 0
        else:
            print(f"❌ Failed to send message: {error}")
            return 1
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(main())
