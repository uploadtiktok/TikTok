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

# معالجة BATCH_SIZE بشكل آمن
batch_size_str = os.environ.get("BATCH_SIZE", "3")
try:
    BATCH_SIZE = int(batch_size_str) if batch_size_str.strip() else 3
except ValueError:
    BATCH_SIZE = 3

VIDEO_FOLDER = "Videos"
LAST_MESSAGE_FILE = "last_message_id.json"
# ====================================

def setup_folders():
    Path(VIDEO_FOLDER).mkdir(parents=True, exist_ok=True)

def load_last_message():
    if os.path.exists(LAST_MESSAGE_FILE):
        with open(LAST_MESSAGE_FILE) as f:
            return json.load(f).get("last_message_id", None)
    return None

def save_last_message(message_id):
    with open(LAST_MESSAGE_FILE, "w") as f:
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
    last_id = load_last_message()
    print(f"📍 Last message ID: {last_id if last_id else 'None (first run)'}")

    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    try:
        await client.start()
        print("✅ Connected")

        channel = await client.get_entity(CHANNEL_USERNAME)
        print(f"📢 Channel: {channel.title}")

        # جلب جميع رسائل الفيديو من الأقدم إلى الأحدث
        print("🔍 Fetching video messages (oldest → newest)...")
        all_videos = []
        async for msg in client.iter_messages(channel, reverse=True):
            if msg.video or (msg.document and is_video_file(msg.document)):
                all_videos.append(msg)

        print(f"🎬 Total videos in channel: {len(all_videos)}")

        if not all_videos:
            print("📭 No videos found.")
            return

        # تحديد الفيديوهات الجديدة بناءً على last_id
        if last_id is None:
            # التشغيل الأول: خذ أول BATCH_SIZE (أقدمها)
            new_videos = all_videos[:BATCH_SIZE]
        else:
            # التشغيل التالي: خذ الفيديوهات التي id > last_id (أحدث)
            new_videos = [v for v in all_videos if v.id > last_id]
            new_videos = new_videos[:BATCH_SIZE]

        if not new_videos:
            print("📭 No new videos to download.")
            return

        print(f"📥 Downloading {len(new_videos)} new video(s)...")

        downloaded_ids = []
        for idx, msg in enumerate(new_videos, 1):
            original_name = get_file_name(msg.document) if msg.document else f"video_{msg.id}.mp4"
            if not original_name:
                original_name = f"video_{msg.id}.mp4"

            timestamp = msg.date.strftime("%Y%m%d_%H%M%S")
            safe_name = f"{msg.id}_{timestamp}_{original_name}"
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
            file_path = Path(VIDEO_FOLDER) / safe_name

            print(f"📥 ({idx}/{len(new_videos)}) Downloading: {original_name} (ID: {msg.id})")
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
            except Exception as e:
                print(f"⚠️ Error downloading {original_name}: {e}")

        # تحديث last_id إلى أكبر ID تم تحميله
        if downloaded_ids:
            new_last_id = max(downloaded_ids)
            save_last_message(new_last_id)
            print(f"📍 Updated last message ID to: {new_last_id}")

        print("\n" + "="*50)
        print(f"📈 SUMMARY:")
        print(f"   ✅ Downloaded: {len(downloaded_ids)}")
        print(f"   📁 New videos added to '{VIDEO_FOLDER}/'")
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
