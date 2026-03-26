#!/usr/bin/env python3
import asyncio
import os
import json
from pathlib import Path
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession

# ========== CONFIGURATION ==========
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
STRING_SESSION = os.environ.get("STRING_SESSION", "")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "zapiershorts")

# Handle BATCH_SIZE safely
batch_size_str = os.environ.get("BATCH_SIZE", "3")
try:
    BATCH_SIZE = int(batch_size_str) if batch_size_str else 3
except ValueError:
    BATCH_SIZE = 3

VIDEO_FOLDER = "Videos"
HISTORY_FILE = "downloaded_videos.json"
LAST_MESSAGE_FILE = "last_message_id.json"
# ====================================

def setup_folders():
    Path(VIDEO_FOLDER).mkdir(parents=True, exist_ok=True)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(list(history), f)

def load_last_message():
    if os.path.exists(LAST_MESSAGE_FILE):
        with open(LAST_MESSAGE_FILE, 'r') as f:
            data = json.load(f)
            return data.get("last_message_id", None)
    return None

def save_last_message(message_id):
    with open(LAST_MESSAGE_FILE, 'w') as f:
        json.dump({"last_message_id": message_id}, f)

def is_video_file(document):
    if document and document.mime_type:
        if document.mime_type.startswith('video/'):
            return True
        if document.attributes:
            for attr in document.attributes:
                if hasattr(attr, 'file_name') and attr.file_name:
                    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
                    if any(attr.file_name.lower().endswith(ext) for ext in video_extensions):
                        return True
    return False

def get_file_name(document):
    if document.attributes:
        for attr in document.attributes:
            if hasattr(attr, 'file_name') and attr.file_name:
                return attr.file_name
    return None

async def fetch_videos():
    print("🎬 GitHub Actions - Telegram Video Fetcher")
    print(f"📦 Batch size: {BATCH_SIZE} videos per run")
    print("-" * 40)
    
    if API_ID == 0 or not API_HASH:
        print("❌ Missing API_ID or API_HASH in secrets")
        return
    
    if not STRING_SESSION:
        print("❌ Missing STRING_SESSION in secrets")
        return
    
    setup_folders()
    downloaded = load_history()
    last_message_id = load_last_message()
    
    print(f"📊 Already downloaded: {len(downloaded)} videos")
    if last_message_id:
        print(f"📍 Last downloaded message ID: {last_message_id}")
    
    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    
    try:
        await client.start()
        print("✅ Connected to Telegram")
        
        print(f"🔍 Getting channel: @{CHANNEL_USERNAME}")
        channel = await client.get_entity(CHANNEL_USERNAME)
        print(f"📢 Channel: {channel.title}")
        
        print("🔍 Scanning messages for videos...")
        
        all_videos = []
        async for message in client.iter_messages(channel, limit=None, offset_id=0):
            is_video = False
            if message.video:
                is_video = True
            elif message.document and is_video_file(message.document):
                is_video = True
            
            if is_video:
                all_videos.append(message)
        
        print(f"🎬 Found {len(all_videos)} total videos in channel")
        
        start_index = 0
        if last_message_id:
            for i, msg in enumerate(all_videos):
                if msg.id == last_message_id:
                    start_index = i + 1
                    break
        
        new_videos = all_videos[start_index:start_index + BATCH_SIZE]
        
        if not new_videos:
            print("\n📭 NO NEW VIDEOS TO DOWNLOAD")
            return
        
        print(f"📥 Downloading {len(new_videos)} new videos...")
        
        downloaded_count = 0
        for message in new_videos:
            if message.video:
                original_filename = f"video_{message.id}.mp4"
            else:
                original_filename = get_file_name(message.document) or f"video_{message.id}.mp4"
            
            timestamp = message.date.strftime("%Y%m%d_%H%M%S")
            file_name = f"{message.id}_{timestamp}_{original_filename}"
            file_name = "".join(c for c in file_name if c.isalnum() or c in '._- ')
            file_path = os.path.join(VIDEO_FOLDER, file_name)
            
            if file_name in downloaded:
                print(f"⏭️  Skipping: {original_filename}")
                continue
            
            print(f"📥 Downloading: {original_filename}")
            
            try:
                if message.video:
                    await client.download_media(message.video, file_path)
                else:
                    await client.download_media(message.document, file_path)
                
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    print(f"✅ Downloaded: {original_filename} ({size_mb:.2f} MB)")
                    downloaded.add(file_name)
                    downloaded_count += 1
                    save_last_message(message.id)
                else:
                    print(f"❌ Download failed: {original_filename}")
                    if os.path.exists(file_path):
                        os.remove(file_path)
            except Exception as e:
                print(f"⚠️ Error: {e}")
        
        save_history(downloaded)
        
        print("\n" + "="*50)
        print(f"📈 SUMMARY:")
        print(f"   ✅ Downloaded: {downloaded_count}")
        print(f"   📁 Total in history: {len(downloaded)}")
        print(f"   📍 Last message ID: {load_last_message()}")
        print("="*50)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        await client.disconnect()
        print("👋 Disconnected")

if __name__ == "__main__":
    asyncio.run(fetch_videos())
