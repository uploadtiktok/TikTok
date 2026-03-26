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

batch_size_str = os.environ.get("BATCH_SIZE", "3")
try:
    BATCH_SIZE = int(batch_size_str) if batch_size_str.strip() else 3
except ValueError:
    BATCH_SIZE = 3

VIDEO_FOLDER = "Videos"
LAST_ID_FILE = "last_message_id.json"
# ====================================

def setup_folders():
    Path(VIDEO_FOLDER).mkdir(parents=True, exist_ok=True)

def load_last_id():
    """تحميل آخر message ID تم تحميله"""
    if os.path.exists(LAST_ID_FILE):
        try:
            with open(LAST_ID_FILE, 'r') as f:
                data = json.load(f)
                return data.get("last_message_id", None)
        except:
            return None
    return None

def save_last_id(message_id):
    """حفظ آخر message ID تم تحميله"""
    with open(LAST_ID_FILE, 'w') as f:
        json.dump({"last_message_id": message_id}, f)

def is_video_file(document):
    if not document:
        return False
    if document.mime_type and document.mime_type.startswith("video/"):
        return True
    if document.attributes:
        for attr in document.attributes:
            if hasattr(attr, "file_name") and attr.file_name:
                ext = attr.file_name.lower().split(".")[-1]
                if ext in ("mp4", "avi", "mov", "mkv", "webm", "flv", "wmv", "m4v"):
                    return True
    return False

def get_file_name(document):
    if document.attributes:
        for attr in document.attributes:
            if hasattr(attr, "file_name") and attr.file_name:
                return attr.file_name
    return None

async def fetch_videos():
    print("🎬 Telegram Video Fetcher")
    print(f"📦 Batch size: {BATCH_SIZE}")
    print("-" * 40)

    if not (API_ID and API_HASH and STRING_SESSION and CHANNEL_USERNAME):
        print("❌ Missing secrets")
        return

    setup_folders()
    last_id = load_last_id()
    
    if last_id:
        print(f"📍 Last downloaded message ID: {last_id}")
        print(f"🔍 Searching for videos with ID > {last_id} (newer videos)...")
    else:
        print("📍 First run - fetching oldest videos first")

    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    try:
        await client.start()
        print("✅ Connected to Telegram")

        channel = await client.get_entity(CHANNEL_USERNAME)
        print(f"📢 Channel: {channel.title}")

        # جلب جميع مقاطع الفيديو من الأحدث إلى الأقدم (للكشف السريع عن الجديد)
        print("🔍 Scanning for video messages...")
        all_videos = []
        async for msg in client.iter_messages(channel, reverse=True):
            if msg.video or (msg.document and is_video_file(msg.document)):
                all_videos.append(msg)

        total = len(all_videos)
        print(f"🎬 Total videos in channel: {total}")

        if total == 0:
            print("📭 No videos found in channel.")
            return

        # عرض جميع IDs الموجودة
        ids_list = [v.id for v in all_videos]
        print(f"📋 Available video IDs: {ids_list}")

        # تحديد المقاطع الجديدة
        if last_id is None:
            # أول تشغيل: تحميل أقدم المقاطع
            videos_to_download = all_videos[:BATCH_SIZE]
            print(f"📥 First run: downloading oldest {len(videos_to_download)} videos")
        else:
            # فلترة المقاطع التي ID > last_id
            videos_to_download = [v for v in all_videos if v.id > last_id]
            
            if not videos_to_download:
                print("\n" + "="*50)
                print("📭 NO NEW VIDEOS TO DOWNLOAD")
                print(f"   Last downloaded ID: {last_id}")
                print(f"   Latest video ID in channel: {max(ids_list)}")
                print(f"   All videos up to ID {max(ids_list)} have been downloaded.")
                print("="*50)
                return
            
            # أخذ فقط BATCH_SIZE من المقاطع الجديدة (الأحدث)
            videos_to_download = videos_to_download[:BATCH_SIZE]
            print(f"📥 Found {len(videos_to_download)} new video(s) with ID > {last_id}")

        print("-" * 40)

        downloaded_ids = []
        for i, msg in enumerate(videos_to_download, 1):
            if msg.video:
                original_name = f"video_{msg.id}.mp4"
            else:
                original_name = get_file_name(msg.document) or f"video_{msg.id}.mp4"

            timestamp = msg.date.strftime("%Y%m%d_%H%M%S")
            safe_name = f"{msg.id}_{timestamp}_{original_name}"
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
            file_path = Path(VIDEO_FOLDER) / safe_name

            print(f"📥 ({i}/{len(videos_to_download)}) Downloading: {original_name} (ID: {msg.id})")
            try:
                if msg.video:
                    await client.download_media(msg.video, str(file_path))
                else:
                    await client.download_media(msg.document, str(file_path))

                if file_path.exists() and file_path.stat().st_size > 0:
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    print(f"✅ Downloaded: {original_name} ({size_mb:.2f} MB)")
                    downloaded_ids.append(msg.id)
                else:
                    print(f"❌ Download failed: {original_name}")
                    if file_path.exists():
                        file_path.unlink()
                    break
            except Exception as e:
                print(f"⚠️ Error: {e}")
                break

        # تحديث آخر ID إلى أكبر ID تم تحميله
        if downloaded_ids:
            new_last_id = max(downloaded_ids)
            save_last_id(new_last_id)
            print(f"\n📍 Updated last message ID to: {new_last_id}")
            print(f"   🔗 Example: https://t.me/{CHANNEL_USERNAME}/{new_last_id}")

        print("\n" + "="*50)
        print(f"📈 SUMMARY:")
        print(f"   ✅ Downloaded: {len(downloaded_ids)}")
        print(f"   📁 Saved in: {VIDEO_FOLDER}/")
        print(f"   📍 Last message ID: {load_last_id()}")
        
        remaining = len([v for v in all_videos if v.id > load_last_id()]) if load_last_id() else 0
        if remaining > 0:
            print(f"   📦 Remaining videos to download: {remaining}")
        print("="*50)

    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        await client.disconnect()
        print("👋 Disconnected")

if __name__ == "__main__":
    asyncio.run(fetch_videos())
