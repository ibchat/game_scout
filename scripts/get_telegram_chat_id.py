#!/usr/bin/env python3
"""
Helper script to get Telegram chat ID for a channel.
Usage: python scripts/get_telegram_chat_id.py <bot_token>
"""
import sys
import httpx

def get_chat_id(bot_token: str) -> None:
    """Get chat ID from recent updates"""
    base_url = f"https://api.telegram.org/bot{bot_token}"
    
    try:
        # Get updates
        url = f"{base_url}/getUpdates"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            response.raise_for_status()
            result = response.json()
            
            if not result.get("ok"):
                print(f"Error: {result.get('description', 'Unknown error')}")
                return
            
            updates = result.get("result", [])
            if not updates:
                print("No updates found. Send a message to the bot or forward a message from the channel to the bot.")
                return
            
            print("Recent chats:")
            seen_chats = set()
            for update in updates:
                if "message" in update:
                    chat = update["message"].get("chat", {})
                    chat_id = chat.get("id")
                    chat_type = chat.get("type")
                    chat_title = chat.get("title") or chat.get("first_name", "Unknown")
                    
                    if chat_id and chat_id not in seen_chats:
                        seen_chats.add(chat_id)
                        print(f"  {chat_type}: {chat_title} (ID: {chat_id})")
                
                elif "channel_post" in update:
                    chat = update["channel_post"].get("chat", {})
                    chat_id = chat.get("id")
                    chat_title = chat.get("title", "Unknown")
                    
                    if chat_id and chat_id not in seen_chats:
                        seen_chats.add(chat_id)
                        print(f"  channel: {chat_title} (ID: {chat_id})")
            
            if not seen_chats:
                print("No chats found in updates.")
                print("\nTo get channel ID:")
                print("1. Add bot to channel as administrator")
                print("2. Forward a message from channel to the bot")
                print("3. Run this script again")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/get_telegram_chat_id.py <bot_token>")
        print("\nExample:")
        print("  python scripts/get_telegram_chat_id.py 8546248502:AAFZwNjcvLfOsClWU-z_8vfPfmSXUS2pUyM")
        sys.exit(1)
    
    bot_token = sys.argv[1]
    get_chat_id(bot_token)
